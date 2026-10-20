import logging
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import httpx
import pytest

import data_manager_client as data_manager_module
from data_manager_client import DataManagerClient
from strategies.services.data_manager_client import DataManagerClient as StrategyClient


@pytest.mark.asyncio
async def test_requests_include_configured_gateway_identity(monkeypatch):
    token = "test-token-that-must-not-leak"
    monkeypatch.setenv("DM_SERVICE_NAME", "realtime-strategies-test")
    monkeypatch.setenv("DM_SERVICE_TOKEN", token)
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"status": "ok"})

    async_client = httpx.AsyncClient

    def mock_async_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", mock_async_client)
    client = DataManagerClient("https://data-manager.test")

    try:
        await client.health()
    finally:
        await client.close()

    assert requests[0].headers["X-Petrosa-Service"] == "realtime-strategies-test"
    assert requests[0].headers["Authorization"] == f"Bearer {token}"


@pytest.mark.asyncio
async def test_health_uses_readiness_contract(monkeypatch):
    monkeypatch.setenv("DM_SERVICE_TOKEN", "test-token")
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/health":
            return httpx.Response(422, json={"detail": "pair required"})
        return httpx.Response(
            200,
            json={"ready": True, "components": {"mongodb": "healthy"}},
        )

    async_client = httpx.AsyncClient

    def mock_async_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", mock_async_client)
    client = DataManagerClient("https://data-manager.test")
    try:
        health = await client.health()
    finally:
        await client.close()

    assert health["ready"] is True
    assert [request.url.path for request in requests] == ["/health/readiness"]


@pytest.mark.asyncio
async def test_client_does_not_retry_http_4xx(monkeypatch):
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(422, json={"detail": "thin data"})

    async_client = httpx.AsyncClient

    def mock_async_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", mock_async_client)
    client = DataManagerClient("https://data-manager.test", max_retries=3)
    try:
        with pytest.raises(data_manager_module.ConnectionError) as error:
            await client.query(
                database="mongodb",
                collection="strategy_lifecycle_states",
                filter={"strategy_id": "thin"},
            )
    finally:
        await client.close()

    assert len(requests) == 1
    assert "endpoint=/api/v1/mongodb/strategy_lifecycle_states" in str(error.value)
    assert "status=422" in str(error.value)
    assert "detail=<redacted>" in str(error.value)
    assert "thin data" not in str(error.value)


@pytest.mark.asyncio
async def test_collection_routes_encode_query_and_nested_datetimes(monkeypatch):
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": [], "updated_count": 1})

    async_client = httpx.AsyncClient

    def mock_async_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", mock_async_client)
    client = DataManagerClient("https://data-manager.test")
    timestamp = datetime(2026, 10, 20, tzinfo=UTC)
    try:
        await client.query(
            database="mongodb",
            collection="strategy_lifecycle_states",
            filter={"metadata": {"at": timestamp}},
            fields=["strategy_id"],
            limit=1,
        )
        await client.update(
            database="mongodb",
            collection="strategy_lifecycle_states",
            filter={"strategy_id": "strategy"},
            data={"changed_at": timestamp, "metadata": [{"at": timestamp}]},
            upsert=True,
        )
    finally:
        await client.close()

    assert requests[0].method == "GET"
    assert requests[0].url.path == "/api/v1/mongodb/strategy_lifecycle_states"
    assert (
        requests[0].url.params["filter"]
        == '{"metadata": {"at": "2026-10-20T00:00:00+00:00"}}'
    )
    assert requests[0].url.params["fields"] == "strategy_id"
    assert requests[0].url.params["limit"] == "1"
    assert requests[1].method == "PUT"
    assert requests[1].url.path == "/api/v1/mongodb/strategy_lifecycle_states"
    assert b'"changed_at":"2026-10-20T00:00:00+00:00"' in requests[1].content
    assert b'"at":"2026-10-20T00:00:00+00:00"' in requests[1].content


@pytest.mark.asyncio
async def test_collection_mutation_routes_preserve_request_shapes(monkeypatch):
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"inserted_count": 1, "deleted_count": 1})

    async_client = httpx.AsyncClient

    def mock_async_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", mock_async_client)
    client = DataManagerClient("https://data-manager.test")
    try:
        await client.insert(
            database="mongodb", collection="strategy_config_audit", data={"event": "x"}
        )
        await client.delete(
            database="mongodb",
            collection="strategy_config_audit",
            filter={"event": "x"},
        )
    finally:
        await client.close()

    assert requests[0].method == "POST"
    assert requests[0].url.path == "/api/v1/mongodb/strategy_config_audit"
    assert requests[0].content == b'{"data":{"event":"x"}}'
    assert requests[1].method == "DELETE"
    assert requests[1].url.path == "/api/v1/mongodb/strategy_config_audit"
    assert requests[1].content == b'{"filter":{"event":"x"}}'


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result",
    [
        {"updated_count": 1, "upserted": False},
        {"updated_count": 0, "upserted": True},
    ],
)
async def test_strategy_upserts_accept_current_update_response_fields(result):
    client = StrategyClient("https://data-manager.test")
    client._client.update = AsyncMock(return_value=result)
    client._client.query = AsyncMock(return_value={"data": []})
    try:
        lifecycle = await client.upsert_lifecycle_state(
            "strategy", {"state": "running"}
        )
        global_config = await client.upsert_global_config("strategy", {}, {})
        symbol_config = await client.upsert_symbol_config("strategy", "BTCUSDT", {}, {})
    finally:
        await client.disconnect()

    assert lifecycle == "strategy"
    assert global_config == "strategy"
    assert symbol_config == "strategy:BTCUSDT"


@pytest.mark.asyncio
async def test_audit_insert_encodes_datetime_payload_at_collection_route(monkeypatch):
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200, json={"inserted_count": 1, "inserted_ids": ["audit"]}
        )

    async_client = httpx.AsyncClient

    def mock_async_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", mock_async_client)
    client = StrategyClient("https://data-manager.test")
    timestamp = datetime(2026, 10, 20, tzinfo=UTC)
    try:
        audit_id = await client.create_audit_record(
            {"strategy_id": "strategy", "metadata": {"reviewed_at": timestamp}}
        )
    finally:
        await client.disconnect()

    assert audit_id == "audit"
    assert requests[0].url.path == "/api/v1/mongodb/strategy_config_audit"
    assert b'"reviewed_at":"2026-10-20T00:00:00+00:00"' in requests[0].content


@pytest.mark.asyncio
async def test_audit_trail_encodes_sort_and_preserves_returned_order(monkeypatch):
    requests = []
    records = [{"changed_at": "new"}, {"changed_at": "old"}]

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": records})

    async_client = httpx.AsyncClient

    def mock_async_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", mock_async_client)
    client = StrategyClient("https://data-manager.test")
    try:
        result = await client.get_audit_trail("strategy", limit=2)
    finally:
        await client.disconnect()

    assert result == records
    assert requests[0].url.params["sort"] == '{"changed_at": -1}'


@pytest.mark.asyncio
async def test_post_encodes_nested_datetimes_without_mutating_input(monkeypatch):
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    async_client = httpx.AsyncClient

    def mock_async_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", mock_async_client)
    client = DataManagerClient("https://data-manager.test")
    timestamp = datetime(2026, 10, 20, tzinfo=UTC)
    payload = {"metadata": [{"at": timestamp}]}
    try:
        await client.post("/custom", json=payload)
    finally:
        await client.close()

    assert payload == {"metadata": [{"at": timestamp}]}
    assert b'"at":"2026-10-20T00:00:00+00:00"' in requests[0].content


@pytest.mark.asyncio
async def test_client_retries_http_5xx(monkeypatch):
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"ready": True})

    async_client = httpx.AsyncClient

    def mock_async_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", mock_async_client)
    client = DataManagerClient("https://data-manager.test", max_retries=3)
    try:
        result = await client.health()
    finally:
        await client.close()

    assert result["ready"] is True
    assert len(requests) == 2


@pytest.mark.asyncio
async def test_service_identity_defaults_when_name_is_unset(monkeypatch):
    monkeypatch.delenv("DM_SERVICE_NAME", raising=False)
    monkeypatch.setenv("DM_SERVICE_TOKEN", "test-token")
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"status": "ok"})

    async_client = httpx.AsyncClient

    def mock_async_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", mock_async_client)
    client = DataManagerClient("https://data-manager.test")
    try:
        await client.health()
    finally:
        await client.close()

    assert requests[0].headers["X-Petrosa-Service"] == "realtime-strategies"


@pytest.mark.asyncio
async def test_missing_token_warns_once_and_sends_only_service_identity(
    monkeypatch, caplog
):
    monkeypatch.delenv("DM_SERVICE_TOKEN", raising=False)
    monkeypatch.setenv("DM_SERVICE_NAME", "realtime-strategies-test")
    data_manager_module._missing_token_warning_emitted = False
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"status": "ok"})

    async_client = httpx.AsyncClient

    def mock_async_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", mock_async_client)
    with caplog.at_level(logging.WARNING, logger="data_manager_client"):
        client = DataManagerClient("https://data-manager.test")
        try:
            await client.health()
        finally:
            await client.close()
        second_client = DataManagerClient("https://data-manager.test")
        await second_client.close()

    assert requests[0].headers["X-Petrosa-Service"] == "realtime-strategies-test"
    assert "Authorization" not in requests[0].headers
    warnings = [
        record for record in caplog.records if record.levelno == logging.WARNING
    ]
    assert len(warnings) == 1
    assert "DM_SERVICE_TOKEN is unset" in warnings[0].message


@pytest.mark.asyncio
async def test_token_is_not_logged_or_repr(monkeypatch, caplog):
    token = "secret-token-never-log"
    monkeypatch.setenv("DM_SERVICE_TOKEN", token)
    data_manager_module._missing_token_warning_emitted = False

    with caplog.at_level(logging.DEBUG, logger="data_manager_client"):
        client = DataManagerClient("https://data-manager.test")
        try:
            assert token not in repr(client)
        finally:
            await client.close()

    assert token not in caplog.text
