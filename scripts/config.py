from utils.path import get_git_root

BASE_DIR = get_git_root()

DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
TMP_DATA_DIR = DATA_DIR / "temp"

for path in [DATA_DIR, RAW_DATA_DIR, TMP_DATA_DIR]:
    path.mkdir(parents=True, exist_ok=True)