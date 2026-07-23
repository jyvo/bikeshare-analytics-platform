from typing import Iterable
import polars as pl

COL_RENAME_MAP = {
    "trip_start_time" : "start_time",
    "trip_stop_time" : "end_time",
    "trip_duration_seconds" : "trip_duration",
    "from_station_id" : "start_station_id",
    "from_station_name" : "start_station_name",
    "to_station_id" : "end_station_id",
    "to_station_name" : "end_station_name"
}

BASE_SCHEMA = {
    "trip_id": "string", 
    "trip_duration": "int",
    "start_station_id": "string",
    "start_station_name": "string",
    "end_station_id": "string",
    "end_station_name": "string",
    "start_time": "datetime",
    "end_time": "datetime",
    "user_type": "string"
}
V2_SCHEMA = BASE_SCHEMA | {"bike_id": "string"}
V3_SCHEMA = V2_SCHEMA | {"bike_model": "string"}

SCHEMA_MAP = {"v1": BASE_SCHEMA,
              "v1.1": BASE_SCHEMA,
              "v2": V2_SCHEMA,
              "v3": V3_SCHEMA}


def standardize_col(col: str) -> str:
    cleaned = "_".join(col.lower().split())
    return COL_RENAME_MAP.get(cleaned, cleaned)


def get_schema_version(cols: Iterable[str]) -> str:
    # versioning based on num cols
    match len(cols):
        # note v1 is missing station id columns in comparison to v1.1 (can be backfilled)
        case 7:
            version = "v1"
            pass
        case 9:
            version = "v1.1"
            pass
        case 10: 
            version = "v2"
            pass
        case 11:
            version = "v3"
            pass
        case _:
            return "N/A"
    return version


def get_schema(version: str) -> dict[str, str] | None:
    return SCHEMA_MAP.get(version)


ISO_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
# variants since polars doesnt have flexible parsing
DAYFIRST_DATETIME_FORMATS = ["%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M"]
MONTHFIRST_DATETIME_FORMATS = ["%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%m-%d-%Y %H:%M:%S", "%m-%d-%Y %H:%M"]

# date convention identifier
def identify_dayfirst(series: pl.Series) -> bool:
    tokens = series.drop_nulls().str.extract_groups(r"^(\d{1,2})[/-](\d{1,2})[/-]\d{2,4}")
    if tokens.len() == 0:
        return True
    first = tokens.struct.field("1").cast(pl.Int64, strict=False)
    second = tokens.struct.field("2").cast(pl.Int64, strict=False)
    if first.is_null().all():
        return True
    if (first > 12).any():
        return True
    if (second > 12).any():
        return False
    return True


# datetime caster with mix formats
def parse_datetime(series: pl.Series) -> pl.Series:
    # try iso first, then proceed with dayfirst/monthfirst
    # hard-coded at the moment, configure later
    parsed = series.str.to_datetime(format=ISO_DATETIME_FORMAT, strict=False)
    remaining = parsed.is_null() & series.is_not_null()
    if remaining.any():
        dayfirst = identify_dayfirst(series.filter(remaining))
        formats = DAYFIRST_DATETIME_FORMATS if dayfirst else MONTHFIRST_DATETIME_FORMATS
        for fmt in formats:
            parsed = parsed.fill_null(series.str.to_datetime(format=fmt, strict=False))
    return parsed



def cast_column(series: pl.Series, dtype: str) -> tuple[pl.Series, pl.Series]:
    if dtype.startswith("datetime"):
        casted = parse_datetime(series)
    elif dtype in ("int", "int64"):
        casted = series.cast(pl.Int64, strict=False)
    elif dtype in ("float", "float64"):
        casted = series.cast(pl.Float64, strict=False)
    else:
        casted = series.cast(pl.Utf8, strict=False)
    failed = casted.is_null() & series.is_not_null()
    return casted, failed
