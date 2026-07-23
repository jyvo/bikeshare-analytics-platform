from schema_registry import standardize_col, get_schema_version, get_schema, parse_datetime, cast_column
from validation.crosswalk import normalize_station_name, match_station_names, match_station_names_historical
from pathlib import Path
from typing import Callable
import polars as pl
import io
import gc
import re
import os


def _read_csv_normalized(path: Path, **kwargs) -> pl.DataFrame:
    with open(path, "rb") as f:
        raw_bytes = f.read()
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw_bytes.decode("latin1")
    return pl.read_csv(io.BytesIO(text.encode("utf-8")), **kwargs)


def build_historical_lookup(registry: "Registry", year: str,
                             name_cols: tuple[str, ...] = ("start_station_name", "end_station_name"),
                             id_cols: tuple[str, ...] = ("start_station_id", "end_station_id")) -> dict[str, str]:
    # match station name against nearby years
    # cross-ref adjacent datasets (prev/next year) in registry
    year_map: dict[int, str] = {}
    for ds_name in registry.get_all_datasets():
        for y in re.findall(r"\d{4}", ds_name):
            year_map[int(y)] = ds_name

    target = int(year)
    adjacent = []
    for candidate in (target - 1, target + 1):
        ds_name = year_map.get(candidate)
        if ds_name and ds_name not in adjacent:
            adjacent.append(ds_name)

    lookup: dict[str, str] = {}
    for ds_name in adjacent:
        entry = registry.get_dataset(ds_name)

        for fname in entry.get_fnames():
            version = entry.get_version(fname)
            schema = get_schema(version)
            if schema is None:
                continue

            casted, _ = entry.cast_to_schema(fname)
            for id_col, name_col in zip(id_cols, name_cols):
                if id_col not in casted.columns or name_col not in casted.columns:
                    continue
                has_id = casted.filter(pl.col(id_col).is_not_null())
                for name, station_id in zip(has_id[name_col], has_id[id_col]):
                    key = normalize_station_name(name)
                    if key and key not in lookup:
                        lookup[key] = station_id

        # lookup station ref table (2014-2015)
        for fname in entry.get_fnames():
            raw = entry.get_df(fname)
            if {"terminal", "station"}.issubset(raw.columns):
                for name, terminal in zip(raw["station"], raw["terminal"]):
                    key = normalize_station_name(name)
                    if key and key not in lookup:
                        lookup[key] = terminal

    return lookup


def check_consistency(df: pl.DataFrame, start_col: str = "start_time", end_col: str = "end_time",
                       duration_col: str = "trip_duration", tolerance_sec: int = 60) -> pl.DataFrame:
    
    if not {start_col, end_col, duration_col}.issubset(df.columns):
        return pl.DataFrame()

    computed = (df[end_col] - df[start_col]).dt.total_seconds()
    provided = df[duration_col].cast(pl.Float64, strict=False)

    unparseable = df[start_col].is_null() | df[end_col].is_null()
    mismatched = (computed - provided).abs() > tolerance_sec
    negative = computed < 0
    flagged = unparseable | mismatched.fill_null(False) | negative.fill_null(False)

    return df.filter(flagged).with_columns([
        computed.filter(flagged).alias("computed_duration"),
        provided.filter(flagged).alias("provided_duration"),
    ])


class DSEntry:
    def __init__(self, name: str, dpath: Path, fpaths: dict[str, Path], col_struct: pl.DataFrame = None):
        self._name = name
        self._dpath = dpath
        self._fpaths = fpaths
        self._struct = col_struct
        self._dfs = {}
        self._comparison = pl.DataFrame()
        self._consol = None
        self._cast_errors = {}
        self._anomalies = pl.DataFrame(schema={"file": pl.Utf8, "row": pl.UInt32, "trip_id": pl.Utf8, "anomaly_type": pl.Utf8, "detail": pl.Utf8})

    def get_struct(self):
        return self._struct

    def get_cast_errors(self) -> dict[str, pl.DataFrame]:
        return self._cast_errors

    def get_anomalies(self) -> pl.DataFrame:
        return self._anomalies

    def _reaudit(self) -> pl.DataFrame:
        # audit colnames on unpacked dfs
        self._struct = None
        gc.collect()

        col_struct = []
        for f, df in self._dfs.items():
            cols = tuple(c for c in df.columns if c != "row")
            schema_version = get_schema_version(cols)
            col_struct.append({"dataset": self._name, "file": f, "columns": cols, "n_cols": len(cols), "version": schema_version})
        self._struct = pl.DataFrame(col_struct)
        return self._struct

    def _to_df(self, path: Path) -> pl.DataFrame:
        try:
            df = _read_csv_normalized(path, infer_schema_length=0)
        except pl.exceptions.ComputeError as exc:
            raise ValueError(f"Failed to parse {path}.") from exc
        df = df.rename({c: standardize_col(c) for c in df.columns})
        return df.with_row_index("row")

    def unpack(self) -> dict.keys:
        if not self._dfs:
            for f, fpath in self._fpaths.items():
                self._dfs[f] = self._to_df(fpath)
        return self._dfs.keys()

    def get_fnames(self) -> dict.keys:
        return self._fpaths.keys()

    def get_fpaths(self) -> dict[str, Path]:
        return self._fpaths

    def get_df(self, fname: str) -> pl.DataFrame:
        if fname not in self._fpaths:
            raise ValueError(f"{fname} does not exist in registry.")
        elif fname not in self._dfs:
            self._dfs[fname] = self._to_df(self._fpaths[fname])
        return self._dfs[fname]

    def compare_dfs(self, func: Callable[[pl.DataFrame], dict]) -> pl.DataFrame:
        if not self._dfs:
            self.unpack()

        rows = [{"file": f, **func(df.drop("row"))} for f, df in self._dfs.items()]
        self._comparison = pl.DataFrame(rows)
        return self._comparison

    def get_version(self, fname: str) -> str:
        match = self._struct.filter(pl.col("file") == fname)["version"]
        if match.len() == 0:
            raise ValueError(f"{fname} does not exist in registry.")
        return match[0]

    def validate_schema(self, fname: str) -> dict:
        version = self.get_version(fname)
        schema = get_schema(version)
        cols = set(self.get_df(fname).columns) - {"row"}

        if schema is None:
            return {"file": fname, "version": version, "schema_found": False, "missing_cols": None, "extra_cols": None}

        expected = set(schema.keys())
        return {
            "file": fname,
            "version": version,
            "schema_found": True,
            "missing_cols": sorted(expected - cols),
            "extra_cols": sorted(cols - expected),
        }

    def cast_to_schema(self, fname: str) -> tuple[pl.DataFrame, pl.DataFrame]:
        version = self.get_version(fname)
        schema = get_schema(version)
        if schema is None:
            raise ValueError(f"No schema registered for version {version!r} ({fname}).")

        raw = self.get_df(fname)
        row_idx = raw["row"]

        error_frames = []
        result_columns = {}
        for col, dtype in schema.items():
            raw_series = raw[col] if col in raw.columns else pl.Series([None] * raw.height, dtype=pl.Utf8)
            casted_series, failed = cast_column(raw_series, dtype)
            result_columns[col] = casted_series
            if failed.any():
                error_frames.append(pl.DataFrame({
                    "file": fname,
                    "column": col,
                    "row": row_idx.filter(failed),
                    "raw_value": raw_series.filter(failed),
                }))

        casted = pl.DataFrame(result_columns)
        errors = (
            pl.concat(error_frames, how="diagonal_relaxed") if error_frames
            else pl.DataFrame(schema={"file": pl.Utf8, "column": pl.Utf8, "row": pl.UInt32, "raw_value": pl.Utf8})
        )
        return casted, errors

    def check_column_integrity(self, fname: str) -> pl.DataFrame:
        _, errors = self.cast_to_schema(fname)
        if errors.is_empty():
            return pl.DataFrame()

        raw = self.get_df(fname)
        last_col = raw.columns[-1]

        other_failed_rows = errors.filter(pl.col("column") != last_col)["row"].unique()
        if other_failed_rows.len() == 0:
            return pl.DataFrame()

        candidates = raw.filter(pl.col("row").is_in(other_failed_rows.implode()))
        return candidates.filter(pl.col(last_col).is_null())

    def repair_column_shift(self, fname: str, rows: pl.Series) -> None:
        df = self.get_df(fname)
        cols = [c for c in df.columns if c not in ("row", "trip_id")]
        mask = pl.col("row").is_in(rows.implode())

        shifted_list = pl.concat_list(cols).list.shift(1)
        df = df.with_columns([
            pl.when(mask).then(shifted_list.list.get(i)).otherwise(pl.col(c)).alias(c)
            for i, c in enumerate(cols)
        ])

        parsed_start = parse_datetime(df["start_time"].gather(rows))
        parsed_end = parse_datetime(df["end_time"].gather(rows))
        new_duration = (parsed_end - parsed_start).dt.total_seconds().cast(pl.Int64).cast(pl.Utf8)

        df = df.with_columns(df["trip_duration"].scatter(rows, new_duration).alias("trip_duration"))
        self._dfs[fname] = df

    def check_duplicates(self, fname: str, subset: list[str] = None) -> pl.DataFrame:
        df = self.get_df(fname)
        subset = subset or (["trip_id"] if "trip_id" in df.columns else None)
        mask = df.is_duplicated() if subset is None else df.select(subset).is_duplicated()
        return df.filter(mask)

    def value_distribution(self, fname: str, col: str) -> pl.DataFrame:
        return self.get_df(fname)[col].value_counts()

    def match_station_ids(self, fname: str, rt_lookup: dict[str, str], historical_lookup: dict[str, str] = None,
                          fuzzy_threshold: int = 90) -> pl.DataFrame:
        casted, _ = self.cast_to_schema(fname)
        if historical_lookup is not None:
            casted = match_station_names_historical(casted, historical_lookup, fuzzy_threshold)
        return match_station_names(casted, rt_lookup, fuzzy_threshold)

    def consol(self, rt_lookup: dict[str, str] = None, historical_lookup: dict[str, str] = None,
               fuzzy_threshold: int = 90, repair_shifts: bool = True) -> pl.DataFrame:
        if not self._dfs:
            self.unpack()

        self._cast_errors = {}
        anomalies = []
        normalized = []

        for fname in self._fpaths:
            version = self.get_version(fname)
            schema = get_schema(version)
            if schema is None:
                continue

            if repair_shifts:
                shifted = self.check_column_integrity(fname)
                if not shifted.is_empty():
                    for row, trip_id in zip(shifted["row"], shifted["trip_id"]):
                        anomalies.append({
                            "file": fname, "row": row, "trip_id": trip_id, "anomaly_type": "column_shift",
                            "detail": "raw field appears missing; downstream columns shifted left by one (repaired)",
                        })
                    self.repair_column_shift(fname, shifted["row"])

            casted, errors = self.cast_to_schema(fname)
            if not errors.is_empty():
                self._cast_errors[fname] = errors
                raw = self.get_df(fname)
                has_trip_id = "trip_id" in raw.columns
                for err_row, err_col, err_val in zip(errors["row"], errors["column"], errors["raw_value"]):
                    trip_id = None
                    if has_trip_id:
                        match = raw.filter(pl.col("row") == err_row)["trip_id"]
                        trip_id = match[0] if match.len() > 0 else None
                    anomalies.append({
                        "file": fname, "row": err_row, "trip_id": trip_id, "anomaly_type": "cast_error",
                        "detail": f"column={err_col!r} failed to cast, raw_value={err_val!r}",
                    })

            if historical_lookup is not None:
                casted = match_station_names_historical(casted, historical_lookup, fuzzy_threshold)
            if rt_lookup is not None:
                casted = match_station_names(casted, rt_lookup, fuzzy_threshold)

            normalized.append(casted.with_columns(pl.lit(fname).alias("source_file")))

        self._consol = pl.concat(normalized, how="diagonal_relaxed") if normalized else pl.DataFrame()
        self._reaudit()

        if not self._consol.is_empty():
            indexed = self._consol.with_row_index("row")

            consistency = check_consistency(indexed)
            for row, trip_id, source_file, computed, provided in zip(
                consistency["row"], consistency["trip_id"], consistency["source_file"],
                consistency["computed_duration"], consistency["provided_duration"],
            ):
                anomalies.append({
                    "file": source_file, "row": row, "trip_id": trip_id,
                    "anomaly_type": "consistency",
                    "detail": f"computed_duration={computed}, provided_duration={provided}",
                })

            dupes = indexed.filter(indexed.select("trip_id").is_duplicated())
            for row, trip_id, source_file in zip(dupes["row"], dupes["trip_id"], dupes["source_file"]):
                anomalies.append({
                    "file": source_file, "row": row, "trip_id": trip_id,
                    "anomaly_type": "duplicate_trip_id",
                    "detail": "trip_id appears more than once in the consolidated dataset",
                })

        anomaly_schema = {"file": pl.Utf8, "row": pl.UInt32, "trip_id": pl.Utf8, "anomaly_type": pl.Utf8, "detail": pl.Utf8}
        self._anomalies = pl.DataFrame(anomalies, schema=anomaly_schema) if anomalies else pl.DataFrame(schema=anomaly_schema)
        return self._consol


class Registry:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._ds = self._load_datasets()

    def _load_datasets(self) -> dict[str, DSEntry]:
        ds = {}
        path = self._path

        # filter through subdirs, load only dir names with YYYY identifiers (ref extract script)
        for d in sorted(os.listdir(path)):
            # refer subdir/dataset name as year (YYYY | YYYY-YYYY))
            ds_name = "-".join([sub for sub in re.split(r'[ _-]', d) if sub.isnumeric()])
            if d[-4:].isnumeric():
                files = {}
                # save schema structure per file within yearly ds
                col_struct = []
                for f in Path(f"{path}/{d}").glob("*.csv"):
                    cols = tuple(standardize_col(c) for c in _read_csv_normalized(f, n_rows=0, infer_schema_length=0).columns)

                    files[f.name] = f
                    schema_version = get_schema_version(cols)
                    # doc schema struct/versioning per file, supports consol later
                    col_struct.append({"dataset": d, "file": f.name, "columns": cols, "n_cols": len(cols), "version": schema_version})
                ds[ds_name] = DSEntry(ds_name, d, files, pl.DataFrame(col_struct))
        return ds

    def audit_schema(self):
        struct = [entry.get_struct() for entry in self._ds.values()]
        return pl.concat(struct, how="diagonal_relaxed")

    def get_all_datasets(self) -> dict[str, DSEntry]:
        return self._ds

    def get_dataset(self, dataset: str) -> DSEntry:
        if dataset not in self._ds:
            raise KeyError(f"{dataset} does not exist in registry.")
        return self._ds[dataset]

    def unpack(self, dataset: str) -> dict.keys:
        if dataset not in self._ds:
            raise KeyError(f"{dataset} does not exist in registry.")
        return self._ds[dataset].unpack()

    def unpack_all(self) -> dict[str, dict.keys]:
        summary = {}
        for ds, entry in self._ds.items():
            summary[ds] = entry.unpack()
        return summary

    def summarize(self) -> pl.DataFrame:
        summary = []
        for ds, entry in self._ds.items():
            summary.append({"dataset": ds, "n_files": len(entry.get_fpaths())})
        return pl.DataFrame(summary)
