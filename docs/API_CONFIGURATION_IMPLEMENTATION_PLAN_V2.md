# API Configuration & Market Metrics Implementation Plan V2
## petrosa-realtime-strategies

**Status**: 📋 Enhanced Implementation Plan  
**Priority**: High  
**Estimated Effort**: 12-16 hours  
**Target Completion**: 2-3 days  

---

## Executive Summary

This enhanced plan implements:
1. **Real-time API Configuration** (original scope - 12 hours)
2. **Market Metrics & Depth Analytics** (NEW - 4 hours)

### Enhancements from V1

✨ **NEW**: Market Pressure & Depth Metrics API
- Real-time order book imbalance metrics
- Market pressure indicators (buy/sell pressure)
- Liquidity depth analysis
- Bid-ask spread analytics
- Volume-weighted metrics
- Historical depth snapshots

---

## Part 1: Configuration API (Original Scope)

*[Same as V1 - Phases 1-7 from original plan]*

Refer to the original implementation plan for:
- Phase 1: Expand Strategy Defaults (2 hours)
- Phase 2: Create Configuration Manager (3 hours)
- Phase 3: Create API Routes (2 hours)
- Phase 4: Integrate with Health Server (1 hour)
- Phase 5: Update Strategy Loading (2 hours)
- Phase 6: Add MongoDB Configuration (30 minutes)
- Phase 7: Update Main Entry Point (30 minutes)

**Subtotal: 11 hours**

---

## Part 2: Market Metrics & Depth Analytics API (NEW)

### Phase 8: Market Data Metrics System (4 hours)

#### Overview

Real-time analytics API exposing market depth insights from the order book data being processed.

#### Architecture

```
Market Data Flow:
1. WebSocket Data → Consumer
2. Consumer → Depth Analyzer (NEW)
3. Depth Analyzer → Metrics Calculator (NEW)
4. Metrics → In-Memory Store (with TTL)
5. API Endpoints → Return Metrics
```

#### File: `strategies/services/depth_analyzer.py` (NEW)

**Purpose**: Analyze order book depth data and calculate market metrics

```python
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
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

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
    strongest_bid_level: Optional[Tuple[float, float]]  # (price, volume)
    strongest_ask_level: Optional[Tuple[float, float]]


@dataclass
class MarketPressureHistory:
    """Historical market pressure data for trend analysis."""
    
    symbol: str
    timeframe: str  # "1m", "5m", "15m"
    
    pressure_history: List[Tuple[datetime, float]]  # (timestamp, net_pressure)
    imbalance_history: List[Tuple[datetime, float]]  # (timestamp, imbalance_ratio)
    
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
        metrics_ttl_seconds: int = 60,
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
        self._current_metrics: Dict[str, DepthMetrics] = {}
        
        # Historical data for trend analysis
        self._pressure_history: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=900)  # 15 min @ 1 update/sec
        )
        self._imbalance_history: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=900)
        )
        
        # Timestamps for TTL management
        self._last_update: Dict[str, float] = {}
        
        logger.info(
            f"Depth analyzer initialized: "
            f"window={history_window_seconds}s, "
            f"max_symbols={max_symbols}"
        )
    
    def analyze_depth(
        self,
        symbol: str,
        bids: List[Tuple[float, float]],  # [(price, quantity), ...]
        asks: List[Tuple[float, float]],
        timestamp: Optional[datetime] = None
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
        bid_volume = sum(qty for _, qty in bids)
        ask_volume = sum(qty for _, qty in asks)
        total_volume = bid_volume + ask_volume
        
        # Order book imbalance
        if total_volume > 0:
            imbalance_ratio = (bid_volume - ask_volume) / total_volume
            imbalance_percent = imbalance_ratio * 100
        else:
            imbalance_ratio = 0.0
            imbalance_percent = 0.0
        
        # Market pressure (normalized to 0-100 scale)
        buy_pressure = min(100, (bid_volume / (total_volume or 1)) * 100)
        sell_pressure = min(100, (ask_volume / (total_volume or 1)) * 100)
        net_pressure = buy_pressure - sell_pressure
        
        # Liquidity depth at different levels
        bid_depth_5 = sum(qty for _, qty in bids[:5])
        ask_depth_5 = sum(qty for _, qty in asks[:5])
        bid_depth_10 = sum(qty for _, qty in bids[:10])
        ask_depth_10 = sum(qty for _, qty in asks[:10])
        
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
        
        # Cleanup old data
        self._cleanup_expired_metrics()
        
        return metrics
    
    def get_current_metrics(self, symbol: str) -> Optional[DepthMetrics]:
        """Get current metrics for a symbol."""
        return self._current_metrics.get(symbol)
    
    def get_all_metrics(self) -> Dict[str, DepthMetrics]:
        """Get current metrics for all symbols."""
        return self._current_metrics.copy()
    
    def get_pressure_history(
        self,
        symbol: str,
        timeframe: str = "5m"
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
    
    def get_market_summary(self) -> Dict[str, any]:
        """
        Get overall market summary across all symbols.
        
        Returns:
            Dictionary with aggregated market metrics
        """
        if not self._current_metrics:
            return {"error": "No data available"}
        
        symbols_bullish = sum(
            1 for m in self._current_metrics.values()
            if m.net_pressure > 20
        )
        symbols_bearish = sum(
            1 for m in self._current_metrics.values()
            if m.net_pressure < -20
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
                "total_liquidity": sum(
                    m.total_liquidity for m in self._current_metrics.values()
                ),
            },
            "top_pressure_symbols": self._get_top_pressure_symbols(),
        }
    
    def _calculate_vwap(self, levels: List[Tuple[float, float]]) -> float:
        """Calculate volume-weighted average price."""
        if not levels:
            return 0.0
        
        total_value = sum(price * qty for price, qty in levels)
        total_volume = sum(qty for _, qty in levels)
        
        return total_value / total_volume if total_volume > 0 else 0.0
    
    def _get_top_pressure_symbols(self, limit: int = 5) -> Dict[str, List[str]]:
        """Get symbols with highest buy/sell pressure."""
        metrics_list = list(self._current_metrics.values())
        
        # Sort by pressure
        by_buy_pressure = sorted(
            metrics_list,
            key=lambda m: m.buy_pressure,
            reverse=True
        )[:limit]
        
        by_sell_pressure = sorted(
            metrics_list,
            key=lambda m: m.sell_pressure,
            reverse=True
        )[:limit]
        
        return {
            "highest_buy_pressure": [m.symbol for m in by_buy_pressure],
            "highest_sell_pressure": [m.symbol for m in by_sell_pressure],
        }
    
    def _cleanup_expired_metrics(self):
        """Remove metrics that have expired based on TTL."""
        current_time = time.time()
        expired_symbols = [
            symbol for symbol, last_update in self._last_update.items()
            if current_time - last_update > self.metrics_ttl
        ]
        
        for symbol in expired_symbols:
            self._current_metrics.pop(symbol, None)
            self._last_update.pop(symbol, None)
            
        if expired_symbols:
            logger.debug(f"Cleaned up metrics for {len(expired_symbols)} symbols")
```

#### File: `strategies/api/metrics_routes.py` (NEW)

**Purpose**: API endpoints for market metrics

```python
"""
Market Metrics API Routes.

Provides endpoints for real-time market depth analytics including:
- Current order book metrics
- Market pressure indicators
- Historical pressure trends
- Overall market summary
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Path, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/metrics", tags=["market-metrics"])

# Global depth analyzer instance (injected on startup)
_depth_analyzer = None


def set_depth_analyzer(analyzer):
    """Set the global depth analyzer instance."""
    global _depth_analyzer
    _depth_analyzer = analyzer


def get_depth_analyzer():
    """Get the global depth analyzer instance."""
    if _depth_analyzer is None:
        raise HTTPException(
            status_code=503,
            detail="Depth analyzer not initialized"
        )
    return _depth_analyzer


@router.get(
    "/depth/{symbol}",
    summary="Get current depth metrics for symbol",
    description="""
    **For LLM Agents**: Get real-time order book depth metrics for a specific symbol.
    
    Returns comprehensive metrics including:
    - Order book imbalance (bid vs ask volume)
    - Market pressure (buy pressure vs sell pressure)
    - Liquidity depth at different levels
    - Bid-ask spread metrics
    - Volume-weighted prices
    - Strongest support/resistance levels
    
    **Example Request**: `GET /api/v1/metrics/depth/BTCUSDT`
    
    **Example Response**:
    ```json
    {
      "symbol": "BTCUSDT",
      "timestamp": "2025-10-21T10:30:00Z",
      "imbalance_ratio": 0.15,
      "imbalance_percent": 15.0,
      "buy_pressure": 57.5,
      "sell_pressure": 42.5,
      "net_pressure": 15.0,
      "spread_bps": 2.5,
      "mid_price": 67500.0,
      "total_liquidity": 15.5,
      "strongest_bid_level": [67450.0, 2.5],
      "strongest_ask_level": [67550.0, 1.8]
    }
    ```
    
    **Use Cases**:
    - Monitor market sentiment for a symbol
    - Detect order book imbalances
    - Identify liquidity conditions
    - Track bid-ask spread changes
    """,
)
async def get_depth_metrics(
    symbol: str = Path(..., description="Trading symbol (e.g., BTCUSDT)")
):
    """Get current depth metrics for a symbol."""
    try:
        analyzer = get_depth_analyzer()
        metrics = analyzer.get_current_metrics(symbol.upper())
        
        if metrics is None:
            return {
                "error": f"No metrics available for {symbol}",
                "message": "Symbol may not be actively tracked or data is stale"
            }
        
        return {
            "symbol": metrics.symbol,
            "timestamp": metrics.timestamp.isoformat(),
            "imbalance": {
                "ratio": round(metrics.imbalance_ratio, 4),
                "percent": round(metrics.imbalance_percent, 2),
                "bid_volume": round(metrics.bid_volume, 4),
                "ask_volume": round(metrics.ask_volume, 4),
            },
            "pressure": {
                "buy_pressure": round(metrics.buy_pressure, 2),
                "sell_pressure": round(metrics.sell_pressure, 2),
                "net_pressure": round(metrics.net_pressure, 2),
            },
            "liquidity": {
                "total": round(metrics.total_liquidity, 4),
                "bid_depth_5": round(metrics.bid_depth_5, 4),
                "ask_depth_5": round(metrics.ask_depth_5, 4),
                "bid_depth_10": round(metrics.bid_depth_10, 4),
                "ask_depth_10": round(metrics.ask_depth_10, 4),
            },
            "spread": {
                "best_bid": metrics.best_bid,
                "best_ask": metrics.best_ask,
                "spread_abs": round(metrics.spread_abs, 2),
                "spread_bps": round(metrics.spread_bps, 2),
                "mid_price": metrics.mid_price,
            },
            "vwap": {
                "bid": round(metrics.vwap_bid, 2),
                "ask": round(metrics.vwap_ask, 2),
            },
            "order_book_quality": {
                "bid_levels": metrics.bid_levels,
                "ask_levels": metrics.ask_levels,
                "total_levels": metrics.total_levels,
            },
            "strongest_levels": {
                "bid": {
                    "price": metrics.strongest_bid_level[0] if metrics.strongest_bid_level else None,
                    "volume": round(metrics.strongest_bid_level[1], 4) if metrics.strongest_bid_level else None,
                } if metrics.strongest_bid_level else None,
                "ask": {
                    "price": metrics.strongest_ask_level[0] if metrics.strongest_ask_level else None,
                    "volume": round(metrics.strongest_ask_level[1], 4) if metrics.strongest_ask_level else None,
                } if metrics.strongest_ask_level else None,
            },
        }
    
    except Exception as e:
        logger.error(f"Error getting depth metrics for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/pressure/{symbol}",
    summary="Get market pressure history",
    description="""
    **For LLM Agents**: Get historical market pressure data for trend analysis.
    
    Returns pressure history over different timeframes:
    - 1m (1 minute): Last 60 data points
    - 5m (5 minutes): Last 300 data points
    - 15m (15 minutes): Last 900 data points
    
    Includes:
    - Pressure history (time series)
    - Imbalance history (time series)
    - Statistical summary (avg, max, min)
    - Trend analysis (bullish/bearish/neutral)
    - Trend strength indicator
    
    **Example Request**: `GET /api/v1/metrics/pressure/BTCUSDT?timeframe=5m`
    
    **Use Cases**:
    - Identify pressure trends
    - Detect sustained buying/selling
    - Confirm momentum signals
    - Track market sentiment changes
    """,
)
async def get_pressure_history(
    symbol: str = Path(..., description="Trading symbol"),
    timeframe: str = Query("5m", description="Timeframe: 1m, 5m, or 15m"),
):
    """Get market pressure history for a symbol."""
    try:
        if timeframe not in ["1m", "5m", "15m"]:
            raise HTTPException(
                status_code=400,
                detail="Invalid timeframe. Must be '1m', '5m', or '15m'"
            )
        
        analyzer = get_depth_analyzer()
        history = analyzer.get_pressure_history(symbol.upper(), timeframe)
        
        if history is None:
            return {
                "error": f"No pressure history available for {symbol}",
                "message": "Symbol may not be actively tracked"
            }
        
        return {
            "symbol": history.symbol,
            "timeframe": history.timeframe,
            "summary": {
                "avg_pressure": round(history.avg_pressure, 2),
                "max_pressure": round(history.max_pressure, 2),
                "min_pressure": round(history.min_pressure, 2),
                "trend": history.trend,
                "trend_strength": round(history.trend_strength, 2),
            },
            "data_points": len(history.pressure_history),
            "pressure_history": [
                {"timestamp": ts.isoformat(), "pressure": round(p, 2)}
                for ts, p in history.pressure_history[-100:]  # Last 100 points
            ],
            "imbalance_history": [
                {"timestamp": ts.isoformat(), "imbalance": round(i, 4)}
                for ts, i in history.imbalance_history[-100:]
            ],
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting pressure history for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/summary",
    summary="Get overall market summary",
    description="""
    **For LLM Agents**: Get aggregated market metrics across all tracked symbols.
    
    Returns:
    - Number of symbols tracked
    - Market sentiment distribution (bullish/bearish/neutral)
    - Average market pressure
    - Average order book imbalance
    - Average spread
    - Total liquidity
    - Top symbols by buy/sell pressure
    
    **Example Request**: `GET /api/v1/metrics/summary`
    
    **Use Cases**:
    - Get overall market sentiment
    - Identify market-wide trends
    - Compare individual symbols to market average
    - Monitor overall liquidity conditions
    """,
)
async def get_market_summary():
    """Get overall market summary."""
    try:
        analyzer = get_depth_analyzer()
        summary = analyzer.get_market_summary()
        return summary
    
    except Exception as e:
        logger.error(f"Error getting market summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/all",
    summary="Get metrics for all symbols",
    description="""
    **For LLM Agents**: Get current metrics for all tracked symbols.
    
    Returns a dictionary with symbol as key and metrics as value.
    
    **Example Request**: `GET /api/v1/metrics/all`
    
    **Use Cases**:
    - Bulk monitoring of all symbols
    - Identify outliers
    - Cross-symbol analysis
    - Dashboard data feed
    """,
)
async def get_all_metrics():
    """Get current metrics for all symbols."""
    try:
        analyzer = get_depth_analyzer()
        all_metrics = analyzer.get_all_metrics()
        
        # Convert to JSON-friendly format
        result = {}
        for symbol, metrics in all_metrics.items():
            result[symbol] = {
                "timestamp": metrics.timestamp.isoformat(),
                "net_pressure": round(metrics.net_pressure, 2),
                "imbalance_percent": round(metrics.imbalance_percent, 2),
                "spread_bps": round(metrics.spread_bps, 2),
                "total_liquidity": round(metrics.total_liquidity, 4),
                "mid_price": metrics.mid_price,
            }
        
        return {
            "symbols_count": len(result),
            "metrics": result
        }
    
    except Exception as e:
        logger.error(f"Error getting all metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

#### Integration with Consumer

**File**: `strategies/core/consumer.py` (UPDATE)

Add depth analyzer integration:

```python
from strategies.services.depth_analyzer import DepthAnalyzer

class NATSConsumer:
    def __init__(
        self,
        # ... existing params ...
        depth_analyzer: Optional[DepthAnalyzer] = None,
    ):
        # ... existing code ...
        self.depth_analyzer = depth_analyzer or DepthAnalyzer()
    
    async def _process_market_data(self, market_data: MarketDataMessage):
        """Process market data through strategies AND depth analyzer."""
        
        # Existing strategy processing...
        
        # NEW: Analyze depth data if it's a depth update
        if market_data.stream and 'depth' in market_data.stream:
            try:
                depth_data = market_data.data
                if hasattr(depth_data, 'bids') and hasattr(depth_data, 'asks'):
                    symbol = market_data.stream.split('@')[0].upper()
                    
                    # Convert to list of tuples
                    bids = [(float(b.price), float(b.quantity)) for b in depth_data.bids]
                    asks = [(float(a.price), float(a.quantity)) for a in depth_data.asks]
                    
                    # Analyze and store metrics
                    self.depth_analyzer.analyze_depth(symbol, bids, asks)
                    
            except Exception as e:
                self.logger.error(f"Error analyzing depth data: {e}")
```

#### Integration with Health Server

**File**: `strategies/health/server.py` (UPDATE)

Include metrics router:

```python
from strategies.api.metrics_routes import router as metrics_router
from strategies.api.metrics_routes import set_depth_analyzer

# In __init__:
self.app.include_router(metrics_router)

# In lifespan:
# After initializing depth_analyzer
set_depth_analyzer(depth_analyzer)
```

---

## Combined Implementation Timeline

### Day 1 (8 hours)
**Morning** (4 hours):
- Phase 1: Expand Strategy Defaults (2 hours)
- Phase 2: Create Configuration Manager (start - 2 hours)

**Afternoon** (4 hours):
- Phase 2: Complete Configuration Manager (1 hour)
- Phase 3: Create API Routes (2 hours)
- Phase 8: Create Depth Analyzer (start - 1 hour)

### Day 2 (8 hours)
**Morning** (4 hours):
- Phase 8: Complete Depth Analyzer & Metrics API (3 hours)
- Phase 4: Integrate with Health Server (1 hour)

**Afternoon** (4 hours):
- Phase 5: Update Strategy Loading (2 hours)
- Phase 6 & 7: MongoDB + Main Entry Point (1 hour)
- Integration Testing (1 hour)

### Total: 16 hours over 2 days

---

## Enhanced API Endpoints Summary

### Configuration API (11 endpoints)
- `GET /api/v1/strategies` - List all strategies
- `GET /api/v1/strategies/{id}/schema` - Get parameter schema
- `GET /api/v1/strategies/{id}/defaults` - Get defaults
- `GET /api/v1/strategies/{id}/config` - Get global config
- `GET /api/v1/strategies/{id}/config/{symbol}` - Get symbol config
- `POST /api/v1/strategies/{id}/config` - Update global config
- `POST /api/v1/strategies/{id}/config/{symbol}` - Update symbol config
- `DELETE /api/v1/strategies/{id}/config` - Delete global config
- `DELETE /api/v1/strategies/{id}/config/{symbol}` - Delete symbol config
- `GET /api/v1/strategies/{id}/audit` - Get audit trail
- `POST /api/v1/strategies/cache/refresh` - Refresh cache

### Market Metrics API (4 endpoints) ✨ NEW
- `GET /api/v1/metrics/depth/{symbol}` - Current depth metrics
- `GET /api/v1/metrics/pressure/{symbol}?timeframe=5m` - Pressure history
- `GET /api/v1/metrics/summary` - Overall market summary
- `GET /api/v1/metrics/all` - All symbols metrics

---

## Testing Plan (Enhanced)

### Unit Tests for Depth Analyzer

```python
import pytest
from strategies.services.depth_analyzer import DepthAnalyzer

def test_analyze_depth():
    """Test depth analysis calculation."""
    analyzer = DepthAnalyzer()
    
    bids = [(100.0, 1.0), (99.5, 2.0), (99.0, 1.5)]
    asks = [(100.5, 0.5), (101.0, 1.0), (101.5, 0.8)]
    
    metrics = analyzer.analyze_depth("BTCUSDT", bids, asks)
    
    assert metrics.symbol == "BTCUSDT"
    assert metrics.bid_volume == 4.5
    assert metrics.ask_volume == 2.3
    assert metrics.imbalance_ratio > 0  # More bids than asks
    assert metrics.buy_pressure > metrics.sell_pressure
    assert metrics.spread_abs == 0.5

def test_pressure_history():
    """Test pressure history tracking."""
    analyzer = DepthAnalyzer()
    
    # Add some data points
    for i in range(100):
        bids = [(100.0, 2.0)]
        asks = [(100.5, 1.0)]
        analyzer.analyze_depth("BTCUSDT", bids, asks)
    
    history = analyzer.get_pressure_history("BTCUSDT", "1m")
    
    assert history is not None
    assert history.trend == "bullish"  # More bid volume
    assert len(history.pressure_history) == 100

def test_market_summary():
    """Test market summary aggregation."""
    analyzer = DepthAnalyzer()
    
    # Add data for multiple symbols
    analyzer.analyze_depth("BTCUSDT", [(100, 2.0)], [(100.5, 1.0)])
    analyzer.analyze_depth("ETHUSDT", [(2000, 1.0)], [(2005, 2.0)])
    
    summary = analyzer.get_market_summary()
    
    assert summary["symbols_tracked"] == 2
    assert "market_sentiment" in summary
    assert "liquidity" in summary
```

### Integration Tests for Metrics API

```python
import pytest
from fastapi.testclient import TestClient

def test_get_depth_metrics(client):
    """Test depth metrics endpoint."""
    response = client.get("/api/v1/metrics/depth/BTCUSDT")
    assert response.status_code == 200
    data = response.json()
    
    assert "symbol" in data
    assert "imbalance" in data
    assert "pressure" in data
    assert "liquidity" in data

def test_get_pressure_history(client):
    """Test pressure history endpoint."""
    response = client.get("/api/v1/metrics/pressure/BTCUSDT?timeframe=5m")
    assert response.status_code == 200
    data = response.json()
    
    assert "summary" in data
    assert "trend" in data["summary"]
    assert data["summary"]["trend"] in ["bullish", "bearish", "neutral"]

def test_get_market_summary(client):
    """Test market summary endpoint."""
    response = client.get("/api/v1/metrics/summary")
    assert response.status_code == 200
    data = response.json()
    
    assert "symbols_tracked" in data
    assert "market_sentiment" in data
    assert "liquidity" in data
```

---

## Usage Examples

### Example 1: Monitor Market Pressure

```bash
# Get current pressure for BTC
curl http://realtime-strategies:8080/api/v1/metrics/depth/BTCUSDT | jq

# Response shows buy/sell pressure balance
{
  "symbol": "BTCUSDT",
  "pressure": {
    "buy_pressure": 65.5,
    "sell_pressure": 34.5,
    "net_pressure": 31.0
  },
  "imbalance": {
    "ratio": 0.31,
    "percent": 31.0
  }
}
```

### Example 2: Track Pressure Trends

```bash
# Get 5-minute pressure history
curl "http://realtime-strategies:8080/api/v1/metrics/pressure/BTCUSDT?timeframe=5m" | jq

# Response shows trend
{
  "symbol": "BTCUSDT",
  "summary": {
    "trend": "bullish",
    "trend_strength": 0.75,
    "avg_pressure": 25.5
  }
}
```

### Example 3: Overall Market Sentiment

```bash
# Get market-wide summary
curl http://realtime-strategies:8080/api/v1/metrics/summary | jq

# Response
{
  "symbols_tracked": 45,
  "market_sentiment": {
    "bullish_symbols": 28,
    "bearish_symbols": 12,
    "neutral_symbols": 5,
    "avg_net_pressure": 15.5
  }
}
```

### Example 4: Dashboard Data Feed

```bash
# Get all symbols metrics for dashboard
curl http://realtime-strategies:8080/api/v1/metrics/all | jq

# Returns metrics for all tracked symbols
{
  "symbols_count": 45,
  "metrics": {
    "BTCUSDT": {
      "net_pressure": 31.0,
      "imbalance_percent": 15.5,
      "spread_bps": 2.5
    },
    "ETHUSDT": { ... }
  }
}
```

---

## Benefits of Enhanced Plan

### Configuration API Benefits
✅ Real-time parameter updates (no restarts)
✅ Per-symbol strategy customization
✅ Full audit trail
✅ Schema-based validation
✅ Backward compatible

### Market Metrics API Benefits ✨ NEW
✅ Real-time market pressure indicators
✅ Order book imbalance detection
✅ Liquidity depth analysis
✅ Historical trend tracking
✅ Market sentiment aggregation
✅ Support/resistance level identification
✅ Spread monitoring
✅ Volume-weighted pricing

### Use Cases
- **Traders**: Monitor market pressure before trading
- **Risk Managers**: Track liquidity and spread conditions
- **Strategies**: Use pressure data for signal confirmation
- **Dashboards**: Real-time market overview
- **Alerts**: Trigger on pressure/imbalance thresholds
- **Research**: Analyze market microstructure

---

## Success Criteria (Enhanced)

### Configuration API
- ✅ All 6 strategies configurable via API
- ✅ Configuration updates take effect within 60 seconds
- ✅ Full audit trail maintained
- ✅ Zero downtime during updates

### Market Metrics API ✨ NEW
- ✅ Depth metrics updated in real-time (< 1 second lag)
- ✅ Pressure history maintained for 15 minutes
- ✅ API response time < 50ms (metrics)
- ✅ Handles 100+ symbols simultaneously
- ✅ Memory usage < 100MB for metrics storage
- ✅ No impact on strategy processing performance

---

## Next Steps

1. **Review enhanced plan** - Confirm market metrics requirements
2. **Approve implementation** - Proceed with both parts
3. **Phase implementation** - Configuration first, then metrics
4. **Deploy to production** - Monitor both systems
5. **Iterate based on feedback** - Add more metrics as needed

---

**Questions?**

- Configuration API follows proven TA Bot pattern
- Market Metrics API provides unique depth insights
- Both systems integrate seamlessly
- Production-ready architecture

Ready to implement when you approve! 🚀

**Document Version**: 2.0  
**Last Updated**: 2025-10-21  
**Status**: Awaiting Approval

