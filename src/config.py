import os
from pathlib import Path

from dotenv import load_dotenv

# packaged with the egg, proj root is one level up
PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

# config data directories
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
TMP_DATA_DIR = DATA_DIR / "temp"
RT_SNAPSHOT_DIR = DATA_DIR / "snapshot"

# config API parameters
CKAN_FEED = "https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action"
GBFS_FEED = "https://toronto.publicbikesystem.net/customer/gbfs/v3.0"
CKAN_RT_PACKAGE_PARAMS = {"id": "bike-share-toronto"}
HIST_PACKAGE_PARAMS = {"id": "bike-share-toronto-ridership-data"}
