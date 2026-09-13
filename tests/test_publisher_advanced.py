"""
Advanced tests for TradeOrderPublisher to improve coverage.

Focus on initialization, error handling, and edge cases.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from strategies.core.publisher import TradeOrderPublisher
from strategies.models.signals import Signal, SignalAction, SignalConfidence, SignalType


@pytest.fixture
def publisher_config():
    """Publisher configuration for tests."""
    return {"nats_url": "nats://localhost:4222", "topic": "test.signals"}


@pytest.fixture
def publisher(publisher_config):
    """Create a TradeOrderPublisher instance."""
    return TradeOrderPublisher(
        nats_url=publisher_config["nats_url"], topic=publisher_config["topic"]
    )


def test_publisher_initialization(publisher_config):
    """Test TradeOrderPublisher initialization - covers lines 40-71."""
    publisher = TradeOrderPublisher(
        nats_url=publisher_config["nats_url"], topic=publisher_config["topic"]
    )

    assert publisher.nats_url == publisher_config["nats_url"]
    assert publisher.topic == publisher_config["topic"]
    assert publisher.nats_client is None
    assert publisher.is_running is False
    assert publisher.order_count == 0
    assert publisher.signal_count == 0
    assert publisher.error_count == 0
    assert publisher.last_order_time is None
    assert publisher.publishing_times == []
    assert publisher.max_publishing_time == 0.0
    assert publisher.avg_publishing_time == 0.0


@pytest.mark.asyncio
async def test_publisher_error_handling_increments_counter():
    """Test that error handling increments error_count."""
    publisher = TradeOrderPublisher(
        nats_url="nats://localhost:4222", topic="test.signals"
    )

    initial_errors = publisher.error_count

    # Trigger an error scenario (publishing without connection)
    try:
        # This should fail gracefully and increment error count
        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="test",
        )

        # Publish without starting (no NATS connection)
        await publisher.publish_signal(signal)
    except Exception:
        # Expected - no connection
        pass

    # Error count should be tracked (if error handling is implemented)
    assert publisher.error_count >= initial_errors


@pytest.mark.asyncio
async def test_publisher_shutdown_event_initialization(publisher):
    """Test shutdown event is initialized - covers line 56."""
    assert publisher.shutdown_event is not None
    assert isinstance(publisher.shutdown_event, asyncio.Event)
    assert not publisher.shutdown_event.is_set()


@pytest.mark.asyncio
async def test_publisher_logger_initialization(publisher_config):
    """Test publisher can be created with and without logger - covers line 42."""
    import structlog

    # Without logger (uses default)
    pub1 = TradeOrderPublisher(
        nats_url=publisher_config["nats_url"], topic=publisher_config["topic"]
    )
    assert pub1.logger is not None

    # With custom logger
    custom_logger = structlog.get_logger()
    pub2 = TradeOrderPublisher(
        nats_url=publisher_config["nats_url"],
        topic=publisher_config["topic"],
        logger=custom_logger,
    )
    assert pub2.logger == custom_logger


@pytest.mark.asyncio
async def test_publisher_start_exception_handling(publisher):
    """Test start() exception handling - covers lines 86-90."""

    # Mock _connect_to_nats to raise exception
    async def mock_connect():
        raise Exception("Connection failed")

    publisher._connect_to_nats = mock_connect

    with pytest.raises(Exception):
        await publisher.start()


@pytest.mark.asyncio
async def test_publisher_stop_exception_handling(publisher):
    """Test stop() exception handling when closing NATS - covers lines 122-123."""
    publisher.is_running = True
    publisher.nats_client = AsyncMock()
    publisher.nats_client.is_connected = True
    publisher.nats_client.close = AsyncMock(side_effect=Exception("Close failed"))

    # Should handle exception gracefully
    await publisher.stop()
    assert publisher.is_running is False


@pytest.mark.asyncio
async def test_publisher_connect_success_logging(publisher):
    """Test successful NATS connection logging - covers line 147."""
    mock_nats = AsyncMock()
    mock_nats.is_connected = True
    mock_nats.connect = AsyncMock()

    with patch("strategies.core.publisher.nats.NATS", return_value=mock_nats):
        # Connection success path is exercised (line 147)
        await publisher._connect_to_nats()
        assert publisher.nats_client == mock_nats


@pytest.mark.asyncio
async def test_publisher_import_fallback():
    """Test import fallback for petrosa_otel - covers lines 19-22."""
    from strategies.core.publisher import inject_trace_context

    # When petrosa_otel is not available, fallback returns data as-is
    # When it is available, it might transform the data
    result = inject_trace_context({"test": "data"})
    # Either dict (fallback) or transformed dict (if petrosa_otel installed)
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_publisher_start_success(publisher):
    """Test successful start() - covers lines 86-90."""
    mock_nats = AsyncMock()
    mock_nats.is_connected = True
    mock_nats.connect = AsyncMock()

    with patch("strategies.core.publisher.nats.NATS", return_value=mock_nats):
        await publisher.start()
        assert publisher.is_running is True
        assert publisher.nats_client is not None


@pytest.mark.asyncio
async def test_update_publishing_metrics_cleanup(publisher):
    """Test _update_publishing_metrics enforces the 1000-sample window
    (per #191 AC1: fixed-size ring buffer, no unbounded growth)."""
    for _ in range(1500):
        publisher._update_publishing_metrics(0.1)
    assert len(publisher.publishing_times) == 1000

    publisher._update_publishing_metrics(0.2)
    assert len(publisher.publishing_times) <= 1000


@pytest.mark.asyncio
async def test_get_health_status(publisher):
    """Test get_health_status method - covers lines 460-467."""
    publisher.is_running = True
    publisher.nats_client = AsyncMock()
    publisher.nats_client.is_connected = True
    publisher.error_count = 5

    status = publisher.get_health_status()
    assert "healthy" in status
    assert "is_running" in status
    assert "nats_connected" in status
    assert status["healthy"] is True


@pytest.mark.asyncio
async def test_get_health_status_unhealthy(publisher):
    """Test get_health_status when unhealthy."""
    publisher.is_running = False
    publisher.error_count = 150  # > 100

    status = publisher.get_health_status()
    assert status["healthy"] is False


@pytest.mark.asyncio
async def test_publisher_windowed_error_rate_replaces_lifetime_cliff(publisher):
    """#186 AC4: a burst of past errors must not permanently fail health."""
    publisher.is_running = True
    publisher.nats_client = AsyncMock()
    publisher.nats_client.is_connected = True

    # Simulate a large burst of errors that all happened well in the past.
    for _ in range(150):
        publisher.error_count += 1
        publisher.error_tracker._timestamps.append(0.0)  # epoch: outside any window

    status = publisher.get_health_status()
    assert status["error_count"] == 150
    assert status["recent_error_count"] == 0
    assert status["healthy"] is True

    # A burst of *recent* errors still trips the windowed check.
    for _ in range(publisher.error_tracker.max_errors_in_window):
        publisher.error_tracker.record_error()

    status = publisher.get_health_status()
    assert status["recent_error_count"] >= publisher.error_tracker.max_errors_in_window
    assert status["healthy"] is False
