"""
Additional tests for NATSConsumer to improve coverage to 90%.

Covers remaining uncovered lines in consumer.py.
"""

import asyncio
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from strategies.core.consumer import NATSConsumer
from strategies.core.publisher import TradeOrderPublisher
from strategies.models.market_data import MarketDataMessage


@pytest.fixture
def mock_publisher():
    """Create a mock publisher."""
    publisher = Mock(spec=TradeOrderPublisher)
    publisher.publish_signal = AsyncMock()
    publisher.publish_order = AsyncMock()
    return publisher


@pytest.fixture
def consumer(mock_publisher):
    """Create a NATSConsumer instance."""
    return NATSConsumer(
        nats_url="nats://test:4222",
        topic="test.topic",
        consumer_name="test-consumer",
        consumer_group="test-group",
        publisher=mock_publisher,
    )


@pytest.mark.asyncio
async def test_consumer_start_success(consumer):
    """Test successful start() - covers lines 180-187."""
    mock_nats = AsyncMock()
    mock_nats.is_connected = True
    mock_nats.connect = AsyncMock()
    mock_nats.subscribe = AsyncMock(return_value=AsyncMock())

    with patch("strategies.core.consumer.nats.NATS", return_value=mock_nats):
        await consumer.start()
        assert consumer.is_running is True
        assert consumer.nats_client is not None


@pytest.mark.asyncio
async def test_consumer_process_message_debug_log_guarded_when_disabled(consumer):
    """Per #221: the per-message debug log at consumer.py:397 must be
    guarded by is_enabled_for(DEBUG) so it never builds/emits the log when
    DEBUG is disabled — this was the prime suspect for the 420K debug-log
    spike shipped to Grafana Loki."""
    mock_msg = Mock()
    mock_msg.data = json.dumps({"stream": "btcusdt@depth@20ms", "data": {}}).encode()

    consumer.logger = Mock()
    consumer.logger.is_enabled_for = Mock(return_value=False)
    consumer._parse_market_data = Mock(return_value=None)

    await consumer._process_message(mock_msg)

    consumer.logger.is_enabled_for.assert_called()
    for call in consumer.logger.debug.call_args_list:
        assert call.args[0] != "Received message"


@pytest.mark.asyncio
async def test_consumer_process_message_debug_log_emitted_when_enabled(consumer):
    """When DEBUG is enabled, the guard must still let the log through."""
    mock_msg = Mock()
    mock_msg.data = json.dumps({"stream": "btcusdt@depth@20ms", "data": {}}).encode()

    consumer.logger = Mock()
    consumer.logger.is_enabled_for = Mock(return_value=True)
    consumer._parse_market_data = Mock(return_value=None)

    await consumer._process_message(mock_msg)

    received_calls = [
        c
        for c in consumer.logger.debug.call_args_list
        if c.args[0] == "Received message"
    ]
    assert len(received_calls) == 1


@pytest.mark.asyncio
async def test_consumer_process_message_invalid_market_data(consumer):
    """Test _process_message with invalid market data - covers lines 358-368."""
    mock_msg = Mock()
    mock_msg.data = json.dumps(
        {
            "stream": "btcusdt@depth@20ms",
            "data": {},  # Invalid data
        }
    ).encode()

    consumer._parse_market_data = Mock(return_value=None)  # Simulate invalid parse

    await consumer._process_message(mock_msg)
    # Should handle gracefully


@pytest.mark.asyncio
async def test_consumer_process_message_success(consumer):
    """Test _process_message success path - covers lines 370-405."""
    from strategies.models.market_data import DepthLevel, DepthUpdate

    mock_msg = Mock()
    mock_msg.data = json.dumps(
        {
            "stream": "btcusdt@depth@20ms",
            "data": {
                "e": "depthUpdate",
                "E": int(datetime.now(UTC).timestamp() * 1000),
                "s": "BTCUSDT",
                "U": 1,
                "u": 1,
                "b": [["50000.0", "1.0"]],
                "a": [["50001.0", "1.0"]],
            },
        }
    ).encode()

    # Mock successful parsing
    depth_data = DepthUpdate(
        symbol="BTCUSDT",
        event_time=int(datetime.now(UTC).timestamp() * 1000),
        first_update_id=1,
        final_update_id=1,
        bids=[DepthLevel(price="50000.0", quantity="1.0")],
        asks=[DepthLevel(price="50001.0", quantity="1.0")],
    )

    market_data = MarketDataMessage(
        stream="btcusdt@depth@20ms",
        data=depth_data,
        timestamp=datetime.now(UTC),
    )

    consumer._parse_market_data = Mock(return_value=market_data)
    consumer._process_market_data = AsyncMock()

    await consumer._process_message(mock_msg)
    assert consumer.message_count > 0


@pytest.mark.asyncio
async def test_consumer_process_message_processing_error(consumer):
    """Test _process_message processing error - covers lines 407-417."""
    from strategies.models.market_data import DepthLevel, DepthUpdate

    mock_msg = Mock()
    mock_msg.data = json.dumps(
        {
            "stream": "btcusdt@depth@20ms",
            "data": {
                "e": "depthUpdate",
                "E": int(datetime.now(UTC).timestamp() * 1000),
                "s": "BTCUSDT",
                "U": 1,
                "u": 1,
                "b": [["50000.0", "1.0"]],
                "a": [["50001.0", "1.0"]],
            },
        }
    ).encode()

    depth_data = DepthUpdate(
        symbol="BTCUSDT",
        event_time=int(datetime.now(UTC).timestamp() * 1000),
        first_update_id=1,
        final_update_id=1,
        bids=[DepthLevel(price="50000.0", quantity="1.0")],
        asks=[DepthLevel(price="50001.0", quantity="1.0")],
    )

    market_data = MarketDataMessage(
        stream="btcusdt@depth@20ms",
        data=depth_data,
        timestamp=datetime.now(UTC),
    )

    consumer._parse_market_data = Mock(return_value=market_data)
    consumer._process_market_data = AsyncMock(side_effect=Exception("Processing error"))

    await consumer._process_message(mock_msg)
    # Should handle error gracefully


@pytest.mark.asyncio
async def test_consumer_process_market_logic_strategies_list_signals(consumer):
    """Test _process_market_logic_strategies with list of signals - covers lines 711-721."""
    from strategies.models.market_data import DepthLevel, DepthUpdate
    from strategies.models.signals import (
        Signal,
        SignalAction,
        SignalConfidence,
        SignalType,
    )

    depth_data = DepthUpdate(
        symbol="BTCUSDT",
        event_time=int(datetime.now(UTC).timestamp() * 1000),
        first_update_id=1,
        final_update_id=1,
        bids=[DepthLevel(price="50000.0", quantity="1.0")],
        asks=[DepthLevel(price="50001.0", quantity="1.0")],
    )

    market_data = MarketDataMessage(
        stream="btcusdt@depth@20ms",
        data=depth_data,
        timestamp=datetime.now(UTC),
    )

    # Mock cross_exchange_spread to return list of signals
    if "cross_exchange_spread" in consumer.market_logic_strategies:
        strategy = consumer.market_logic_strategies["cross_exchange_spread"]
        strategy.process_market_data = AsyncMock(
            return_value=[
                Signal(
                    symbol="BTCUSDT",
                    signal_type=SignalType.BUY,
                    signal_action=SignalAction.OPEN_LONG,
                    confidence=SignalConfidence.HIGH,
                    confidence_score=0.85,
                    price=50000.0,
                    strategy_name="cross_exchange_spread",
                    signal_id="test-signal-12345",
                ),
                Signal(
                    symbol="BTCUSDT",
                    signal_type=SignalType.SELL,
                    signal_action=SignalAction.OPEN_SHORT,
                    confidence=SignalConfidence.MEDIUM,
                    confidence_score=0.65,
                    price=50000.0,
                    strategy_name="cross_exchange_spread",
                    signal_id="test-signal-67890",
                ),
            ]
        )

    await consumer._process_market_logic_strategies(market_data)
    # Should handle list of signals


@pytest.mark.asyncio
async def test_consumer_publish_market_logic_signals(consumer):
    """Test _publish_market_logic_signals - covers lines 752-769."""
    from strategies.models.signals import (
        Signal,
        SignalAction,
        SignalConfidence,
        SignalType,
    )

    signals = [
        Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="test",
            signal_id="test-signal-12345",
        ),
    ]

    await consumer._publish_market_logic_signals(signals)
    # Should publish signals


@pytest.mark.asyncio
async def test_consumer_publish_market_logic_signals_error(consumer):
    """Test _publish_market_logic_signals error handling - covers lines 768-769."""
    from strategies.models.signals import (
        Signal,
        SignalAction,
        SignalConfidence,
        SignalType,
    )

    signals = [
        Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="test",
            signal_id="test-signal-12345",
        ),
    ]

    # Mock publisher to raise exception
    consumer.publisher.publish_order = AsyncMock(side_effect=Exception("Publish error"))

    await consumer._publish_market_logic_signals(signals)
    # Should handle error gracefully
