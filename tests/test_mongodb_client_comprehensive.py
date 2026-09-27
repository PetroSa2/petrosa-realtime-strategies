"""Tests for the data-manager-only configuration facade."""

import importlib
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest


def test_import_fails_when_data_manager_client_is_unavailable(monkeypatch):
    """A missing data-manager client must not activate a Mongo fallback."""
    import strategies.db.mongodb_client as module

    monkeypatch.setitem(sys.modules, "strategies.services.data_manager_client", None)
    with pytest.raises(ImportError):
        importlib.reload(module)
    importlib.reload(module)


@pytest.mark.asyncio
async def test_facade_delegates_to_data_manager(monkeypatch):
    from strategies.db import mongodb_client

    client = mongodb_client.MongoDBClient()
    client.data_manager_client = MagicMock()
    client.data_manager_client.connect = AsyncMock()
    client.data_manager_client.get_global_config = AsyncMock(return_value={"version": 1})

    assert await client.connect() is True
    assert await client.get_global_config("strategy") == {"version": 1}
    assert client.use_data_manager is True
    client.data_manager_client.connect.assert_awaited_once()


@pytest.mark.asyncio
async def test_connect_failure_is_degraded(monkeypatch):
    from strategies.db.mongodb_client import MongoDBClient

    client = MongoDBClient()
    client.data_manager_client.connect = AsyncMock(side_effect=RuntimeError("down"))

    assert await client.connect() is False
    assert client.is_connected is False
