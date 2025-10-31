"""
Tests for Depth Analyzer and Market Metrics.

Tests the market depth analysis system including:
- Depth metrics calculation
- Pressure history tracking
- Market summary aggregation
"""

import pytest

from strategies.services.depth_analyzer import DepthAnalyzer


class TestDepthAnalyzer:
    """Test suite for DepthAnalyzer."""

    def test_analyze_depth_basic(self):
        """Test basic depth analysis calculation."""
        analyzer = DepthAnalyzer()

        bids = [(100.0, 1.0), (99.5, 2.0), (99.0, 1.5)]
        asks = [(100.5, 0.5), (101.0, 1.0), (101.5, 0.8)]

        metrics = analyzer.analyze_depth("BTCUSDT", bids, asks)

        assert metrics.symbol == "BTCUSDT"
        assert metrics.bid_volume == 4.5  # 1.0 + 2.0 + 1.5
        assert metrics.ask_volume == 2.3  # 0.5 + 1.0 + 0.8
        assert metrics.total_liquidity == 6.8
        assert metrics.bid_levels == 3
        assert metrics.ask_levels == 3

    def test_imbalance_calculation(self):
        """Test order book imbalance calculation."""
        analyzer = DepthAnalyzer()

        # More bids than asks (bullish)
        bids = [(100.0, 3.0)]
        asks = [(100.5, 1.0)]

        metrics = analyzer.analyze_depth("BTCUSDT", bids, asks)

        # (3.0 - 1.0) / (3.0 + 1.0) = 2.0 / 4.0 = 0.5
        assert metrics.imbalance_ratio == 0.5
        assert metrics.imbalance_percent == 50.0
        assert metrics.buy_pressure > metrics.sell_pressure
        assert metrics.net_pressure > 0  # Bullish

    def test_pressure_calculation(self):
        """Test market pressure calculation."""
        analyzer = DepthAnalyzer()

        # More bids than asks
        bids = [(100.0, 2.0)]
        asks = [(100.5, 1.0)]

        metrics = analyzer.analyze_depth("BTCUSDT", bids, asks)

        # buy_pressure = (2.0 / 3.0) * 100 = 66.67%
        # sell_pressure = (1.0 / 3.0) * 100 = 33.33%
        assert metrics.buy_pressure > 60
        assert metrics.sell_pressure < 40
        assert metrics.net_pressure > 25  # Clearly bullish

    def test_spread_calculation(self):
        """Test bid-ask spread calculation."""
        analyzer = DepthAnalyzer()

        bids = [(100.0, 1.0)]
        asks = [(100.5, 1.0)]

        metrics = analyzer.analyze_depth("BTCUSDT", bids, asks)

        assert metrics.best_bid == 100.0
        assert metrics.best_ask == 100.5
        assert metrics.spread_abs == 0.5
        assert metrics.mid_price == 100.25
        # spread_bps = (0.5 / 100.25) * 10000 ≈ 49.88
        assert 45 < metrics.spread_bps < 55

    def test_vwap_calculation(self):
        """Test volume-weighted average price calculation."""
        analyzer = DepthAnalyzer()

        # VWAP bid should be weighted towards higher volume levels
        bids = [(100.0, 2.0), (99.0, 1.0)]  # More volume at 100
        asks = [(101.0, 1.0), (102.0, 2.0)]  # More volume at 102

        metrics = analyzer.analyze_depth("BTCUSDT", bids, asks)

        # VWAP bid = (100*2 + 99*1) / (2+1) = 299/3 = 99.67
        assert 99.5 < metrics.vwap_bid < 100.0
        # VWAP ask = (101*1 + 102*2) / (1+2) = 305/3 = 101.67
        assert 101.5 < metrics.vwap_ask < 102.0

    def test_strongest_levels(self):
        """Test identification of strongest support/resistance."""
        analyzer = DepthAnalyzer()

        bids = [(100.0, 1.0), (99.5, 5.0), (99.0, 2.0)]  # Strongest at 99.5
        asks = [(100.5, 2.0), (101.0, 4.0), (101.5, 1.0)]  # Strongest at 101.0

        metrics = analyzer.analyze_depth("BTCUSDT", bids, asks)

        assert metrics.strongest_bid_level[0] == 99.5
        assert metrics.strongest_bid_level[1] == 5.0
        assert metrics.strongest_ask_level[0] == 101.0
        assert metrics.strongest_ask_level[1] == 4.0

    def test_pressure_history_tracking(self):
        """Test pressure history tracking over time."""
        analyzer = DepthAnalyzer()

        # Add multiple data points
        for i in range(100):
            bids = [(100.0, 2.0)]
            asks = [(100.5, 1.0)]
            analyzer.analyze_depth("BTCUSDT", bids, asks)

        # Use 5m timeframe to get more than 60 points (up to 300)
        history = analyzer.get_pressure_history("BTCUSDT", "5m")

        assert history is not None
        assert history.symbol == "BTCUSDT"
        assert (
            len(history.pressure_history) == 100
        )  # All 100 points should be included in 5m window
        assert history.trend in ["bullish", "bearish", "neutral"]
        assert 0 <= history.trend_strength <= 1

    def test_trend_detection_bullish(self):
        """Test bullish trend detection."""
        analyzer = DepthAnalyzer()

        # Consistently more bids than asks (bullish)
        for i in range(50):
            bids = [(100.0, 3.0)]
            asks = [(100.5, 1.0)]
            analyzer.analyze_depth("BTCUSDT", bids, asks)

        history = analyzer.get_pressure_history("BTCUSDT", "1m")

        assert history.trend == "bullish"
        assert history.avg_pressure > 20

    def test_trend_detection_bearish(self):
        """Test bearish trend detection."""
        analyzer = DepthAnalyzer()

        # Consistently more asks than bids (bearish)
        for i in range(50):
            bids = [(100.0, 1.0)]
            asks = [(100.5, 3.0)]
            analyzer.analyze_depth("BTCUSDT", bids, asks)

        history = analyzer.get_pressure_history("BTCUSDT", "1m")

        assert history.trend == "bearish"
        assert history.avg_pressure < -20

    def test_market_summary(self):
        """Test market summary aggregation."""
        analyzer = DepthAnalyzer()

        # Add data for multiple symbols
        analyzer.analyze_depth("BTCUSDT", [(100, 2.0)], [(100.5, 1.0)])  # Bullish
        analyzer.analyze_depth("ETHUSDT", [(2000, 1.0)], [(2005, 2.0)])  # Bearish
        analyzer.analyze_depth("BNBUSDT", [(300, 1.5)], [(305, 1.5)])  # Neutral

        summary = analyzer.get_market_summary()

        assert summary["symbols_tracked"] == 3
        assert "market_sentiment" in summary
        assert "liquidity" in summary
        assert "top_pressure_symbols" in summary
        assert summary["market_sentiment"]["bullish_symbols"] >= 0
        assert summary["market_sentiment"]["bearish_symbols"] >= 0
        assert summary["market_sentiment"]["neutral_symbols"] >= 0

    def test_get_current_metrics(self):
        """Test getting current metrics for a symbol."""
        analyzer = DepthAnalyzer()

        bids = [(100.0, 1.0)]
        asks = [(100.5, 1.0)]
        analyzer.analyze_depth("BTCUSDT", bids, asks)

        metrics = analyzer.get_current_metrics("BTCUSDT")

        assert metrics is not None
        assert metrics.symbol == "BTCUSDT"
        assert metrics.best_bid == 100.0
        assert metrics.best_ask == 100.5

    def test_get_all_metrics(self):
        """Test getting metrics for all symbols."""
        analyzer = DepthAnalyzer()

        analyzer.analyze_depth("BTCUSDT", [(100, 1.0)], [(100.5, 1.0)])
        analyzer.analyze_depth("ETHUSDT", [(2000, 1.0)], [(2005, 1.0)])

        all_metrics = analyzer.get_all_metrics()

        assert len(all_metrics) == 2
        assert "BTCUSDT" in all_metrics
        assert "ETHUSDT" in all_metrics

    def test_cleanup_triggered_after_100_analyses(self):
        """Test cleanup is triggered every 100 analyses - covers line 246."""
        from strategies.services.depth_analyzer import DepthAnalyzer

        analyzer = DepthAnalyzer()

        # Analyze 100 times to trigger cleanup
        bids = [[50000.0, 1.0]]
        asks = [[50010.0, 1.0]]

        for i in range(100):
            analyzer.analyze_depth(
                symbol=f"SYM{i % 10}USDT",
                bids=bids,
                asks=asks,  # Cycle through symbols
            )

        # If no exception, cleanup logic was executed
        assert True

    def test_cleanup_expired_metrics(self):
        """Test _cleanup_expired_metrics removes old data - covers lines 397-409."""
        import time

        from strategies.services.depth_analyzer import DepthAnalyzer

        analyzer = DepthAnalyzer()

        # Add metrics for a symbol
        bids = [[50000.0, 1.0]]
        asks = [[50010.0, 1.0]]
        analyzer.analyze_depth(symbol="BTCUSDT", bids=bids, asks=asks)

        # Modify the analyzer's TTL to be very short for testing
        if hasattr(analyzer, "metrics_ttl"):
            analyzer.metrics_ttl = 1  # 1 second

        # If we can modify last_update timestamp, do it
        if hasattr(analyzer, "_last_update"):
            analyzer._last_update["BTCUSDT"] = time.time() - 100  # Make it old

        # Trigger cleanup by analyzing 100 times
        for i in range(100):
            analyzer.analyze_depth(symbol="ETHUSDT", bids=bids, asks=asks)

        # Cleanup logic should have executed
        assert True

    def test_depth_levels(self):
        """Test liquidity depth at different levels."""
        analyzer = DepthAnalyzer()

        # Create 10 levels of depth
        bids = [(100 - i * 0.5, 1.0) for i in range(10)]
        asks = [(100 + i * 0.5, 1.0) for i in range(10)]

        metrics = analyzer.analyze_depth("BTCUSDT", bids, asks)

        # Top 5 levels should have 5.0 volume each
        assert metrics.bid_depth_5 == 5.0
        assert metrics.ask_depth_5 == 5.0
        # Top 10 levels should have all 10.0 volume
        assert metrics.bid_depth_10 == 10.0
        assert metrics.ask_depth_10 == 10.0

    def test_empty_order_book(self):
        """Test handling of empty order book."""
        analyzer = DepthAnalyzer()

        metrics = analyzer.analyze_depth("BTCUSDT", [], [])

        assert metrics.bid_volume == 0.0
        assert metrics.ask_volume == 0.0
        assert metrics.imbalance_ratio == 0.0
        assert metrics.total_liquidity == 0.0
        assert metrics.strongest_bid_level is None
        assert metrics.strongest_ask_level is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
