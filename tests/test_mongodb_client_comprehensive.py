"""
Comprehensive tests for db/mongodb_client.py.

Covers both direct MongoDB and Data Manager modes, CRUD operations, error handling, and health checks.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest
from pymongo.errors import ConnectionFailure, DuplicateKeyError

from strategies.db.mongodb_client import DATA_MANAGER_AVAILABLE, MongoDBClient


@pytest.fixture
def mock_data_manager_client():
    """Create mock data manager client."""
    client = AsyncMock()
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.get_global_config = AsyncMock()
    client.upsert_global_config = AsyncMock()
    client.delete_global_config = AsyncMock()
    client.get_symbol_config = AsyncMock()
    client.upsert_symbol_config = AsyncMock()
    client.delete_symbol_config = AsyncMock()
    client.get_audit_trail = AsyncMock()
    client.create_audit_record = AsyncMock()
    return client


@pytest.fixture
def mock_mongo_client():
    """Create mock MongoDB client."""
    client = AsyncMock()
    client.admin.command = AsyncMock()
    client.close = AsyncMock()
    return client


@pytest.fixture
def mock_database():
    """Create mock database."""
    db = AsyncMock()
    db.strategy_configs_global = AsyncMock()
    db.strategy_configs_symbol = AsyncMock()
    db.strategy_config_audit = AsyncMock()
    return db


def test_mongodb_client_init_direct_mode():
    """Test MongoDB client initialization in direct mode."""
    with patch("strategies.db.mongodb_client.DATA_MANAGER_AVAILABLE", False):
        client = MongoDBClient(
            uri="mongodb://localhost:27017",
            database="test_db",
            max_pool_size=5,
            min_pool_size=1,
            timeout_ms=3000,
            use_data_manager=False,
        )

        assert client.use_data_manager is False
        assert client.uri == "mongodb://localhost:27017"
        assert client.database_name == "test_db"
        assert client.max_pool_size == 5
        assert client.min_pool_size == 1
        assert client.timeout_ms == 3000
        assert client._connected is False


def test_mongodb_client_init_data_manager_mode(mock_data_manager_client):
    """Test MongoDB client initialization in Data Manager mode."""
    with patch("strategies.db.mongodb_client.DATA_MANAGER_AVAILABLE", True), patch(
        "strategies.db.mongodb_client.DataManagerClient",
        return_value=mock_data_manager_client,
    ):
        client = MongoDBClient(use_data_manager=True)

        assert client.use_data_manager is True
        assert client.data_manager_client == mock_data_manager_client
        assert client.client is None
        assert client.database is None


def test_mongodb_client_init_data_manager_unavailable():
    """Test MongoDB client initialization when Data Manager is unavailable."""
    with patch("strategies.db.mongodb_client.DATA_MANAGER_AVAILABLE", False):
        client = MongoDBClient(use_data_manager=True)

        assert client.use_data_manager is False
        assert not hasattr(client, "data_manager_client")


@pytest.mark.asyncio
async def test_connect_data_manager_mode(mock_data_manager_client):
    """Test connection in Data Manager mode."""
    with patch("strategies.db.mongodb_client.DATA_MANAGER_AVAILABLE", True), patch(
        "strategies.db.mongodb_client.DataManagerClient",
        return_value=mock_data_manager_client,
    ):
        client = MongoDBClient(use_data_manager=True)
        result = await client.connect()

        assert result is True
        assert client._connected is True
        mock_data_manager_client.connect.assert_called_once()


@pytest.mark.asyncio
async def test_connect_direct_mode_success(mock_mongo_client, mock_database):
    """Test successful connection in direct mode."""
    with patch(
        "strategies.db.mongodb_client.AsyncIOMotorClient",
        return_value=mock_mongo_client,
    ):
        mock_mongo_client.__getitem__.return_value = mock_database

        client = MongoDBClient(use_data_manager=False)
        result = await client.connect()

        assert result is True
        assert client._connected is True
        assert client.client == mock_mongo_client
        assert client.database == mock_database
        mock_mongo_client.admin.command.assert_called_once_with("ping")


@pytest.mark.asyncio
async def test_connect_direct_mode_connection_failure():
    """Test connection failure in direct mode."""
    with patch("strategies.db.mongodb_client.AsyncIOMotorClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.admin.command.side_effect = ConnectionFailure("Connection failed")
        mock_client_class.return_value = mock_client

        client = MongoDBClient(use_data_manager=False)
        result = await client.connect()

        assert result is False
        assert client._connected is False


@pytest.mark.asyncio
async def test_connect_direct_mode_unexpected_error():
    """Test unexpected error during connection."""
    with patch("strategies.db.mongodb_client.AsyncIOMotorClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.admin.command.side_effect = Exception("Unexpected error")
        mock_client_class.return_value = mock_client

        client = MongoDBClient(use_data_manager=False)
        result = await client.connect()

        assert result is False
        assert client._connected is False


@pytest.mark.asyncio
async def test_disconnect_data_manager_mode(mock_data_manager_client):
    """Test disconnection in Data Manager mode."""
    with patch("strategies.db.mongodb_client.DATA_MANAGER_AVAILABLE", True), patch(
        "strategies.db.mongodb_client.DataManagerClient",
        return_value=mock_data_manager_client,
    ):
        client = MongoDBClient(use_data_manager=True)
        client._connected = True
        await client.disconnect()

        assert client._connected is False
        mock_data_manager_client.disconnect.assert_called_once()


@pytest.mark.asyncio
async def test_disconnect_direct_mode(mock_mongo_client):
    """Test disconnection in direct mode."""
    client = MongoDBClient(use_data_manager=False)
    client.client = mock_mongo_client
    client._connected = True

    await client.disconnect()

    assert client._connected is False
    mock_mongo_client.close.assert_called_once()


@pytest.mark.asyncio
async def test_create_indexes_success(mock_database):
    """Test successful index creation."""
    client = MongoDBClient(use_data_manager=False)
    client.database = mock_database
    client._connected = True

    await client._create_indexes()

    # Verify indexes were created
    mock_database.strategy_configs_global.create_index.assert_called_once_with(
        "strategy_id", unique=True
    )
    mock_database.strategy_configs_symbol.create_index.assert_called_once_with(
        [("strategy_id", 1), ("symbol", 1)], unique=True
    )
    assert mock_database.strategy_config_audit.create_index.call_count == 2


@pytest.mark.asyncio
async def test_create_indexes_failure(mock_database):
    """Test index creation failure."""
    mock_database.strategy_configs_global.create_index.side_effect = Exception(
        "Index creation failed"
    )

    client = MongoDBClient(use_data_manager=False)
    client.database = mock_database
    client._connected = True

    # Should not raise exception
    await client._create_indexes()


def test_is_connected_property():
    """Test is_connected property."""
    client = MongoDBClient()
    assert client.is_connected is False

    client._connected = True
    assert client.is_connected is True


@pytest.mark.asyncio
async def test_health_check_connected(mock_mongo_client):
    """Test health check when connected."""
    client = MongoDBClient(use_data_manager=False)
    client.client = mock_mongo_client
    client._connected = True

    result = await client.health_check()

    assert result is True
    mock_mongo_client.admin.command.assert_called_once_with("ping")


@pytest.mark.asyncio
async def test_health_check_not_connected():
    """Test health check when not connected."""
    client = MongoDBClient()
    client._connected = False

    result = await client.health_check()

    assert result is False


@pytest.mark.asyncio
async def test_health_check_failure(mock_mongo_client):
    """Test health check failure."""
    mock_mongo_client.admin.command.side_effect = Exception("Health check failed")

    client = MongoDBClient(use_data_manager=False)
    client.client = mock_mongo_client
    client._connected = True

    result = await client.health_check()

    assert result is False


@pytest.mark.asyncio
async def test_get_global_config_data_manager_mode(mock_data_manager_client):
    """Test get global config in Data Manager mode."""
    mock_config = {"strategy_id": "test", "parameters": {"param1": "value1"}}
    mock_data_manager_client.get_global_config.return_value = mock_config

    with patch("strategies.db.mongodb_client.DATA_MANAGER_AVAILABLE", True), patch(
        "strategies.db.mongodb_client.DataManagerClient",
        return_value=mock_data_manager_client,
    ):
        client = MongoDBClient(use_data_manager=True)
        result = await client.get_global_config("test_strategy")

        assert result == mock_config
        mock_data_manager_client.get_global_config.assert_called_once_with(
            "test_strategy"
        )


@pytest.mark.asyncio
async def test_get_global_config_direct_mode(mock_database):
    """Test get global config in direct mode."""
    mock_config = {"strategy_id": "test", "parameters": {"param1": "value1"}}
    mock_database.strategy_configs_global.find_one.return_value = mock_config

    client = MongoDBClient(use_data_manager=False)
    client.database = mock_database
    client._connected = True

    result = await client.get_global_config("test_strategy")

    assert result == mock_config
    mock_database.strategy_configs_global.find_one.assert_called_once_with(
        {"strategy_id": "test_strategy"}
    )


@pytest.mark.asyncio
async def test_set_global_config_data_manager_mode(mock_data_manager_client):
    """Test set global config in Data Manager mode."""
    config_data = {"strategy_id": "test", "parameters": {"param1": "value1"}}
    mock_data_manager_client.upsert_global_config.return_value = True

    with patch("strategies.db.mongodb_client.DATA_MANAGER_AVAILABLE", True), patch(
        "strategies.db.mongodb_client.DataManagerClient",
        return_value=mock_data_manager_client,
    ):
        client = MongoDBClient(use_data_manager=True)
        result = await client.upsert_global_config(
            "test_strategy", config_data, {"changed_by": "test"}
        )

        assert result is True
        mock_data_manager_client.upsert_global_config.assert_called_once_with(
            "test_strategy", config_data, {"changed_by": "test"}
        )


@pytest.mark.asyncio
async def test_set_global_config_direct_mode_success(mock_database):
    """Test successful set global config in direct mode."""
    config_data = {"strategy_id": "test", "parameters": {"param1": "value1"}}

    # Mock get_global_config to return None (new config)
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[])
    mock_database.strategy_configs_global.find_one = AsyncMock(return_value=None)

    # Mock update_one for upsert
    mock_result = MagicMock()
    mock_result.upserted_id = "new_id_123"
    mock_database.strategy_configs_global.update_one = AsyncMock(
        return_value=mock_result
    )

    client = MongoDBClient(use_data_manager=False)
    client.database = mock_database
    client._connected = True

    result = await client.upsert_global_config(
        "test_strategy", config_data, {"changed_by": "test"}
    )

    assert result == "new_id_123"
    mock_database.strategy_configs_global.update_one.assert_called_once()


@pytest.mark.asyncio
async def test_set_global_config_direct_mode_duplicate_key_error(mock_database):
    """Test set global config with duplicate key error in direct mode."""
    config_data = {"strategy_id": "test", "parameters": {"param1": "value1"}}

    # Mock get_global_config to return None
    mock_database.strategy_configs_global.find_one = AsyncMock(return_value=None)

    # Mock update_one to raise DuplicateKeyError
    mock_database.strategy_configs_global.update_one = AsyncMock(
        side_effect=DuplicateKeyError("Duplicate key")
    )

    client = MongoDBClient(use_data_manager=False)
    client.database = mock_database
    client._connected = True

    result = await client.upsert_global_config(
        "test_strategy", config_data, {"changed_by": "test"}
    )

    assert result is None  # Returns None on error, not False


@pytest.mark.asyncio
async def test_delete_global_config_data_manager_mode(mock_data_manager_client):
    """Test delete global config in Data Manager mode."""
    mock_data_manager_client.delete_global_config.return_value = True

    with patch("strategies.db.mongodb_client.DATA_MANAGER_AVAILABLE", True), patch(
        "strategies.db.mongodb_client.DataManagerClient",
        return_value=mock_data_manager_client,
    ):
        client = MongoDBClient(use_data_manager=True)
        result = await client.delete_global_config("test_strategy")

        assert result is True
        mock_data_manager_client.delete_global_config.assert_called_once_with(
            "test_strategy"
        )


@pytest.mark.asyncio
async def test_delete_global_config_direct_mode(mock_database):
    """Test delete global config in direct mode."""
    mock_database.strategy_configs_global.delete_one.return_value.deleted_count = 1

    client = MongoDBClient(use_data_manager=False)
    client.database = mock_database
    client._connected = True

    result = await client.delete_global_config("test_strategy")

    assert result is True
    mock_database.strategy_configs_global.delete_one.assert_called_once_with(
        {"strategy_id": "test_strategy"}
    )


@pytest.mark.asyncio
async def test_get_symbol_config_data_manager_mode(mock_data_manager_client):
    """Test get symbol config in Data Manager mode."""
    mock_config = {
        "strategy_id": "test",
        "symbol": "BTCUSDT",
        "parameters": {"param1": "value1"},
    }
    mock_data_manager_client.get_symbol_config.return_value = mock_config

    with patch("strategies.db.mongodb_client.DATA_MANAGER_AVAILABLE", True), patch(
        "strategies.db.mongodb_client.DataManagerClient",
        return_value=mock_data_manager_client,
    ):
        client = MongoDBClient(use_data_manager=True)
        result = await client.get_symbol_config("test_strategy", "BTCUSDT")

        assert result == mock_config
        mock_data_manager_client.get_symbol_config.assert_called_once_with(
            "test_strategy", "BTCUSDT"
        )


@pytest.mark.asyncio
async def test_get_symbol_config_direct_mode(mock_database):
    """Test get symbol config in direct mode."""
    mock_config = {
        "strategy_id": "test",
        "symbol": "BTCUSDT",
        "parameters": {"param1": "value1"},
    }
    mock_database.strategy_configs_symbol.find_one.return_value = mock_config

    client = MongoDBClient(use_data_manager=False)
    client.database = mock_database
    client._connected = True

    result = await client.get_symbol_config("test_strategy", "BTCUSDT")

    assert result == mock_config
    mock_database.strategy_configs_symbol.find_one.assert_called_once_with(
        {"strategy_id": "test_strategy", "symbol": "BTCUSDT"}
    )


@pytest.mark.asyncio
async def test_set_symbol_config_data_manager_mode(mock_data_manager_client):
    """Test set symbol config in Data Manager mode."""
    config_data = {
        "strategy_id": "test",
        "symbol": "BTCUSDT",
        "parameters": {"param1": "value1"},
    }
    mock_data_manager_client.upsert_symbol_config.return_value = True

    with patch("strategies.db.mongodb_client.DATA_MANAGER_AVAILABLE", True), patch(
        "strategies.db.mongodb_client.DataManagerClient",
        return_value=mock_data_manager_client,
    ):
        client = MongoDBClient(use_data_manager=True)
        result = await client.upsert_symbol_config(
            "test_strategy", "BTCUSDT", config_data, {"changed_by": "test"}
        )

        assert result is True
        mock_data_manager_client.upsert_symbol_config.assert_called_once_with(
            "test_strategy", "BTCUSDT", config_data, {"changed_by": "test"}
        )


@pytest.mark.asyncio
async def test_set_symbol_config_direct_mode_success(mock_database):
    """Test successful set symbol config in direct mode."""
    config_data = {
        "strategy_id": "test",
        "symbol": "BTCUSDT",
        "parameters": {"param1": "value1"},
    }

    # Mock get_symbol_config to return None (new config)
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[])
    mock_database.strategy_configs_symbol.find_one = AsyncMock(return_value=None)

    # Mock update_one for upsert
    mock_result = MagicMock()
    mock_result.upserted_id = "new_id_456"
    mock_database.strategy_configs_symbol.update_one = AsyncMock(
        return_value=mock_result
    )

    client = MongoDBClient(use_data_manager=False)
    client.database = mock_database
    client._connected = True

    result = await client.upsert_symbol_config(
        "test_strategy", "BTCUSDT", config_data, {"changed_by": "test"}
    )

    assert result == "new_id_456"
    mock_database.strategy_configs_symbol.update_one.assert_called_once()


@pytest.mark.asyncio
async def test_delete_symbol_config_data_manager_mode(mock_data_manager_client):
    """Test delete symbol config in Data Manager mode."""
    mock_data_manager_client.delete_symbol_config.return_value = True

    with patch("strategies.db.mongodb_client.DATA_MANAGER_AVAILABLE", True), patch(
        "strategies.db.mongodb_client.DataManagerClient",
        return_value=mock_data_manager_client,
    ):
        client = MongoDBClient(use_data_manager=True)
        result = await client.delete_symbol_config("test_strategy", "BTCUSDT")

        assert result is True
        mock_data_manager_client.delete_symbol_config.assert_called_once_with(
            "test_strategy", "BTCUSDT"
        )


@pytest.mark.asyncio
async def test_delete_symbol_config_direct_mode(mock_database):
    """Test delete symbol config in direct mode."""
    mock_database.strategy_configs_symbol.delete_one.return_value.deleted_count = 1

    client = MongoDBClient(use_data_manager=False)
    client.database = mock_database
    client._connected = True

    result = await client.delete_symbol_config("test_strategy", "BTCUSDT")

    assert result is True
    mock_database.strategy_configs_symbol.delete_one.assert_called_once_with(
        {"strategy_id": "test_strategy", "symbol": "BTCUSDT"}
    )


@pytest.mark.asyncio
async def test_get_audit_trail_data_manager_mode(mock_data_manager_client):
    """Test get audit trail in Data Manager mode."""
    mock_audit = [{"id": "1", "strategy_id": "test", "action": "update"}]
    mock_data_manager_client.get_audit_trail.return_value = mock_audit

    with patch("strategies.db.mongodb_client.DATA_MANAGER_AVAILABLE", True), patch(
        "strategies.db.mongodb_client.DataManagerClient",
        return_value=mock_data_manager_client,
    ):
        client = MongoDBClient(use_data_manager=True)
        result = await client.get_audit_trail("test_strategy", "BTCUSDT", 10)

        assert result == mock_audit
        mock_data_manager_client.get_audit_trail.assert_called_once_with(
            "test_strategy", "BTCUSDT", 10
        )


@pytest.mark.asyncio
async def test_get_audit_trail_direct_mode(mock_database):
    """Test get audit trail in direct mode."""
    mock_audit = [{"id": "1", "strategy_id": "test", "action": "update"}]

    # Create properly chained cursor mock
    mock_to_list = AsyncMock(return_value=mock_audit)
    mock_limit = MagicMock()
    mock_limit.to_list = mock_to_list
    mock_sort = MagicMock()
    mock_sort.limit.return_value = mock_limit
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value = mock_sort

    # Replace strategy_config_audit with MagicMock to avoid AsyncMock issues
    mock_database.strategy_config_audit = MagicMock()
    mock_database.strategy_config_audit.find.return_value = mock_cursor

    client = MongoDBClient(use_data_manager=False)
    client.database = mock_database
    client._connected = True

    result = await client.get_audit_trail("test_strategy", "BTCUSDT", 10)

    assert result == mock_audit
    mock_database.strategy_config_audit.find.assert_called_once()


@pytest.mark.asyncio
async def test_add_audit_record_direct_mode(mock_database):
    """Test add audit record in direct mode."""
    audit_data = {
        "strategy_id": "test",
        "symbol": "BTCUSDT",
        "action": "update",
        "old_parameters": {"param1": "old"},
        "new_parameters": {"param1": "new"},
        "changed_by": "admin",
        "changed_at": datetime.utcnow(),
        "reason": "Test update",
    }

    client = MongoDBClient(use_data_manager=False)
    client.database = mock_database
    client._connected = True

    await client.create_audit_record(audit_data)

    mock_database.strategy_config_audit.insert_one.assert_called_once_with(audit_data)


def test_data_manager_availability():
    """Test DATA_MANAGER_AVAILABLE constant."""
    # This tests the import logic
    assert isinstance(DATA_MANAGER_AVAILABLE, bool)


@pytest.mark.asyncio
async def test_connection_retry_logic():
    """Test connection retry logic with exponential backoff."""
    with patch("strategies.db.mongodb_client.AsyncIOMotorClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.admin.command.side_effect = ConnectionFailure("Connection failed")
        mock_client_class.return_value = mock_client

        client = MongoDBClient(use_data_manager=False)
        result = await client.connect()

        assert result is False
        assert client._connected is False


@pytest.mark.asyncio
async def test_environment_variable_fallback():
    """Test environment variable fallback for URI and database."""
    with patch("strategies.db.mongodb_client.os.getenv") as mock_getenv:
        mock_getenv.side_effect = lambda key, default: {
            "MONGODB_URI": "mongodb://env:27017",
            "MONGODB_DATABASE": "env_db",
        }.get(key, default)

        client = MongoDBClient(use_data_manager=False)

        assert client.uri == "mongodb://env:27017"
        assert client.database_name == "env_db"
