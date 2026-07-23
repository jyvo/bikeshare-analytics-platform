from rapidfuzz import process, fuzz
from utils.api_client import GBFSClient
import polars as pl

import re
import unicodedata


def get_rt_stations(GBFSfeed: str) -> pl.DataFrame:
    client = GBFSClient(GBFSfeed)
    client.get_data_feeds()

    response = client.fetch_data("station_information")
    station_data = response["data"]["stations"]
    station_df = pl.DataFrame(station_data, infer_schema_length=None)

    cleaned = station_df.select(["station_id", "name", "lat", "lon", "address", "short_name"])
    # get en text for name and short_name
    cleaned = cleaned.with_columns([
        pl.col("name").map_elements(lambda x: GBFSClient.map_data(x, "language", "text").get("en"), return_dtype=pl.Utf8),
        pl.col("short_name").map_elements(lambda x: GBFSClient.map_data(x, "language", "text").get("en"), return_dtype=pl.Utf8),
    ])
    # temp fill since some stations have the same name and address
    cleaned = cleaned.with_columns(pl.col("address").fill_null(pl.col("name")))
    return cleaned


def normalize_station_name(name) -> str | None:
    # sanitize station names for crosswalk matching
    if name is None:
        return None
    text = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"\bat\b", "/", text)
    text = re.sub(r"[\\/]+", "/", text)
    text = re.sub(r"\s*/\s*", " / ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def build_rt_lookup(rt_stations: pl.DataFrame, name_cols: tuple[str, ...] = ("name", "address", "short_name")) -> dict[str, str]:
    lookup = {}
    for col in name_cols:
        if col not in rt_stations.columns:
            continue
        for name, station_id in zip(rt_stations[col], rt_stations["station_id"]):
            key = normalize_station_name(name)
            if key and key not in lookup:
                lookup[key] = station_id
    return lookup


def _match_station_names_cascade(df: pl.DataFrame, lookup: dict[str, str], fuzzy_threshold: int, matched_via_prefix: str) -> pl.DataFrame:
    if not lookup:
        return df.clone()

    result = df
    choices = list(lookup.keys())
    fuzzy_cache: dict[str, str | None] = {}

    def resolve_fuzzy(name: str) -> str | None:
        if name not in fuzzy_cache:
            best = process.extractOne(name, choices, scorer=fuzz.token_sort_ratio, score_cutoff=fuzzy_threshold)
            fuzzy_cache[name] = best[0] if best is not None else None
        return fuzzy_cache[name]

    for prefix in ("start", "end"):
        id_col, name_col = f"{prefix}_station_id", f"{prefix}_station_name"
        if id_col not in result.columns or name_col not in result.columns:
            continue

        inferred_col, matched_via_col = f"{prefix}_id_inferred", f"{prefix}_matched_via"
        # check from prior results instead of False/null to not overwrite prev match
        inferred = result[inferred_col].clone() if inferred_col in result.columns else pl.Series([False] * result.height)
        matched_via = result[matched_via_col].clone() if matched_via_col in result.columns else pl.Series([None] * result.height, dtype=pl.Utf8)

        # force Utf8 so nulls can be replaced later
        id_series = result[id_col].cast(pl.Utf8)
        name_series = result[name_col]

        needs_match = id_series.is_null() & name_series.is_not_null()
        needs_idx = needs_match.arg_true()
        if needs_idx.len() == 0:
            result = result.with_columns([id_series.alias(id_col), inferred.alias(inferred_col), matched_via.alias(matched_via_col)])
            continue

        normalized = name_series.gather(needs_idx).map_elements(normalize_station_name, return_dtype=pl.Utf8)

        exact_ids = normalized.map_elements(lambda n: lookup.get(n) if n is not None else None, return_dtype=pl.Utf8)
        exact_hit = exact_ids.is_not_null()

        if exact_hit.any():
            exact_idx = needs_idx.filter(exact_hit)
            id_series = id_series.scatter(exact_idx, exact_ids.filter(exact_hit))
            inferred = inferred.scatter(exact_idx, pl.Series([True] * exact_hit.sum()))
            matched_via = matched_via.scatter(exact_idx, pl.Series([f"{matched_via_prefix}exact_name"] * exact_hit.sum()))

        # fuzzy-match only distinct names still unresolved after the exact tier
        fuzzy_scope = ~exact_hit
        fuzzy_idx = needs_idx.filter(fuzzy_scope)
        fuzzy_names = normalized.filter(fuzzy_scope)
        for unique_name in fuzzy_names.unique():
            if unique_name is not None:
                resolve_fuzzy(unique_name)

        fuzzy_matches = fuzzy_names.map_elements(lambda n: fuzzy_cache.get(n), return_dtype=pl.Utf8)
        fuzzy_ids = fuzzy_matches.map_elements(lambda m: lookup.get(m) if m is not None else None, return_dtype=pl.Utf8)
        fuzzy_hit = fuzzy_ids.is_not_null()

        if fuzzy_hit.any():
            hit_idx = fuzzy_idx.filter(fuzzy_hit)
            id_series = id_series.scatter(hit_idx, fuzzy_ids.filter(fuzzy_hit))
            inferred = inferred.scatter(hit_idx, pl.Series([True] * fuzzy_hit.sum()))
            matched_via = matched_via.scatter(hit_idx, pl.Series([f"{matched_via_prefix}fuzzy_name"] * fuzzy_hit.sum()))

        result = result.with_columns([
            id_series.alias(id_col),
            inferred.alias(inferred_col),
            matched_via.alias(matched_via_col),
        ])

    return result


def match_station_names(df: pl.DataFrame, rt_lookup: dict[str, str], fuzzy_threshold: int = 90) -> pl.DataFrame:
    # name-only (2016 carries no ids/coords): exact_name -> fuzzy_name
    return _match_station_names_cascade(df, rt_lookup, fuzzy_threshold, matched_via_prefix="")


def match_station_names_historical(df: pl.DataFrame, historical_lookup: dict[str, str], fuzzy_threshold: int = 90) -> pl.DataFrame:
    # cross ref via loaders.pl_loader.build_historical_lookup) before the RT match runs
    return _match_station_names_cascade(df, historical_lookup, fuzzy_threshold, matched_via_prefix="historical_")
