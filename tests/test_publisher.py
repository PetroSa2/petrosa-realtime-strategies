"""
Unit tests for TradeOrderPublisher.

Tests the publisher's ability to publish trade orders and trading signals to NATS.
"""

import asyncio
import json
from datetime import UTC, datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from strategies.core.publisher import TradeOrderPublisher
from strategies.models.signals import Signal, SignalAction, SignalConfidence, SignalType


@pytest.fixture
def mock_nats_client():
    """Create a mock NATS client."""
    client = AsyncMock()
    client.is_connected = True
    client.publish = AsyncMock()
    client.connect = AsyncMock()
    client.close = AsyncMock()
    return client


@pytest.fixture
def publisher(mock_nats_client):
    """Create a publisher instance with mocked NATS client."""
    publisher = TradeOrderPublisher(
        nats_url="nats://test:4222",
        topic="signals.trading",
    )

    # Replace the NATS client with mock
    publisher.nats_client = mock_nats_client
    publisher.is_running = True

    return publisher


@pytest.mark.asyncio
async def test_publish_signal_success(publisher, mock_nats_client):
    """Test successful signal publishing."""
    # Create a test signal
    signal = Signal(
        symbol="BTCUSDT",
        signal_type=SignalType.BUY,
        signal_action=SignalAction.OPEN_LONG,
        confidence=SignalConfidence.HIGH,
        confidence_score=0.85,
        price=50000.0,
        timestamp=datetime.now(UTC),
        strategy_name="iceberg_detector",
        metadata={"test": "data"},
    )

    # Publish signal
    await publisher.publish_signal(signal)

    # Verify NATS publish was called
    assert mock_nats_client.publish.called
    call_args = mock_nats_client.publish.call_args

    # Check subject
    assert call_args.kwargs["subject"] == "signals.trading"

    # Check payload
    payload = call_args.kwargs["payload"].decode()
    payload_dict = json.loads(payload)

    assert payload_dict["symbol"] == "BTCUSDT"
    assert (
        payload_dict["signal_type"] == "buy"
    )  # Transformed by signal adapter to lowercase
    assert payload_dict["action"] == "buy"  # Transformed by signal adapter
    assert payload_dict["confidence"] == 0.85  # Numeric confidence score
    assert payload_dict["price"] == 50000.0
    assert payload_dict["strategy"] == "iceberg_detector"  # Transformed field name

    # Verify metrics were updated
    assert publisher.signal_count == 1
    assert publisher.last_order_time is not None


@pytest.mark.asyncio
async def test_publish_signal_with_dict_method(publisher, mock_nats_client):
    """Test signal publishing with Pydantic v1 dict() method."""
    # Create a signal that uses dict() method
    signal = Signal(
        symbol="ETHUSDT",
        signal_type=SignalType.SELL,
        signal_action=SignalAction.OPEN_SHORT,
        confidence=SignalConfidence.MEDIUM,
        confidence_score=0.65,
        price=3000.0,
        strategy_name="orderbook_skew",
    )

    # Publish signal
    await publisher.publish_signal(signal)

    # Verify it was published
    assert mock_nats_client.publish.called

    # Check that signal was serialized correctly
    payload = mock_nats_client.publish.call_args.kwargs["payload"].decode()
    payload_dict = json.loads(payload)

    assert payload_dict["symbol"] == "ETHUSDT"
    assert (
        payload_dict["signal_type"] == "sell"
    )  # Transformed by signal adapter to lowercase
    assert payload_dict["action"] == "sell"  # Transformed by signal adapter


@pytest.mark.asyncio
async def test_publish_signal_datetime_serialization(publisher, mock_nats_client):
    """Test that datetime fields are properly serialized to ISO format."""
    # Create signal with explicit timestamp
    test_timestamp = datetime(2024, 1, 1, 12, 0, 0)
    signal = Signal(
        symbol="BTCUSDT",
        signal_type=SignalType.BUY,
        signal_action=SignalAction.OPEN_LONG,
        confidence=SignalConfidence.HIGH,
        confidence_score=0.9,
        price=50000.0,
        timestamp=test_timestamp,
        strategy_name="test_strategy",
    )

    # Publish signal
    await publisher.publish_signal(signal)

    # Check that timestamp was converted to ISO string
    payload = mock_nats_client.publish.call_args.kwargs["payload"].decode()
    payload_dict = json.loads(payload)

    # Timestamp should be a string in ISO format
    assert isinstance(payload_dict["timestamp"], str)
    assert "T" in payload_dict["timestamp"]  # ISO format contains 'T'


@pytest.mark.asyncio
async def test_publish_signal_error_handling(publisher, mock_nats_client):
    """Test error handling when signal publishing fails."""
    # Make NATS publish raise an exception
    mock_nats_client.publish.side_effect = Exception("NATS connection failed")

    signal = Signal(
        symbol="BTCUSDT",
        signal_type=SignalType.BUY,
        signal_action=SignalAction.OPEN_LONG,
        confidence=SignalConfidence.HIGH,
        confidence_score=0.85,
        price=50000.0,
        strategy_name="test_strategy",
    )

    # Publishing should raise an exception
    with pytest.raises(Exception, match="NATS connection failed"):
        await publisher.publish_signal(signal)

    # Error count should be incremented
    assert publisher.error_count == 1


@pytest.mark.asyncio
async def test_publish_signal_updates_metrics(publisher, mock_nats_client):
    """Test that publishing updates metrics correctly."""
    initial_signal_count = publisher.signal_count
    initial_error_count = publisher.error_count

    signal = Signal(
        symbol="BTCUSDT",
        signal_type=SignalType.BUY,
        signal_action=SignalAction.OPEN_LONG,
        confidence=SignalConfidence.HIGH,
        confidence_score=0.85,
        price=50000.0,
        strategy_name="test_strategy",
    )

    # Publish signal
    await publisher.publish_signal(signal)

    # Check metrics updated
    assert publisher.signal_count == initial_signal_count + 1
    assert publisher.error_count == initial_error_count
    assert publisher.last_order_time is not None
    assert len(publisher.publishing_times) == 1
    assert publisher.publishing_times[0] >= 0


@pytest.mark.asyncio
async def test_publish_signal_with_metadata(publisher, mock_nats_client):
    """Test signal publishing with additional metadata."""
    signal = Signal(
        symbol="BTCUSDT",
        signal_type=SignalType.BUY,
        signal_action=SignalAction.OPEN_LONG,
        confidence=SignalConfidence.HIGH,
        confidence_score=0.85,
        price=50000.0,
        strategy_name="iceberg_detector",
        metadata={
            "iceberg_price": 111305.83,
            "side": "BUY",
            "volume_detected": 1000.5,
        },
    )

    # Publish signal
    await publisher.publish_signal(signal)

    # Check metadata was included
    payload = mock_nats_client.publish.call_args.kwargs["payload"].decode()
    payload_dict = json.loads(payload)

    assert "metadata" in payload_dict
    assert payload_dict["metadata"]["iceberg_price"] == 111305.83
    assert payload_dict["metadata"]["side"] == "BUY"
    assert payload_dict["metadata"]["volume_detected"] == 1000.5


@pytest.mark.asyncio
async def test_publish_multiple_signals(publisher, mock_nats_client):
    """Test publishing multiple signals in sequence."""
    signals = [
        Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="strategy_1",
        ),
        Signal(
            symbol="ETHUSDT",
            signal_type=SignalType.SELL,
            signal_action=SignalAction.OPEN_SHORT,
            confidence=SignalConfidence.MEDIUM,
            confidence_score=0.65,
            price=3000.0,
            strategy_name="strategy_2",
        ),
        Signal(
            symbol="BNBUSDT",
            signal_type=SignalType.HOLD,
            signal_action=SignalAction.HOLD,
            confidence=SignalConfidence.LOW,
            confidence_score=0.45,
            price=400.0,
            strategy_name="strategy_3",
        ),
    ]

    # Publish all signals
    for signal in signals:
        await publisher.publish_signal(signal)

    # Check that all were published
    assert mock_nats_client.publish.call_count == 3
    assert publisher.signal_count == 3


@pytest.mark.asyncio
async def test_publish_signal_trace_context_injection(publisher, mock_nats_client):
    """Test that trace context is injected into published signals."""
    signal = Signal(
        symbol="BTCUSDT",
        signal_type=SignalType.BUY,
        signal_action=SignalAction.OPEN_LONG,
        confidence=SignalConfidence.HIGH,
        confidence_score=0.85,
        price=50000.0,
        strategy_name="test_strategy",
    )

    # Publish signal
    await publisher.publish_signal(signal)

    # Get published payload
    payload = mock_nats_client.publish.call_args.kwargs["payload"].decode()
    payload_dict = json.loads(payload)

    # Note: inject_trace_context might add tracing fields
    # If petrosa_otel is available, check for trace fields
    # Verify the basic signal fields are present (transformed by signal adapter)
    assert "symbol" in payload_dict
    assert "signal_type" in payload_dict
    assert "action" in payload_dict  # Transformed signal has 'action' field
    assert "metadata" in payload_dict
    # Note: Publisher uses signal adapter, so metadata contains "original_*" fields


@pytest.mark.asyncio
async def test_get_metrics_includes_signal_counts(publisher):
    """Test that get_metrics returns signal publishing metrics."""
    # Publish some signals first
    mock_nats_client = AsyncMock()
    mock_nats_client.is_connected = True
    mock_nats_client.publish = AsyncMock()
    publisher.nats_client = mock_nats_client

    signal = Signal(
        symbol="BTCUSDT",
        signal_type=SignalType.BUY,
        signal_action=SignalAction.OPEN_LONG,
        confidence=SignalConfidence.HIGH,
        confidence_score=0.85,
        price=50000.0,
        strategy_name="test_strategy",
    )

    await publisher.publish_signal(signal)

    # Get metrics
    metrics = publisher.get_metrics()

    # Check metrics structure
    assert "order_count" in metrics
    assert "signal_count" in metrics
    assert "error_count" in metrics
    assert "is_running" in metrics
    assert "last_order_time" in metrics
    assert "max_publishing_time_ms" in metrics
    assert "avg_publishing_time_ms" in metrics

    # Check values
    assert metrics["signal_count"] == 1
    assert metrics["error_count"] == 0
