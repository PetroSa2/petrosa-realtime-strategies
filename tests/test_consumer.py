"""
Tests for strategies/core/consumer.py - focused on testable methods.
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from strategies.models.market_data import (
    DepthLevel,
    DepthUpdate,
    MarketDataMessage,
    TickerData,
    TradeData,
)


class TestMarketDataTransformation:
    """Test market data transformation methods."""

    @pytest.fixture
    def consumer_for_transform(self):
        """Create minimal consumer for transformation tests."""
        from strategies.core.consumer import NATSConsumer

        mock_publisher = AsyncMock()
        consumer = object.__new__(NATSConsumer)
        consumer.logger = MagicMock()
        return consumer

    def test_transform_ticker_data(self, consumer_for_transform):
        """Test ticker data transformation."""
        raw_data = {
            "s": "BTCUSDT",
            "p": "1000.00",
            "P": "2.00",
            "w": "50000.00",
            "x": "49000.00",
            "c": "50000.00",
            "Q": "0.1",
            "b": "49900.00",
            "B": "10.0",
            "a": "50100.00",
            "A": "10.0",
            "o": "48000.00",
            "h": "51000.00",
            "l": "47000.00",
            "v": "100.0",
            "q": "5000000.00",
            "O": 1640995200000,
            "C": 1641081600000,
            "F": 1,
            "L": 100,
            "n": 100,
            "E": 1641081600000,
        }

        result = consumer_for_transform._transform_ticker_data(raw_data)

        assert result is not None
        assert isinstance(result, TickerData)
        assert result.symbol == "BTCUSDT"
        assert result.last_price == "50000.00"
        assert result.volume == "100.0"

    def test_transform_trade_data(self, consumer_for_transform):
        """Test trade data transformation."""
        raw_data = {
            "s": "BTCUSDT",
            "t": 123456,
            "p": "50000.00",
            "q": "0.1",
            "b": 1001,
            "a": 1002,
            "T": 1640995200000,
            "m": True,
            "E": 1640995200000,
        }

        result = consumer_for_transform._transform_trade_data(raw_data)

        assert result is not None
        assert isinstance(result, TradeData)
        assert result.symbol == "BTCUSDT"
        assert result.price == "50000.00"
        assert result.quantity == "0.1"
        assert result.is_buyer_maker is True

    def test_transform_depth_data(self, consumer_for_transform):
        """Test depth data transformation."""
        raw_data = {
            "s": "BTCUSDT",
            "E": 1640995200000,
            "U": 1000,
            "u": 1001,
            "bids": [["50000.00", "1.0"], ["49999.00", "2.0"]],
            "asks": [["50001.00", "1.0"], ["50002.00", "2.0"]],
        }

        result = consumer_for_transform._transform_depth_data(raw_data)

        assert result is not None
        assert isinstance(result, DepthUpdate)
        assert result.symbol == "BTCUSDT"
        assert len(result.bids) == 2
        assert len(result.asks) == 2
        assert result.first_update_id == 1000
        assert result.final_update_id == 1001

    def test_transform_ticker_data_missing_fields(self, consumer_for_transform):
        """Test ticker transformation with missing fields."""
        raw_data = {
            "s": "BTCUSDT",
            "c": "50000.00",
        }

        result = consumer_for_transform._transform_ticker_data(raw_data)

        # Should handle gracefully or return None
        assert result is None or isinstance(result, TickerData)

    def test_transform_trade_data_missing_fields(self, consumer_for_transform):
        """Test trade transformation with missing fields."""
        raw_data = {
            "s": "BTCUSDT",
            "p": "50000.00",
        }

        result = consumer_for_transform._transform_trade_data(raw_data)

        # Should handle gracefully or return None
        assert result is None or isinstance(result, TradeData)

    def test_transform_depth_data_empty_orderbook(self, consumer_for_transform):
        """Test depth transformation with empty orderbook."""
        raw_data = {
            "s": "BTCUSDT",
            "E": 1640995200000,
            "U": 1000,
            "u": 1001,
            "bids": [],
            "asks": [],
        }

        result = consumer_for_transform._transform_depth_data(raw_data)

        assert result is not None
        assert isinstance(result, DepthUpdate)
        assert len(result.bids) == 0
        assert len(result.asks) == 0

    def test_parse_market_data_ticker(self, consumer_for_transform):
        """Test parsing complete ticker message."""
        message_data = {
            "stream": "btcusdt@ticker",
            "data": {
                "s": "BTCUSDT",
                "p": "1000.00",
                "P": "2.00",
                "w": "50000.00",
                "x": "49000.00",
                "c": "50000.00",
                "Q": "0.1",
                "b": "49900.00",
                "B": "10.0",
                "a": "50100.00",
                "A": "10.0",
                "o": "48000.00",
                "h": "51000.00",
                "l": "47000.00",
                "v": "100.0",
                "q": "5000000.00",
                "O": 1640995200000,
                "C": 1641081600000,
                "F": 1,
                "L": 100,
                "n": 100,
                "E": 1641081600000,
            },
        }

        result = consumer_for_transform._parse_market_data(message_data)

        assert result is not None
        assert result.stream == "btcusdt@ticker"
        assert isinstance(result.data, TickerData)

    def test_parse_market_data_trade(self, consumer_for_transform):
        """Test parsing complete trade message."""
        message_data = {
            "stream": "btcusdt@trade",
            "data": {
                "s": "BTCUSDT",
                "t": 123456,
                "p": "50000.00",
                "q": "0.1",
                "b": 1001,
                "a": 1002,
                "T": 1640995200000,
                "m": True,
                "E": 1640995200000,
            },
        }

        result = consumer_for_transform._parse_market_data(message_data)

        assert result is not None
        assert result.stream == "btcusdt@trade"
        assert isinstance(result.data, TradeData)

    def test_parse_market_data_depth(self, consumer_for_transform):
        """Test parsing complete depth message."""
        message_data = {
            "stream": "btcusdt@depth",
            "data": {
                "s": "BTCUSDT",
                "E": 1640995200000,
                "U": 1000,
                "u": 1001,
                "bids": [["50000.00", "1.0"]],
                "asks": [["50001.00", "1.0"]],
            },
        }

        result = consumer_for_transform._parse_market_data(message_data)

        assert result is not None
        assert result.stream == "btcusdt@depth"
        assert isinstance(result.data, DepthUpdate)

    def test_parse_market_data_invalid(self, consumer_for_transform):
        """Test parsing invalid message."""
        message_data = {"invalid": "data"}

        result = consumer_for_transform._parse_market_data(message_data)

        assert result is None

    def test_parse_market_data_unknown_stream(self, consumer_for_transform):
        """Test parsing unknown stream type."""
        message_data = {
            "stream": "btcusdt@unknown",
            "data": {"test": "data"},
        }

        result = consumer_for_transform._parse_market_data(message_data)

        assert result is None


class TestConsumerAsyncProcessing:
    """Test consumer async processing methods."""

    @pytest.fixture
    def async_consumer(self):
        """Create minimal consumer for async tests."""
        from unittest.mock import AsyncMock, MagicMock

        from strategies.core.consumer import NATSConsumer

        mock_publisher = AsyncMock()
        consumer = object.__new__(NATSConsumer)
        consumer.logger = MagicMock()
        consumer.depth_analyzer = MagicMock()
        consumer.microstructure_strategies = {}
        consumer.market_logic_strategies = {}
        consumer.publisher = mock_publisher
        consumer.metrics = MagicMock()
        return consumer

    @pytest.mark.asyncio
    async def test_process_market_data_depth(self, async_consumer):
        """Test processing depth market data."""
        message = MarketDataMessage(
            stream="btcusdt@depth",
            data=DepthUpdate(
                symbol="BTCUSDT",
                event_time=1640995200000,
                first_update_id=1000,
                final_update_id=1001,
                bids=[DepthLevel(price="50000.00", quantity="1.0")],
                asks=[DepthLevel(price="50001.00", quantity="1.0")],
            ),
        )

        # Should not raise exception
        await async_consumer._process_market_data(message)

    @pytest.mark.asyncio
    async def test_process_market_data_trade(self, async_consumer):
        """Test processing trade market data."""
        message = MarketDataMessage(
            stream="btcusdt@trade",
            data=TradeData(
                symbol="BTCUSDT",
                trade_id=123456,
                price="50000.00",
                quantity="0.1",
                buyer_order_id=1001,
                seller_order_id=1002,
                trade_time=1640995200000,
                is_buyer_maker=True,
                event_time=1640995200000,
            ),
        )

        # Should not raise exception
        await async_consumer._process_market_data(message)

    @pytest.mark.asyncio
    async def test_process_market_data_ticker(self, async_consumer):
        """Test processing ticker market data."""
        message = MarketDataMessage(
            stream="btcusdt@ticker",
            data=TickerData(
                symbol="BTCUSDT",
                price_change="1000.00",
                price_change_percent="2.00",
                weighted_avg_price="50000.00",
                prev_close_price="49000.00",
                last_price="50000.00",
                last_qty="0.1",
                bid_price="49900.00",
                bid_qty="10.0",
                ask_price="50100.00",
                ask_qty="10.0",
                open_price="48000.00",
                high_price="51000.00",
                low_price="47000.00",
                volume="100.0",
                quote_volume="5000000.00",
                open_time=1640995200000,
                close_time=1641081600000,
                first_id=1,
                last_id=100,
                count=100,
                event_time=1641081600000,
            ),
        )

        # Should not raise exception
        await async_consumer._process_market_data(message)

    @pytest.mark.asyncio
    async def test_process_depth_data_directly(self, async_consumer):
        """Test _process_depth_data method."""
        message = MarketDataMessage(
            stream="btcusdt@depth",
            data=DepthUpdate(
                symbol="BTCUSDT",
                event_time=1640995200000,
                first_update_id=1000,
                final_update_id=1001,
                bids=[DepthLevel(price="50000.00", quantity="1.0")],
                asks=[DepthLevel(price="50001.00", quantity="1.0")],
            ),
        )

        # Should not raise exception
        await async_consumer._process_depth_data(message)

    @pytest.mark.asyncio
    async def test_process_trade_data_directly(self, async_consumer):
        """Test _process_trade_data method."""
        message = MarketDataMessage(
            stream="btcusdt@trade",
            data=TradeData(
                symbol="BTCUSDT",
                trade_id=123456,
                price="50000.00",
                quantity="0.1",
                buyer_order_id=1001,
                seller_order_id=1002,
                trade_time=1640995200000,
                is_buyer_maker=True,
                event_time=1640995200000,
            ),
        )

        # Should not raise exception
        await async_consumer._process_trade_data(message)

    @pytest.mark.asyncio
    async def test_process_ticker_data_directly(self, async_consumer):
        """Test _process_ticker_data method."""
        message = MarketDataMessage(
            stream="btcusdt@ticker",
            data=TickerData(
                symbol="BTCUSDT",
                price_change="1000.00",
                price_change_percent="2.00",
                weighted_avg_price="50000.00",
                prev_close_price="49000.00",
                last_price="50000.00",
                last_qty="0.1",
                bid_price="49900.00",
                bid_qty="10.0",
                ask_price="50100.00",
                ask_qty="10.0",
                open_price="48000.00",
                high_price="51000.00",
                low_price="47000.00",
                volume="100.0",
                quote_volume="5000000.00",
                open_time=1640995200000,
                close_time=1641081600000,
                first_id=1,
                last_id=100,
                count=100,
                event_time=1641081600000,
            ),
        )

        # Should not raise exception
        await async_consumer._process_ticker_data(message)

    @pytest.mark.asyncio
    async def test_process_microstructure_strategies(self, async_consumer):
        """Test _process_microstructure_strategies method."""
        from unittest.mock import AsyncMock

        # Setup microstructure strategies
        async_consumer.microstructure_strategies = {
            "spread_liquidity": AsyncMock(),
            "iceberg_detector": AsyncMock(),
        }

        bids = [(50000.0, 1.0), (49999.0, 1.5)]
        asks = [(50001.0, 1.0), (50002.0, 1.5)]

        # Should not raise exception
        await async_consumer._process_microstructure_strategies(
            symbol="BTCUSDT", bids=bids, asks=asks
        )

    @pytest.mark.asyncio
    async def test_process_market_logic_strategies(self, async_consumer):
        """Test _process_market_logic_strategies method."""
        from unittest.mock import AsyncMock, MagicMock

        # Setup market logic strategies
        async_consumer.market_logic_strategies = {
            "btc_dominance": AsyncMock(),
            "cross_exchange_spread": AsyncMock(),
            "onchain_metrics": AsyncMock(),
        }
        async_consumer.metrics.start_operation = MagicMock()
        async_consumer.metrics.record_error = MagicMock()

        message = MarketDataMessage(
            stream="btcusdt@ticker",
            data=TickerData(
                symbol="BTCUSDT",
                price_change="1000.00",
                price_change_percent="2.00",
                weighted_avg_price="50000.00",
                prev_close_price="49000.00",
                last_price="50000.00",
                last_qty="0.1",
                bid_price="49900.00",
                bid_qty="10.0",
                ask_price="50100.00",
                ask_qty="10.0",
                open_price="48000.00",
                high_price="51000.00",
                low_price="47000.00",
                volume="100.0",
                quote_volume="5000000.00",
                open_time=1640995200000,
                close_time=1641081600000,
                first_id=1,
                last_id=100,
                count=100,
                event_time=1641081600000,
            ),
        )

        # Should not raise exception
        await async_consumer._process_market_logic_strategies(message)
