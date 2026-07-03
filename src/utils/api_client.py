import requests
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class Client(ABC):
    def __init__(self, base_url: str, package_path: str, package_params: Dict[str, Any]=None) -> None:
        self._base_url = base_url.rstrip("/")
        self._package_path = package_path
        self._package_params = package_params

        self._session = requests.Session()

        self._package_cache: Optional[dict] = None
        self._data_feeds: Optional[dict] = None
    
    def _get(self, endpoint_path: str, params: dict = None) -> dict:
        url = f"{self._base_url}/{endpoint_path.lstrip('/')}"
        response = self._session.get(url, params=params)
        response.raise_for_status()
        return response.json()
    
    def get_package(self) -> dict:
        if self._package_cache is None:
            self._package_cache = self._get(self._package_path, params=self._package_params)
        return self._package_cache
    
    @abstractmethod
    def get_data_feeds(self) -> Optional[dict]:
        ...

    def fetch_data(self, endpoint_name: str) -> Optional[dict]:
        url = self.get_data_feeds()[endpoint_name]
        response = self._session.get(url)
        response.raise_for_status()
        return response.json()

    def clear_cache(self) -> None:
        self._package_cache = None
        self._data_feeds = None

    @classmethod
    def map_data(cls, data: list, key: str, val: str) -> dict:
        return {dat[key]: dat[val] for dat in data}


class CKANClient(Client):
    def __init__(self, base_url: str, package_params: Dict[str, Any]) -> None:
        super().__init__(base_url, "package_show", package_params)
        self._resource_cache: Optional[dict] = None
    
    def get_resource_metadata(self) -> Optional[dict]:
        if self._resource_cache is None:
            package = self.get_package()
            if not package.get("success"):
                logger.error("Failed to retrieve package information.")
                return None
            
            resources = package["result"]["resources"]
            target = next((res for res in resources if res["format"].lower() == "json"), None)
            if not target:
                logger.warning("No JSON resource found in the package.")
                return None
            
            self._resource_cache = self._get("resource_show", params={"id": target["id"]})
        return self._resource_cache

    def get_data_feeds(self) -> Optional[dict]:
        if self._data_feeds is None:
            resource_metadata = self.get_resource_metadata()
            if resource_metadata is None:
                return None

            data_feed_url = resource_metadata["result"]["url"]
            if not data_feed_url:
                logger.error("Resource metadata does not contain a valid URL.")
                return None
            
            response = self._session.get(data_feed_url)
            response.raise_for_status()
            data_feeds = response.json()["data"]["en"]["feeds"]

            self._data_feeds = self.map_data(data_feeds, key="name", val="url")
        return self._data_feeds
    
    def clear_cache(self) -> None:
        super().clear_cache()
        self._resource_cache = None

class GBFSClient(Client):
    def __init__(self, base_url: str):
        super().__init__(base_url, package_path="gbfs.json")
        self._base_url = self._base_url.removesuffix("/gbfs.json")

    def get_data_feeds(self):
        if self._data_feeds is None:
            package = self.get_package()
            if package is None:
                return None
            
            data_feeds = package["data"]["feeds"]
            self._data_feeds = self.map_data(data_feeds, key="name", val="url")
        return self._data_feeds
