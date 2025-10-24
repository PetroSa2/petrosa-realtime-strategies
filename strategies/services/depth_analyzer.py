"""
Market Depth Analyzer.

Analyzes order book depth data to provide real-time market metrics including:
- Order book imbalance
- Market pressure (buy/sell)
- Liquidity depth
- Bid-ask spread
- Volume-weighted metrics
"""

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class DepthMetrics:
    """Metrics calculated from order book depth."""

    symbol: str
    timestamp: datetime

    # Order Book Imbalance
    bid_volume: float
    ask_volume: float
    imbalance_ratio: float  # (bid - ask) / (bid + ask), range: [-1, 1]
    imbalance_percent: float  # imbalance as percentage

    # Market Pressure
    buy_pressure: float  # 0-100 scale
    sell_pressure: float  # 0-100 scale
    net_pressure: float  # buy_pressure - sell_pressure, range: [-100, 100]

    # Liquidity Depth
    total_liquidity: float  # bid_volume + ask_volume
    bid_depth_5: float  # Total volume at top 5 bid levels
    ask_depth_5: float  # Total volume at top 5 ask levels
    bid_depth_10: float
    ask_depth_10: float

    # Spread Metrics
    best_bid: float
    best_ask: float
    spread_abs: float  # best_ask - best_bid
    spread_bps: float  # spread in basis points
    mid_price: float  # (best_bid + best_ask) / 2

    # Volume-Weighted Metrics
    vwap_bid: float  # Volume-weighted average bid price
    vwap_ask: float  # Volume-weighted average ask price

    # Order Book Quality
    bid_levels: int  # Number of bid levels
    ask_levels: int  # Number of ask levels
    total_levels: int

    # Support/Resistance Levels (strongest levels by volume)
    strongest_bid_level: Optional[tuple[float, float]]  # (price, volume)
    strongest_ask_level: Optional[tuple[float, float]]


@dataclass
class MarketPressureHistory:
    """Historical market pressure data for trend analysis."""

    symbol: str
    timeframe: str  # "1m", "5m", "15m"

    pressure_history: list[tuple[datetime, float]]  # (timestamp, net_pressure)
    imbalance_history: list[tuple[datetime, float]]  # (timestamp, imbalance_ratio)

    avg_pressure: float
    max_pressure: float
    min_pressure: float

    trend: str  # "bullish", "bearish", "neutral"
    trend_strength: float  # 0-1 scale


class DepthAnalyzer:
    """
    Analyzes order book depth data and maintains real-time metrics.

    Features:
    - Real-time metric calculation
    - Historical trend tracking (1m, 5m, 15m windows)
    - In-memory storage with TTL
    - Configurable analysis parameters
    """

    def __init__(
        self,
        history_window_seconds: int = 900,  # 15 minutes
        max_symbols: int = 100,
        metrics_ttl_seconds: int = 300,  # 5 minutes
    ):
        """
        Initialize depth analyzer.

        Args:
            history_window_seconds: How long to keep historical data
            max_symbols: Maximum number of symbols to track
            metrics_ttl_seconds: TTL for metrics cache
        """
        self.history_window = history_window_seconds
        self.max_symbols = max_symbols
        self.metrics_ttl = metrics_ttl_seconds

        # Current metrics for each symbol
        self._current_metrics: dict[str, DepthMetrics] = {}

        # Historical data for trend analysis
        self._pressure_history: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=900)  # 15 min @ 1 update/sec
        )
        self._imbalance_history: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=900)
        )

        # Timestamps for TTL management
        self._last_update: dict[str, float] = {}

        logger.info(
            f"Depth analyzer initialized: "
            f"window={history_window_seconds}s, "
            f"max_symbols={max_symbols}, "
            f"metrics_ttl={metrics_ttl_seconds}s"
        )

    def analyze_depth(
        self,
        symbol: str,
        bids: list[tuple[float, float]],  # [(price, quantity), ...]
        asks: list[tuple[float, float]],
        timestamp: Optional[datetime] = None,
    ) -> DepthMetrics:
        """
        Analyze order book depth and calculate metrics.

        Args:
            symbol: Trading symbol
            bids: List of (price, quantity) tuples for bids
            asks: List of (price, quantity) tuples for asks
            timestamp: Optional timestamp (defaults to now)

        Returns:
            DepthMetrics object with calculated metrics
        """
        if timestamp is None:
            timestamp = datetime.utcnow()

        # Calculate basic volumes
        bid_volume = sum(qty for _, qty in bids) if bids else 0.0
        ask_volume = sum(qty for _, qty in asks) if asks else 0.0
        total_volume = bid_volume + ask_volume

        # Order book imbalance
        if total_volume > 0:
            imbalance_ratio = (bid_volume - ask_volume) / total_volume
            imbalance_percent = imbalance_ratio * 100
        else:
            imbalance_ratio = 0.0
            imbalance_percent = 0.0

        # Market pressure (normalized to 0-100 scale)
        buy_pressure = (bid_volume / (total_volume or 1)) * 100
        sell_pressure = (ask_volume / (total_volume or 1)) * 100
        net_pressure = buy_pressure - sell_pressure

        # Liquidity depth at different levels
        bid_depth_5 = sum(qty for _, qty in bids[:5]) if len(bids) >= 5 else bid_volume
        ask_depth_5 = sum(qty for _, qty in asks[:5]) if len(asks) >= 5 else ask_volume
        bid_depth_10 = (
            sum(qty for _, qty in bids[:10]) if len(bids) >= 10 else bid_volume
        )
        ask_depth_10 = (
            sum(qty for _, qty in asks[:10]) if len(asks) >= 10 else ask_volume
        )

        # Spread metrics
        best_bid = bids[0][0] if bids else 0.0
        best_ask = asks[0][0] if asks else 0.0
        spread_abs = best_ask - best_bid if (best_bid and best_ask) else 0.0
        mid_price = (best_bid + best_ask) / 2 if (best_bid and best_ask) else 0.0
        spread_bps = (spread_abs / mid_price * 10000) if mid_price > 0 else 0.0

        # Volume-weighted prices
        vwap_bid = self._calculate_vwap(bids) if bids else 0.0
        vwap_ask = self._calculate_vwap(asks) if asks else 0.0

        # Order book quality
        bid_levels = len(bids)
        ask_levels = len(asks)
        total_levels = bid_levels + ask_levels

        # Strongest levels (by volume)
        strongest_bid = max(bids, key=lambda x: x[1]) if bids else None
        strongest_ask = max(asks, key=lambda x: x[1]) if asks else None

        # Create metrics object
        metrics = DepthMetrics(
            symbol=symbol,
            timestamp=timestamp,
            bid_volume=bid_volume,
            ask_volume=ask_volume,
            imbalance_ratio=imbalance_ratio,
            imbalance_percent=imbalance_percent,
            buy_pressure=buy_pressure,
            sell_pressure=sell_pressure,
            net_pressure=net_pressure,
            total_liquidity=total_volume,
            bid_depth_5=bid_depth_5,
            ask_depth_5=ask_depth_5,
            bid_depth_10=bid_depth_10,
            ask_depth_10=ask_depth_10,
            best_bid=best_bid,
            best_ask=best_ask,
            spread_abs=spread_abs,
            spread_bps=spread_bps,
            mid_price=mid_price,
            vwap_bid=vwap_bid,
            vwap_ask=vwap_ask,
            bid_levels=bid_levels,
            ask_levels=ask_levels,
            total_levels=total_levels,
            strongest_bid_level=strongest_bid,
            strongest_ask_level=strongest_ask,
        )

        # Store current metrics
        self._current_metrics[symbol] = metrics
        self._last_update[symbol] = time.time()

        # Update historical data
        self._pressure_history[symbol].append((timestamp, net_pressure))
        self._imbalance_history[symbol].append((timestamp, imbalance_ratio))

        # Cleanup old data periodically
        if len(self._current_metrics) % 100 == 0:
            self._cleanup_expired_metrics()

        return metrics

    def get_current_metrics(self, symbol: str) -> Optional[DepthMetrics]:
        """Get current metrics for a symbol."""
        return self._current_metrics.get(symbol)

    def get_all_metrics(self) -> dict[str, DepthMetrics]:
        """Get current metrics for all symbols."""
        return self._current_metrics.copy()

    def get_pressure_history(
        self, symbol: str, timeframe: str = "5m"
    ) -> Optional[MarketPressureHistory]:
        """
        Get historical market pressure data.

        Args:
            symbol: Trading symbol
            timeframe: "1m", "5m", or "15m"

        Returns:
            MarketPressureHistory object or None
        """
        if symbol not in self._pressure_history:
            return None

        # Determine how many data points to include
        points_map = {"1m": 60, "5m": 300, "15m": 900}
        num_points = points_map.get(timeframe, 300)

        pressure_data = list(self._pressure_history[symbol])[-num_points:]
        imbalance_data = list(self._imbalance_history[symbol])[-num_points:]

        if not pressure_data:
            return None

        # Calculate statistics
        pressures = [p for _, p in pressure_data]
        avg_pressure = sum(pressures) / len(pressures)
        max_pressure = max(pressures)
        min_pressure = min(pressures)

        # Determine trend
        if len(pressures) >= 10:
            recent_avg = sum(pressures[-10:]) / 10
            if recent_avg > 20:
                trend = "bullish"
                trend_strength = min(1.0, recent_avg / 50)
            elif recent_avg < -20:
                trend = "bearish"
                trend_strength = min(1.0, abs(recent_avg) / 50)
            else:
                trend = "neutral"
                trend_strength = 1.0 - (abs(recent_avg) / 20)
        else:
            trend = "neutral"
            trend_strength = 0.5

        return MarketPressureHistory(
            symbol=symbol,
            timeframe=timeframe,
            pressure_history=pressure_data,
            imbalance_history=imbalance_data,
            avg_pressure=avg_pressure,
            max_pressure=max_pressure,
            min_pressure=min_pressure,
            trend=trend,
            trend_strength=trend_strength,
        )

    def get_market_summary(self) -> dict[str, any]:
        """
        Get overall market summary across all symbols.

        Returns:
            Dictionary with aggregated market metrics
        """
        if not self._current_metrics:
            return {"error": "No data available"}

        symbols_bullish = sum(
            1 for m in self._current_metrics.values() if m.net_pressure > 20
        )
        symbols_bearish = sum(
            1 for m in self._current_metrics.values() if m.net_pressure < -20
        )
        symbols_neutral = len(self._current_metrics) - symbols_bullish - symbols_bearish

        avg_pressure = sum(
            m.net_pressure for m in self._current_metrics.values()
        ) / len(self._current_metrics)

        avg_imbalance = sum(
            m.imbalance_ratio for m in self._current_metrics.values()
        ) / len(self._current_metrics)

        avg_spread_bps = sum(
            m.spread_bps for m in self._current_metrics.values()
        ) / len(self._current_metrics)

        total_liquidity = sum(m.total_liquidity for m in self._current_metrics.values())

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "symbols_tracked": len(self._current_metrics),
            "market_sentiment": {
                "bullish_symbols": symbols_bullish,
                "bearish_symbols": symbols_bearish,
                "neutral_symbols": symbols_neutral,
                "avg_net_pressure": round(avg_pressure, 2),
                "avg_imbalance_ratio": round(avg_imbalance, 3),
            },
            "liquidity": {
                "avg_spread_bps": round(avg_spread_bps, 2),
                "total_liquidity": round(total_liquidity, 4),
            },
            "top_pressure_symbols": self._get_top_pressure_symbols(),
        }

    def _calculate_vwap(self, levels: list[tuple[float, float]]) -> float:
        """Calculate volume-weighted average price."""
        if not levels:
            return 0.0

        total_value = sum(price * qty for price, qty in levels)
        total_volume = sum(qty for _, qty in levels)

        return total_value / total_volume if total_volume > 0 else 0.0

    def _get_top_pressure_symbols(self, limit: int = 5) -> dict[str, list[str]]:
        """Get symbols with highest buy/sell pressure."""
        metrics_list = list(self._current_metrics.values())

        # Sort by pressure
        by_buy_pressure = sorted(
            metrics_list, key=lambda m: m.buy_pressure, reverse=True
        )[:limit]

        by_sell_pressure = sorted(
            metrics_list, key=lambda m: m.sell_pressure, reverse=True
        )[:limit]

        return {
            "highest_buy_pressure": [m.symbol for m in by_buy_pressure],
            "highest_sell_pressure": [m.symbol for m in by_sell_pressure],
        }

    def _cleanup_expired_metrics(self):
        """Remove metrics that have expired based on TTL."""
        current_time = time.time()
        expired_symbols = [
            symbol
            for symbol, last_update in self._last_update.items()
            if current_time - last_update > self.metrics_ttl
        ]

        for symbol in expired_symbols:
            self._current_metrics.pop(symbol, None)
            self._last_update.pop(symbol, None)

        if expired_symbols:
            logger.debug(f"Cleaned up metrics for {len(expired_symbols)} symbols")
