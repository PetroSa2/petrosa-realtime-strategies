"""
Tests for strategies/models/orders.py.
"""

from datetime import datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from strategies.models.orders import (
    OrderMetrics,
    OrderResponse,
    OrderSide,
    OrderStatus,
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
        with pytest.raises(ValidationError) as exc_info:
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
        assert exc_info.value is not None

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
        with pytest.raises(ValidationError) as exc_info:
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
        assert exc_info.value is not None

    def test_confidence_score_range(self):
        """Test confidence score must be 0-1."""
        with pytest.raises(ValidationError) as exc_info:
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
        assert exc_info.value is not None

    def test_leverage_range(self):
        """Test leverage must be 1-125."""
        with pytest.raises(ValidationError) as exc_info:
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
        assert exc_info.value is not None

    def test_order_id_validation(self):
        """Test order ID validation."""
        with pytest.raises(ValidationError) as exc_info:
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
        assert exc_info.value is not None

    def test_signal_id_validation(self):
        """Test signal ID validation."""
        with pytest.raises(ValidationError) as exc_info:
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
        assert exc_info.value is not None

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

    def test_is_market_order_property(self):
        """Test is_market_order property."""
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

        assert order.is_market_order is True

    def test_is_limit_order_property(self):
        """Test is_limit_order property."""
        order = TradeOrder(
            order_id=str(uuid4()),
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            price=50000.0,
            quantity=0.001,
            position_type=PositionType.LONG,
            strategy_name="test_strategy",
            signal_id=str(uuid4()),
            confidence_score=0.85,
        )

        assert order.is_limit_order is True

    def test_is_stop_order_property(self):
        """Test is_stop_order property."""
        order = TradeOrder(
            order_id=str(uuid4()),
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            order_type=OrderType.STOP_MARKET,
            stop_price=49000.0,
            quantity=0.001,
            position_type=PositionType.LONG,
            strategy_name="test_strategy",
            signal_id=str(uuid4()),
            confidence_score=0.85,
        )

        assert order.is_stop_order is True

    def test_is_buy_order_property(self):
        """Test is_buy_order property."""
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

        assert order.is_buy_order is True
        assert order.is_sell_order is False

    def test_is_long_position_property(self):
        """Test is_long_position property."""
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

        assert order.is_long_position is True
        assert order.is_short_position is False

    def test_estimated_value_with_price(self):
        """Test estimated_value calculation with price."""
        order = TradeOrder(
            order_id=str(uuid4()),
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            price=50000.0,
            quantity=0.01,
            position_type=PositionType.LONG,
            strategy_name="test_strategy",
            signal_id=str(uuid4()),
            confidence_score=0.85,
        )

        assert order.estimated_value == 500.0

    def test_estimated_value_without_price(self):
        """Test estimated_value returns 0 without price."""
        order = TradeOrder(
            order_id=str(uuid4()),
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.01,
            position_type=PositionType.LONG,
            strategy_name="test_strategy",
            signal_id=str(uuid4()),
            confidence_score=0.85,
        )

        assert order.estimated_value == 0.0

    def test_to_dict_market_order(self):
        """Test to_dict for market order."""
        order_id = str(uuid4())
        signal_id = str(uuid4())

        order = TradeOrder(
            order_id=order_id,
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.001,
            position_type=PositionType.LONG,
            strategy_name="test_strategy",
            signal_id=signal_id,
            confidence_score=0.85,
        )

        order_dict = order.to_dict()

        assert order_dict["order_id"] == order_id
        assert order_dict["symbol"] == "BTCUSDT"
        assert order_dict["side"] == "BUY"
        assert order_dict["order_type"] == "MARKET"
        assert order_dict["quantity"] == 0.001
        assert "price" not in order_dict  # Market order has no price
        assert "stop_price" not in order_dict

    def test_to_dict_limit_order_with_price(self):
        """Test to_dict for limit order includes price."""
        order = TradeOrder(
            order_id=str(uuid4()),
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            price=50000.0,
            quantity=0.001,
            position_type=PositionType.LONG,
            strategy_name="test_strategy",
            signal_id=str(uuid4()),
            confidence_score=0.85,
        )

        order_dict = order.to_dict()

        assert order_dict["price"] == 50000.0

    def test_to_dict_stop_order_with_stop_price(self):
        """Test to_dict for stop order includes stop_price."""
        order = TradeOrder(
            order_id=str(uuid4()),
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            order_type=OrderType.STOP_MARKET,
            stop_price=49000.0,
            quantity=0.001,
            position_type=PositionType.LONG,
            strategy_name="test_strategy",
            signal_id=str(uuid4()),
            confidence_score=0.85,
        )

        order_dict = order.to_dict()

        assert order_dict["stop_price"] == 49000.0


class TestOrderResponse:
    """Test OrderResponse model."""

    def test_create_order_response(self):
        """Test creating an order response."""
        response = OrderResponse(
            order_id=str(uuid4()),
            status="success",
            message="Order placed successfully",
        )

        assert response.order_id is not None
        assert response.status == "success"
        assert response.message == "Order placed successfully"

    def test_order_response_is_success(self):
        """Test is_success property."""
        response = OrderResponse(
            order_id=str(uuid4()),
            status="success",
            message="Order placed",
        )

        assert response.is_success is True

    def test_order_response_is_error(self):
        """Test is_error property."""
        response = OrderResponse(
            order_id=str(uuid4()),
            status="error",
            message="Order failed",
        )

        assert response.is_error is True


class TestOrderStatus:
    """Test OrderStatus model."""

    def test_create_order_status(self):
        """Test creating an order status."""
        status = OrderStatus(
            order_id=str(uuid4()),
            symbol="BTCUSDT",
            status="filled",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.001,
            filled_quantity=0.001,
            time_in_force=TimeInForce.GTC,
            position_type=PositionType.LONG,
            leverage=1,
            reduce_only=False,
            close_on_trigger=False,
            strategy_name="test_strategy",
            signal_id=str(uuid4()),
            confidence_score=0.85,
            created_time=datetime.utcnow(),
            updated_time=datetime.utcnow(),
        )

        assert status.symbol == "BTCUSDT"
        assert status.status == "filled"

    def test_is_filled_property(self):
        """Test is_filled property."""
        status = OrderStatus(
            order_id=str(uuid4()),
            symbol="BTCUSDT",
            status="filled",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.001,
            filled_quantity=0.001,
            time_in_force=TimeInForce.GTC,
            position_type=PositionType.LONG,
            leverage=1,
            reduce_only=False,
            close_on_trigger=False,
            strategy_name="test_strategy",
            signal_id=str(uuid4()),
            confidence_score=0.85,
            created_time=datetime.utcnow(),
            updated_time=datetime.utcnow(),
        )

        assert status.is_filled is True

    def test_is_partially_filled_property(self):
        """Test is_partially_filled property."""
        status = OrderStatus(
            order_id=str(uuid4()),
            symbol="BTCUSDT",
            status="partially_filled",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1.0,
            filled_quantity=0.5,
            time_in_force=TimeInForce.GTC,
            position_type=PositionType.LONG,
            leverage=1,
            reduce_only=False,
            close_on_trigger=False,
            strategy_name="test_strategy",
            signal_id=str(uuid4()),
            confidence_score=0.85,
            created_time=datetime.utcnow(),
            updated_time=datetime.utcnow(),
        )

        assert status.is_partially_filled is True

    def test_is_pending_property(self):
        """Test is_pending property."""
        status = OrderStatus(
            order_id=str(uuid4()),
            symbol="BTCUSDT",
            status="pending",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.001,
            time_in_force=TimeInForce.GTC,
            position_type=PositionType.LONG,
            leverage=1,
            reduce_only=False,
            close_on_trigger=False,
            strategy_name="test_strategy",
            signal_id=str(uuid4()),
            confidence_score=0.85,
            created_time=datetime.utcnow(),
            updated_time=datetime.utcnow(),
        )

        assert status.is_pending is True

    def test_is_cancelled_property(self):
        """Test is_cancelled property."""
        status = OrderStatus(
            order_id=str(uuid4()),
            symbol="BTCUSDT",
            status="cancelled",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.001,
            time_in_force=TimeInForce.GTC,
            position_type=PositionType.LONG,
            leverage=1,
            reduce_only=False,
            close_on_trigger=False,
            strategy_name="test_strategy",
            signal_id=str(uuid4()),
            confidence_score=0.85,
            created_time=datetime.utcnow(),
            updated_time=datetime.utcnow(),
        )

        assert status.is_cancelled is True

    def test_is_rejected_property(self):
        """Test is_rejected property."""
        status = OrderStatus(
            order_id=str(uuid4()),
            symbol="BTCUSDT",
            status="rejected",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.001,
            time_in_force=TimeInForce.GTC,
            position_type=PositionType.LONG,
            leverage=1,
            reduce_only=False,
            close_on_trigger=False,
            strategy_name="test_strategy",
            signal_id=str(uuid4()),
            confidence_score=0.85,
            created_time=datetime.utcnow(),
            updated_time=datetime.utcnow(),
        )

        assert status.is_rejected is True

    def test_fill_percentage_full(self):
        """Test fill_percentage when fully filled."""
        status = OrderStatus(
            order_id=str(uuid4()),
            symbol="BTCUSDT",
            status="filled",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1.0,
            filled_quantity=1.0,
            time_in_force=TimeInForce.GTC,
            position_type=PositionType.LONG,
            leverage=1,
            reduce_only=False,
            close_on_trigger=False,
            strategy_name="test_strategy",
            signal_id=str(uuid4()),
            confidence_score=0.85,
            created_time=datetime.utcnow(),
            updated_time=datetime.utcnow(),
        )

        assert status.fill_percentage == 100.0

    def test_fill_percentage_partial(self):
        """Test fill_percentage when partially filled."""
        status = OrderStatus(
            order_id=str(uuid4()),
            symbol="BTCUSDT",
            status="partial",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=2.0,
            filled_quantity=0.5,
            time_in_force=TimeInForce.GTC,
            position_type=PositionType.LONG,
            leverage=1,
            reduce_only=False,
            close_on_trigger=False,
            strategy_name="test_strategy",
            signal_id=str(uuid4()),
            confidence_score=0.85,
            created_time=datetime.utcnow(),
            updated_time=datetime.utcnow(),
        )

        assert status.fill_percentage == 25.0

    def test_fill_percentage_zero_quantity(self):
        """Test fill_percentage with zero quantity."""
        status = OrderStatus(
            order_id=str(uuid4()),
            symbol="BTCUSDT",
            status="new",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.0,
            filled_quantity=0.0,
            time_in_force=TimeInForce.GTC,
            position_type=PositionType.LONG,
            leverage=1,
            reduce_only=False,
            close_on_trigger=False,
            strategy_name="test_strategy",
            signal_id=str(uuid4()),
            confidence_score=0.85,
            created_time=datetime.utcnow(),
            updated_time=datetime.utcnow(),
        )

        assert status.fill_percentage == 0.0

    def test_remaining_quantity(self):
        """Test remaining_quantity calculation."""
        status = OrderStatus(
            order_id=str(uuid4()),
            symbol="BTCUSDT",
            status="partial",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1.0,
            filled_quantity=0.3,
            time_in_force=TimeInForce.GTC,
            position_type=PositionType.LONG,
            leverage=1,
            reduce_only=False,
            close_on_trigger=False,
            strategy_name="test_strategy",
            signal_id=str(uuid4()),
            confidence_score=0.85,
            created_time=datetime.utcnow(),
            updated_time=datetime.utcnow(),
        )

        assert status.remaining_quantity == 0.7


class TestOrderMetrics:
    """Test OrderMetrics model."""

    def test_create_order_metrics(self):
        """Test creating order metrics."""
        metrics = OrderMetrics()

        assert metrics.total_orders_submitted == 0
        assert metrics.success_rate == 0.0

    def test_update_metrics_single_order(self):
        """Test updating metrics with single order."""
        metrics = OrderMetrics()

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

        response = OrderResponse(
            order_id=order.order_id, status="success", message="Order submitted"
        )

        metrics.update_metrics(order, response, processing_time_ms=15.5)

        assert metrics.total_orders_submitted == 1
        assert metrics.orders_by_status["success"] == 1
        assert metrics.orders_by_strategy["test_strategy"] == 1
        assert metrics.orders_by_symbol["BTCUSDT"] == 1
        assert metrics.average_processing_time_ms == 15.5
        assert metrics.last_order_timestamp == order.timestamp
        assert metrics.success_rate == 100.0

    def test_update_metrics_multiple_orders(self):
        """Test updating metrics with multiple orders."""
        metrics = OrderMetrics()

        # Order 1 - Success
        order1 = TradeOrder(
            order_id=str(uuid4()),
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.001,
            position_type=PositionType.LONG,
            strategy_name="strategy1",
            signal_id=str(uuid4()),
            confidence_score=0.85,
        )
        response1 = OrderResponse(
            order_id=order1.order_id, status="success", message="Order 1 submitted"
        )
        metrics.update_metrics(order1, response1, processing_time_ms=10.0)

        # Order 2 - Failed
        order2 = TradeOrder(
            order_id=str(uuid4()),
            symbol="ETHUSDT",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            price=3000.0,
            quantity=0.01,
            position_type=PositionType.SHORT,
            strategy_name="strategy2",
            signal_id=str(uuid4()),
            confidence_score=0.75,
        )
        response2 = OrderResponse(
            order_id=order2.order_id, status="failed", message="Insufficient funds"
        )
        metrics.update_metrics(order2, response2, processing_time_ms=20.0)

        assert metrics.total_orders_submitted == 2
        assert metrics.orders_by_status["success"] == 1
        assert metrics.orders_by_status["failed"] == 1
        assert metrics.average_processing_time_ms == 15.0  # (10 + 20) / 2
        assert metrics.success_rate == 50.0  # 1/2 * 100

    def test_get_order_distribution_empty(self):
        """Test get_order_distribution with no orders."""
        metrics = OrderMetrics()

        distribution = metrics.get_order_distribution()

        assert distribution == {}

    def test_get_order_distribution_with_orders(self):
        """Test get_order_distribution with orders."""
        metrics = OrderMetrics()

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
        response = OrderResponse(
            order_id=order.order_id, status="success", message="Order submitted"
        )
        metrics.update_metrics(order, response, processing_time_ms=10.0)

        distribution = metrics.get_order_distribution()

        assert isinstance(distribution, dict)
        assert "status_success" in distribution
        assert distribution["status_success"] == 1.0
        assert "strategy_test_strategy" in distribution
        assert distribution["strategy_test_strategy"] == 1.0
        assert "symbol_BTCUSDT" in distribution
        assert distribution["symbol_BTCUSDT"] == 1.0


