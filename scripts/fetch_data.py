from config import RAW_DATA_DIR
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

            try:
                resp = requests.get(resource_metadata["result"]["url"], stream=True)
                resp.raise_for_status()

                with open(RAW_DATA_DIR / file_name, "wb") as f:
                    f.write(resp.content)

                print(f"Downloaded: {file_name}")

            except requests.exceptions.RequestException as e:
                print(f"Error downloading file: {e}")
    print("Downloaded all raw data files")

if __name__ == "__main__":
    main()