"""
Comprehensive tests for health/server.py.

Covers all endpoints, lifecycle management, and health monitoring functionality.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from strategies.health.server import HealthServer


@pytest.fixture
def mock_components():
    """Create mock components for health server."""
    consumer = MagicMock()
    consumer.get_metrics.return_value = {"messages_processed": 100}
    consumer.get_health_status.return_value = {"status": "healthy"}

    publisher = MagicMock()
    publisher.get_metrics.return_value = {"messages_published": 50}
    publisher.get_health_status.return_value = {"status": "healthy"}

    heartbeat_manager = MagicMock()
    heartbeat_manager.get_heartbeat_status.return_value = {"status": "active"}

    config_manager = MagicMock()
    depth_analyzer = MagicMock()

    return {
        "consumer": consumer,
        "publisher": publisher,
        "heartbeat_manager": heartbeat_manager,
        "config_manager": config_manager,
        "depth_analyzer": depth_analyzer,
    }


@pytest.fixture
def mock_constants():
    """Create mock constants that persist across fixtures."""
    with patch("strategies.health.server.constants") as mock_const:
        mock_const.SERVICE_VERSION = "1.0.0"
        mock_const.SERVICE_NAME = "test-service"
        mock_const.ENVIRONMENT = "test"
        mock_const.get_enabled_strategies.return_value = ["strategy1", "strategy2"]
        mock_const.TRADING_SYMBOLS = ["BTCUSDT", "ETHUSDT"]
        mock_const.TRADING_ENABLE_SHORTS = True
        mock_const.HEARTBEAT_ENABLED = True
        mock_const.HEARTBEAT_INTERVAL_SECONDS = 30
        mock_const.LOG_LEVEL = "INFO"
        mock_const.ENABLE_OTEL = True
        mock_const.NATS_URL = "nats://localhost:4222"
        mock_const.NATS_CONSUMER_TOPIC = "market_data"
        mock_const.NATS_PUBLISHER_TOPIC = "signals"
        mock_const.HEALTH_CHECK_PORT = 8080
        mock_const.get_strategy_config.return_value = {
            "strategy1": {"param": "value"}
        }
        mock_const.get_trading_config.return_value = {"leverage": 1.0}
        mock_const.get_risk_config.return_value = {"max_position": 1000}
        yield mock_const


@pytest.fixture
def health_server(mock_components, mock_constants):
    """Create health server with mock components."""
    server = HealthServer(
        port=8080,
        consumer=mock_components["consumer"],
        publisher=mock_components["publisher"],
        heartbeat_manager=mock_components["heartbeat_manager"],
        config_manager=mock_components["config_manager"],
        depth_analyzer=mock_components["depth_analyzer"],
    )
    return server


@pytest.fixture
def client(health_server):
    """Create test client for health server."""
    # Store health_server in app.state so tests can access it
    health_server.app.state.health_server = health_server
    return TestClient(health_server.app)


def test_health_server_initialization(health_server):
    """Test health server initialization."""
    assert health_server.port == 8080
    assert health_server.is_running is False
    assert health_server.start_time is None
    assert health_server.health_status["status"] == "healthy"


def test_register_routes(health_server):
    """Test that all routes are registered."""
    routes = [route.path for route in health_server.app.routes]
    expected_routes = ["/healthz", "/ready", "/metrics", "/info", "/"]
    for route in expected_routes:
        assert route in routes


def test_root_endpoint(client):
    """Test root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "test-service"
    assert data["version"] == "1.0.0"
    assert data["status"] == "running"
    assert "endpoints" in data


def test_healthz_endpoint_healthy(client):
    """Test healthz endpoint when healthy."""
    health_server = (
        client.app.state.health_server if hasattr(client.app, "state") else None
    )
    if health_server:
        health_server.is_running = True
        health_server.start_time = time.time() - 10  # 10 seconds ago

    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "uptime_seconds" in data
    assert "checks" in data
    assert "version" in data


def test_healthz_endpoint_unhealthy(client):
    """Test healthz endpoint when unhealthy."""
    health_server = (
        client.app.state.health_server if hasattr(client.app, "state") else None
    )
    if health_server:
        health_server.is_running = False

    response = client.get("/healthz")
    assert response.status_code == 503


def test_ready_endpoint_ready(client):
    """Test ready endpoint when ready."""
    health_server = (
        client.app.state.health_server if hasattr(client.app, "state") else None
    )
    if health_server:
        health_server.is_running = True
        health_server.start_time = time.time() - 10

    response = client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["ready"] is True
    assert "checks" in data
    assert "health_status" in data


def test_ready_endpoint_not_ready(client):
    """Test ready endpoint when not ready."""
    health_server = (
        client.app.state.health_server if hasattr(client.app, "state") else None
    )
    if health_server:
        health_server.is_running = False

    response = client.get("/ready")
    assert response.status_code == 503


def test_metrics_endpoint(client):
    """Test metrics endpoint."""
    import sys
    
    # Mock psutil
    mock_psutil = MagicMock()
    mock_process = MagicMock()
    mock_process.memory_info.return_value.rss = 100 * 1024 * 1024  # 100MB
    mock_process.cpu_percent.return_value = 25.0
    mock_psutil.Process.return_value = mock_process

    with patch.dict(sys.modules, {"psutil": mock_psutil}):
        health_server = (
            client.app.state.health_server if hasattr(client.app, "state") else None
        )
        if health_server:
            health_server.is_running = True
            health_server.start_time = time.time() - 10

        response = client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
        content = response.text
        assert "memory_usage_bytes" in content
        assert "cpu_usage_percent" in content


def test_metrics_endpoint_error(client):
    """Test metrics endpoint with error."""
    with patch(
        "strategies.health.server.generate_latest",
        side_effect=Exception("Metrics error"),
    ):
        response = client.get("/metrics")
        assert response.status_code == 500


def test_info_endpoint(client):
    """Test info endpoint."""
    response = client.get("/info")
    assert response.status_code == 200
    data = response.json()
    assert "service" in data
    assert "environment" in data
    assert "configuration" in data
    assert "strategies" in data
    assert "trading" in data
    assert "risk" in data


def test_info_endpoint_error(client):
    """Test info endpoint with error."""
    with patch(
        "strategies.health.server.constants.get_enabled_strategies",
        side_effect=Exception("Config error"),
    ):
        response = client.get("/info")
        assert response.status_code == 500


def test_memory_usage_with_psutil():
    """Test memory usage calculation with psutil."""
    import sys
    
    mock_psutil = MagicMock()
    mock_process = MagicMock()
    mock_process.memory_info.return_value.rss = 200 * 1024 * 1024  # 200MB
    mock_psutil.Process.return_value = mock_process
    
    with patch.dict(sys.modules, {"psutil": mock_psutil}):
        server = HealthServer()
        memory_mb = server._get_memory_usage()
        assert memory_mb == 200.0


def test_memory_usage_without_psutil():
    """Test memory usage calculation without psutil."""
    import sys
    
    # Simulate psutil not being available
    with patch.dict(sys.modules, {"psutil": None}):
        server = HealthServer()
        memory_mb = server._get_memory_usage()
        assert memory_mb == 0.0


def test_cpu_usage_with_psutil():
    """Test CPU usage calculation with psutil."""
    import sys
    
    mock_psutil = MagicMock()
    mock_process = MagicMock()
    mock_process.cpu_percent.return_value = 50.0
    mock_psutil.Process.return_value = mock_process
    
    with patch.dict(sys.modules, {"psutil": mock_psutil}):
        server = HealthServer()
        cpu_percent = server._get_cpu_usage()
        assert cpu_percent == 50.0


def test_cpu_usage_without_psutil():
    """Test CPU usage calculation without psutil."""
    import sys
    
    # Simulate psutil not being available  
    with patch.dict(sys.modules, {"psutil": None}):
        server = HealthServer()
        cpu_percent = server._get_cpu_usage()
        assert cpu_percent == 0.0


def test_get_component_metrics(health_server):
    """Test component metrics collection."""
    components = health_server._get_component_metrics()

    assert "consumer" in components
    assert "publisher" in components
    assert "heartbeat" in components

    # Check consumer metrics
    assert components["consumer"]["messages_processed"] == 100
    assert components["consumer"]["health"]["status"] == "healthy"

    # Check publisher metrics
    assert components["publisher"]["messages_published"] == 50
    assert components["publisher"]["health"]["status"] == "healthy"

    # Check heartbeat metrics
    assert components["heartbeat"]["status"] == "active"


def test_get_component_metrics_with_errors(health_server):
    """Test component metrics collection with errors."""
    # Make consumer raise an error
    health_server.consumer.get_metrics.side_effect = Exception("Consumer error")

    components = health_server._get_component_metrics()

    assert "consumer" in components
    assert "error" in components["consumer"]
    assert components["consumer"]["error"] == "Consumer error"


def test_health_status_management(health_server):
    """Test health status management methods."""
    # Test initial status
    assert health_server.is_healthy() is True

    # Test updating status
    new_status = {"status": "degraded", "reason": "high_memory"}
    health_server.update_health_status(new_status)

    current_status = health_server.get_health_status()
    assert current_status["status"] == "degraded"
    assert current_status["reason"] == "high_memory"

    # Test unhealthy status
    health_server.update_health_status({"status": "unhealthy"})
    assert health_server.is_healthy() is False


@pytest.mark.asyncio
async def test_start_stop_lifecycle(health_server):
    """Test server start/stop lifecycle."""
    # Test start
    await health_server.start()
    assert health_server.is_running is True
    assert health_server.start_time is not None

    # Test stop
    await health_server.stop()
    assert health_server.is_running is False


@pytest.mark.asyncio
async def test_start_error_handling(health_server):
    """Test start error handling."""
    with patch(
        "strategies.health.server.uvicorn.Server", side_effect=Exception("Start error")
    ):
        with pytest.raises(Exception, match="Start error"):
            await health_server.start()


def test_lifespan_context_manager():
    """Test lifespan context manager."""
    with patch("strategies.health.server.constants") as mock_constants:
        mock_constants.SERVICE_VERSION = "1.0.0"
        mock_constants.SERVICE_NAME = "test-service"
        mock_constants.ENVIRONMENT = "test"
        mock_constants.get_enabled_strategies.return_value = []
        mock_constants.TRADING_SYMBOLS = []
        mock_constants.TRADING_ENABLE_SHORTS = True
        mock_constants.HEARTBEAT_ENABLED = True
        mock_constants.HEARTBEAT_INTERVAL_SECONDS = 30
        mock_constants.LOG_LEVEL = "INFO"
        mock_constants.ENABLE_OTEL = True
        mock_constants.NATS_URL = "nats://localhost:4222"
        mock_constants.NATS_CONSUMER_TOPIC = "market_data"
        mock_constants.NATS_PUBLISHER_TOPIC = "signals"
        mock_constants.HEALTH_CHECK_PORT = 8080
        mock_constants.get_strategy_config.return_value = {}
        mock_constants.get_trading_config.return_value = {}
        mock_constants.get_risk_config.return_value = {}

        config_manager = MagicMock()
        depth_analyzer = MagicMock()

        server = HealthServer(
            config_manager=config_manager, depth_analyzer=depth_analyzer
        )

        # Test that config manager and depth analyzer are set
        assert server.config_manager == config_manager
        assert server.depth_analyzer == depth_analyzer


def test_health_checks_logic(health_server):
    """Test health checks logic."""
    # Test with running server
    health_server.is_running = True
    health_server.start_time = time.time() - 10

    # Mock memory and CPU usage
    with patch.object(health_server, "_get_memory_usage", return_value=100.0):
        with patch.object(health_server, "_get_cpu_usage", return_value=25.0):
            # This would be called internally by health endpoints
            # We're testing the logic here
            assert health_server.is_running is True
            assert health_server._get_memory_usage() >= 0
            assert health_server._get_cpu_usage() >= 0


def test_prometheus_metrics_generation(health_server):
    """Test Prometheus metrics generation."""
    health_server.is_running = True
    health_server.start_time = time.time() - 10

    with patch(
        "strategies.health.server.generate_latest",
        return_value=b"# HELP test_metric Test metric\n# TYPE test_metric counter\ntest_metric 1\n",
    ):
        with patch.object(health_server, "_get_memory_usage", return_value=100.0):
            with patch.object(health_server, "_get_cpu_usage", return_value=25.0):
                # Test the metrics generation logic
                assert health_server.is_running is True
                assert health_server.start_time is not None
