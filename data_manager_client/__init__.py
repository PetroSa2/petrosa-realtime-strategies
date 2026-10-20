"""Small async HTTP client for the data-manager generic API."""

import asyncio
import json
import logging
import os
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

import httpx

from .exceptions import ConnectionError

logger = logging.getLogger(__name__)
_missing_token_warning_emitted = False


def _json_safe(value: Any) -> Any:
    """Return a JSON-safe copy without mutating caller-owned values."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe(item) for item in value]
    return value


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
            except httpx.HTTPStatusError as exc:
                endpoint = exc.request.url.path
                if (
                    exc.response.status_code not in {408, 429}
                    and 400 <= exc.response.status_code < 500
                ):
                    raise ConnectionError(
                        f"data-manager request failed: endpoint={endpoint} "
                        f"status={exc.response.status_code} detail=<redacted>"
                    ) from exc
                if attempt >= self.max_retries:
                    raise ConnectionError(
                        f"data-manager request failed: endpoint={endpoint} "
                        f"status={exc.response.status_code} detail=<redacted>"
                    ) from exc
                await asyncio.sleep(2**attempt)
            except httpx.RequestError as exc:
                if attempt >= self.max_retries:
                    raise ConnectionError(str(exc)) from exc
                await asyncio.sleep(2**attempt)

        raise ConnectionError("data-manager request exhausted retries")

    async def health(self) -> dict[str, Any]:
        return await self._request("GET", "/health/readiness")

    async def query(
        self,
        *,
        database: str,
        collection: str,
        filter: dict[str, Any] | None = None,
        fields: list[str] | None = None,
        sort: dict[str, int] | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"filter": json.dumps(_json_safe(filter or {}))}
        if fields is not None:
            params["fields"] = ",".join(fields)
        if sort is not None:
            params["sort"] = json.dumps(_json_safe(sort))
        if limit is not None:
            params["limit"] = limit
        return await self._request(
            "GET", f"/api/v1/{database}/{collection}", params=params
        )

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
            "PUT",
            f"/api/v1/{database}/{collection}",
            json={
                "filter": _json_safe(filter),
                "data": _json_safe(data),
                "upsert": upsert,
            },
        )

    async def delete(
        self, *, database: str, collection: str, filter: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._request(
            "DELETE",
            f"/api/v1/{database}/{collection}",
            json={"filter": _json_safe(filter)},
        )

    async def insert(
        self, *, database: str, collection: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"/api/v1/{database}/{collection}",
            json={"data": _json_safe(data)},
        )

    async def post(
        self, path: str, *, json: dict[str, Any], params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return await self._request("POST", path, json=_json_safe(json), params=params)

    async def close(self) -> None:
        await self._client.aclose()


__all__ = ["ConnectionError", "DataManagerClient"]
