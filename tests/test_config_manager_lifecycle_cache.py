import time
from unittest.mock import AsyncMock

import pytest

from strategies.services.config_manager import StrategyConfigManager


class LifecycleStore:
    is_connected = True

    def __init__(self, state):
        self.get_lifecycle_state = AsyncMock(return_value=state)
        self.get_global_config = AsyncMock(return_value=None)

    async def ensure_connected(self):
        return True


@pytest.mark.asyncio
async def test_lifecycle_state_is_cached_for_the_config_ttl():
    store = LifecycleStore({"strategy_id": "btc_dominance", "state": "paused"})
    manager = StrategyConfigManager(store, cache_ttl_seconds=60)

    first = await manager.get_lifecycle_state("btc_dominance")
    second = await manager.get_lifecycle_state("btc_dominance")

    assert first == second
    store.get_lifecycle_state.assert_awaited_once_with("btc_dominance")


@pytest.mark.asyncio
async def test_unavailable_lifecycle_state_is_cached_for_the_config_ttl():
    store = LifecycleStore(None)
    manager = StrategyConfigManager(store, cache_ttl_seconds=60)

    assert await manager.get_lifecycle_state("btc_dominance") is None
    assert await manager.get_lifecycle_state("btc_dominance") is None

    store.get_lifecycle_state.assert_awaited_once_with("btc_dominance")


@pytest.mark.asyncio
async def test_lifecycle_lookup_failure_is_cached_for_the_config_ttl():
    store = LifecycleStore(None)
    store.get_lifecycle_state.side_effect = RuntimeError("422")
    manager = StrategyConfigManager(store, cache_ttl_seconds=60)

    assert await manager.get_lifecycle_state("btc_dominance") is None
    assert await manager.get_lifecycle_state("btc_dominance") is None

    store.get_lifecycle_state.assert_awaited_once_with("btc_dominance")


@pytest.mark.asyncio
async def test_lifecycle_state_refreshes_after_the_config_ttl():
    store = LifecycleStore({"strategy_id": "btc_dominance", "state": "running"})
    manager = StrategyConfigManager(store, cache_ttl_seconds=60)

    await manager.get_lifecycle_state("btc_dominance")
    manager._lifecycle_cache["btc_dominance"] = (None, time.time() - 61)
    await manager.get_lifecycle_state("btc_dominance")

    assert store.get_lifecycle_state.await_count == 2


@pytest.mark.asyncio
async def test_config_lookup_reuses_cached_lifecycle_state():
    store = LifecycleStore({"strategy_id": "btc_dominance", "state": "paused"})
    manager = StrategyConfigManager(store, cache_ttl_seconds=60)

    first = await manager.get_config("btc_dominance")
    second = await manager.get_config("btc_dominance")

    assert first["parameters"]["enabled"] is False
    assert second["parameters"]["enabled"] is False
    store.get_lifecycle_state.assert_awaited_once_with("btc_dominance")


def test_lifecycle_cache_has_a_fixed_capacity():
    manager = StrategyConfigManager(cache_ttl_seconds=60)

    for index in range(1025):
        manager._set_lifecycle_cache(str(index), None)

    assert len(manager._lifecycle_cache) == 1024
    assert "0" not in manager._lifecycle_cache
