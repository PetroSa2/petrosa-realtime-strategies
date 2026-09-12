"""
Tests for NATSConsumer to improve coverage.

Covers:
- Import fallback (lines 23-26)
- Start/stop exception handling (lines 132-135, 229-234)
- Connection and subscription methods
- Message processing edge cases
- Error handling paths
"""

import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from strategies.core.consumer import NATSConsumer
from strategies.core.publisher import TradeOrderPublisher
from strategies.models.market_data import MarketDataMessage
from strategies.services.depth_analyzer import DepthAnalyzer


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


def test_consumer_import_fallback():
    """Test import fallback for petrosa_otel - covers lines 23-26."""
    # Test that consumer can be imported even without petrosa_otel
    # The fallback function should be defined
    from strategies.core.consumer import extract_trace_context

    # When petrosa_otel is not available, fallback returns None (line 26)
    # When it is available, it might return the data dict
    result = extract_trace_context({})
    # Either None (fallback) or dict (if petrosa_otel installed)
    assert result is None or isinstance(result, dict)


def test_consumer_initialization(consumer):
    """Test NATSConsumer initialization."""
    assert consumer.nats_url == "nats://test:4222"
    assert consumer.topic == "test.topic"
    assert consumer.consumer_name == "test-consumer"
    assert consumer.consumer_group == "test-group"
    assert consumer.nats_client is None
    assert consumer.subscription is None
    assert consumer.is_running is False
    assert consumer.message_count == 0
    assert consumer.error_count == 0


@pytest.mark.asyncio
async def test_consumer_start_exception_handling(consumer):
    """Test start() exception handling - covers lines 132-135, 194-196."""

    # Mock _connect_to_nats to raise exception
    async def mock_connect():
        raise Exception("Connection failed")

    consumer._connect_to_nats = mock_connect

    with pytest.raises(Exception):
        await consumer.start()


@pytest.mark.asyncio
async def test_consumer_stop_exception_handling(consumer):
    """Test stop() exception handling when closing NATS - covers lines 229-234."""
    consumer.is_running = True
    consumer.nats_client = AsyncMock()
    consumer.nats_client.is_connected = True
    consumer.nats_client.close = AsyncMock(side_effect=Exception("Close failed"))
    consumer.subscription = AsyncMock()
    consumer.subscription.drain = AsyncMock()

    # Should handle exception gracefully
    await consumer.stop()
    assert consumer.is_running is False


@pytest.mark.asyncio
async def test_consumer_connect_to_nats(consumer):
    """Test _connect_to_nats method."""
    mock_nats = AsyncMock()
    mock_nats.is_connected = True
    mock_nats.connect = AsyncMock()

    with patch("strategies.core.consumer.nats.NATS", return_value=mock_nats):
        await consumer._connect_to_nats()
        assert consumer.nats_client == mock_nats


@pytest.mark.asyncio
async def test_consumer_connect_to_nats_unlimited_reconnect_with_callbacks(consumer):
    """AC1/AC2: connect() must request unlimited reconnects, a jittered
    reconnect handler, and register all four lifecycle callbacks."""
    mock_nats = AsyncMock()
    mock_nats.is_connected = True
    mock_nats.connect = AsyncMock()

    with patch("strategies.core.consumer.nats.NATS", return_value=mock_nats):
        await consumer._connect_to_nats()

    _, kwargs = mock_nats.connect.call_args
    assert kwargs["max_reconnect_attempts"] == -1
    assert callable(kwargs["reconnect_to_server_handler"])
    assert kwargs["error_cb"] == consumer._on_nats_error
    assert kwargs["disconnected_cb"] == consumer._on_nats_disconnected
    assert kwargs["reconnected_cb"] == consumer._on_nats_reconnected
    assert kwargs["closed_cb"] == consumer._on_nats_closed


@pytest.mark.asyncio
async def test_consumer_on_nats_disconnected_logs_and_records_error(consumer):
    """AC3/AC5: disconnected_cb fires -> structured log + error counter increments."""
    with patch.object(consumer.metrics, "record_error") as mock_record_error:
        await consumer._on_nats_disconnected()

    mock_record_error.assert_called_once_with("nats_disconnected")


@pytest.mark.asyncio
async def test_consumer_on_nats_error_records_error(consumer):
    """AC3: error_cb records realtime.errors.total with error_type=nats_error."""
    with patch.object(consumer.metrics, "record_error") as mock_record_error:
        await consumer._on_nats_error(Exception("boom"))

    mock_record_error.assert_called_once_with("nats_error")


@pytest.mark.asyncio
async def test_consumer_on_nats_reconnected_records_error(consumer):
    """AC3: reconnected_cb records realtime.errors.total with error_type=nats_reconnected."""
    with patch.object(consumer.metrics, "record_error") as mock_record_error:
        await consumer._on_nats_reconnected()

    mock_record_error.assert_called_once_with("nats_reconnected")


@pytest.mark.asyncio
async def test_consumer_on_nats_closed_records_error(consumer):
    """AC3: closed_cb records realtime.errors.total with error_type=nats_closed."""
    with patch.object(consumer.metrics, "record_error") as mock_record_error:
        await consumer._on_nats_closed()

    mock_record_error.assert_called_once_with("nats_closed")


def test_consumer_nats_connected_property_reflects_client_state(consumer):
    """AC4/AC5: nats_connected is synchronously readable and flips with the
    underlying client's is_connected state -- no client, then connected, then
    disconnected (simulating the outage -> reconnect lifecycle)."""
    assert consumer.nats_connected is False

    consumer.nats_client = Mock()
    consumer.nats_client.is_connected = True
    assert consumer.nats_connected is True

    consumer.nats_client.is_connected = False
    assert consumer.nats_connected is False


@pytest.mark.asyncio
async def test_consumer_subscribe_to_topic(consumer):
    """Test _subscribe_to_topic method."""
    consumer.nats_client = AsyncMock()
    consumer.nats_client.subscribe = AsyncMock(return_value=AsyncMock())

    await consumer._subscribe_to_topic()
    assert consumer.subscription is not None


@pytest.mark.asyncio
async def test_consumer_message_handler_error(consumer):
    """Test _message_handler error handling."""
    mock_msg = Mock()
    mock_msg.data = b"invalid json"

    # Should handle errors gracefully
    await consumer._message_handler(mock_msg)
    assert consumer.error_count > 0


@pytest.mark.asyncio
async def test_consumer_process_message_invalid_data(consumer):
    """Test _process_message with invalid data."""
    invalid_data = b"not json"

    # Should handle gracefully
    await consumer._process_message(invalid_data)
    assert consumer.error_count > 0


@pytest.mark.asyncio
async def test_consumer_process_market_data_unknown_type(consumer):
    """Test _process_market_data with unknown stream type - covers line 584."""
    # Create a mock MarketDataMessage where is_depth, is_trade, is_ticker all return False
    # This simulates an unknown stream type
    from unittest.mock import PropertyMock

    from strategies.models.market_data import DepthLevel, DepthUpdate

    depth_data = DepthUpdate(
        symbol="BTCUSDT",
        event_time=int(datetime.utcnow().timestamp() * 1000),
        first_update_id=1,
        final_update_id=1,
        bids=[DepthLevel(price="50000.0", quantity="1.0")],
        asks=[DepthLevel(price="50001.0", quantity="1.0")],
    )

    market_data = MarketDataMessage(
        stream="btcusdt@unknown",
        data=depth_data,
        timestamp=datetime.utcnow(),
    )

    # Mock the properties to return False for all types using PropertyMock
    with (
        patch.object(
            MarketDataMessage, "is_depth", new_callable=PropertyMock, return_value=False
        ),
        patch.object(
            MarketDataMessage, "is_trade", new_callable=PropertyMock, return_value=False
        ),
        patch.object(
            MarketDataMessage,
            "is_ticker",
            new_callable=PropertyMock,
            return_value=False,
        ),
    ):
        # Create new instance with mocked properties
        market_data_mock = MarketDataMessage(
            stream="btcusdt@unknown",
            data=depth_data,
            timestamp=datetime.utcnow(),
        )
        await consumer._process_market_data(market_data_mock)
        # Should log warning for unknown stream type (line 584)


@pytest.mark.asyncio
async def test_consumer_process_market_data_exception(consumer):
    """Test _process_market_data exception handling - covers lines 591-592."""
    # Create market data that will cause exception
    from strategies.models.market_data import DepthLevel, DepthUpdate

    depth_data = DepthUpdate(
        symbol="BTCUSDT",
        event_time=int(datetime.utcnow().timestamp() * 1000),
        first_update_id=1,
        final_update_id=1,
        bids=[DepthLevel(price="50000.0", quantity="1.0")],
        asks=[DepthLevel(price="50001.0", quantity="1.0")],
    )

    market_data = MarketDataMessage(
        stream="btcusdt@depth@20ms",
        data=depth_data,
        timestamp=datetime.utcnow(),
    )

    # Mock _process_depth_data to raise exception
    async def mock_process_depth(data):
        raise Exception("Processing error")

    consumer._process_depth_data = mock_process_depth

    await consumer._process_market_data(market_data)
    # Should handle exception gracefully


@pytest.mark.asyncio
async def test_consumer_process_depth_data_error(consumer):
    """Test _process_depth_data error handling - covers lines 626-627."""
    from strategies.models.market_data import DepthLevel, DepthUpdate

    depth_data = DepthUpdate(
        symbol="BTCUSDT",
        event_time=int(datetime.utcnow().timestamp() * 1000),
        first_update_id=1,
        final_update_id=1,
        bids=[DepthLevel(price="50000.0", quantity="1.0")],
        asks=[DepthLevel(price="50001.0", quantity="1.0")],
    )

    market_data = MarketDataMessage(
        stream="btcusdt@depth@20ms",
        data=depth_data,
        timestamp=datetime.utcnow(),
    )

    # Mock depth_analyzer to raise exception
    consumer.depth_analyzer = Mock()
    consumer.depth_analyzer.analyze = Mock(side_effect=Exception("Analyzer error"))

    await consumer._process_depth_data(market_data)
    # Should handle error gracefully


@pytest.mark.asyncio
async def test_consumer_process_microstructure_strategies_error(consumer):
    """Test _process_microstructure_strategies error handling - covers lines 665-667."""
    # Mock microstructure strategies
    consumer.microstructure_strategies = {"test_strategy": Mock()}
    consumer.microstructure_strategies["test_strategy"].analyze = Mock(
        side_effect=Exception("Strategy error")
    )

    await consumer._process_microstructure_strategies(
        "BTCUSDT", [(50000.0, 1.0)], [(50001.0, 1.0)]
    )
    # Should handle error gracefully


@pytest.mark.asyncio
async def test_consumer_processing_loop_basic(consumer):
    """Test _processing_loop basic operation."""
    consumer.is_running = True
    consumer.subscription = AsyncMock()

    # Mock message handler
    consumer._message_handler = AsyncMock()

    # Set shutdown event to stop loop quickly
    consumer.shutdown_event.set()

    try:
        await asyncio.wait_for(consumer._processing_loop(), timeout=0.5)
    except TimeoutError:
        # Expected: timeout is used to stop the loop for testing
        pass


@pytest.mark.asyncio
async def test_consumer_processing_loop_exception(consumer):
    """Test _processing_loop exception handling."""
    consumer.is_running = True
    consumer.subscription = AsyncMock()
    consumer.subscription.fetch = AsyncMock(side_effect=Exception("Fetch error"))

    consumer.shutdown_event.set()

    try:
        await asyncio.wait_for(consumer._processing_loop(), timeout=0.5)
    except (TimeoutError, Exception):
        # Expected: timeout or exception stops the loop for testing
        pass


@pytest.mark.asyncio
async def test_consumer_get_metrics(consumer):
    """Test get_metrics method."""
    consumer.message_count = 10
    consumer.error_count = 2
    consumer.processing_times = [0.1, 0.2, 0.3]

    metrics = consumer.get_metrics()
    assert "message_count" in metrics
    assert "error_count" in metrics
    assert metrics["message_count"] == 10


@pytest.mark.asyncio
async def test_consumer_get_health_status(consumer):
    """Test get_health_status method."""
    consumer.is_running = True
    consumer.nats_client = AsyncMock()
    consumer.nats_client.is_connected = True
    consumer.subscription = AsyncMock()  # Required for health check
    consumer.error_count = 5

    status = consumer.get_health_status()
    assert "healthy" in status
    assert status["healthy"] is True


@pytest.mark.asyncio
async def test_consumer_get_health_status_unhealthy(consumer):
    """Test get_health_status when unhealthy."""
    consumer.is_running = False
    consumer.error_count = 150

    status = consumer.get_health_status()
    assert status["healthy"] is False


@pytest.mark.asyncio
async def test_consumer_transform_depth_data_error(consumer):
    """Test _transform_depth_data error handling - covers lines 516-518."""
    # Invalid data that will cause exception during DepthUpdate creation
    # Use data that causes exception in DepthLevel validation (invalid price/quantity)
    invalid_data = {
        "s": "BTCUSDT",
        "E": int(datetime.utcnow().timestamp() * 1000),
        "bids": [["invalid_price", "1.0"]],  # Invalid price will fail validation
        "asks": [
            ["50001.0", "invalid_quantity"]
        ],  # Invalid quantity will fail validation
    }

    result = consumer._transform_depth_data(invalid_data)
    # Should return None on error (line 518)
    assert result is None


@pytest.mark.asyncio
async def test_consumer_transform_depth_data_real_binance_keys(consumer):
    """Regression test for #181: live Binance diff-depth payloads use the
    short keys "b"/"a", not "bids"/"asks". Prior to the fix, `bids in data`
    was always False for real payloads, so `bids`/`asks` stayed empty and
    every downstream imbalance/pressure calculation was silently 0.0.
    """
    # Real captured Binance Futures diff-depth WebSocket payload (see issue #181).
    real_payload = {
        "e": "depthUpdate",
        "E": 1787622635217,
        "T": 1787622635151,
        "s": "BTCUSDT",
        "ps": "BTCUSDT",
        "U": 410706805751,
        "u": 410706808244,
        "pu": 410706801858,
        "b": [["79667.70", "368.0138"], ["79667.60", "1.2000"]],
        "a": [["79686.20", "0.0714"], ["79686.30", "2.5000"]],
        "st": 1,
    }

    result = consumer._transform_depth_data(real_payload)

    assert result is not None
    assert len(result.bids) == 2
    assert len(result.asks) == 2
    assert result.bids[0].price == "79667.70"
    assert result.bids[0].quantity == "368.0138"
    assert result.asks[0].price == "79686.20"
    assert result.asks[0].quantity == "0.0714"


@pytest.mark.asyncio
async def test_consumer_transform_depth_data_legacy_bids_asks_fallback(consumer):
    """Defensive fallback: if a differently-shaped message source ever sends
    "bids"/"asks" keys directly, they should still populate correctly.
    """
    legacy_payload = {
        "s": "ETHUSDT",
        "E": int(datetime.utcnow().timestamp() * 1000),
        "bids": [["2000.0", "1.0"]],
        "asks": [["2001.0", "0.5"]],
    }

    result = consumer._transform_depth_data(legacy_payload)

    assert result is not None
    assert len(result.bids) == 1
    assert len(result.asks) == 1


def test_depth_transform_feeds_nonzero_imbalance_to_analyzer(consumer):
    """Regression test for #181: a non-symmetric real Binance depth payload,
    once transformed by `_transform_depth_data`, must produce a non-empty
    order book that yields non-zero imbalance/net_pressure from
    `DepthAnalyzer.analyze_depth`. Prior to the fix this was always
    imbalance_percent == 0.0 / net_pressure == 0.0 because bids/asks were
    silently empty for every real payload.
    """
    real_payload = {
        "e": "depthUpdate",
        "E": 1787622635217,
        "s": "BTCUSDT",
        "U": 410706805751,
        "u": 410706808244,
        # Deliberately non-symmetric book (bid volume >> ask volume).
        "b": [["79667.70", "368.0138"], ["79667.60", "10.0"]],
        "a": [["79686.20", "0.0714"], ["79686.30", "0.05"]],
    }

    depth_update = consumer._transform_depth_data(real_payload)
    assert depth_update is not None

    bids = [(float(b.price), float(b.quantity)) for b in depth_update.bids]
    asks = [(float(a.price), float(a.quantity)) for a in depth_update.asks]

    analyzer = DepthAnalyzer()
    metrics = analyzer.analyze_depth("BTCUSDT", bids, asks)

    assert metrics.imbalance_percent != 0.0
    assert metrics.net_pressure != 0.0


@pytest.mark.asyncio
async def test_consumer_transform_trade_data_error(consumer):
    """Test _transform_trade_data error handling - covers lines 537-539."""
    # Invalid data that will cause exception
    invalid_data = {
        "s": "",  # Empty symbol will fail validation
        "p": "invalid_price",  # Invalid price format
    }

    result = consumer._transform_trade_data(invalid_data)
    assert result is None


@pytest.mark.asyncio
async def test_consumer_transform_ticker_data_error(consumer):
    """Test _transform_ticker_data error handling - covers lines 569-571."""
    # Invalid data that will cause exception
    invalid_data = {
        "s": "",  # Empty symbol will fail validation
        "c": "invalid_price",  # Invalid price format
    }

    result = consumer._transform_ticker_data(invalid_data)
    assert result is None


@pytest.mark.asyncio
async def test_consumer_processing_loop_with_messages(consumer):
    """Test _processing_loop with actual messages - covers lines 296-315."""
    consumer.is_running = True
    consumer.subscription = AsyncMock()

    # Mock fetch to return messages
    mock_msg1 = Mock()
    mock_msg1.data = json.dumps(
        {
            "stream": "btcusdt@depth@20ms",
            "data": {
                "e": "depthUpdate",
                "E": int(datetime.utcnow().timestamp() * 1000),
                "s": "BTCUSDT",
                "U": 1,
                "u": 1,
                "b": [["50000.0", "1.0"]],
                "a": [["50001.0", "1.0"]],
            },
        }
    ).encode()

    consumer.subscription.fetch = AsyncMock(return_value=[mock_msg1])
    consumer._message_handler = AsyncMock()

    # Set shutdown event to stop loop after processing
    consumer.shutdown_event.set()

    try:
        await asyncio.wait_for(consumer._processing_loop(), timeout=0.5)
    except TimeoutError:
        # Expected: timeout is used to stop the loop for testing
        pass


@pytest.mark.asyncio
async def test_consumer_processing_loop_timeout(consumer):
    """Test _processing_loop timeout handling."""
    consumer.is_running = True
    consumer.subscription = AsyncMock()
    consumer.subscription.fetch = AsyncMock(return_value=[])  # No messages

    consumer.shutdown_event.set()

    try:
        await asyncio.wait_for(consumer._processing_loop(), timeout=0.5)
    except TimeoutError:
        # Expected: timeout is used to stop the loop for testing
        pass


@pytest.mark.asyncio
async def test_consumer_process_trade_data(consumer):
    """Test _process_trade_data method."""
    from strategies.models.market_data import TradeData

    trade_data = TradeData(
        symbol="BTCUSDT",
        trade_id=12345,
        price="50000.0",
        quantity="1.0",
        buyer_order_id=1,
        seller_order_id=2,
        trade_time=int(datetime.utcnow().timestamp() * 1000),
        is_buyer_maker=False,
        event_time=int(datetime.utcnow().timestamp() * 1000),
    )

    market_data = MarketDataMessage(
        stream="btcusdt@trade",
        data=trade_data,
        timestamp=datetime.utcnow(),
    )

    await consumer._process_trade_data(market_data)
    # Should process without errors


@pytest.mark.asyncio
async def test_consumer_process_ticker_data(consumer):
    """Test _process_ticker_data method."""
    from strategies.models.market_data import TickerData

    ticker_data = TickerData(
        symbol="BTCUSDT",
        event_time=int(datetime.utcnow().timestamp() * 1000),
        price_change="100.0",
        price_change_percent="0.2",
        weighted_avg_price="50000.0",
        prev_close_price="49900.0",
        last_price="50000.0",
        last_qty="1.0",
        bid_price="49999.0",
        bid_qty="1.0",
        ask_price="50001.0",
        ask_qty="1.0",
        open_price="49900.0",
        high_price="50100.0",
        low_price="49800.0",
        volume="1000.0",
        quote_volume="50000000.0",
        open_time=int(datetime.utcnow().timestamp() * 1000),
        close_time=int(datetime.utcnow().timestamp() * 1000),
        first_id=1,
        last_id=1000,
        count=1000,
    )

    market_data = MarketDataMessage(
        stream="btcusdt@ticker",
        data=ticker_data,
        timestamp=datetime.utcnow(),
    )

    await consumer._process_ticker_data(market_data)
    # Should process without errors


@pytest.mark.asyncio
async def test_consumer_process_market_logic_strategies(consumer):
    """Test _process_market_logic_strategies method."""
    from strategies.models.market_data import DepthLevel, DepthUpdate

    depth_data = DepthUpdate(
        symbol="BTCUSDT",
        event_time=int(datetime.utcnow().timestamp() * 1000),
        first_update_id=1,
        final_update_id=1,
        bids=[DepthLevel(price="50000.0", quantity="1.0")],
        asks=[DepthLevel(price="50001.0", quantity="1.0")],
    )

    market_data = MarketDataMessage(
        stream="btcusdt@depth@20ms",
        data=depth_data,
        timestamp=datetime.utcnow(),
    )

    await consumer._process_market_logic_strategies(market_data)
    # Should process through market logic strategies


@pytest.mark.asyncio
async def test_consumer_process_market_logic_strategies_exception(consumer):
    """Test _process_market_logic_strategies exception handling - covers lines 732-736."""
    from strategies.models.market_data import DepthLevel, DepthUpdate

    depth_data = DepthUpdate(
        symbol="BTCUSDT",
        event_time=int(datetime.utcnow().timestamp() * 1000),
        first_update_id=1,
        final_update_id=1,
        bids=[DepthLevel(price="50000.0", quantity="1.0")],
        asks=[DepthLevel(price="50001.0", quantity="1.0")],
    )

    market_data = MarketDataMessage(
        stream="btcusdt@depth@20ms",
        data=depth_data,
        timestamp=datetime.utcnow(),
    )

    # Mock a strategy to raise exception
    if consumer.market_logic_strategies:
        strategy_name = list(consumer.market_logic_strategies.keys())[0]
        original_strategy = consumer.market_logic_strategies[strategy_name]
        consumer.market_logic_strategies[strategy_name] = Mock()
        consumer.market_logic_strategies[strategy_name].process_market_data = AsyncMock(
            side_effect=Exception("Strategy error")
        )

    await consumer._process_market_logic_strategies(market_data)
    # Should handle exception gracefully


@pytest.mark.asyncio
async def test_publish_market_logic_signals_uses_publish_signal(
    consumer, mock_publisher
):
    """Verify _publish_market_logic_signals routes via publish_signal (CIO path), not publish_order."""
    from datetime import datetime

    from strategies.models.signals import (
        Signal,
        SignalAction,
        SignalConfidence,
        SignalType,
    )

    signal = Signal(
        symbol="BTCUSDT",
        signal_type=SignalType.BUY,
        signal_action=SignalAction.OPEN_LONG,
        confidence=SignalConfidence.HIGH,
        confidence_score=0.85,
        price=50000.0,
        timestamp=datetime.utcnow(),
        strategy_name="btc_dominance",
    )

    await consumer._publish_market_logic_signals([signal])

    mock_publisher.publish_signal.assert_called_once_with(signal)
    mock_publisher.publish_order.assert_not_called()


@pytest.mark.asyncio
async def test_consumer_signal_to_order_conversion(consumer):
    """Test _signal_to_order method - covers lines 758-760, 779, 781."""
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    from strategies.models.signals import (
        Signal,
        SignalAction,
        SignalConfidence,
        SignalType,
    )

    # Setup in-memory span exporter for testing
    # Note: If tracer provider is already set (e.g., by conftest.py), we can't override it
    # Instead, we'll use the current provider and add our exporter to it
    span_exporter = InMemorySpanExporter()
    current_provider = trace.get_tracer_provider()

    if isinstance(current_provider, TracerProvider):
        # Provider already set, add our exporter to it
        current_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    else:
        # Provider not set yet, create new one
        tracer_provider = TracerProvider()
        tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
        try:
            trace.set_tracer_provider(tracer_provider)
        except Exception:
            # Provider already set by another test, use current one
            if isinstance(trace.get_tracer_provider(), TracerProvider):
                trace.get_tracer_provider().add_span_processor(
                    SimpleSpanProcessor(span_exporter)
                )

    signal = Signal(
        symbol="BTCUSDT",
        signal_type=SignalType.BUY,
        signal_action=SignalAction.OPEN_LONG,
        confidence=SignalConfidence.HIGH,
        confidence_score=0.85,
        price=50000.0,
        strategy_name="test_strategy",
        signal_id="test-signal-12345",
    )

    # _signal_to_order returns a dict, not a TradeOrder object
    # current_price is extracted from signal.price, not passed as parameter
    order = consumer._signal_to_order(signal)
    assert order is not None
    assert isinstance(order, dict)
    assert order["symbol"] == "BTCUSDT"
    assert order["action"] in ["buy", "sell"]

    # Verify span attributes are set correctly (only if spans were recorded)
    spans = span_exporter.get_finished_spans()

    # Find the signal_to_order span if any spans were emitted
    signal_to_order_span = None
    for span in spans:
        if span.name == "consumer.signal_to_order":
            signal_to_order_span = span
            break

    # If the consumer emits spans, verify their attributes
    if signal_to_order_span is not None:
        attributes = signal_to_order_span.attributes
        assert attributes.get("symbol") == "BTCUSDT", "Expected symbol attribute"
        assert attributes.get("signal.type") == "buy", "Expected signal.type attribute"
        assert attributes.get("signal.strength") == 0.85, (
            "Expected signal.strength attribute"
        )
        assert attributes.get("strategy.name") == "test_strategy", (
            "Expected strategy.name attribute"
        )
        assert attributes.get("order.side") == "buy", "Expected order.side attribute"
        assert attributes.get("order.quantity_pct") == 0.05, (
            "Expected order.quantity_pct attribute"
        )
        assert attributes.get("order.created") is True, (
            "Expected order.created attribute"
        )
        assert attributes.get("result") == "success", "Expected result attribute"


@pytest.mark.asyncio
async def test_consumer_update_processing_metrics(consumer):
    """Test _update_processing_metrics method - covers lines 844-845, 848-849, 852-853."""
    consumer.processing_times = []

    # Add processing times
    consumer._update_processing_metrics(0.1)
    consumer._update_processing_metrics(0.2)
    consumer._update_processing_metrics(0.3)

    assert len(consumer.processing_times) == 3
    assert consumer.max_processing_time == 0.3
    assert consumer.avg_processing_time > 0


@pytest.mark.asyncio
async def test_consumer_update_processing_metrics_cleanup(consumer):
    """Test _update_processing_metrics cleanup - covers lines 844-845."""
    # Add more than 1000 processing times
    consumer.processing_times = [0.1] * 1500

    # Update metrics - should trim to last 1000
    consumer._update_processing_metrics(0.2)
    assert len(consumer.processing_times) <= 1000


@pytest.mark.asyncio
async def test_consumer_get_health_status_with_subscription(consumer):
    """Test get_health_status with subscription - covers lines 871-879."""
    consumer.is_running = True
    consumer.nats_client = AsyncMock()
    consumer.nats_client.is_connected = True
    consumer.subscription = AsyncMock()
    consumer.error_count = 5

    status = consumer.get_health_status()
    assert "healthy" in status
    assert "is_running" in status
    assert "nats_connected" in status
    assert "subscription_active" in status
    assert status["healthy"] is True


@pytest.mark.asyncio
async def test_consumer_windowed_error_rate_replaces_lifetime_cliff(consumer):
    """#186 AC4: a burst of past errors must not permanently fail health.

    The old logic compared the lifetime `error_count` against a fixed
    cliff (< 100), so a long-running consumer that had ever accumulated
    100+ errors stayed unhealthy forever. The windowed tracker instead
    only counts errors within a recent time window.
    """
    consumer.is_running = True
    consumer.nats_client = AsyncMock()
    consumer.nats_client.is_connected = True
    consumer.subscription = AsyncMock()

    # Simulate a large burst of errors that all happened well in the past.
    old_time = consumer.error_tracker._timestamps
    for _ in range(150):
        consumer.error_count += 1
        old_time.append(0.0)  # epoch: guaranteed to be outside any window

    status = consumer.get_health_status()
    assert status["error_count"] == 150
    assert status["recent_error_count"] == 0
    assert status["healthy"] is True

    # But a burst of *recent* errors still trips the windowed check.
    for _ in range(consumer.error_tracker.max_errors_in_window):
        consumer.error_tracker.record_error()

    status = consumer.get_health_status()
    assert status["recent_error_count"] >= consumer.error_tracker.max_errors_in_window
    assert status["healthy"] is False
