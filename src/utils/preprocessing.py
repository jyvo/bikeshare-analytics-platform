import pandas as pd
import numpy as np

def normalize_column_names(column_names: pd.Index) -> pd.Index:
    return column_names.str.replace(r'\s+', '_', regex=True).str.lower()

def normalize_datetimes(dates: pd.Series) -> pd.Series:
    return pd.to_datetime(dates, format='%m/%d/%y %H:%M:%S', errors='coerce')

def calc_trip_duration(df:pd.DataFrame, start_col_name:str, end_col_name:str, index:pd.Index=slice(None)):
    start_time = pd.to_datetime(df.loc[index, start_col_name])
    end_time = pd.to_datetime(df.loc[index, end_col_name])
    return (end_time - start_time).dt.total_seconds().astype('int64')

def na_dtype_df(df:pd.DataFrame, name:str, columns:list|set) -> pd.DataFrame:
    new_entry = pd.DataFrame({'name': [name]})
    for col in columns:
        if col in df.columns:
            new_entry[col] = df[col].isna().sum()
            new_entry[f'{col}_dtype'] = df[col].dtype
        else:
            new_entry[col] = np.nan
            new_entry[f'{col}_dtype'] = np.nan
    return new_entry

def get_dtype_cols(df:pd.DataFrame) -> list:
    return [col for col in df.columns if col.endswith('_dtype')]

def count_col_dtypes(df:pd.DataFrame, summarize_all:bool=False) -> None:
    dtype_cols = get_dtype_cols(df)
    for dtype in dtype_cols:
        val_counts = df[dtype].value_counts()
        if len(val_counts.tolist()) > 1 or summarize_all:
            print(val_counts)
            print()
    return

def standardize_colnames(cols: tuple[str]) -> list[str]:
    mapping = {"trip_start_time" : "start_time",
                "trip_stop_time" : "end_time",
                "trip_duration_seconds" : "trip_duration",
                "to_station_id" : "start_station_id",
                "to_station_name" : "start_station_name",
                "from_station_id" : "end_station_id",
                "from_station_name" : "end_station_name"}
    
    standardized = []
    for col in cols:
        cleaned = "_".join(col.lower().split())
        if cleaned in mapping:
            cleaned = mapping[cleaned]
        standardized.append(cleaned)
    return standardized