"""
Comprehensive tests for config_routes.py FastAPI endpoints.

Covers all endpoints with success/error paths, validation, and edge cases.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from strategies.api.config_routes import get_config_manager, router, set_config_manager
from strategies.api.response_models import ConfigUpdateRequest
from strategies.services.config_manager import StrategyConfigManager


@pytest.fixture
def app():
    """Create FastAPI app with config routes."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_config_manager():
    """Create mock config manager."""
    manager = AsyncMock(spec=StrategyConfigManager)
    return manager


@pytest.fixture
def setup_config_manager(mock_config_manager):
    """Set the global config manager."""
    set_config_manager(mock_config_manager)
    yield mock_config_manager
    set_config_manager(None)


def test_get_config_manager_not_initialized():
    """Test get_config_manager raises 503 when not initialized."""
    set_config_manager(None)
    with pytest.raises(Exception) as exc_info:
        get_config_manager()
    assert "503" in str(exc_info.value)


def test_set_config_manager():
    """Test setting config manager."""
    manager = AsyncMock()
    set_config_manager(manager)
    assert get_config_manager() == manager


@pytest.mark.asyncio
async def test_list_strategies_success(client, setup_config_manager):
    """Test successful strategy listing."""
    mock_strategies = [
        {
            "strategy_id": "test_strategy",
            "name": "Test Strategy",
            "description": "A test strategy",
            "has_global_config": True,
            "symbol_overrides": ["BTCUSDT"],
            "parameter_count": 5,
        }
    ]
    setup_config_manager.list_strategies.return_value = mock_strategies

    response = client.get("/api/v1/strategies")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["data"]) == 1
    assert data["data"][0]["strategy_id"] == "test_strategy"
    assert data["metadata"]["total_count"] == 1


@pytest.mark.asyncio
async def test_list_strategies_error(client, setup_config_manager):
    """Test strategy listing with error."""
    setup_config_manager.list_strategies.side_effect = Exception("Database error")

    response = client.get("/api/v1/strategies")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "INTERNAL_ERROR"


@pytest.mark.asyncio
async def test_get_strategy_schema_success(client):
    """Test successful schema retrieval."""
    with patch(
        "strategies.api.config_routes.get_parameter_schema"
    ) as mock_schema, patch(
        "strategies.api.config_routes.get_strategy_defaults"
    ) as mock_defaults, patch(
        "strategies.api.config_routes.get_strategy_metadata"
    ) as mock_metadata:
        mock_defaults.return_value = {"param1": 10, "param2": "test"}
        mock_schema.return_value = {
            "param1": {
                "type": "int",
                "min": 1,
                "max": 100,
                "description": "Test param",
            },
            "param2": {"type": "str", "description": "String param"},
        }
        mock_metadata.return_value = {"name": "Test Strategy"}

        response = client.get("/api/v1/strategies/test_strategy/schema")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]) == 2
        assert data["data"][0]["name"] == "param1"
        assert data["data"][0]["type"] == "int"


@pytest.mark.asyncio
async def test_get_strategy_schema_not_found(client):
    """Test schema retrieval for non-existent strategy."""
    with patch("strategies.api.config_routes.get_strategy_defaults") as mock_defaults:
        mock_defaults.return_value = None

        response = client.get("/api/v1/strategies/nonexistent/schema")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_get_strategy_schema_error(client):
    """Test schema retrieval with error."""
    with patch("strategies.api.config_routes.get_parameter_schema") as mock_schema:
        mock_schema.side_effect = Exception("Schema error")

        response = client.get("/api/v1/strategies/test_strategy/schema")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "INTERNAL_ERROR"


@pytest.mark.asyncio
async def test_get_strategy_defaults_success(client):
    """Test successful defaults retrieval."""
    with patch(
        "strategies.api.config_routes.get_strategy_defaults"
    ) as mock_defaults, patch(
        "strategies.api.config_routes.get_strategy_metadata"
    ) as mock_metadata:
        mock_defaults.return_value = {"param1": 10, "param2": "test"}
        mock_metadata.return_value = {"name": "Test Strategy"}

        response = client.get("/api/v1/strategies/test_strategy/defaults")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["param1"] == 10
        assert data["metadata"]["strategy_name"] == "Test Strategy"


@pytest.mark.asyncio
async def test_get_strategy_defaults_not_found(client):
    """Test defaults retrieval for non-existent strategy."""
    with patch("strategies.api.config_routes.get_strategy_defaults") as mock_defaults:
        mock_defaults.return_value = None

        response = client.get("/api/v1/strategies/nonexistent/defaults")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_get_global_config_success(client, setup_config_manager):
    """Test successful global config retrieval."""
    mock_config = {
        "parameters": {"param1": 10},
        "version": 2,
        "source": "mongodb",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-02T00:00:00Z",
        "cache_hit": True,
        "load_time_ms": 5,
    }
    setup_config_manager.get_config.return_value = mock_config

    response = client.get("/api/v1/strategies/test_strategy/config")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["strategy_id"] == "test_strategy"
    assert data["data"]["parameters"]["param1"] == 10
    assert data["data"]["is_override"] is False


@pytest.mark.asyncio
async def test_get_symbol_config_success(client, setup_config_manager):
    """Test successful symbol config retrieval."""
    mock_config = {
        "parameters": {"param1": 15},
        "version": 1,
        "source": "mongodb",
        "is_override": True,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-02T00:00:00Z",
    }
    setup_config_manager.get_config.return_value = mock_config

    response = client.get("/api/v1/strategies/test_strategy/config/BTCUSDT")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["symbol"] == "BTCUSDT"
    assert data["data"]["is_override"] is True


@pytest.mark.asyncio
async def test_get_config_error(client, setup_config_manager):
    """Test config retrieval with error."""
    setup_config_manager.get_config.side_effect = Exception("Config error")

    response = client.get("/api/v1/strategies/test_strategy/config")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "INTERNAL_ERROR"


@pytest.mark.asyncio
async def test_update_global_config_success(client, setup_config_manager):
    """Test successful global config update."""
    mock_config = MagicMock()
    mock_config.strategy_id = "test_strategy"
    mock_config.parameters = {"param1": 20}
    mock_config.version = 2
    mock_config.created_at.isoformat.return_value = "2024-01-01T00:00:00Z"
    mock_config.updated_at.isoformat.return_value = "2024-01-02T00:00:00Z"

    setup_config_manager.set_config.return_value = (True, mock_config, [])

    request_data = {
        "parameters": {"param1": 20},
        "changed_by": "admin",
        "reason": "Test update",
        "validate_only": False,
    }

    response = client.post("/api/v1/strategies/test_strategy/config", json=request_data)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["strategy_id"] == "test_strategy"
    assert data["metadata"]["action"] == "updated"


@pytest.mark.asyncio
async def test_update_global_config_validation_error(client, setup_config_manager):
    """Test global config update with validation error."""
    setup_config_manager.set_config.return_value = (False, None, ["Invalid parameter"])

    request_data = {
        "parameters": {"invalid_param": "bad_value"},
        "changed_by": "admin",
        "validate_only": False,
    }

    response = client.post("/api/v1/strategies/test_strategy/config", json=request_data)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_update_global_config_validate_only(client, setup_config_manager):
    """Test global config update with validate_only=True."""
    setup_config_manager.set_config.return_value = (True, None, [])

    request_data = {
        "parameters": {"param1": 20},
        "changed_by": "admin",
        "validate_only": True,
    }

    response = client.post("/api/v1/strategies/test_strategy/config", json=request_data)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["metadata"]["validation"] == "passed"


@pytest.mark.asyncio
async def test_update_symbol_config_success(client, setup_config_manager):
    """Test successful symbol config update."""
    mock_config = MagicMock()
    mock_config.strategy_id = "test_strategy"
    mock_config.parameters = {"param1": 25}
    mock_config.version = 1
    mock_config.created_at.isoformat.return_value = "2024-01-01T00:00:00Z"
    mock_config.updated_at.isoformat.return_value = "2024-01-02T00:00:00Z"

    setup_config_manager.set_config.return_value = (True, mock_config, [])

    request_data = {
        "parameters": {"param1": 25},
        "changed_by": "admin",
        "reason": "Symbol-specific update",
    }

    response = client.post(
        "/api/v1/strategies/test_strategy/config/BTCUSDT", json=request_data
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["symbol"] == "BTCUSDT"
    assert data["data"]["is_override"] is True


@pytest.mark.asyncio
async def test_delete_global_config_success(client, setup_config_manager):
    """Test successful global config deletion."""
    setup_config_manager.delete_config.return_value = (True, [])

    response = client.delete(
        "/api/v1/strategies/test_strategy/config?changed_by=admin&reason=Cleanup"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "deleted successfully" in data["data"]["message"]


@pytest.mark.asyncio
async def test_delete_global_config_failure(client, setup_config_manager):
    """Test global config deletion failure."""
    setup_config_manager.delete_config.return_value = (False, ["Delete failed"])

    response = client.delete("/api/v1/strategies/test_strategy/config?changed_by=admin")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "DELETE_FAILED"


@pytest.mark.asyncio
async def test_delete_symbol_config_success(client, setup_config_manager):
    """Test successful symbol config deletion."""
    setup_config_manager.delete_config.return_value = (True, [])

    response = client.delete(
        "/api/v1/strategies/test_strategy/config/BTCUSDT?changed_by=admin"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["metadata"]["symbol"] == "BTCUSDT"


@pytest.mark.asyncio
async def test_get_audit_trail_success(client, setup_config_manager):
    """Test successful audit trail retrieval."""
    mock_record = MagicMock()
    mock_record.id = "audit_123"
    mock_record.strategy_id = "test_strategy"
    mock_record.symbol = "BTCUSDT"
    mock_record.action = "update"
    mock_record.old_parameters = {"param1": 10}
    mock_record.new_parameters = {"param1": 20}
    mock_record.changed_by = "admin"
    mock_record.changed_at.isoformat.return_value = "2024-01-01T00:00:00Z"
    mock_record.reason = "Test change"

    setup_config_manager.get_audit_trail.return_value = [mock_record]

    response = client.get("/api/v1/strategies/test_strategy/audit?limit=50")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["data"]) == 1
    assert data["data"][0]["strategy_id"] == "test_strategy"
    assert data["metadata"]["count"] == 1


@pytest.mark.asyncio
async def test_refresh_cache_success(client, setup_config_manager):
    """Test successful cache refresh."""
    setup_config_manager.refresh_cache.return_value = None

    response = client.post("/api/v1/strategies/cache/refresh")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "refreshed successfully" in data["data"]["message"]


@pytest.mark.asyncio
async def test_refresh_cache_error(client, setup_config_manager):
    """Test cache refresh with error."""
    setup_config_manager.refresh_cache.side_effect = Exception("Cache error")

    response = client.post("/api/v1/strategies/cache/refresh")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "INTERNAL_ERROR"


def test_config_update_request_model():
    """Test ConfigUpdateRequest model validation."""
    # Valid request
    request = ConfigUpdateRequest(
        parameters={"param1": 10},
        changed_by="admin",
        reason="Test",
        validate_only=False,
    )
    assert request.parameters == {"param1": 10}
    assert request.changed_by == "admin"
    assert request.reason == "Test"
    assert request.validate_only is False

    # Request with defaults
    request_defaults = ConfigUpdateRequest(
        parameters={"param1": 20}, changed_by="admin"
    )
    assert request_defaults.reason is None
    assert request_defaults.validate_only is False
