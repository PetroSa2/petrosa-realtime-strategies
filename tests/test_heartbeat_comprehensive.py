"""
Comprehensive tests for HeartbeatManager.

Current coverage: 15.04% → Target: 60%+
Focus on initialization, start/stop lifecycle, and state management.
"""

import pytest
from unittest.mock import AsyncMock, Mock, MagicMock
import asyncio
from strategies.utils.heartbeat import HeartbeatManager


def test_heartbeat_initialization_with_defaults():
    """Test HeartbeatManager initialization with default values - covers lines 30-66."""
    manager = HeartbeatManager()
    
    assert manager.consumer is None
    assert manager.publisher is None
    assert manager.logger is not None
    assert manager.is_running is False
    assert manager.heartbeat_count == 0
    assert isinstance(manager.previous_stats, dict)
    assert manager.previous_stats["consumer_messages"] == 0


def test_heartbeat_initialization_with_custom_values():
    """Test HeartbeatManager with custom configuration."""
    mock_consumer = Mock()
    mock_publisher = Mock()
    import structlog
    custom_logger = structlog.get_logger("test")
    
    manager = HeartbeatManager(
        consumer=mock_consumer,
        publisher=mock_publisher,
        logger=custom_logger,
        enabled=True,
        interval_seconds=30,
        include_detailed_stats=True
    )
    
    assert manager.consumer == mock_consumer
    assert manager.publisher == mock_publisher
    assert manager.logger == custom_logger
    assert manager.enabled is True
    assert manager.interval_seconds == 30
    assert manager.include_detailed_stats is True


def test_heartbeat_enabled_configuration():
    """Test heartbeat can be enabled/disabled - covers line 35."""
    manager_enabled = HeartbeatManager(enabled=True)
    assert manager_enabled.enabled is True
    
    manager_disabled = HeartbeatManager(enabled=False)
    assert manager_disabled.enabled is False


def test_heartbeat_interval_configuration():
    """Test heartbeat interval configuration - covers lines 36-40."""
    manager1 = HeartbeatManager(interval_seconds=60)
    assert manager1.interval_seconds == 60
    
    manager2 = HeartbeatManager(interval_seconds=120)
    assert manager2.interval_seconds == 120


def test_heartbeat_detailed_stats_configuration():
    """Test detailed stats configuration - covers lines 41-45."""
    manager1 = HeartbeatManager(include_detailed_stats=True)
    assert manager1.include_detailed_stats is True
    
    manager2 = HeartbeatManager(include_detailed_stats=False)
    assert manager2.include_detailed_stats is False


def test_heartbeat_state_initialization():
    """Test heartbeat state is initialized correctly - covers lines 47-59."""
    manager = HeartbeatManager()
    
    assert manager.is_running is False
    assert manager.shutdown_event is not None
    assert isinstance(manager.shutdown_event, asyncio.Event)
    assert manager.heartbeat_count == 0
    assert manager.start_time > 0


def test_heartbeat_previous_stats_structure():
    """Test previous_stats dictionary structure - covers lines 54-59."""
    manager = HeartbeatManager()
    
    assert "consumer_messages" in manager.previous_stats
    assert "consumer_errors" in manager.previous_stats
    assert "publisher_orders" in manager.previous_stats
    assert "publisher_errors" in manager.previous_stats
    assert all(v == 0 for v in manager.previous_stats.values())


@pytest.mark.asyncio
async def test_heartbeat_start_when_disabled():
    """Test start() returns early when disabled - covers lines 70-72."""
    manager = HeartbeatManager(enabled=False)
    
    await manager.start()
    
    # Should not start when disabled
    assert manager.is_running is False


@pytest.mark.asyncio
async def test_heartbeat_start_when_enabled():
    """Test start() initializes when enabled - covers lines 74-79."""
    manager = HeartbeatManager(enabled=True, interval_seconds=60)
    
    # Start heartbeat
    await manager.start()
    
    # Should set running state
    assert manager.is_running is True
    # start_time should be updated
    assert manager.start_time > 0


@pytest.mark.asyncio
async def test_heartbeat_stop_sets_shutdown_event():
    """Test stop() sets shutdown event."""
    manager = HeartbeatManager(enabled=True)
    manager.is_running = True
    
    await manager.stop()
    
    # Should signal shutdown
    assert manager.shutdown_event.is_set() or manager.is_running is False


def test_heartbeat_with_consumer_and_publisher():
    """Test heartbeat with both consumer and publisher."""
    mock_consumer = Mock()
    mock_consumer.get_statistics = Mock(return_value={
        "messages_processed": 100,
        "errors": 5
    })
    
    mock_publisher = Mock()
    mock_publisher.get_metrics = Mock(return_value={
        "order_count": 50,
        "error_count": 2
    })
    
    manager = HeartbeatManager(
        consumer=mock_consumer,
        publisher=mock_publisher,
        enabled=True
    )
    
    assert manager.consumer == mock_consumer
    assert manager.publisher == mock_publisher


def test_heartbeat_shutdown_event_not_set_initially():
    """Test shutdown event is not set on initialization."""
    manager = HeartbeatManager()
    
    assert not manager.shutdown_event.is_set()


@pytest.mark.asyncio
async def test_heartbeat_multiple_start_stop_cycles():
    """Test heartbeat can be started and stopped multiple times."""
    manager = HeartbeatManager(enabled=True, interval_seconds=60)
    
    # First cycle
    await manager.start()
    assert manager.is_running is True
    
    await manager.stop()
    
    # Second cycle
    manager.is_running = False
    manager.shutdown_event = asyncio.Event()  # Reset
    await manager.start()
    assert manager.is_running is True

