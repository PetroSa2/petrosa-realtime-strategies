"""
Tests for strategies/models/orders.py.
"""

from datetime import datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from strategies.models.orders import (
    OrderSide,
    OrderType,
    PositionType,
    TimeInForce,
    TradeOrder,
)


class TestTradeOrder:
    """Test TradeOrder model."""

    def test_create_market_buy_order(self):
        """Test creating a market buy order."""
        order = TradeOrder(
            order_id=str(uuid4()),
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.001,
            position_type=PositionType.LONG,
            strategy_name="test_strategy",
            signal_id=str(uuid4()),
            confidence_score=0.85,
        )

        assert order.symbol == "BTCUSDT"
        assert order.side == OrderSide.BUY
        assert order.order_type == OrderType.MARKET
        assert order.quantity == 0.001
        assert order.position_type == PositionType.LONG

    def test_create_limit_sell_order(self):
        """Test creating a limit sell order."""
        order = TradeOrder(
            order_id=str(uuid4()),
            symbol="ETHUSDT",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=0.1,
            price=3000.0,
            position_type=PositionType.SHORT,
            strategy_name="test_strategy",
            signal_id=str(uuid4()),
            confidence_score=0.75,
        )

        assert order.price == 3000.0
        assert order.order_type == OrderType.LIMIT

    def test_create_stop_market_order(self):
        """Test creating a stop market order."""
        order = TradeOrder(
            order_id=str(uuid4()),
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            order_type=OrderType.STOP_MARKET,
            quantity=0.001,
            stop_price=49000.0,
            position_type=PositionType.LONG,
            reduce_only=True,
            strategy_name="test_strategy",
            signal_id=str(uuid4()),
            confidence_score=0.9,
        )

        assert order.stop_price == 49000.0
        assert order.reduce_only is True

    def test_order_with_leverage(self):
        """Test order with leverage."""
        order = TradeOrder(
            order_id=str(uuid4()),
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.01,
            position_type=PositionType.LONG,
            leverage=10,
            strategy_name="test_strategy",
            signal_id=str(uuid4()),
            confidence_score=0.85,
        )

        assert order.leverage == 10

    def test_order_with_metadata(self):
        """Test order with metadata."""
        metadata = {
            "entry_price": 50000.0,
            "stop_loss": 48000.0,
            "take_profit": 52000.0,
        }

        order = TradeOrder(
            order_id=str(uuid4()),
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.001,
            position_type=PositionType.LONG,
            strategy_name="test_strategy",
            signal_id=str(uuid4()),
            confidence_score=0.85,
            metadata=metadata,
        )

        assert order.metadata == metadata

    def test_symbol_validation(self):
        """Test symbol validation."""
        with pytest.raises(ValidationError):
            TradeOrder(
                order_id=str(uuid4()),
                symbol="BTC",  # Too short
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=0.001,
                position_type=PositionType.LONG,
                strategy_name="test_strategy",
                signal_id=str(uuid4()),
                confidence_score=0.85,
            )

    def test_symbol_uppercase_conversion(self):
        """Test symbol is converted to uppercase."""
        order = TradeOrder(
            order_id=str(uuid4()),
            symbol="btcusdt",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.001,
            position_type=PositionType.LONG,
            strategy_name="test_strategy",
            signal_id=str(uuid4()),
            confidence_score=0.85,
        )

        assert order.symbol == "BTCUSDT"

    def test_quantity_validation_positive(self):
        """Test quantity must be positive."""
        with pytest.raises(ValidationError):
            TradeOrder(
                order_id=str(uuid4()),
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=-0.001,  # Negative
                position_type=PositionType.LONG,
                strategy_name="test_strategy",
                signal_id=str(uuid4()),
                confidence_score=0.85,
            )

    def test_confidence_score_range(self):
        """Test confidence score must be 0-1."""
        with pytest.raises(ValidationError):
            TradeOrder(
                order_id=str(uuid4()),
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=0.001,
                position_type=PositionType.LONG,
                strategy_name="test_strategy",
                signal_id=str(uuid4()),
                confidence_score=1.5,  # Out of range
            )

    def test_leverage_range(self):
        """Test leverage must be 1-125."""
        with pytest.raises(ValidationError):
            TradeOrder(
                order_id=str(uuid4()),
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=0.001,
                position_type=PositionType.LONG,
                leverage=200,  # Too high
                strategy_name="test_strategy",
                signal_id=str(uuid4()),
                confidence_score=0.85,
            )

    def test_order_id_validation(self):
        """Test order ID validation."""
        with pytest.raises(ValidationError):
            TradeOrder(
                order_id="short",  # Too short
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=0.001,
                position_type=PositionType.LONG,
                strategy_name="test_strategy",
                signal_id=str(uuid4()),
                confidence_score=0.85,
            )

    def test_signal_id_validation(self):
        """Test signal ID validation."""
        with pytest.raises(ValidationError):
            TradeOrder(
                order_id=str(uuid4()),
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=0.001,
                position_type=PositionType.LONG,
                strategy_name="test_strategy",
                signal_id="short",  # Too short
                confidence_score=0.85,
            )

    def test_time_in_force_default(self):
        """Test time_in_force defaults to GTC."""
        order = TradeOrder(
            order_id=str(uuid4()),
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.001,
            position_type=PositionType.LONG,
            strategy_name="test_strategy",
            signal_id=str(uuid4()),
            confidence_score=0.85,
        )

        assert order.time_in_force == TimeInForce.GTC

    def test_leverage_default(self):
        """Test leverage defaults to 1."""
        order = TradeOrder(
            order_id=str(uuid4()),
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.001,
            position_type=PositionType.LONG,
            strategy_name="test_strategy",
            signal_id=str(uuid4()),
            confidence_score=0.85,
        )

        assert order.leverage == 1

    def test_reduce_only_default(self):
        """Test reduce_only defaults to False."""
        order = TradeOrder(
            order_id=str(uuid4()),
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.001,
            position_type=PositionType.LONG,
            strategy_name="test_strategy",
            signal_id=str(uuid4()),
            confidence_score=0.85,
        )

        assert order.reduce_only is False

    def test_metadata_default(self):
        """Test metadata defaults to empty dict."""
        order = TradeOrder(
            order_id=str(uuid4()),
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.001,
            position_type=PositionType.LONG,
            strategy_name="test_strategy",
            signal_id=str(uuid4()),
            confidence_score=0.85,
        )

        assert order.metadata == {}

