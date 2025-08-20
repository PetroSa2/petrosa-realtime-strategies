"""
Basic unit tests for Petrosa Realtime Strategies service.
"""

import pytest
from strategies.models.market_data import MarketDataMessage, DepthUpdate, TradeData, TickerData
from strategies.models.signals import Signal, SignalType, SignalAction, SignalConfidence
from strategies.models.orders import TradeOrder, OrderType, OrderSide, PositionType


class TestMarketDataModels:
    """Test market data models."""

    def test_depth_update_creation(self):
        """Test creating a depth update."""
        depth_data = {
            "symbol": "BTCUSDT",
            "event_time": 1234567890000,
            "first_update_id": 123456789,
            "final_update_id": 123456789,
            "bids": [{"price": "50000.00", "quantity": "1.0"}, {"price": "49999.00", "quantity": "2.0"}],
            "asks": [{"price": "50001.00", "quantity": "1.0"}, {"price": "50002.00", "quantity": "2.0"}]
        }
        
        depth_update = DepthUpdate(**depth_data)
        
        assert depth_update.symbol == "BTCUSDT"
        assert depth_update.event_time == 1234567890000
        assert len(depth_update.bids) == 2
        assert len(depth_update.asks) == 2
        assert depth_update.spread_percent > 0
        assert depth_update.mid_price == 50000.5

    def test_trade_data_creation(self):
        """Test creating trade data."""
        trade_data = {
            "symbol": "BTCUSDT",
            "trade_id": 123456789,
            "price": "50000.00",
            "quantity": "1.0",
            "buyer_order_id": 123456789,
            "seller_order_id": 123456790,
            "trade_time": 1234567890000,
            "is_buyer_maker": False,
            "event_time": 1234567890000
        }
        
        trade = TradeData(**trade_data)
        
        assert trade.symbol == "BTCUSDT"
        assert trade.price_float == 50000.0
        assert trade.quantity_float == 1.0
        assert trade.notional_value == 50000.0

    def test_ticker_data_creation(self):
        """Test creating ticker data."""
        ticker_data = {
            "symbol": "BTCUSDT",
            "price_change": "100.00",
            "price_change_percent": "0.2",
            "weighted_avg_price": "50000.00",
            "prev_close_price": "49900.00",
            "last_price": "50000.00",
            "last_qty": "1.0",
            "bid_price": "49999.00",
            "bid_qty": "1.0",
            "ask_price": "50001.00",
            "ask_qty": "1.0",
            "open_price": "49900.00",
            "high_price": "50100.00",
            "low_price": "49800.00",
            "volume": "1000.0",
            "quote_volume": "50000000.0",
            "open_time": 1234567890000,
            "close_time": 1234567890000,
            "first_id": 123456789,
            "last_id": 123456790,
            "count": 100,
            "event_time": 1234567890000
        }
        
        ticker = TickerData(**ticker_data)
        
        assert ticker.symbol == "BTCUSDT"
        assert ticker.price_change_float == 100.0
        assert ticker.price_change_percent_float == 0.2
        assert ticker.last_price_float == 50000.0


class TestSignalModels:
    """Test signal models."""

    def test_signal_creation(self):
        """Test creating a signal."""
        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.8,
            price=50000.0,
            strategy_name="test_strategy"
        )
        
        assert signal.symbol == "BTCUSDT"
        assert signal.signal_type == SignalType.BUY
        assert signal.is_buy_signal is True
        assert signal.is_high_confidence is True
        assert signal.confidence_score == 0.8

    def test_signal_validation(self):
        """Test signal validation."""
        # Test invalid confidence score
        with pytest.raises(ValueError):
            Signal(
                symbol="BTCUSDT",
                signal_type=SignalType.BUY,
                signal_action=SignalAction.OPEN_LONG,
                confidence=SignalConfidence.HIGH,
                confidence_score=1.5,  # Invalid: > 1.0
                price=50000.0,
                strategy_name="test_strategy"
            )


class TestOrderModels:
    """Test order models."""

    def test_trade_order_creation(self):
        """Test creating a trade order."""
        order = TradeOrder(
            order_id="test_order_123456789",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1.0,
            position_type=PositionType.LONG,
            strategy_name="test_strategy",
            signal_id="test_signal_123456789",
            confidence_score=0.8
        )
        
        assert order.symbol == "BTCUSDT"
        assert order.side == OrderSide.BUY
        assert order.order_type == OrderType.MARKET
        assert order.is_market_order is True
        assert order.is_buy_order is True
        assert order.is_long_position is True

    def test_order_validation(self):
        """Test order validation."""
        # Test invalid order ID
        with pytest.raises(ValueError):
            TradeOrder(
                order_id="short",  # Too short
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=1.0,
                position_type=PositionType.LONG,
                strategy_name="test_strategy",
                signal_id="test_signal_123456789",
                confidence_score=0.8
            )


class TestMarketDataMessage:
    """Test market data message wrapper."""

    def test_market_data_message_creation(self, sample_market_data):
        """Test creating a market data message."""
        message = MarketDataMessage(**sample_market_data)
        
        assert message.stream == "btcusdt@depth20"
        assert message.symbol == "BTCUSDT"
        assert message.stream_type == "depth20"
        assert message.is_depth is True
        assert message.is_trade is False
        assert message.is_ticker is False

    def test_market_data_message_validation(self):
        """Test market data message validation."""
        # Test invalid stream format
        with pytest.raises(ValueError):
            MarketDataMessage(
                stream="invalid_stream",
                data={}
            )
