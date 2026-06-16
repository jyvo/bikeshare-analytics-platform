from utils.path import get_git_root

BASE_DIR = get_git_root()

# config data directories
DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
TMP_DATA_DIR = DATA_DIR / "temp"

# config API parameters
API_PUB_BASE_URL = "https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action"
PACKAGE_PARAMS = {"id": "bike-share-toronto"}
