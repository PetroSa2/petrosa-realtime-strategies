"""Regression coverage for the strategy lifecycle control surface."""

from datetime import UTC, datetime

import pytest

from strategies.services.config_manager import StrategyConfigManager


class FakeLifecycleMongo:
    """Small in-memory stand-in for the lifecycle collection."""

    is_connected = True

    def __init__(self):
        self.states = {}

    async def get_lifecycle_state(self, strategy_id):
        return self.states.get(strategy_id)

    async def upsert_lifecycle_state(self, strategy_id, state):
        self.states[strategy_id] = state
        return strategy_id

    async def get_global_config(self, strategy_id):
        return None


@pytest.mark.asyncio
async def test_pause_is_durable_and_reflected_by_enabled_alias():
    manager = StrategyConfigManager(FakeLifecycleMongo())

    success, state, retry_after = await manager.set_lifecycle_state(
        "iceberg_detector", "paused", "test", "maintenance"
    )
    config = await manager.get_config("iceberg_detector")

    assert success is True
    assert retry_after is None
    assert state["expires_at"] is None
    assert config["parameters"]["enabled"] is False


@pytest.mark.asyncio
async def test_pause_persists_cio_expiry():
    manager = StrategyConfigManager(FakeLifecycleMongo())
    expires_at = datetime(2030, 1, 1, tzinfo=UTC)

    success, state, retry_after = await manager.set_lifecycle_state(
        "iceberg_detector",
        "paused",
        "petrosa-cio:lifecycle:iceberg_detector",
        "CIO_PAUSE: pause it",
        expires_at,
    )

    assert success is True
    assert retry_after is None
    assert state["expires_at"] == expires_at
    assert manager.mongodb_client.states["iceberg_detector"]["expires_at"] == expires_at


@pytest.mark.asyncio
async def test_expired_pause_resumes_and_is_durable(caplog):
    manager = StrategyConfigManager(FakeLifecycleMongo())
    manager.mongodb_client.states["iceberg_detector"] = {
        "state": "paused",
        "reason": "CIO_PAUSE: pause it",
        "changed_at": datetime(2020, 1, 1, tzinfo=UTC),
        "expires_at": datetime(2020, 1, 1, 0, 30, tzinfo=UTC),
    }

    config = await manager.get_config("iceberg_detector")

    assert config["parameters"]["enabled"] is True
    assert manager.mongodb_client.states["iceberg_detector"]["state"] == "running"
    assert "LIFECYCLE_PAUSE_EXPIRED" in caplog.text


@pytest.mark.asyncio
async def test_newer_pause_wins_over_expired_pause():
    class NewerPauseMongo(FakeLifecycleMongo):
        def __init__(self):
            super().__init__()
            self.reads = 0

        async def get_lifecycle_state(self, strategy_id):
            self.reads += 1
            if self.reads == 1:
                return {
                    "state": "paused",
                    "changed_at": datetime(2020, 1, 1, tzinfo=UTC),
                    "expires_at": datetime(2020, 1, 1, 0, 30, tzinfo=UTC),
                }
            return {
                "state": "paused",
                "changed_at": datetime(2020, 1, 1, 0, 45, tzinfo=UTC),
                "expires_at": datetime(2020, 1, 1, 1, 15, tzinfo=UTC),
            }

    manager = StrategyConfigManager(NewerPauseMongo())

    config = await manager.get_config("iceberg_detector")

    assert config["parameters"]["enabled"] is False
    assert manager.mongodb_client.reads == 2


@pytest.mark.asyncio
async def test_resume_is_throttled_inside_configured_window():
    manager = StrategyConfigManager(FakeLifecycleMongo())
    manager.resume_cooldown_seconds = 60

    first, _, first_retry = await manager.set_lifecycle_state(
        "iceberg_detector", "running", "test"
    )
    second, _, retry_after = await manager.set_lifecycle_state(
        "iceberg_detector", "running", "test"
    )

    assert first is True
    assert first_retry is None
    assert second is False
    assert retry_after is not None
    assert retry_after <= 60


@pytest.mark.asyncio
async def test_pause_is_not_throttled_after_parameter_lifecycle_change():
    manager = StrategyConfigManager(FakeLifecycleMongo())
    now = datetime.now(UTC)
    manager.mongodb_client.states["iceberg_detector"] = {
        "state": "running",
        "changed_at": now,
    }

    success, _, retry_after = await manager.set_lifecycle_state(
        "iceberg_detector", "paused", "petrosa-cio:config"
    )

    assert success is True
    assert retry_after is None
