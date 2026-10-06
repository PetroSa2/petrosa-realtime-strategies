"""Small async HTTP client for the data-manager generic API."""

import asyncio
import logging
import os
from typing import Any

import httpx

from .exceptions import ConnectionError

logger = logging.getLogger(__name__)
_missing_token_warning_emitted = False


class DataManagerClient:
    """Call data-manager without opening a service-owned database connection."""

    def __init__(
        self,
        base_url: str,
        timeout: int = 30,
        max_retries: int = 3,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        headers = {
            "X-Petrosa-Service": os.getenv("DM_SERVICE_NAME", "realtime-strategies")
        }
        token = os.getenv("DM_SERVICE_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        else:
            global _missing_token_warning_emitted
            if not _missing_token_warning_emitted:
                logger.warning(
                    "DM_SERVICE_TOKEN is unset; data-manager calls use service identity only"
                )
                _missing_token_warning_emitted = True

        self._client = httpx.AsyncClient(
            base_url=self.base_url, timeout=timeout, headers=headers
        )

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        for attempt in range(self.max_retries + 1):
            try:
                response = await self._client.request(method, path, **kwargs)
                response.raise_for_status()
                payload = response.json()
                return payload if isinstance(payload, dict) else {"data": payload}
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                if attempt >= self.max_retries:
                    raise ConnectionError(str(exc)) from exc
                await asyncio.sleep(2**attempt)

        raise ConnectionError("data-manager request exhausted retries")

    async def health(self) -> dict[str, Any]:
        return await self._request("GET", "/health")

    async def query(
        self,
        *,
        database: str,
        collection: str,
        filter: dict[str, Any] | None = None,
        fields: list[str] | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "database": database,
            "collection": collection,
            "filter": filter or {},
        }
        if fields is not None:
            payload["fields"] = fields
        if limit is not None:
            payload["limit"] = limit
        return await self._request("POST", "/api/v1/mongodb/query", json=payload)

    async def update(
        self,
        *,
        database: str,
        collection: str,
        filter: dict[str, Any],
        data: dict[str, Any],
        upsert: bool = False,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/v1/mongodb/update",
            json={
                "database": database,
                "collection": collection,
                "filter": filter,
                "data": data,
                "upsert": upsert,
            },
        )

    async def delete(
        self, *, database: str, collection: str, filter: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/v1/mongodb/delete",
            json={"database": database, "collection": collection, "filter": filter},
        )

    async def insert(
        self, *, database: str, collection: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/v1/mongodb/insert",
            json={"database": database, "collection": collection, "data": data},
        )

    async def post(
        self, path: str, *, json: dict[str, Any], params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return await self._request("POST", path, json=json, params=params)

    async def close(self) -> None:
        await self._client.aclose()


__all__ = ["ConnectionError", "DataManagerClient"]
