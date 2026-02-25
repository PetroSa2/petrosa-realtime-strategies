"""
Unit and integration tests for configuration rollback in Realtime Strategies.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from strategies.api.config_routes import router, set_config_manager
from strategies.models.strategy_config import StrategyConfig, StrategyConfigAudit
from strategies.services.config_manager import StrategyConfigManager


@pytest.fixture
def mock_mongodb_client():
    client = AsyncMock()
    client.is_connected = True
    client.use_data_manager = False
    client.database = MagicMock()
    return client


@pytest.fixture
def config_manager(mock_mongodb_client):
    return StrategyConfigManager(
        mongodb_client=mock_mongodb_client, cache_ttl_seconds=60
    )


@pytest.fixture
def client(config_manager):
    from fastapi import FastAPI

    app = FastAPI()
    # router already has prefix "/api/v1" defined in its declaration
    app.include_router(router)
    set_config_manager(config_manager)
    return TestClient(app)


@pytest.fixture
def sample_history():
    return [
        StrategyConfigAudit(
            id="audit_3",
            strategy_id="s1",
            action="UPDATE",
            old_parameters={"rsi": 14, "version": 2},
            new_parameters={"rsi": 21, "version": 3},
            changed_by="user1",
            changed_at=datetime.utcnow(),
        ),
        StrategyConfigAudit(
            id="audit_2",
            strategy_id="s1",
            action="UPDATE",
            old_parameters={"rsi": 10, "version": 1},
            new_parameters={"rsi": 14, "version": 2},
            changed_by="user1",
            changed_at=datetime.utcnow(),
        ),
        StrategyConfigAudit(
            id="audit_1",
            strategy_id="s1",
            action="CREATE",
            new_parameters={"rsi": 10, "version": 1},
            changed_by="user1",
            changed_at=datetime.utcnow(),
        ),
    ]


@pytest.mark.asyncio
class TestStrategyConfigRollback:
    async def test_get_previous_config(self, config_manager, sample_history):
        """Test getting the immediately preceding configuration."""
        with patch.object(
            config_manager, "get_audit_trail", return_value=sample_history
        ):
            prev_config = await config_manager.get_previous_config("s1")
            assert prev_config is not None
            assert prev_config["rsi"] == 14
            assert "version" not in prev_config  # Should be stripped

    async def test_get_config_by_version_optimized(
        self, config_manager, mock_mongodb_client
    ):
        """Test optimized version lookup using database query."""
        # 1. Setup mock cursor
        mock_cursor = MagicMock()
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.to_list = AsyncMock(
            return_value=[{"new_parameters": {"rsi": 10, "version": 1}}]
        )

        mock_mongodb_client.database.strategy_config_audit.find.return_value = (
            mock_cursor
        )

        # 2. Execute
        config = await config_manager.get_config_by_version("s1", 1)

        # 3. Verify
        assert config["rsi"] == 10
        assert "version" not in config  # Should be stripped
        mock_mongodb_client.database.strategy_config_audit.find.assert_called_with(
            {"strategy_id": "s1", "new_parameters.version": 1}
        )

    async def test_get_config_by_id_security(self, config_manager, sample_history):
        """Test configuration by ID lookup includes security filtering."""
        with patch.object(
            config_manager, "get_audit_trail", return_value=sample_history
        ):
            # Should find if it belongs to s1
            config = await config_manager.get_config_by_id("s1", "audit_2")
            assert config is not None
            assert config["rsi"] == 14

            # Explicit security check: found record MUST have matching strategy_id
            # (get_config_by_id checks this internally)
            with patch.object(
                config_manager,
                "get_audit_trail",
                return_value=[
                    StrategyConfigAudit(
                        id="audit_evil",
                        strategy_id="s2",
                        action="CREATE",
                        new_parameters={"rsi": 99, "version": 1},
                        changed_by="attacker",
                        changed_at=datetime.utcnow(),
                    )
                ],
            ):
                config = await config_manager.get_config_by_id("s1", "audit_evil")
                assert config is None

    async def test_rollback_success(self, config_manager, sample_history):
        """Test successful rollback execution."""
        with patch.object(
            config_manager, "get_audit_trail", return_value=sample_history
        ), patch.object(
            config_manager, "set_config", new_callable=AsyncMock
        ) as mock_set_config:
            mock_set_config.return_value = (True, MagicMock(spec=StrategyConfig), [])

            success, config, errors = await config_manager.rollback_config(
                strategy_id="s1", changed_by="admin"
            )

            assert success is True
            mock_set_config.assert_called_once()
            kwargs = mock_set_config.call_args[1]
            assert kwargs["parameters"]["rsi"] == 14
            assert "version" not in kwargs["parameters"]  # CRITICAL: Verify stripped

    async def test_rollback_invalid_version(self, config_manager):
        """Test rejection of invalid version numbers."""
        success, config, errors = await config_manager.rollback_config(
            strategy_id="s1", changed_by="admin", target_version=0
        )
        assert success is False
        assert "Invalid version number" in errors[0]

    async def test_rollback_rejects_cross_strategy_audit_id(self, config_manager):
        """Ensure rollback rejects audit IDs belonging to a different strategy."""
        # Mock audit trail returning an entry for a DIFFERENT strategy
        wrong_strategy_audit = StrategyConfigAudit(
            id="audit_s2",
            strategy_id="s2",
            action="CREATE",
            new_parameters={"rsi": 99, "version": 1},
            changed_by="tester",
            changed_at=datetime.utcnow(),
        )

        with patch.object(
            config_manager, "get_audit_trail", return_value=[wrong_strategy_audit]
        ):
            # Attempt to rollback s1 using an ID that belongs to s2
            success, config, errors = await config_manager.rollback_config(
                strategy_id="s1", changed_by="admin", rollback_id="audit_s2"
            )

            # Should fail with security error
            assert success is False
            assert "not found for strategy s1" in errors[0]


def test_rollback_api_integration(client, config_manager):
    """Test the rollback API endpoint."""
    with patch.object(
        config_manager, "rollback_config", new_callable=AsyncMock
    ) as mock_rollback:
        mock_rollback.return_value = (True, MagicMock(spec=StrategyConfig), [])

        payload = {
            "changed_by": "admin",
            "target_version": 2,
            "rollback_id": "audit_123",
            "reason": "API test",
        }
        # Endpoint is /api/v1/strategies/{strategy_id}/rollback
        response = client.post("/api/v1/strategies/s1/rollback", json=payload)

        assert response.status_code == 200
        mock_rollback.assert_called_once_with(
            strategy_id="s1",
            changed_by="admin",
            symbol=None,
            target_version=2,
            rollback_id="audit_123",
            reason="API test",
        )


def test_restore_api_alias(client, config_manager):
    """Test the restore API alias."""
    with patch.object(
        config_manager, "rollback_config", new_callable=AsyncMock
    ) as mock_rollback:
        mock_rollback.return_value = (True, MagicMock(spec=StrategyConfig), [])

        response = client.post(
            "/api/v1/strategies/s1/restore", json={"changed_by": "admin"}
        )

        assert response.status_code == 200
        mock_rollback.assert_called_once()
