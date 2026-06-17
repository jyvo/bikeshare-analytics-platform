import requests
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class APIClient:
    def __init__(self, base_url: str, package_params: Dict[str, Any]) -> None:
        self._base_url = base_url.rstrip("/")
        self._package_params = package_params

        self._session = requests.Session()
        
        self._package_cache: Optional[dict] = None
        self._resource_cache: Optional[dict] = None
        self._endpoints_cache: Optional[list] = None

    def _get(self, endpoint_path: str, params: dict = None) -> dict:
        url = f"{self._base_url}/{endpoint_path.lstrip('/')}"
        response = self._session.get(url, params=params)
        response.raise_for_status()
        return response.json()
    
    def get_session(self) -> requests.Session:
        return self._session

    def get_package(self) -> dict:
        if self._package_cache is None:
            self._package_cache = self._get("package_show", params=self._package_params)
        return self._package_cache

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

    def get_endpoints(self) -> Optional[list]:
        if self._endpoints_cache is None:
            resource_metadata = self.get_resource_metadata()
            if resource_metadata is None:
                return None

            endpoints_url = resource_metadata["result"]["url"]
            if not endpoints_url:
                logger.error("Resource metadata does not contain a valid URL.")
                return None
            
            response = self._session.get(endpoints_url)
            response.raise_for_status()

            self._endpoints_cache = response.json()["data"]["en"]["feeds"]
        return self._endpoints_cache
    
    def clear_cache(self) -> None:
        self._package_cache = None
        self._resource_cache = None
        self._endpoints_cache = None
