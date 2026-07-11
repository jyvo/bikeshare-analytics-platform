from typing import Iterable

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
    "start_time": "datetime64[ns]",
    "end_time": "datetime",
    "user_type": "string"
}
V2_SCHEMA = BASE_SCHEMA | {"bike_id": "string"}
V3_SCHEMA = V2_SCHEMA | {"bike_model": "string"}


def standardize_colnames(cols: Iterable[str]) -> list[str]:
    standardized = []
    for col in cols:
        cleaned = "_".join(col.lower().split())
        cleaned = COL_RENAME_MAP.get(cleaned, cleaned)
        standardized.append(cleaned)
    return standardized


def get_schema(cols: Iterable[str]) -> dict[str, str]:
    cleaned = standardize_colnames(cols)

    # versioning
    match len(cleaned):
        # base 9 columns (fill na then reference for missing station ids)
        case 7 | 9:
            schema = BASE_SCHEMA
            pass
        case 10: 
            schema = V2_SCHEMA
            pass
        case 11:
            schema = V3_SCHEMA
            pass
        case _:
            raise ValueError(f"Unexpected number of columns: {len(cleaned)}")
    return schema

