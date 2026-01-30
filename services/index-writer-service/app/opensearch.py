import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from app.config import Settings

TRANSIENT_STATUSES = {429, 503, 504}


class OpenSearchClient:
    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.os_url.rstrip("/")
        self.timeout_sec = settings.timeout_sec
        self.health_check_interval_sec = settings.health_check_interval_sec
        self.health_sleep_yellow_sec = settings.health_sleep_yellow_sec
        self.health_sleep_red_sec = settings.health_sleep_red_sec
        self._last_health_check = 0.0
        self._last_health_status = "green"

    def request(self, method: str, path: str, body: Optional[Any] = None) -> Tuple[int, str]:
        url = f"{self.base_url}{path}"
        data = None
        headers: Dict[str, str] = {}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_sec) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise RuntimeError(f"OpenSearch request failed: {exc}") from exc

    def request_raw(self, method: str, path: str, payload: bytes, headers: Dict[str, str]) -> Tuple[int, str]:
        url = f"{self.base_url}{path}"
        request = urllib.request.Request(url, data=payload, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_sec) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise RuntimeError(f"OpenSearch request failed: {exc}") from exc

    def cluster_health(self) -> str:
        now = time.time()
        if now - self._last_health_check < self.health_check_interval_sec:
            return self._last_health_status
        status, body = self.request("GET", "/_cluster/health")
        if status >= 300:
            self._last_health_status = "red"
        else:
            data = json.loads(body)
            self._last_health_status = data.get("status", "red")
        self._last_health_check = now
        return self._last_health_status

    def maybe_throttle(self) -> None:
        status = self.cluster_health()
        if status == "red":
            time.sleep(self.health_sleep_red_sec)
        elif status == "yellow":
            time.sleep(self.health_sleep_yellow_sec)

    def list_indices(self, pattern: str) -> List[str]:
        status, body = self.request("GET", f"/_cat/indices/{pattern}?h=index")
        if status == 404:
            return []
        if status >= 300:
            raise RuntimeError(f"Failed to list indices ({status}): {body}")
        return [line.strip() for line in body.splitlines() if line.strip()]

    def index_exists(self, index_name: str) -> bool:
        status, _ = self.request("HEAD", f"/{index_name}")
        return 200 <= status < 300

    def delete_index(self, index_name: str) -> None:
        status, body = self.request("DELETE", f"/{index_name}")
        if status >= 300 and status != 404:
            raise RuntimeError(f"Failed to delete index {index_name} ({status}): {body}")

    def create_index(self, index_name: str, mapping: Dict[str, Any]) -> None:
        status, body = self.request("PUT", f"/{index_name}", mapping)
        if status >= 300:
            raise RuntimeError(f"Failed to create index {index_name} ({status}): {body}")

    def update_settings(self, index_name: str, settings: Dict[str, Any]) -> None:
        status, body = self.request("PUT", f"/{index_name}/_settings", settings)
        if status >= 300:
            raise RuntimeError(f"Failed to update settings {index_name} ({status}): {body}")

    def refresh(self, index_name: str) -> None:
        status, body = self.request("POST", f"/{index_name}/_refresh")
        if status >= 300:
            raise RuntimeError(f"Refresh failed ({status}): {body}")

    def count(self, index_name: str) -> int:
        status, body = self.request("GET", f"/{index_name}/_count")
        if status >= 300:
            raise RuntimeError(f"Count failed ({status}): {body}")
        return json.loads(body).get("count", 0)

    def search(self, index_name: str, body: Dict[str, Any]) -> Dict[str, Any]:
        status, response = self.request("POST", f"/{index_name}/_search", body)
        if status >= 300:
            raise RuntimeError(f"Search failed ({status}): {response}")
        return json.loads(response)

    def update_aliases(self, actions: List[Dict[str, Any]]) -> None:
        status, body = self.request("POST", "/_aliases", {"actions": actions})
        if status >= 300:
            raise RuntimeError(f"Alias update failed ({status}): {body}")

    def resolve_alias_indices(self, alias_name: str) -> List[str]:
        status, body = self.request("GET", f"/_alias/{alias_name}")
        if status == 404:
            return []
        if status >= 300:
            raise RuntimeError(f"Alias lookup failed ({status}): {body}")
        data = json.loads(body)
        return list(data.keys())
