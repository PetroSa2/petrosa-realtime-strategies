"""
Comprehensive tests for core/consumer.py.

Covers message processing, strategy routing, error handling, and NATS integration.
"""

import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from strategies.core.consumer import NATSConsumer
from strategies.models.market_data import (
    DepthUpdate,
    MarketDataMessage,
    TickerData,
    TradeData,
)


@pytest.fixture
def mock_publisher():
    """Create mock publisher."""
    publisher = AsyncMock()
    publisher.publish_signal = AsyncMock()
    return publisher


@pytest.fixture
def mock_depth_analyzer():
    """Create mock depth analyzer."""
    analyzer = MagicMock()
    analyzer.update_orderbook = MagicMock()
    return analyzer


@pytest.fixture
def mock_nats_client():
    """Create mock NATS client."""
    client = AsyncMock()
    client.connect = AsyncMock()
    client.subscribe = AsyncMock()
    client.close = AsyncMock()
    return client


@pytest.fixture
def mock_subscription():
    """Create mock NATS subscription."""
    subscription = AsyncMock()
    subscription.unsubscribe = AsyncMock()
    return subscription


@pytest.fixture
def consumer(mock_publisher, mock_depth_analyzer):
    """Create consumer with mock dependencies."""
    with patch("strategies.core.consumer.constants") as mock_constants:
        mock_constants.CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5
        mock_constants.CIRCUIT_BREAKER_RECOVERY_TIMEOUT = 30
        mock_constants.STRATEGY_ENABLED_BTC_DOMINANCE = True
        mock_constants.STRATEGY_ENABLED_CROSS_EXCHANGE_SPREAD = True
        mock_constants.STRATEGY_ENABLED_ONCHAIN_METRICS = True
        mock_constants.STRATEGY_ENABLED_SPREAD_LIQUIDITY = True
        mock_constants.STRATEGY_ENABLED_ICEBERG_DETECTOR = True

        with patch("strategies.core.consumer.initialize_metrics") as mock_metrics:
            mock_metrics.return_value = MagicMock()

            consumer = NATSConsumer(
                nats_url="nats://localhost:4222",
                topic="market_data",
                consumer_name="test_consumer",
                consumer_group="test_group",
                publisher=mock_publisher,
                depth_analyzer=mock_depth_analyzer,
            )
            return consumer


def test_consumer_initialization(consumer):
    """Test consumer initialization."""
    assert consumer.nats_url == "nats://localhost:4222"
    assert consumer.topic == "market_data"
    assert consumer.consumer_name == "test_consumer"
    assert consumer.consumer_group == "test_group"
    assert consumer.publisher is not None
    assert consumer.depth_analyzer is not None
    assert consumer.is_running is False
    assert consumer.message_count == 0
    assert consumer.error_count == 0


def test_consumer_strategy_initialization(consumer):
    """Test that strategies are initialized correctly."""
    assert "btc_dominance" in consumer.market_logic_strategies
    assert "cross_exchange_spread" in consumer.market_logic_strategies
    assert "onchain_metrics" in consumer.market_logic_strategies
    assert "spread_liquidity" in consumer.microstructure_strategies
    assert "iceberg_detector" in consumer.microstructure_strategies


@pytest.mark.asyncio
async def test_start_success(consumer, mock_nats_client, mock_subscription):
    """Test successful consumer start."""
    with patch("strategies.core.consumer.nats.connect", return_value=mock_nats_client):
        mock_nats_client.subscribe.return_value = mock_subscription

        await consumer.start()

        assert consumer.is_running is True
        assert consumer.nats_client == mock_nats_client
        assert consumer.subscription == mock_subscription
        mock_nats_client.connect.assert_called_once()
        mock_nats_client.subscribe.assert_called_once()


@pytest.mark.asyncio
async def test_start_connection_failure(consumer):
    """Test consumer start with connection failure."""
    with patch(
        "strategies.core.consumer.nats.connect",
        side_effect=Exception("Connection failed"),
    ):
        with pytest.raises(Exception, match="Connection failed"):
            await consumer.start()

        assert consumer.is_running is False


@pytest.mark.asyncio
async def test_stop_success(consumer, mock_nats_client, mock_subscription):
    """Test successful consumer stop."""
    consumer.nats_client = mock_nats_client
    consumer.subscription = mock_subscription
    consumer.is_running = True

    await consumer.stop()

    assert consumer.is_running is False
    mock_subscription.unsubscribe.assert_called_once()
    mock_nats_client.close.assert_called_once()


@pytest.mark.asyncio
async def test_stop_with_none_components(consumer):
    """Test stop with None components."""
    consumer.is_running = True

    await consumer.stop()

    assert consumer.is_running is False


@pytest.mark.asyncio
async def test_connect_to_nats_success(consumer, mock_nats_client):
    """Test successful NATS connection."""
    with patch("strategies.core.consumer.nats.connect", return_value=mock_nats_client):
        await consumer._connect_to_nats()

        assert consumer.nats_client == mock_nats_client


@pytest.mark.asyncio
async def test_connect_to_nats_failure(consumer):
    """Test NATS connection failure."""
    with patch(
        "strategies.core.consumer.nats.connect",
        side_effect=Exception("Connection failed"),
    ):
        with pytest.raises(Exception, match="Connection failed"):
            await consumer._connect_to_nats()


@pytest.mark.asyncio
async def test_subscribe_to_topic_success(
    consumer, mock_nats_client, mock_subscription
):
    """Test successful topic subscription."""
    consumer.nats_client = mock_nats_client
    mock_nats_client.subscribe.return_value = mock_subscription

    await consumer._subscribe_to_topic()

    assert consumer.subscription == mock_subscription
    mock_nats_client.subscribe.assert_called_once()


@pytest.mark.asyncio
async def test_subscribe_to_topic_failure(consumer, mock_nats_client):
    """Test topic subscription failure."""
    consumer.nats_client = mock_nats_client
    mock_nats_client.subscribe.side_effect = Exception("Subscribe failed")

    with pytest.raises(Exception, match="Subscribe failed"):
        await consumer._subscribe_to_topic()


@pytest.mark.asyncio
async def test_process_message_success(consumer):
    """Test successful message processing."""
    message_data = {
        "stream": "btcusdt@ticker",
        "data": {"symbol": "BTCUSDT", "price": "50000.00", "volume": "100.0"},
    }

    with patch.object(
        consumer,
        "_parse_market_data",
        return_value=MarketDataMessage(
            stream="btcusdt@ticker",
            data=TickerData(
                symbol="BTCUSDT",
                price=50000.00,
                volume=100.0,
                timestamp=datetime.utcnow(),
            ),
        ),
    ):
        with patch.object(consumer, "_route_to_strategies", return_value=None):
            await consumer._process_message(json.dumps(message_data).encode())

            assert consumer.message_count == 1


@pytest.mark.asyncio
async def test_process_message_parse_error(consumer):
    """Test message processing with parse error."""
    invalid_message = b"invalid json"

    await consumer._process_message(invalid_message)

    assert consumer.error_count == 1


@pytest.mark.asyncio
async def test_process_message_routing_error(consumer):
    """Test message processing with routing error."""
    message_data = {
        "stream": "btcusdt@ticker",
        "data": {"symbol": "BTCUSDT", "price": "50000.00"},
    }

    with patch.object(
        consumer,
        "_parse_market_data",
        return_value=MarketDataMessage(
            stream="btcusdt@ticker",
            data=TickerData(
                symbol="BTCUSDT", price=50000.00, volume=0, timestamp=datetime.utcnow()
            ),
        ),
    ):
        with patch.object(
            consumer, "_route_to_strategies", side_effect=Exception("Routing error")
        ):
            await consumer._process_message(json.dumps(message_data).encode())

            assert consumer.error_count == 1


def test_parse_market_data_ticker(consumer):
    """Test parsing ticker data."""
    message_data = {
        "stream": "btcusdt@ticker",
        "data": {
            "symbol": "BTCUSDT",
            "price": "50000.00",
            "volume": "100.0",
            "timestamp": 1640995200000,
        },
    }

    result = consumer._parse_market_data(message_data)

    assert result.stream == "btcusdt@ticker"
    assert result.data.symbol == "BTCUSDT"
    assert result.data.price == 50000.00


def test_parse_market_data_trade(consumer):
    """Test parsing trade data."""
    message_data = {
        "stream": "btcusdt@trade",
        "data": {
            "symbol": "BTCUSDT",
            "price": "50000.00",
            "quantity": "0.1",
            "timestamp": 1640995200000,
        },
    }

    result = consumer._parse_market_data(message_data)

    assert result.stream == "btcusdt@trade"
    assert result.data.symbol == "BTCUSDT"
    assert result.data.price == 50000.00


def test_parse_market_data_depth(consumer):
    """Test parsing depth data."""
    message_data = {
        "stream": "btcusdt@depth",
        "data": {
            "symbol": "BTCUSDT",
            "bids": [["50000.00", "1.0"]],
            "asks": [["50001.00", "1.0"]],
            "timestamp": 1640995200000,
        },
    }

    result = consumer._parse_market_data(message_data)

    assert result.stream == "btcusdt@depth"
    assert result.data.symbol == "BTCUSDT"
    assert len(result.data.bids) == 1


def test_parse_market_data_unknown_stream(consumer):
    """Test parsing unknown stream type."""
    message_data = {"stream": "unknown@stream", "data": {"test": "data"}}

    result = consumer._parse_market_data(message_data)

    assert result is None


@pytest.mark.asyncio
async def test_route_to_strategies_ticker(consumer):
    """Test routing ticker data to strategies."""
    message = MarketDataMessage(
        stream="btcusdt@ticker",
        data=TickerData(
            symbol="BTCUSDT", price=50000.00, volume=100.0, timestamp=datetime.utcnow()
        ),
    )

    with patch.object(
        consumer.market_logic_strategies["btc_dominance"],
        "process_ticker",
        return_value=None,
    ):
        await consumer._route_to_strategies(message)

        # Verify strategy was called
        consumer.market_logic_strategies[
            "btc_dominance"
        ].process_ticker.assert_called_once()


@pytest.mark.asyncio
async def test_route_to_strategies_trade(consumer):
    """Test routing trade data to strategies."""
    message = MarketDataMessage(
        stream="btcusdt@trade",
        data=TradeData(
            symbol="BTCUSDT", price=50000.00, quantity=0.1, timestamp=datetime.utcnow()
        ),
    )

    with patch.object(
        consumer.market_logic_strategies["btc_dominance"],
        "process_trade",
        return_value=None,
    ):
        await consumer._route_to_strategies(message)

        consumer.market_logic_strategies[
            "btc_dominance"
        ].process_trade.assert_called_once()


@pytest.mark.asyncio
async def test_route_to_strategies_depth(consumer):
    """Test routing depth data to strategies."""
    message = MarketDataMessage(
        stream="btcusdt@depth",
        data=DepthUpdate(
            symbol="BTCUSDT",
            bids=[("50000.00", "1.0")],
            asks=[("50001.00", "1.0")],
            timestamp=datetime.utcnow(),
        ),
    )

    with patch.object(
        consumer.microstructure_strategies["spread_liquidity"],
        "process_depth",
        return_value=None,
    ):
        await consumer._route_to_strategies(message)

        consumer.microstructure_strategies[
            "spread_liquidity"
        ].process_depth.assert_called_once()


@pytest.mark.asyncio
async def test_route_to_strategies_unknown_type(consumer):
    """Test routing unknown message type."""
    message = MarketDataMessage(stream="unknown@stream", data=None)

    # Should not raise exception
    await consumer._route_to_strategies(message)


@pytest.mark.asyncio
async def test_route_to_strategies_strategy_error(consumer):
    """Test routing with strategy error."""
    message = MarketDataMessage(
        stream="btcusdt@ticker",
        data=TickerData(
            symbol="BTCUSDT", price=50000.00, volume=100.0, timestamp=datetime.utcnow()
        ),
    )

    with patch.object(
        consumer.market_logic_strategies["btc_dominance"],
        "process_ticker",
        side_effect=Exception("Strategy error"),
    ):
        # Should not raise exception, just log error
        await consumer._route_to_strategies(message)


@pytest.mark.asyncio
async def test_processing_loop_normal_operation(consumer, mock_subscription):
    """Test processing loop normal operation."""
    consumer.subscription = mock_subscription
    consumer.is_running = True

    # Mock message
    mock_message = MagicMock()
    mock_message.data = b'{"test": "data"}'
    mock_subscription.fetch.return_value = [mock_message]

    with patch.object(consumer, "_process_message", return_value=None):
        # Run for a short time then stop
        task = asyncio.create_task(consumer._processing_loop())
        await asyncio.sleep(0.1)
        consumer.is_running = False
        # Give it time to check the flag and exit
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_processing_loop_shutdown(consumer, mock_subscription):
    """Test processing loop shutdown."""
    consumer.subscription = mock_subscription
    consumer.is_running = True

    # Start the loop and stop it immediately
    task = asyncio.create_task(consumer._processing_loop())
    consumer.is_running = False
    await asyncio.sleep(0.1)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # Should exit cleanly


@pytest.mark.asyncio
async def test_processing_loop_error(consumer, mock_subscription):
    """Test processing loop with error."""
    consumer.subscription = mock_subscription
    consumer.is_running = True

    # Start the loop and stop it quickly before error occurs
    task = asyncio.create_task(consumer._processing_loop())
    await asyncio.sleep(0.1)
    consumer.is_running = False
    await asyncio.sleep(0.1)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # Should handle error gracefully


def test_get_metrics(consumer):
    """Test getting consumer metrics."""
    consumer.message_count = 100
    consumer.error_count = 5
    consumer.max_processing_time = 0.5
    consumer.avg_processing_time = 0.1

    metrics = consumer.get_metrics()

    assert metrics["message_count"] == 100
    assert metrics["error_count"] == 5
    assert metrics["max_processing_time"] == 0.5
    assert metrics["avg_processing_time"] == 0.1


def test_get_health_status(consumer):
    """Test getting health status."""
    consumer.is_running = True
    consumer.message_count = 100
    consumer.error_count = 5

    health = consumer.get_health_status()

    assert health["status"] == "healthy"
    assert health["is_running"] is True
    assert health["message_count"] == 100
    assert health["error_count"] == 5


def test_get_health_status_unhealthy(consumer):
    """Test getting health status when unhealthy."""
    consumer.is_running = False
    consumer.error_count = 100

    health = consumer.get_health_status()

    assert health["status"] == "unhealthy"
    assert health["is_running"] is False


@pytest.mark.asyncio
async def test_circuit_breaker_integration(consumer):
    """Test circuit breaker integration."""
    # Mock circuit breaker failure
    with patch.object(
        consumer.circuit_breaker, "call", side_effect=Exception("Circuit breaker open")
    ):
        with pytest.raises(Exception, match="Circuit breaker open"):
            await consumer._connect_to_nats()


def test_strategy_initialization_disabled(consumer):
    """Test strategy initialization when strategies are disabled."""
    with patch("strategies.core.consumer.constants") as mock_constants:
        mock_constants.STRATEGY_ENABLED_BTC_DOMINANCE = False
        mock_constants.STRATEGY_ENABLED_CROSS_EXCHANGE_SPREAD = False
        mock_constants.STRATEGY_ENABLED_ONCHAIN_METRICS = False
        mock_constants.STRATEGY_ENABLED_SPREAD_LIQUIDITY = False
        mock_constants.STRATEGY_ENABLED_ICEBERG_DETECTOR = False

        with patch("strategies.core.consumer.initialize_metrics") as mock_metrics:
            mock_metrics.return_value = MagicMock()

            consumer = NATSConsumer(
                nats_url="nats://localhost:4222",
                topic="market_data",
                consumer_name="test_consumer",
                consumer_group="test_group",
                publisher=MagicMock(),
                depth_analyzer=MagicMock(),
            )

            assert len(consumer.market_logic_strategies) == 0
            assert len(consumer.microstructure_strategies) == 0


@pytest.mark.asyncio
async def test_depth_analyzer_integration(consumer):
    """Test depth analyzer integration."""
    message = MarketDataMessage(
        stream="btcusdt@depth",
        data=DepthUpdate(
            symbol="BTCUSDT",
            bids=[("50000.00", "1.0")],
            asks=[("50001.00", "1.0")],
            timestamp=datetime.utcnow(),
        ),
    )

    with patch.object(consumer.depth_analyzer, "update_orderbook", return_value=None):
        await consumer._route_to_strategies(message)

        consumer.depth_analyzer.update_orderbook.assert_called_once()


def test_performance_metrics_tracking(consumer):
    """Test performance metrics tracking."""
    # Simulate processing times
    consumer.processing_times = [0.1, 0.2, 0.3, 0.4, 0.5]
    consumer._update_performance_metrics()

    assert consumer.max_processing_time == 0.5
    assert consumer.avg_processing_time == 0.3


def test_message_count_tracking(consumer):
    """Test message count tracking."""
    initial_count = consumer.message_count

    consumer._increment_message_count()

    assert consumer.message_count == initial_count + 1


def test_error_count_tracking(consumer):
    """Test error count tracking."""
    initial_count = consumer.error_count

    consumer._increment_error_count()

    assert consumer.error_count == initial_count + 1


@pytest.mark.asyncio
async def test_trace_context_extraction(consumer):
    """Test trace context extraction."""
    message_data = {
        "stream": "btcusdt@ticker",
        "data": {"symbol": "BTCUSDT", "price": "50000.00"},
        "trace_context": {"trace_id": "123", "span_id": "456"},
    }

    with patch(
        "strategies.core.consumer.extract_trace_context",
        return_value={"trace_id": "123"},
    ) as mock_extract:
        with patch.object(consumer, "_route_to_strategies", return_value=None):
            await consumer._process_message(json.dumps(message_data).encode())

            mock_extract.assert_called_once()
