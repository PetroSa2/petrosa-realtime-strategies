"""
Tests for configuration rollback in Realtime Strategies.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
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
    # Setup
    mock_mongodb_client.data_manager_client.rollback_strategy_config.return_value = True
    
    manager = StrategyConfigManager(mongodb_client=mock_mongodb_client)
    # Mock get_config
    manager.get_config = AsyncMock(return_value={"parameters": {"threshold": 1.5}})
    
    # Execute
    success, config, errors = await manager.rollback_config("orderbook_skew", "admin")
    
    # Verify
    assert success is True
    assert config.strategy_id == "orderbook_skew"
    mock_mongodb_client.data_manager_client.rollback_strategy_config.assert_called_once()
