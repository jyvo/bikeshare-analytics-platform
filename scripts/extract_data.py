from config import RAW_DATA_DIR, TMP_DATA_DIR
import zipfile
import shutil

def main():
    TMP_DATA_DIR.mkdir(parents=True, exist_ok=True)

    for path in RAW_DATA_DIR.rglob("*"):
        if not path.is_file():
            continue

        destination = TMP_DATA_DIR / path.stem
        destination.mkdir(parents=True, exist_ok=True)

        if path.suffix.lower() == ".xlsx":
            shutil.copy2(path, destination)
            print(f"Copied {path.name}")
        else:
            try:
                with zipfile.ZipFile(path, "r") as zf:
                    zf.testzip()
                    zf.extractall(destination)
                print(f"Extracted {path.name}")
                
            except zipfile.BadZipFile:
                print(f"Failed to unzip the following file: {path.name}")

    print("Extracted all available files")

if __name__ == "__main__":
    main()