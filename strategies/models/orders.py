"""
Order models for trade orders sent to the TradeEngine.

This module contains Pydantic models for representing trade orders,
order types, sides, and position management.
"""

from datetime import datetime
from enum import Enum, StrEnum
from typing import Any, Optional

from pydantic import BaseModel, Field, validator


class OrderType(StrEnum):
    """Types of orders supported."""

    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_MARKET = "STOP_MARKET"
    STOP_LIMIT = "STOP_LIMIT"


class OrderSide(StrEnum):
    """Order sides."""

    BUY = "BUY"
    SELL = "SELL"


class TimeInForce(StrEnum):
    """Time in force options."""

    GTC = "GTC"  # Good Till Canceled
    IOC = "IOC"  # Immediate or Cancel
    FOK = "FOK"  # Fill or Kill


class PositionType(StrEnum):
    """Position types for futures trading."""

    LONG = "LONG"
    SHORT = "SHORT"


class TradeOrder(BaseModel):
    """Trade order model for sending to TradeEngine."""

    order_id: str = Field(..., description="Unique order ID")
    symbol: str = Field(..., description="Trading symbol")
    side: OrderSide = Field(..., description="Order side")
    order_type: OrderType = Field(..., description="Order type")
    quantity: float = Field(..., gt=0, description="Order quantity")
    price: float | None = Field(
        None, gt=0, description="Order price (required for LIMIT orders)"
    )
    stop_price: float | None = Field(
        None, gt=0, description="Stop price (for STOP orders)"
    )
    time_in_force: TimeInForce = Field(
        default=TimeInForce.GTC, description="Time in force"
    )
    position_type: PositionType = Field(..., description="Position type (LONG/SHORT)")
    leverage: int = Field(default=1, ge=1, le=125, description="Leverage for futures")
    reduce_only: bool = Field(default=False, description="Reduce only flag")
    close_on_trigger: bool = Field(default=False, description="Close on trigger flag")
    strategy_name: str = Field(..., description="Strategy that generated the order")
    signal_id: str = Field(
        ..., description="ID of the signal that triggered this order"
    )
    confidence_score: float = Field(
        ..., ge=0.0, le=1.0, description="Signal confidence score"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Order timestamp"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )

    @validator("symbol")
    def validate_symbol(cls, v):
        """Validate trading symbol format."""
        if not v or len(v) < 6:
            raise ValueError("Invalid symbol format")
        return v.upper()

    @validator("order_id")
    def validate_order_id(cls, v):
        """Validate order ID format."""
        if not v or len(v) < 10:
            raise ValueError("Order ID must be at least 10 characters")
        return v

    @validator("signal_id")
    def validate_signal_id(cls, v):
        """Validate signal ID format."""
        if not v or len(v) < 10:
            raise ValueError("Signal ID must be at least 10 characters")
        return v

    @validator("price")
    def validate_price_for_limit_orders(cls, v, values):
        """Validate price is provided for LIMIT orders."""
        if (
            values.get("order_type") in [OrderType.LIMIT, OrderType.STOP_LIMIT]
            and v is None
        ):
            raise ValueError("Price is required for LIMIT and STOP_LIMIT orders")
        return v

    @validator("stop_price")
    def validate_stop_price_for_stop_orders(cls, v, values):
        """Validate stop price is provided for STOP orders."""
        if (
            values.get("order_type") in [OrderType.STOP_MARKET, OrderType.STOP_LIMIT]
            and v is None
        ):
            raise ValueError("Stop price is required for STOP orders")
        return v

    @validator("confidence_score")
    def validate_confidence_score(cls, v):
        """Validate confidence score is between 0 and 1."""
        if not 0.0 <= v <= 1.0:
            raise ValueError("Confidence score must be between 0.0 and 1.0")
        return v

    @property
    def is_market_order(self) -> bool:
        """Check if this is a market order."""
        return self.order_type == OrderType.MARKET

    @property
    def is_limit_order(self) -> bool:
        """Check if this is a limit order."""
        return self.order_type == OrderType.LIMIT

    @property
    def is_stop_order(self) -> bool:
        """Check if this is a stop order."""
        return self.order_type in [OrderType.STOP_MARKET, OrderType.STOP_LIMIT]

    @property
    def is_buy_order(self) -> bool:
        """Check if this is a buy order."""
        return self.side == OrderSide.BUY

    @property
    def is_sell_order(self) -> bool:
        """Check if this is a sell order."""
        return self.side == OrderSide.SELL

    @property
    def is_long_position(self) -> bool:
        """Check if this is for a long position."""
        return self.position_type == PositionType.LONG

    @property
    def is_short_position(self) -> bool:
        """Check if this is for a short position."""
        return self.position_type == PositionType.SHORT

    @property
    def estimated_value(self) -> float:
        """Estimate the order value."""
        if self.price:
            return self.quantity * self.price
        return 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert order to dictionary for API calls."""
        order_dict = {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "order_type": self.order_type.value,
            "quantity": self.quantity,
            "time_in_force": self.time_in_force.value,
            "position_type": self.position_type.value,
            "leverage": self.leverage,
            "reduce_only": self.reduce_only,
            "close_on_trigger": self.close_on_trigger,
            "strategy_name": self.strategy_name,
            "signal_id": self.signal_id,
            "confidence_score": self.confidence_score,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

        if self.price is not None:
            order_dict["price"] = self.price

        if self.stop_price is not None:
            order_dict["stop_price"] = self.stop_price

        return order_dict


class OrderResponse(BaseModel):
    """Response from TradeEngine for order submission."""

    order_id: str = Field(..., description="Order ID")
    status: str = Field(..., description="Order status")
    message: str = Field(..., description="Response message")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Response timestamp"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )

    @property
    def is_success(self) -> bool:
        """Check if the order was successful."""
        return self.status.lower() in ["success", "accepted", "submitted"]

    @property
    def is_error(self) -> bool:
        """Check if the order failed."""
        return self.status.lower() in ["error", "failed", "rejected"]


class OrderStatus(BaseModel):
    """Order status information."""

    order_id: str = Field(..., description="Order ID")
    symbol: str = Field(..., description="Trading symbol")
    status: str = Field(..., description="Order status")
    side: OrderSide = Field(..., description="Order side")
    order_type: OrderType = Field(..., description="Order type")
    quantity: float = Field(..., description="Order quantity")
    filled_quantity: float = Field(default=0.0, description="Filled quantity")
    price: float | None = Field(None, description="Order price")
    average_price: float | None = Field(None, description="Average fill price")
    stop_price: float | None = Field(None, description="Stop price")
    time_in_force: TimeInForce = Field(..., description="Time in force")
    position_type: PositionType = Field(..., description="Position type")
    leverage: int = Field(..., description="Leverage")
    reduce_only: bool = Field(..., description="Reduce only flag")
    close_on_trigger: bool = Field(..., description="Close on trigger flag")
    strategy_name: str = Field(..., description="Strategy name")
    signal_id: str = Field(..., description="Signal ID")
    confidence_score: float = Field(..., description="Confidence score")
    created_time: datetime = Field(..., description="Order creation time")
    updated_time: datetime = Field(..., description="Last update time")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )

    @property
    def is_filled(self) -> bool:
        """Check if the order is completely filled."""
        return self.filled_quantity >= self.quantity

    @property
    def is_partially_filled(self) -> bool:
        """Check if the order is partially filled."""
        return 0 < self.filled_quantity < self.quantity

    @property
    def is_pending(self) -> bool:
        """Check if the order is pending."""
        return self.status.lower() in ["pending", "new", "submitted"]

    @property
    def is_cancelled(self) -> bool:
        """Check if the order is cancelled."""
        return self.status.lower() in ["cancelled", "canceled"]

    @property
    def is_rejected(self) -> bool:
        """Check if the order is rejected."""
        return self.status.lower() in ["rejected", "failed"]

    @property
    def fill_percentage(self) -> float:
        """Calculate fill percentage."""
        if self.quantity == 0:
            return 0.0
        return (self.filled_quantity / self.quantity) * 100

    @property
    def remaining_quantity(self) -> float:
        """Calculate remaining quantity."""
        return self.quantity - self.filled_quantity


class OrderMetrics(BaseModel):
    """Metrics for order processing and performance."""

    total_orders_submitted: int = Field(default=0, description="Total orders submitted")
    orders_by_status: dict[str, int] = Field(
        default_factory=dict, description="Orders by status"
    )
    orders_by_strategy: dict[str, int] = Field(
        default_factory=dict, description="Orders by strategy"
    )
    orders_by_symbol: dict[str, int] = Field(
        default_factory=dict, description="Orders by symbol"
    )
    average_processing_time_ms: float = Field(
        default=0.0, description="Average processing time"
    )
    order_submission_rate: float = Field(default=0.0, description="Orders per second")
    last_order_timestamp: datetime | None = Field(
        default=None, description="Last order timestamp"
    )
    total_order_value: float = Field(default=0.0, description="Total order value")
    success_rate: float = Field(default=0.0, description="Order success rate")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metrics"
    )

    def update_metrics(
        self, order: TradeOrder, response: OrderResponse, processing_time_ms: float
    ) -> None:
        """Update metrics with a new order."""
        self.total_orders_submitted += 1

        # Update orders by status
        status = response.status.lower()
        self.orders_by_status[status] = self.orders_by_status.get(status, 0) + 1

        # Update orders by strategy
        self.orders_by_strategy[order.strategy_name] = (
            self.orders_by_strategy.get(order.strategy_name, 0) + 1
        )

        # Update orders by symbol
        self.orders_by_symbol[order.symbol] = (
            self.orders_by_symbol.get(order.symbol, 0) + 1
        )

        # Update processing time
        if self.total_orders_submitted == 1:
            self.average_processing_time_ms = processing_time_ms
        else:
            self.average_processing_time_ms = (
                self.average_processing_time_ms * (self.total_orders_submitted - 1)
                + processing_time_ms
            ) / self.total_orders_submitted

        # Update last order timestamp
        self.last_order_timestamp = order.timestamp

        # Update total order value
        self.total_order_value += order.estimated_value

        # Update success rate
        successful_orders = sum(
            count
            for status, count in self.orders_by_status.items()
            if status in ["success", "accepted", "submitted"]
        )
        self.success_rate = (successful_orders / self.total_orders_submitted) * 100

    def get_order_distribution(self) -> dict[str, float]:
        """Get order distribution percentages."""
        if self.total_orders_submitted == 0:
            return {}

        distribution = {}

        # Status distribution
        for status, count in self.orders_by_status.items():
            distribution[f"status_{status}"] = count / self.total_orders_submitted

        # Strategy distribution
        for strategy, count in self.orders_by_strategy.items():
            distribution[f"strategy_{strategy}"] = count / self.total_orders_submitted

        # Symbol distribution
        for symbol, count in self.orders_by_symbol.items():
            distribution[f"symbol_{symbol}"] = count / self.total_orders_submitted

        return distribution
