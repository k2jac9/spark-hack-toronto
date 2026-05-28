"""Thin client for the City of Toronto CKAN open-data API.

Used both to discover dataset resources and to pull rows. Network calls are
isolated here so the rest of the app can run against cached/sample data offline
(critical: the venue Wi-Fi is unreliable — pre-download with scripts/download_data.py).
"""
from __future__ import annotations

from typing import Any

import httpx

from ..config import settings


class CKANClient:
    def __init__(self, base_url: str | None = None, timeout: float = 30.0) -> None:
        self.base_url = (base_url or settings.ckan_base_url).rstrip("/")
        self._client = httpx.Client(timeout=timeout)

    def _action(self, action: str, **params: Any) -> Any:
        """Call a CKAN action API endpoint and return its `result` payload."""
        resp = self._client.get(f"{self.base_url}/api/3/action/{action}", params=params)
        resp.raise_for_status()
        body = resp.json()
        if not body.get("success", False):
            raise RuntimeError(f"CKAN action {action} failed: {body.get('error')}")
        return body["result"]

    def package(self, slug: str) -> dict[str, Any]:
        """Metadata for a dataset, including its downloadable resources."""
        return self._action("package_show", id=slug)

    def resources(self, slug: str) -> list[dict[str, Any]]:
        return self.package(slug).get("resources", [])

    def datastore_search(
        self, resource_id: str, *, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        """Page rows from a datastore-active resource."""
        result = self._action(
            "datastore_search", id=resource_id, limit=limit, offset=offset
        )
        return result.get("records", [])

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "CKANClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
