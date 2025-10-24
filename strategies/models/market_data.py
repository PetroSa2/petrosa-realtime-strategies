"""
Market data models for Binance WebSocket streams.

This module contains Pydantic models for processing real-time market data
from Binance WebSocket streams including depth updates, trades, and tickers.
"""

from datetime import datetime
from typing import Union

from pydantic import BaseModel, Field, validator


class DepthLevel(BaseModel):
    """Represents a single level in the order book."""

    price: str = Field(..., description="Price level")
    quantity: str = Field(..., description="Quantity at this price level")

    @validator("price", "quantity")
    def validate_numeric_string(cls, v):
        """Validate that the string can be converted to a float."""
        try:
            float(v)
            return v
        except ValueError:
            raise ValueError(f"Invalid numeric string: {v}")


class DepthUpdate(BaseModel):
    """Order book depth update from Binance WebSocket."""

    symbol: str = Field(..., description="Trading symbol (e.g., BTCUSDT)")
    event_time: int = Field(..., description="Event time in milliseconds")
    first_update_id: int = Field(..., description="First update ID")
    final_update_id: int = Field(..., description="Final update ID")
    bids: list[DepthLevel] = Field(..., description="Bid orders")
    asks: list[DepthLevel] = Field(..., description="Ask orders")

    @validator("symbol")
    def validate_symbol(cls, v):
        """Validate trading symbol format."""
        if not v or len(v) < 6:
            raise ValueError("Invalid symbol format")
        return v.upper()

    @property
    def timestamp(self) -> datetime:
        """Convert event_time to datetime."""
        return datetime.fromtimestamp(self.event_time / 1000)

    @property
    def spread_percent(self) -> float:
        """Calculate the bid-ask spread as a percentage."""
        if not self.bids or not self.asks:
            return 0.0

        best_bid = float(self.bids[0].price)
        best_ask = float(self.asks[0].price)
        return ((best_ask - best_bid) / best_bid) * 100

    @property
    def mid_price(self) -> float:
        """Calculate the mid price."""
        if not self.bids or not self.asks:
            return 0.0

        best_bid = float(self.bids[0].price)
        best_ask = float(self.asks[0].price)
        return (best_bid + best_ask) / 2


class TradeData(BaseModel):
    """Individual trade data from Binance WebSocket."""

    symbol: str = Field(..., description="Trading symbol")
    trade_id: int = Field(..., description="Trade ID")
    price: str = Field(..., description="Trade price")
    quantity: str = Field(..., description="Trade quantity")
    buyer_order_id: int = Field(..., description="Buyer order ID")
    seller_order_id: int = Field(..., description="Seller order ID")
    trade_time: int = Field(..., description="Trade time in milliseconds")
    is_buyer_maker: bool = Field(..., description="Whether buyer is maker")
    event_time: int = Field(..., description="Event time in milliseconds")

    @validator("symbol")
    def validate_symbol(cls, v):
        """Validate trading symbol format."""
        if not v or len(v) < 6:
            raise ValueError("Invalid symbol format")
        return v.upper()

    @validator("price", "quantity")
    def validate_numeric_string(cls, v):
        """Validate that the string can be converted to a float."""
        try:
            float(v)
            return v
        except ValueError:
            raise ValueError(f"Invalid numeric string: {v}")

    @property
    def timestamp(self) -> datetime:
        """Convert trade_time to datetime."""
        return datetime.fromtimestamp(self.trade_time / 1000)

    @property
    def price_float(self) -> float:
        """Get price as float."""
        return float(self.price)

    @property
    def quantity_float(self) -> float:
        """Get quantity as float."""
        return float(self.quantity)

    @property
    def notional_value(self) -> float:
        """Calculate the notional value of the trade."""
        return self.price_float * self.quantity_float


class TickerData(BaseModel):
    """24hr ticker data from Binance WebSocket."""

    symbol: str = Field(..., description="Trading symbol")
    price_change: str = Field(..., description="Price change")
    price_change_percent: str = Field(..., description="Price change percent")
    weighted_avg_price: str = Field(..., description="Weighted average price")
    prev_close_price: str = Field(..., description="Previous close price")
    last_price: str = Field(..., description="Last price")
    last_qty: str = Field(..., description="Last quantity")
    bid_price: str = Field(..., description="Bid price")
    bid_qty: str = Field(..., description="Bid quantity")
    ask_price: str = Field(..., description="Ask price")
    ask_qty: str = Field(..., description="Ask quantity")
    open_price: str = Field(..., description="Open price")
    high_price: str = Field(..., description="High price")
    low_price: str = Field(..., description="Low price")
    volume: str = Field(..., description="Volume")
    quote_volume: str = Field(..., description="Quote volume")
    open_time: int = Field(..., description="Open time in milliseconds")
    close_time: int = Field(..., description="Close time in milliseconds")
    first_id: int = Field(..., description="First trade ID")
    last_id: int = Field(..., description="Last trade ID")
    count: int = Field(..., description="Trade count")
    event_time: int = Field(..., description="Event time in milliseconds")

    @validator("symbol")
    def validate_symbol(cls, v):
        """Validate trading symbol format."""
        if not v or len(v) < 6:
            raise ValueError("Invalid symbol format")
        return v.upper()

    @validator(
        "price_change",
        "price_change_percent",
        "weighted_avg_price",
        "prev_close_price",
        "last_price",
        "last_qty",
        "bid_price",
        "bid_qty",
        "ask_price",
        "ask_qty",
        "open_price",
        "high_price",
        "low_price",
        "volume",
        "quote_volume",
    )
    def validate_numeric_string(cls, v):
        """Validate that the string can be converted to a float."""
        try:
            float(v)
            return v
        except ValueError:
            raise ValueError(f"Invalid numeric string: {v}")

    @property
    def timestamp(self) -> datetime:
        """Convert event_time to datetime."""
        return datetime.fromtimestamp(self.event_time / 1000)

    @property
    def price_change_float(self) -> float:
        """Get price change as float."""
        return float(self.price_change)

    @property
    def price_change_percent_float(self) -> float:
        """Get price change percent as float."""
        return float(self.price_change_percent)

    @property
    def last_price_float(self) -> float:
        """Get last price as float."""
        return float(self.last_price)

    @property
    def volume_float(self) -> float:
        """Get volume as float."""
        return float(self.volume)

    @property
    def quote_volume_float(self) -> float:
        """Get quote volume as float."""
        return float(self.quote_volume)


class MarketDataMessage(BaseModel):
    """Generic market data message wrapper."""

    stream: str = Field(..., description="Stream name")
    data: Union[DepthUpdate, TradeData, TickerData] = Field(
        ..., description="Market data"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Message timestamp"
    )

    @validator("stream")
    def validate_stream(cls, v):
        """Validate stream name format."""
        if not v or "@" not in v:
            raise ValueError("Invalid stream format")
        return v

    @property
    def symbol(self) -> str:
        """Extract symbol from stream name."""
        return self.stream.split("@")[0].upper()

    @property
    def stream_type(self) -> str:
        """Extract stream type from stream name."""
        return self.stream.split("@")[1]

    @property
    def is_depth(self) -> bool:
        """Check if this is a depth update."""
        return isinstance(self.data, DepthUpdate)

    @property
    def is_trade(self) -> bool:
        """Check if this is a trade."""
        return isinstance(self.data, TradeData)

    @property
    def is_ticker(self) -> bool:
        """Check if this is a ticker."""
        return isinstance(self.data, TickerData)
