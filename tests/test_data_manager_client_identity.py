import logging

import httpx
import pytest

import data_manager_client as data_manager_module
from data_manager_client import DataManagerClient


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
