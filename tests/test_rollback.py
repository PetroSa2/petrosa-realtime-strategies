"""
Tests for configuration rollback in Realtime Strategies.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from strategies.models.strategy_config import StrategyConfig
from strategies.services.config_manager import StrategyConfigManager


@pytest.fixture
def mock_mongodb_client():
    client = MagicMock()
    client.is_connected = True
    client.use_data_manager = True
    client.data_manager_client = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_strategy_config_rollback(mock_mongodb_client):
    """Test strategy config rollback using the new implementation."""
    # 1. Setup
    manager = StrategyConfigManager(mongodb_client=mock_mongodb_client)

    # Mock get_audit_trail to return sample history
    mock_audit = MagicMock()
    mock_audit.action = "UPDATE"
    mock_audit.old_parameters = {"rsi": 14, "version": 2}
    mock_audit.new_parameters = {"rsi": 21, "version": 3}

    # 2. Mock necessary methods
    with patch.object(
        manager, "get_audit_trail", new_callable=AsyncMock
    ) as mock_get_audit:
        mock_get_audit.return_value = [mock_audit]

        with patch.object(
            manager, "set_config", new_callable=AsyncMock
        ) as mock_set_config:
            mock_set_config.return_value = (True, MagicMock(spec=StrategyConfig), [])

            # 3. Execute
            success, config, errors = await manager.rollback_config("rsi_bot", "admin")

            # 4. Verify
            assert success is True
            mock_set_config.assert_called_once()
            kwargs = mock_set_config.call_args[1]
            assert kwargs["parameters"]["rsi"] == 14
