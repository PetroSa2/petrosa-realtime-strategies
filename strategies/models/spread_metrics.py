"""
Spread Metrics Models.

Data models for tracking bid-ask spread metrics and calculating
liquidity event signals based on spread widening/narrowing patterns.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class SpreadMetrics:
    """
    Comprehensive spread metrics for a single orderbook snapshot.

    Attributes:
        symbol: Trading symbol (e.g., BTCUSDT)
        timestamp: Snapshot timestamp
        best_bid: Best bid price
        best_ask: Best ask price
        mid_price: (best_bid + best_ask) / 2
        spread_abs: Absolute spread (best_ask - best_bid)
        spread_bps: Spread in basis points (10,000 basis points = 1%)
        spread_pct: Spread as percentage
        bid_volume_top5: Total bid volume in top 5 levels
        ask_volume_top5: Total ask volume in top 5 levels
        total_depth: bid_volume + ask_volume
    """

    symbol: str
    timestamp: datetime

    # Price levels
    best_bid: float
    best_ask: float
    mid_price: float

    # Spread measurements
    spread_abs: float
    spread_bps: float
    spread_pct: float

    # Depth context
    bid_volume_top5: float
    ask_volume_top5: float
    total_depth: float

    def __post_init__(self):
        """Validate metrics."""
        if self.best_bid <= 0 or self.best_ask <= 0:
            raise ValueError(
                f"Invalid bid/ask prices: bid={self.best_bid}, ask={self.best_ask}"
            )

        if self.best_ask <= self.best_bid:
            raise ValueError(
                f"Ask must be greater than bid: bid={self.best_bid}, ask={self.best_ask}"
            )


@dataclass
class SpreadSnapshot:
    """
    Historical snapshot with comparative metrics.

    Used for tracking spread evolution over time and detecting
    significant changes (widening/narrowing events).
    """

    metrics: SpreadMetrics

    # Comparative metrics (vs recent history)
    spread_ratio: float | None = None  # current_spread / avg_spread
    spread_velocity: float | None = None  # rate of change (% per second)
    persistence_seconds: float | None = None  # time above/below threshold

    # Context flags
    is_widening: bool = False  # Spread increasing rapidly
    is_narrowing: bool = False  # Spread decreasing rapidly
    is_abnormal: bool = False  # Spread significantly different from avg

    # Depth analysis
    depth_reduction_pct: float | None = None  # % reduction vs avg depth


@dataclass
class SpreadEvent:
    """
    Detected spread event (widening or narrowing).

    Represents a significant liquidity event that may generate
    a trading signal.
    """

    event_type: str  # "widening" or "narrowing"
    symbol: str
    timestamp: datetime

    # Event metrics
    spread_before_bps: float
    spread_current_bps: float
    spread_ratio: float
    spread_velocity: float

    # Persistence
    duration_seconds: float
    persistence_above_threshold: bool

    # Signal strength
    confidence: float
    reasoning: str

    # Context
    snapshot: SpreadSnapshot
