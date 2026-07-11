from schema_registry import standardize_colnames
from pathlib import Path
import pandas as pd
import re
import os


class DSEntry:
    def __init__(self, name: str, dpath: Path, fpaths: dict[str, Path], audit: pd.DataFrame=None):
        self._name = name
        self._dpath = dpath
        self._fpaths = fpaths
        self._audit = audit
        self._dfs = {}
        self._consol = None

    def get_audit(self):
        return self._audit

    def _reaudit(self) -> pd.DataFrame:
        # audits on unpacked dfs
        audit = []
        for fname, df in self._dfs.items():
            cols = tuple(df.columns)
            audit.append({"dataset": self._name, "file": fname, "columns": cols, "n_cols": len(cols)})
        self._audit = pd.DataFrame(audit)
        return self._audit

    def _to_df(self, path: Path) -> pd.DataFrame:
        try:
            return pd.read_csv(path, encoding="utf-8-sig")
        except UnicodeDecodeError:
            return pd.read_csv(path, encoding="latin1")

    def unpack(self) -> dict.keys:
        for fname, fpath in self._fpaths.items():
            self._dfs[fname] = self._to_df(fpath)
        return self._dfs.keys()
    
    def get_fnames(self) -> dict.keys:
        return self._fpaths.keys()

    def get_fpaths(self) -> dict[str, Path]:
        return self._fpaths
    
    def get_file(self, fname: str) -> pd.DataFrame:
        if fname not in self._fpaths:
            raise ValueError(f"{fname} does not exist in registry.")
        elif fname not in self._dfs:
            self._dfs[fname] = self._to_df(self._fpaths[fname])
        return self._dfs[fname]

    def consol(self) -> pd.DataFrame:
        if not self._dfs:
            self.unpack()
        
        # add additional measures from normalization checker
        # for instance, 2014-2015 does not follow schema
        
        # rename -> backfill ids -> cast
        # currently normalize_to_schema performs rename -> cast
        normalized = [normaalize_to_schema(df) for df in self._dfs.values()]
        self._combined = pd.concat(normalized, ignore_index=True)
        self._reaudit()
        return self._combined
    

class Registry:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._ds = self._load_datasets()

    def _load_datasets(self) -> dict[str, DSEntry]:
        ds = {}
        path = self._path
        for d in sorted(os.listdir(path)):
            ds_name = "-".join([sub for sub in re.split(r'[ _-]', d) if sub.isnumeric()])
            if d[-4:].isnumeric():
                files = {}
                audit = []
                for f in Path(f"{path}/{d}").glob("*.csv"):
                    try:
                        cols = tuple(pd.read_csv(f, nrows=0, encoding="utf-8-sig").columns)
                    except UnicodeDecodeError:
                        cols = tuple(pd.read_csv(f, nrows=0, encoding="latin1").columns)

                    files[f.name] = f
                    audit.append({"dataset": d, "file": f.name, "columns": cols, "n_cols": len(cols)})
                ds[ds_name] = DSEntry(ds_name, d, files, pd.DataFrame(audit))
        return ds
    
    def audit_cols(self):
        audits = [entry.get_audit() for entry in self._ds.values()]
        return pd.concat(audits, ignore_index=True)
    
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
    
    def summarize(self) -> pd.DataFrame:
        summary = []
        for ds, entry in self._ds.items():
            summary.append({"dataset": ds, "n_files": len(entry.get_fpaths())})
        return pd.DataFrame(summary)



def normaalize_to_schema(df: pd.DataFrame) -> pd.DataFrame:
    # base 9 columns (fill na then reference for missing station ids)
    base = {"trip_id": str, 
            "trip_duration": "Int64",
            "start_station_id": str,
            "start_station_name": str,
            "end_station_id": str,
            "end_station_name": str,
            "start_time": "datetime64[ns]",
            "end_time": "datetime64[ns]",
            "user_type": str}
    v2 = base | {"bike_id": str}
    v3 = v2 | {"bike_model": str}

    cleaned = standardize_colnames(df.columns)
    df = df.copy()
    df.columns = cleaned

    # versioning
    match len(cleaned):
        case 7 | 9:
            schema = base
            pass
        case 10: 
            schema = v2
            pass
        case 11:
            schema = v3
            pass
        case _:
            raise ValueError(f"Unexpected number of columns: {len(cleaned)}")
    
    # apply schema to df, type casting
    # handle nullable type castings
    for col, dtype in schema.items():
        if col not in df.columns:
            df[col] = pd.NA
            continue

        if "id" in col:
            df[col] = df[col].astype("Int64").astype(str)
        if dtype == "datetime64[ns]":
            df[col] = pd.to_datetime(df[col], errors="coerce")
        elif dtype == "Int64":
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
        else:
            df[col] = df[col].astype(str)

    return df
