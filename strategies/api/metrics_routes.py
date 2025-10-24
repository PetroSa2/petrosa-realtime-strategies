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

from fastapi import APIRouter, HTTPException, Path, Query, status

from strategies.services.depth_analyzer import DepthAnalyzer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/metrics", tags=["market-metrics"])

# Global depth analyzer instance (injected on startup)
_depth_analyzer: Optional[DepthAnalyzer] = None


def set_depth_analyzer(analyzer: DepthAnalyzer) -> None:
    """Set the global depth analyzer instance."""
    global _depth_analyzer
    _depth_analyzer = analyzer


def get_depth_analyzer() -> DepthAnalyzer:
    """Get the global depth analyzer instance."""
    if _depth_analyzer is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Depth analyzer not initialized",
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

    **Use Cases**:
    - Monitor market sentiment for a symbol
    - Detect order book imbalances
    - Identify liquidity conditions
    - Track bid-ask spread changes
    """,
)
async def get_depth_metrics(
    symbol: str = Path(..., description="Trading symbol (e.g., BTCUSDT)"),
):
    """Get current depth metrics for a symbol."""
    try:
        analyzer = get_depth_analyzer()
        metrics = analyzer.get_current_metrics(symbol.upper())

        if metrics is None:
            return {
                "error": f"No metrics available for {symbol}",
                "message": "Symbol may not be actively tracked or data is stale",
                "suggestion": "Check GET /api/v1/metrics/all to see tracked symbols",
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
                "interpretation": (
                    "bullish"
                    if metrics.net_pressure > 20
                    else "bearish"
                    if metrics.net_pressure < -20
                    else "neutral"
                ),
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
                "spread": round(abs(metrics.vwap_bid - metrics.vwap_ask), 2),
            },
            "order_book_quality": {
                "bid_levels": metrics.bid_levels,
                "ask_levels": metrics.ask_levels,
                "total_levels": metrics.total_levels,
            },
            "strongest_levels": {
                "bid": {
                    "price": metrics.strongest_bid_level[0],
                    "volume": round(metrics.strongest_bid_level[1], 4),
                }
                if metrics.strongest_bid_level
                else None,
                "ask": {
                    "price": metrics.strongest_ask_level[0],
                    "volume": round(metrics.strongest_ask_level[1], 4),
                }
                if metrics.strongest_ask_level
                else None,
            },
        }

    except HTTPException:
        raise
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
                detail="Invalid timeframe. Must be '1m', '5m', or '15m'",
            )

        analyzer = get_depth_analyzer()
        history = analyzer.get_pressure_history(symbol.upper(), timeframe)

        if history is None:
            return {
                "error": f"No pressure history available for {symbol}",
                "message": "Symbol may not be actively tracked",
            }

        # Limit history data points in response to last 100
        pressure_limited = history.pressure_history[-100:]
        imbalance_limited = history.imbalance_history[-100:]

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
            "total_data_points": len(history.pressure_history),
            "returned_data_points": len(pressure_limited),
            "pressure_history": [
                {"timestamp": ts.isoformat(), "pressure": round(p, 2)}
                for ts, p in pressure_limited
            ],
            "imbalance_history": [
                {"timestamp": ts.isoformat(), "imbalance": round(i, 4)}
                for ts, i in imbalance_limited
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
    **For LLM Agents**: Get current metrics for all tracked symbols with filtering and pagination.

    Returns metrics for symbols with comprehensive filtering capabilities.

    **Example Request**: `GET /api/v1/metrics/all?symbols=BTCUSDT,ETHUSDT&limit=50`

    **Use Cases**:
    - Bulk monitoring of specific symbols
    - Identify outliers with pressure filters
    - Cross-symbol analysis
    - Dashboard data feed
    """,
)
async def get_all_metrics(
    symbols: str | None = Query(
        None, description="Comma-separated list of symbols to filter"
    ),
    min_pressure: float | None = Query(None, description="Minimum net pressure filter"),
    max_pressure: float | None = Query(None, description="Maximum net pressure filter"),
    trend: str | None = Query(
        None, description="Filter by trend (bullish, bearish, neutral)"
    ),
    limit: int = Query(
        50,
        ge=1,
        le=200,
        description="Maximum number of symbols (default: 50, max: 200)",
    ),
    offset: int = Query(0, ge=0, description="Pagination offset (default: 0)"),
    sort_by: str = Query(
        "symbol", description="Sort by field (symbol, pressure, imbalance, liquidity)"
    ),
    sort_order: str = Query("asc", description="Sort order (asc, desc)"),
):
    """Get current metrics for all symbols with filtering and pagination."""
    try:
        analyzer = get_depth_analyzer()
        all_metrics = analyzer.get_all_metrics()

        # Convert to list of tuples for easier filtering and sorting
        metrics_list = []
        for symbol, metrics in all_metrics.items():
            trend_classification = (
                "bullish"
                if metrics.net_pressure > 20
                else "bearish"
                if metrics.net_pressure < -20
                else "neutral"
            )

            metrics_list.append(
                (
                    symbol,
                    {
                        "timestamp": metrics.timestamp.isoformat(),
                        "net_pressure": round(metrics.net_pressure, 2),
                        "imbalance_percent": round(metrics.imbalance_percent, 2),
                        "spread_bps": round(metrics.spread_bps, 2),
                        "total_liquidity": round(metrics.total_liquidity, 4),
                        "mid_price": metrics.mid_price,
                        "trend": trend_classification,
                    },
                )
            )

        # Apply symbol filter
        if symbols:
            symbol_list = [s.strip().upper() for s in symbols.split(",")]
            metrics_list = [(s, m) for s, m in metrics_list if s in symbol_list]

        # Apply pressure filters
        if min_pressure is not None:
            metrics_list = [
                (s, m) for s, m in metrics_list if m["net_pressure"] >= min_pressure
            ]

        if max_pressure is not None:
            metrics_list = [
                (s, m) for s, m in metrics_list if m["net_pressure"] <= max_pressure
            ]

        # Apply trend filter
        if trend:
            trend_lower = trend.lower()
            metrics_list = [
                (s, m) for s, m in metrics_list if m["trend"] == trend_lower
            ]

        total_count = len(metrics_list)

        # Apply sorting
        reverse = sort_order.lower() == "desc"
        if sort_by == "symbol":
            metrics_list.sort(key=lambda x: x[0], reverse=reverse)
        elif sort_by == "pressure":
            metrics_list.sort(key=lambda x: x[1]["net_pressure"], reverse=reverse)
        elif sort_by == "imbalance":
            metrics_list.sort(key=lambda x: x[1]["imbalance_percent"], reverse=reverse)
        elif sort_by == "liquidity":
            metrics_list.sort(key=lambda x: x[1]["total_liquidity"], reverse=reverse)

        # Apply pagination
        paginated_metrics = metrics_list[offset : offset + limit]

        # Convert back to dict for response
        result = {symbol: metrics for symbol, metrics in paginated_metrics}

        return {
            "data": result,
            "pagination": {
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "page": (offset // limit) + 1,
                "pages": (total_count + limit - 1) // limit if limit > 0 else 0,
                "has_next": offset + limit < total_count,
                "has_previous": offset > 0,
            },
            "filters_applied": {
                "symbols": symbols,
                "min_pressure": min_pressure,
                "max_pressure": max_pressure,
                "trend": trend,
            },
            "sort": {
                "by": sort_by,
                "order": sort_order,
            },
            "symbols_count": len(result),
        }

    except Exception as e:
        logger.error(f"Error getting all metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))
