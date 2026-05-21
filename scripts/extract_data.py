from config import RAW_DATA_DIR, TMP_DATA_DIR
import zipfile
import re
import pandas as pd

def main():
    TMP_DATA_DIR.mkdir(parents=True, exist_ok=True)

    for path in RAW_DATA_DIR.rglob("*"):
        if not path.is_file():
            continue

        destination = TMP_DATA_DIR / path.stem
        destination.mkdir(parents=True, exist_ok=True)

        if path.suffix.lower() == ".xlsx":
            file_df = pd.read_excel(path, sheet_name=None)

            for sheet_name, df in file_df.items():
                split_name = re.split(r"[ _-]+", sheet_name)
                normalize = [w.capitalize() if re.fullmatch(r"[qQ]\d+", w) else w.lower() for w in split_name]
                sanitized_sheet_name = "-".join(normalize)

                csv_path = destination / f"{sanitized_sheet_name}.csv"
                df.to_csv(csv_path, index=False)
            
            print(f"Converted {path.name} to CSV")
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