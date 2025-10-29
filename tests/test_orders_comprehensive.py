"""
Comprehensive tests for Order models to achieve 90%+ coverage.

Current coverage: 73.44% → Target: 90%+
Focus on validator error paths and edge cases.
"""

import pytest
from datetime import datetime
from strategies.models.orders import (
    TradeOrder,
    OrderType,
    OrderSide,
    TimeInForce,
    PositionType,
)


class TestOrderEnums:
    """Test Order enum values."""

    def test_order_type_values(self):
        """Test OrderType enum values."""
        assert OrderType.MARKET == "MARKET"
        assert OrderType.LIMIT == "LIMIT"
        assert OrderType.STOP_MARKET == "STOP_MARKET"
        assert OrderType.STOP_LIMIT == "STOP_LIMIT"

    def test_order_side_values(self):
        """Test OrderSide enum values."""
        assert OrderSide.BUY == "BUY"
        assert OrderSide.SELL == "SELL"

    def test_time_in_force_values(self):
        """Test TimeInForce enum values."""
        assert TimeInForce.GTC == "GTC"
        assert TimeInForce.IOC == "IOC"
        assert TimeInForce.FOK == "FOK"

    def test_position_type_values(self):
        """Test PositionType enum values."""
        assert PositionType.LONG == "LONG"
        assert PositionType.SHORT == "SHORT"


class TestTradeOrderValidators:
    """Test TradeOrder validator error paths."""

    def test_validate_symbol_too_short(self):
        """Test symbol validator rejects short symbols - covers line 85."""
        with pytest.raises(ValueError, match="Invalid symbol format"):
            TradeOrder(
                order_id="order123456",
                symbol="BTC",  # Too short
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=0.1,
                position_type=PositionType.LONG,
                strategy_name="test",
                signal_id="signal123456",
                confidence_score=0.85
            )

    def test_validate_order_id_too_short(self):
        """Test order_id validator rejects short IDs - covers line 92."""
        with pytest.raises(ValueError, match="Order ID must be at least 10 characters"):
            TradeOrder(
                order_id="short",  # Too short
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=0.1,
                position_type=PositionType.LONG,
                strategy_name="test",
                signal_id="signal123456",
                confidence_score=0.85
            )

    def test_validate_signal_id_too_short(self):
        """Test signal_id validator rejects short IDs - covers line 99."""
        with pytest.raises(ValueError, match="Signal ID must be at least 10 characters"):
            TradeOrder(
                order_id="order123456",
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=0.1,
                position_type=PositionType.LONG,
                strategy_name="test",
                signal_id="short",  # Too short
                confidence_score=0.85
            )

    def test_validate_limit_order_requires_price(self):
        """Test LIMIT order validator requires price - covers lines 105-110."""
        with pytest.raises(ValueError, match="Price is required for LIMIT"):
            TradeOrder(
                order_id="order123456",
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,  # LIMIT order
                quantity=0.1,
                price=None,  # Missing price
                position_type=PositionType.LONG,
                strategy_name="test",
                signal_id="signal123456",
                confidence_score=0.85
            )

    def test_validate_stop_limit_order_requires_price(self):
        """Test STOP_LIMIT order validator requires price - covers lines 105-110."""
        with pytest.raises(ValueError, match="Price is required for"):
            TradeOrder(
                order_id="order123456",
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.STOP_LIMIT,  # STOP_LIMIT order
                quantity=0.1,
                price=None,  # Missing price
                stop_price=49000.0,
                position_type=PositionType.LONG,
                strategy_name="test",
                signal_id="signal123456",
                confidence_score=0.85
            )

    def test_validate_stop_market_order_requires_stop_price(self):
        """Test STOP_MARKET order validator requires stop_price - covers lines 115-120."""
        with pytest.raises(ValueError, match="Stop price is required for STOP"):
            TradeOrder(
                order_id="order123456",
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.STOP_MARKET,  # STOP_MARKET order
                quantity=0.1,
                stop_price=None,  # Missing stop_price
                position_type=PositionType.LONG,
                strategy_name="test",
                signal_id="signal123456",
                confidence_score=0.85
            )

    def test_validate_stop_limit_order_requires_stop_price(self):
        """Test STOP_LIMIT order validator requires stop_price - covers lines 115-120."""
        with pytest.raises(ValueError, match="Stop price is required for STOP"):
            TradeOrder(
                order_id="order123456",
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.STOP_LIMIT,  # STOP_LIMIT order
                quantity=0.1,
                price=50000.0,
                stop_price=None,  # Missing stop_price
                position_type=PositionType.LONG,
                strategy_name="test",
                signal_id="signal123456",
                confidence_score=0.85
            )


class TestTradeOrderCreation:
    """Test TradeOrder creation with various configurations."""

    def test_market_order_buy_long(self):
        """Test creating a MARKET BUY order for LONG position."""
        order = TradeOrder(
            order_id="market_buy_001",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.1,
            position_type=PositionType.LONG,
            strategy_name="test_strategy",
            signal_id="signal_001_123",
            confidence_score=0.85
        )
        
        assert order.order_type == OrderType.MARKET
        assert order.side == OrderSide.BUY
        assert order.position_type == PositionType.LONG
        assert order.time_in_force == TimeInForce.GTC  # Default

    def test_market_order_sell_short(self):
        """Test creating a MARKET SELL order for SHORT position."""
        order = TradeOrder(
            order_id="market_sell_001",
            symbol="ETHUSDT",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=5.0,
            position_type=PositionType.SHORT,
            strategy_name="test_strategy",
            signal_id="signal_002_123",
            confidence_score=0.75
        )
        
        assert order.order_type == OrderType.MARKET
        assert order.side == OrderSide.SELL
        assert order.position_type == PositionType.SHORT

    def test_limit_order_with_price(self):
        """Test creating a LIMIT order with price."""
        order = TradeOrder(
            order_id="limit_buy_001",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.5,
            price=48000.0,
            position_type=PositionType.LONG,
            strategy_name="test_strategy",
            signal_id="signal_003_123",
            confidence_score=0.80
        )
        
        assert order.order_type == OrderType.LIMIT
        assert order.price == 48000.0

    def test_stop_market_order_with_stop_price(self):
        """Test creating a STOP_MARKET order with stop_price."""
        order = TradeOrder(
            order_id="stop_market_001",
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            order_type=OrderType.STOP_MARKET,
            quantity=0.2,
            stop_price=51000.0,
            position_type=PositionType.LONG,
            strategy_name="test_strategy",
            signal_id="signal_004_123",
            confidence_score=0.70
        )
        
        assert order.order_type == OrderType.STOP_MARKET
        assert order.stop_price == 51000.0

    def test_stop_limit_order_with_both_prices(self):
        """Test creating a STOP_LIMIT order with both price and stop_price."""
        order = TradeOrder(
            order_id="stop_limit_001",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.STOP_LIMIT,
            quantity=0.3,
            price=48500.0,
            stop_price=49000.0,
            position_type=PositionType.LONG,
            strategy_name="test_strategy",
            signal_id="signal_005_123",
            confidence_score=0.90
        )
        
        assert order.order_type == OrderType.STOP_LIMIT
        assert order.price == 48500.0
        assert order.stop_price == 49000.0

    def test_order_with_leverage(self):
        """Test order with custom leverage."""
        order = TradeOrder(
            order_id="leveraged_order_001",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.1,
            position_type=PositionType.LONG,
            leverage=10,  # 10x leverage
            strategy_name="test_strategy",
            signal_id="signal_006_123",
            confidence_score=0.85
        )
        
        assert order.leverage == 10

    def test_order_with_reduce_only(self):
        """Test order with reduce_only flag."""
        order = TradeOrder(
            order_id="reduce_only_001",
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=0.1,
            position_type=PositionType.LONG,
            reduce_only=True,  # Close only
            strategy_name="test_strategy",
            signal_id="signal_007_123",
            confidence_score=0.85
        )
        
        assert order.reduce_only is True

    def test_order_with_metadata(self):
        """Test order with custom metadata."""
        metadata = {
            "indicator": "RSI",
            "value": 75.0,
            "reason": "overbought"
        }
        order = TradeOrder(
            order_id="order_meta_001",
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=0.1,
            position_type=PositionType.LONG,
            strategy_name="test_strategy",
            signal_id="signal_008_123",
            confidence_score=0.85,
            metadata=metadata
        )
        
        assert order.metadata == metadata
        assert order.metadata["indicator"] == "RSI"

    def test_order_with_all_time_in_force_options(self):
        """Test order creation with all TimeInForce values."""
        for tif in [TimeInForce.GTC, TimeInForce.IOC, TimeInForce.FOK]:
            order = TradeOrder(
                order_id=f"order_tif_{tif.value}",
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=0.1,
                price=50000.0,
                position_type=PositionType.LONG,
                time_in_force=tif,
                strategy_name="test_strategy",
                signal_id=f"signal_tif_{tif.value}",
                confidence_score=0.85
            )
            assert order.time_in_force == tif

    def test_order_minimum_valid_symbol_length(self):
        """Test order with minimum valid symbol length (6 chars)."""
        order = TradeOrder(
            order_id="order123456",
            symbol="BTCUSD",  # Exactly 6 chars
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.1,
            position_type=PositionType.LONG,
            strategy_name="test",
            signal_id="signal123456",
            confidence_score=0.85
        )
        assert order.symbol == "BTCUSD"

    def test_order_minimum_valid_order_id_length(self):
        """Test order with minimum valid order_id length (10 chars)."""
        order = TradeOrder(
            order_id="order12345",  # Exactly 10 chars
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.1,
            position_type=PositionType.LONG,
            strategy_name="test",
            signal_id="signal123456",
            confidence_score=0.85
        )
        assert len(order.order_id) == 10

    def test_order_confidence_score_boundaries(self):
        """Test order with confidence_score boundary values."""
        # Test 0.0
        order1 = TradeOrder(
            order_id="order123456",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.1,
            position_type=PositionType.LONG,
            strategy_name="test",
            signal_id="signal123456",
            confidence_score=0.0
        )
        assert order1.confidence_score == 0.0
        
        # Test 1.0
        order2 = TradeOrder(
            order_id="order123457",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.1,
            position_type=PositionType.LONG,
            strategy_name="test",
            signal_id="signal123456",
            confidence_score=1.0
        )
        assert order2.confidence_score == 1.0

    def test_order_leverage_minimum(self):
        """Test order with minimum leverage (1x)."""
        order = TradeOrder(
            order_id="order123456",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.1,
            position_type=PositionType.LONG,
            leverage=1,
            strategy_name="test",
            signal_id="signal123456",
            confidence_score=0.85
        )
        assert order.leverage == 1

    def test_order_leverage_maximum(self):
        """Test order with maximum leverage (125x)."""
        order = TradeOrder(
            order_id="order123456",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.1,
            position_type=PositionType.LONG,
            leverage=125,
            strategy_name="test",
            signal_id="signal123456",
            confidence_score=0.85
        )
        assert order.leverage == 125

    def test_order_custom_timestamp(self):
        """Test order with custom timestamp."""
        custom_time = datetime(2024, 1, 1, 12, 0, 0)
        order = TradeOrder(
            order_id="order123456",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.1,
            position_type=PositionType.LONG,
            strategy_name="test",
            signal_id="signal123456",
            confidence_score=0.85,
            timestamp=custom_time
        )
        assert order.timestamp == custom_time

    def test_order_auto_generated_timestamp(self):
        """Test order timestamp is auto-generated."""
        before = datetime.utcnow()
        order = TradeOrder(
            order_id="order123456",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.1,
            position_type=PositionType.LONG,
            strategy_name="test",
            signal_id="signal123456",
            confidence_score=0.85
        )
        after = datetime.utcnow()
        
        assert before <= order.timestamp <= after

    def test_order_close_on_trigger_flag(self):
        """Test order with close_on_trigger flag."""
        order = TradeOrder(
            order_id="order123456",
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            order_type=OrderType.STOP_MARKET,
            quantity=0.1,
            stop_price=51000.0,
            position_type=PositionType.LONG,
            close_on_trigger=True,
            strategy_name="test",
            signal_id="signal123456",
            confidence_score=0.85
        )
        assert order.close_on_trigger is True

    def test_order_symbol_uppercase_conversion(self):
        """Test symbol is converted to uppercase."""
        order = TradeOrder(
            order_id="order123456",
            symbol="btcusdt",  # lowercase
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.1,
            position_type=PositionType.LONG,
            strategy_name="test",
            signal_id="signal123456",
            confidence_score=0.85
        )
        assert order.symbol == "BTCUSDT"

    def test_order_various_quantities(self):
        """Test order with various quantity values."""
        # Very small quantity
        order1 = TradeOrder(
            order_id="order123456",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.00001,  # Very small
            position_type=PositionType.LONG,
            strategy_name="test",
            signal_id="signal123456",
            confidence_score=0.85
        )
        assert order1.quantity == 0.00001
        
        # Large quantity
        order2 = TradeOrder(
            order_id="order123457",
            symbol="DOGEUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100000.0,  # Large
            position_type=PositionType.LONG,
            strategy_name="test",
            signal_id="signal123457",
            confidence_score=0.85
        )
        assert order2.quantity == 100000.0


class TestTradeOrderProperties:
    """Test TradeOrder property methods."""

    def test_is_market_order_property(self):
        """Test is_market_order property - covers line 132."""
        order = TradeOrder(
            order_id="order123456",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.1,
            position_type=PositionType.LONG,
            strategy_name="test",
            signal_id="signal123456",
            confidence_score=0.85
        )
        assert order.is_market_order is True

    def test_is_limit_order_property(self):
        """Test is_limit_order property - covers line 137."""
        order = TradeOrder(
            order_id="order123456",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.1,
            price=50000.0,
            position_type=PositionType.LONG,
            strategy_name="test",
            signal_id="signal123456",
            confidence_score=0.85
        )
        assert order.is_limit_order is True

    def test_is_stop_order_property(self):
        """Test is_stop_order property - covers line 142."""
        order1 = TradeOrder(
            order_id="order123456",
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            order_type=OrderType.STOP_MARKET,
            quantity=0.1,
            stop_price=51000.0,
            position_type=PositionType.LONG,
            strategy_name="test",
            signal_id="signal123456",
            confidence_score=0.85
        )
        assert order1.is_stop_order is True
        
        order2 = TradeOrder(
            order_id="order123457",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.STOP_LIMIT,
            quantity=0.1,
            price=48000.0,
            stop_price=49000.0,
            position_type=PositionType.LONG,
            strategy_name="test",
            signal_id="signal123457",
            confidence_score=0.85
        )
        assert order2.is_stop_order is True

    def test_is_sell_order_property(self):
        """Test is_sell_order property - covers line 152."""
        order = TradeOrder(
            order_id="order123456",
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=0.1,
            position_type=PositionType.SHORT,
            strategy_name="test",
            signal_id="signal123456",
            confidence_score=0.85
        )
        assert order.is_sell_order is True

    def test_is_short_position_property(self):
        """Test is_short_position property - covers line 162."""
        order = TradeOrder(
            order_id="order123456",
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=0.1,
            position_type=PositionType.SHORT,
            strategy_name="test",
            signal_id="signal123456",
            confidence_score=0.85
        )
        assert order.is_short_position is True

    def test_estimated_value_with_price(self):
        """Test estimated_value when price is set - covers lines 167-168."""
        order = TradeOrder(
            order_id="order123456",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.5,
            price=48000.0,
            position_type=PositionType.LONG,
            strategy_name="test",
            signal_id="signal123456",
            confidence_score=0.85
        )
        assert order.estimated_value == 24000.0  # 0.5 * 48000

    def test_estimated_value_without_price(self):
        """Test estimated_value when price is None - covers line 169."""
        order = TradeOrder(
            order_id="order123456",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.5,
            position_type=PositionType.LONG,
            strategy_name="test",
            signal_id="signal123456",
            confidence_score=0.85
        )
        assert order.estimated_value == 0.0  # No price

    def test_to_dict_with_price_and_stop_price(self):
        """Test to_dict includes optional fields - covers lines 192, 195."""
        order = TradeOrder(
            order_id="order123456",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.STOP_LIMIT,
            quantity=0.1,
            price=48500.0,
            stop_price=49000.0,
            position_type=PositionType.LONG,
            strategy_name="test",
            signal_id="signal123456",
            confidence_score=0.85
        )
        
        order_dict = order.to_dict()
        
        assert order_dict["price"] == 48500.0
        assert order_dict["stop_price"] == 49000.0
        assert order_dict["symbol"] == "BTCUSDT"

    def test_validate_confidence_score_out_of_range(self):
        """Test confidence_score validator - covers line 126."""
        from pydantic import ValidationError
        
        with pytest.raises(ValidationError):
            TradeOrder(
                order_id="order123456",
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=0.1,
                position_type=PositionType.LONG,
                strategy_name="test",
                signal_id="signal123456",
                confidence_score=1.5  # Invalid
            )

