"""
Tests for HeartbeatManager metric field naming (per #194 AC3).

The live publish path is `publish_signal()`; `order_count` is dead code
(the order path was removed in #190/#205). These tests confirm the
heartbeat reads `signal_count` and reports it under `signals_*` field
names so the log matches what it actually measures.
"""

from unittest.mock import MagicMock

import pytest

from strategies.utils.heartbeat import HeartbeatManager


@pytest.fixture
def mock_consumer():
    consumer = MagicMock()
    consumer.get_metrics.return_value = {"message_count": 100, "error_count": 1}
    return consumer


@pytest.fixture
def mock_publisher():
    publisher = MagicMock()
    # order_count is dead (per #190/#205) and must never be read for rates;
    # signal_count is the only field that ever increments on the live path.
    publisher.get_metrics.return_value = {
        "order_count": 999,
        "signal_count": 7,
        "error_count": 0,
    }
    return publisher


@pytest.fixture
def heartbeat_manager(mock_consumer, mock_publisher):
    return HeartbeatManager(
        consumer=mock_consumer,
        publisher=mock_publisher,
        enabled=True,
        interval_seconds=60,
        include_detailed_stats=False,
    )


def test_collect_current_stats_reads_signal_count_not_order_count(
    heartbeat_manager,
):
    stats = heartbeat_manager._collect_current_stats()

    assert stats["publisher_signals"] == 7
    assert "publisher_orders" not in stats


@pytest.mark.asyncio
async def test_log_heartbeat_uses_signals_field_names(heartbeat_manager):
    heartbeat_manager.logger = MagicMock()

    await heartbeat_manager._log_heartbeat()

    assert heartbeat_manager.logger.info.called
    _, kwargs = heartbeat_manager.logger.info.call_args

    # New, honest field names must be present.
    assert kwargs["signals_published_delta"] == 7
    assert kwargs["signals_per_second"] == pytest.approx(7 / 60, abs=0.01)
    assert kwargs["total_signals_published"] == 7

    # The permanently-zero order-based names must be gone.
    assert "orders_published_delta" not in kwargs
    assert "orders_per_second" not in kwargs
    assert "total_orders_published" not in kwargs


@pytest.mark.asyncio
async def test_log_heartbeat_nonzero_signals_per_second_on_real_activity(
    mock_consumer,
):
    """A running service emitting signals shows a non-zero heartbeat rate."""
    publisher = MagicMock()
    publisher.get_metrics.return_value = {
        "order_count": 0,
        "signal_count": 30,
        "error_count": 0,
    }
    manager = HeartbeatManager(
        consumer=mock_consumer,
        publisher=publisher,
        enabled=True,
        interval_seconds=60,
        include_detailed_stats=False,
    )
    manager.logger = MagicMock()

    await manager._log_heartbeat()

    _, kwargs = manager.logger.info.call_args
    assert kwargs["signals_per_second"] > 0.0
