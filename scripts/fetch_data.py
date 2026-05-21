from config import RAW_DATA_DIR
from tqdm import tqdm
import requests

def main():
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

    base_url = "https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action"

    package_url = base_url + "/package_show"
    params = {"id": "bike-share-toronto-ridership-data"}

    package_resp = requests.get(package_url, params=params)

    package_resp.raise_for_status()

    package = package_resp.json()

    for resource in package["result"]["resources"]:
        if not resource["datastore_active"]:
            url = base_url + "/resource_show?id=" + resource["id"]
            resource_metadata = requests.get(url).json()

            file_name = resource_metadata["result"]["name"]
            file_type = "." + resource_metadata["result"]["format"].lower()

            # preserves file extension format (specifically for xlsx files)
            if not file_name.lower().endswith(file_type):
                file_name += file_type

            try:
                resp = requests.get(resource_metadata["result"]["url"], stream=True)
                resp.raise_for_status()

                bar = tqdm(
                    desc=file_name.ljust(35),
                    total=int(resp.headers.get("content-length", 0)),
                    unit="B",
                    unit_scale=True,
                    unit_divisor=1024
                )

                with open(RAW_DATA_DIR / file_name, "wb") as f:
                    # could look to dynamically adjust chunk size based on file size
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            bar.update(len(chunk))
                bar.close()

            except requests.exceptions.RequestException as e:
                print(f"Error downloading file: {e}")

    print("Downloaded all raw data files")

if __name__ == "__main__":
    main()