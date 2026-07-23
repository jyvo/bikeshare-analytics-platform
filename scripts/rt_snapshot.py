from utils.api_client import GBFSClient
from config import GBFS_FEED, RT_SNAPSHOT_DIR
import pandas as pd
import os

snapshots = os.listdir(RT_SNAPSHOT_DIR)

client = GBFSClient(GBFS_FEED)

# unfinished, need to add column integrity checks (scaling and versioning)
# also seems like feed's always updating (if-else check redundant)
# either set a max file lim or time-based retention

station_feed = client.fetch_data("station_information")
last_upd_station = station_feed["last_updated"]

if f"station_{last_upd_station}.csv" in snapshots:
    print(f"station snapshot {last_upd_station} already exists, skipping")
else:
    station_info = station_feed["data"]["stations"]
    info_df = pd.DataFrame(station_info)

    cleaned_info = info_df.drop(columns=["vehicle_types_capacity", "vehicle_docks_capacity", "rental_uris", "rental_methods", "cross_street", "post_code"])
    cleaned_info["name"] = cleaned_info["name"].apply(lambda x: GBFSClient.map_data(x, "language", "text").get("en"))
    cleaned_info["short_name"] = cleaned_info["short_name"].apply(lambda x: GBFSClient.map_data(x, "language", "text").get("en"))
    cleaned_info["address"] = cleaned_info["address"].fillna(cleaned_info["name"])
    cleaned_info["is_valet_station"] = cleaned_info["is_valet_station"].astype(bool).fillna(False)
    # cleaned_info["_valet_station_details"] = cleaned_info["_valet_station_details"].fillna("N/A")

    cleaned_info.to_csv(RT_SNAPSHOT_DIR / f"station_{last_upd_station}.csv", index=False)
    print(f"saved station snapshot {last_upd_station}")

status_feed = client.fetch_data("station_status")
last_upd_status = status_feed["last_updated"]

if f"status_{last_upd_status}.csv" in snapshots:
    print(f"status snapshot {last_upd_status} already exists, skipping")
else:
    status_data = status_feed["data"]["stations"]
    status_df = pd.DataFrame(status_data)

    cleaned_status = status_df.drop(columns=["vehicle_docks_available", "vehicle_types_available"])
    cleaned_status = cleaned_status.join(status_df["vehicle_types_available"].apply(lambda x: GBFSClient.map_data(x, "vehicle_type_id", "count")).apply(pd.Series).add_prefix("available_"))
    cleaned_status["last_reported"] = pd.to_datetime(cleaned_status["last_reported"], format="ISO8601", utc=True).dt.tz_convert(None).dt.floor("ms")
    cleaned_status = cleaned_status.rename(columns=str.lower)

    cleaned_status.to_csv(RT_SNAPSHOT_DIR / f"status_{last_upd_status}.csv", index=False)
    print(f"saved status snapshot {last_upd_status}")
