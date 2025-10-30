"""
Comprehensive tests for services/depth_analyzer.py.

Covers metric calculation, trend analysis, history tracking, and edge cases.
"""

import pytest
import time
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
from collections import deque

from strategies.services.depth_analyzer import DepthAnalyzer, DepthMetrics, MarketPressureHistory


@pytest.fixture
def analyzer():
    """Create depth analyzer instance."""
    return DepthAnalyzer(
        history_window_seconds=900,
        max_symbols=100,
        metrics_ttl_seconds=300
    )


@pytest.fixture
def sample_bids():
    """Sample bid data."""
    return [
        (50000.0, 1.0),
        (49999.0, 2.0),
        (49998.0, 1.5),
        (49997.0, 3.0),
        (49996.0, 2.5)
    ]


@pytest.fixture
def sample_asks():
    """Sample ask data."""
    return [
        (50001.0, 1.2),
        (50002.0, 1.8),
        (50003.0, 2.1),
        (50004.0, 1.7),
        (50005.0, 2.3)
    ]


def test_analyzer_initialization(analyzer):
    """Test analyzer initialization."""
    assert analyzer.history_window == 900
    assert analyzer.max_symbols == 100
    assert analyzer.metrics_ttl == 300
    assert len(analyzer._current_metrics) == 0
    assert len(analyzer._pressure_history) == 0
    assert len(analyzer._imbalance_history) == 0


def test_analyze_depth_basic_calculation(analyzer, sample_bids, sample_asks):
    """Test basic depth analysis calculation."""
    metrics = analyzer.analyze_depth("BTCUSDT", sample_bids, sample_asks)
    
    assert metrics.symbol == "BTCUSDT"
    assert metrics.bid_volume == 10.0  # Sum of bid quantities
    assert metrics.ask_volume == 9.1   # Sum of ask quantities
    assert metrics.total_liquidity == 19.1
    assert metrics.best_bid == 50000.0
    assert metrics.best_ask == 50001.0
    assert metrics.spread_abs == 1.0
    assert metrics.mid_price == 50000.5


def test_analyze_depth_imbalance_calculation(analyzer, sample_bids, sample_asks):
    """Test imbalance calculation."""
    metrics = analyzer.analyze_depth("BTCUSDT", sample_bids, sample_asks)
    
    # Imbalance ratio: (bid - ask) / (bid + ask) = (10.0 - 9.1) / 19.1 ≈ 0.047
    expected_ratio = (10.0 - 9.1) / 19.1
    assert abs(metrics.imbalance_ratio - expected_ratio) < 0.001
    assert abs(metrics.imbalance_percent - expected_ratio * 100) < 0.1


def test_analyze_depth_pressure_calculation(analyzer, sample_bids, sample_asks):
    """Test market pressure calculation."""
    metrics = analyzer.analyze_depth("BTCUSDT", sample_bids, sample_asks)
    
    # Buy pressure: bid_volume / total_volume * 100
    expected_buy_pressure = (10.0 / 19.1) * 100
    assert abs(metrics.buy_pressure - expected_buy_pressure) < 0.1
    
    # Sell pressure: ask_volume / total_volume * 100
    expected_sell_pressure = (9.1 / 19.1) * 100
    assert abs(metrics.sell_pressure - expected_sell_pressure) < 0.1
    
    # Net pressure: buy - sell
    assert abs(metrics.net_pressure - (expected_buy_pressure - expected_sell_pressure)) < 0.1


def test_analyze_depth_liquidity_calculation(analyzer, sample_bids, sample_asks):
    """Test liquidity depth calculation."""
    metrics = analyzer.analyze_depth("BTCUSDT", sample_bids, sample_asks)
    
    # Top 5 levels
    expected_bid_depth_5 = 10.0  # All 5 levels
    expected_ask_depth_5 = 9.1   # All 5 levels
    assert metrics.bid_depth_5 == expected_bid_depth_5
    assert metrics.ask_depth_5 == expected_ask_depth_5
    
    # Top 10 levels (same as all levels in this case)
    assert metrics.bid_depth_10 == expected_bid_depth_5
    assert metrics.ask_depth_10 == expected_ask_depth_5


def test_analyze_depth_spread_calculation(analyzer, sample_bids, sample_asks):
    """Test spread metrics calculation."""
    metrics = analyzer.analyze_depth("BTCUSDT", sample_bids, sample_asks)
    
    assert metrics.spread_abs == 1.0
    assert metrics.mid_price == 50000.5
    
    # Spread in basis points: (spread_abs / mid_price) * 10000
    expected_bps = (1.0 / 50000.5) * 10000
    assert abs(metrics.spread_bps - expected_bps) < 0.001


def test_analyze_depth_vwap_calculation(analyzer, sample_bids, sample_asks):
    """Test VWAP calculation."""
    metrics = analyzer.analyze_depth("BTCUSDT", sample_bids, sample_asks)
    
    # VWAP should be calculated correctly
    assert metrics.vwap_bid > 0
    assert metrics.vwap_ask > 0
    assert metrics.vwap_bid < metrics.vwap_ask  # Bid should be lower than ask


def test_analyze_depth_order_book_quality(analyzer, sample_bids, sample_asks):
    """Test order book quality metrics."""
    metrics = analyzer.analyze_depth("BTCUSDT", sample_bids, sample_asks)
    
    assert metrics.bid_levels == 5
    assert metrics.ask_levels == 5
    assert metrics.total_levels == 10


def test_analyze_depth_strongest_levels(analyzer, sample_bids, sample_asks):
    """Test strongest level identification."""
    metrics = analyzer.analyze_depth("BTCUSDT", sample_bids, sample_asks)
    
    # Strongest bid should be the one with highest volume
    assert metrics.strongest_bid_level is not None
    assert metrics.strongest_bid_level[0] == 49997.0  # Highest volume bid
    assert metrics.strongest_bid_level[1] == 3.0
    
    # Strongest ask should be the one with highest volume
    assert metrics.strongest_ask_level is not None
    assert metrics.strongest_ask_level[0] == 50005.0  # Highest volume ask
    assert metrics.strongest_ask_level[1] == 2.3


def test_analyze_depth_empty_order_book(analyzer):
    """Test analysis with empty order book."""
    metrics = analyzer.analyze_depth("BTCUSDT", [], [])
    
    assert metrics.bid_volume == 0.0
    assert metrics.ask_volume == 0.0
    assert metrics.imbalance_ratio == 0.0
    assert metrics.buy_pressure == 0.0
    assert metrics.sell_pressure == 0.0
    assert metrics.best_bid == 0.0
    assert metrics.best_ask == 0.0
    assert metrics.strongest_bid_level is None
    assert metrics.strongest_ask_level is None


def test_analyze_depth_bids_only(analyzer):
    """Test analysis with only bids."""
    bids = [(50000.0, 1.0), (49999.0, 2.0)]
    metrics = analyzer.analyze_depth("BTCUSDT", bids, [])
    
    assert metrics.bid_volume == 3.0
    assert metrics.ask_volume == 0.0
    assert metrics.imbalance_ratio == 1.0  # All volume is bid
    assert metrics.buy_pressure == 100.0
    assert metrics.sell_pressure == 0.0
    assert metrics.strongest_ask_level is None


def test_analyze_depth_asks_only(analyzer):
    """Test analysis with only asks."""
    asks = [(50001.0, 1.0), (50002.0, 2.0)]
    metrics = analyzer.analyze_depth("BTCUSDT", [], asks)
    
    assert metrics.bid_volume == 0.0
    assert metrics.ask_volume == 3.0
    assert metrics.imbalance_ratio == -1.0  # All volume is ask
    assert metrics.buy_pressure == 0.0
    assert metrics.sell_pressure == 100.0
    assert metrics.strongest_bid_level is None


def test_analyze_depth_insufficient_levels(analyzer):
    """Test analysis with insufficient levels for depth calculation."""
    bids = [(50000.0, 1.0)]  # Only 1 level
    asks = [(50001.0, 1.0)]
    
    metrics = analyzer.analyze_depth("BTCUSDT", bids, asks)
    
    # Should use total volume when insufficient levels
    assert metrics.bid_depth_5 == 1.0
    assert metrics.ask_depth_5 == 1.0
    assert metrics.bid_depth_10 == 1.0
    assert metrics.ask_depth_10 == 1.0


def test_update_orderbook(analyzer, sample_bids, sample_asks):
    """Test updating order book and storing metrics."""
    analyzer.update_orderbook("BTCUSDT", sample_bids, sample_asks)
    
    assert "BTCUSDT" in analyzer._current_metrics
    assert "BTCUSDT" in analyzer._pressure_history
    assert "BTCUSDT" in analyzer._imbalance_history
    assert "BTCUSDT" in analyzer._last_update


def test_get_current_metrics(analyzer, sample_bids, sample_asks):
    """Test getting current metrics."""
    analyzer.update_orderbook("BTCUSDT", sample_bids, sample_asks)
    
    metrics = analyzer.get_current_metrics("BTCUSDT")
    assert metrics is not None
    assert metrics.symbol == "BTCUSDT"
    
    # Test non-existent symbol
    assert analyzer.get_current_metrics("NONEXISTENT") is None


def test_get_pressure_history(analyzer, sample_bids, sample_asks):
    """Test getting pressure history."""
    analyzer.update_orderbook("BTCUSDT", sample_bids, sample_asks)
    
    history = analyzer.get_pressure_history("BTCUSDT", "5m")
    assert history is not None
    assert history.symbol == "BTCUSDT"
    assert history.timeframe == "5m"
    assert len(history.pressure_history) > 0
    assert len(history.imbalance_history) > 0


def test_get_pressure_history_nonexistent_symbol(analyzer):
    """Test getting pressure history for non-existent symbol."""
    history = analyzer.get_pressure_history("NONEXISTENT", "5m")
    assert history is None


def test_get_pressure_history_invalid_timeframe(analyzer, sample_bids, sample_asks):
    """Test getting pressure history with invalid timeframe."""
    analyzer.update_orderbook("BTCUSDT", sample_bids, sample_asks)
    
    history = analyzer.get_pressure_history("BTCUSDT", "invalid")
    assert history is None


def test_get_market_summary(analyzer, sample_bids, sample_asks):
    """Test getting market summary."""
    analyzer.update_orderbook("BTCUSDT", sample_bids, sample_asks)
    analyzer.update_orderbook("ETHUSDT", sample_bids, sample_asks)
    
    summary = analyzer.get_market_summary()
    
    assert summary["total_symbols"] == 2
    assert "bullish_count" in summary
    assert "bearish_count" in summary
    assert "neutral_count" in summary
    assert "avg_pressure" in summary
    assert "avg_imbalance" in summary


def test_get_all_metrics(analyzer, sample_bids, sample_asks):
    """Test getting all metrics."""
    analyzer.update_orderbook("BTCUSDT", sample_bids, sample_asks)
    analyzer.update_orderbook("ETHUSDT", sample_bids, sample_asks)
    
    all_metrics = analyzer.get_all_metrics()
    
    assert len(all_metrics) == 2
    assert "BTCUSDT" in all_metrics
    assert "ETHUSDT" in all_metrics


def test_cleanup_expired_metrics(analyzer, sample_bids, sample_asks):
    """Test cleanup of expired metrics."""
    # Mock old timestamp
    old_time = time.time() - 400  # 400 seconds ago (beyond TTL of 300)
    
    with patch("strategies.services.depth_analyzer.time.time", return_value=old_time):
        analyzer.update_orderbook("BTCUSDT", sample_bids, sample_asks)
    
    # Now with current time
    with patch("strategies.services.depth_analyzer.time.time", return_value=time.time()):
        analyzer._cleanup_expired_metrics()
        
        # Metrics should be cleaned up
        assert "BTCUSDT" not in analyzer._current_metrics


def test_calculate_vwap(analyzer):
    """Test VWAP calculation method."""
    levels = [(100.0, 1.0), (101.0, 2.0), (102.0, 1.0)]
    
    vwap = analyzer._calculate_vwap(levels)
    
    # Expected: (100*1 + 101*2 + 102*1) / (1+2+1) = 404/4 = 101.0
    assert vwap == 101.0


def test_calculate_vwap_empty(analyzer):
    """Test VWAP calculation with empty levels."""
    vwap = analyzer._calculate_vwap([])
    assert vwap == 0.0


def test_calculate_vwap_single_level(analyzer):
    """Test VWAP calculation with single level."""
    levels = [(100.0, 1.0)]
    
    vwap = analyzer._calculate_vwap(levels)
    assert vwap == 100.0


def test_find_strongest_level(analyzer):
    """Test finding strongest level by volume."""
    levels = [(100.0, 1.0), (101.0, 3.0), (102.0, 2.0)]
    
    strongest = analyzer._find_strongest_level(levels)
    
    assert strongest == (101.0, 3.0)  # Highest volume


def test_find_strongest_level_empty(analyzer):
    """Test finding strongest level with empty levels."""
    strongest = analyzer._find_strongest_level([])
    assert strongest is None


def test_calculate_trend_bullish(analyzer):
    """Test trend calculation for bullish market."""
    # Create pressure history with increasing trend
    history = deque([
        (datetime.utcnow() - timedelta(minutes=10), 10.0),
        (datetime.utcnow() - timedelta(minutes=5), 20.0),
        (datetime.utcnow(), 30.0)
    ])
    
    trend, strength = analyzer._calculate_trend(history)
    
    assert trend == "bullish"
    assert strength > 0.5


def test_calculate_trend_bearish(analyzer):
    """Test trend calculation for bearish market."""
    # Create pressure history with decreasing trend
    history = deque([
        (datetime.utcnow() - timedelta(minutes=10), 30.0),
        (datetime.utcnow() - timedelta(minutes=5), 20.0),
        (datetime.utcnow(), 10.0)
    ])
    
    trend, strength = analyzer._calculate_trend(history)
    
    assert trend == "bearish"
    assert strength > 0.5


def test_calculate_trend_neutral(analyzer):
    """Test trend calculation for neutral market."""
    # Create pressure history with no clear trend
    history = deque([
        (datetime.utcnow() - timedelta(minutes=10), 20.0),
        (datetime.utcnow() - timedelta(minutes=5), 21.0),
        (datetime.utcnow(), 19.0)
    ])
    
    trend, strength = analyzer._calculate_trend(history)
    
    assert trend == "neutral"
    assert strength < 0.5


def test_calculate_trend_insufficient_data(analyzer):
    """Test trend calculation with insufficient data."""
    history = deque([(datetime.utcnow(), 20.0)])
    
    trend, strength = analyzer._calculate_trend(history)
    
    assert trend == "neutral"
    assert strength == 0.0


def test_max_symbols_limit(analyzer):
    """Test maximum symbols limit."""
    # Create analyzer with small limit
    small_analyzer = DepthAnalyzer(max_symbols=2)
    
    # Add more symbols than limit
    small_analyzer.update_orderbook("SYMBOL1", [(100.0, 1.0)], [(101.0, 1.0)])
    small_analyzer.update_orderbook("SYMBOL2", [(100.0, 1.0)], [(101.0, 1.0)])
    small_analyzer.update_orderbook("SYMBOL3", [(100.0, 1.0)], [(101.0, 1.0)])
    
    # Should only have 2 symbols
    assert len(small_analyzer._current_metrics) <= 2


def test_metrics_ttl_expiration(analyzer, sample_bids, sample_asks):
    """Test metrics TTL expiration."""
    # Mock old timestamp
    old_time = time.time() - 400  # 400 seconds ago (beyond TTL of 300)
    
    with patch("strategies.services.depth_analyzer.time.time", return_value=old_time):
        analyzer.update_orderbook("BTCUSDT", sample_bids, sample_asks)
    
    # Check that metrics are considered expired
    with patch("strategies.services.depth_analyzer.time.time", return_value=time.time()):
        metrics = analyzer.get_current_metrics("BTCUSDT")
        assert metrics is None


def test_pressure_history_trend_calculation(analyzer, sample_bids, sample_asks):
    """Test pressure history trend calculation."""
    # Add multiple updates to create history
    for i in range(10):
        timestamp = datetime.utcnow() - timedelta(seconds=i*10)
        with patch("strategies.services.depth_analyzer.datetime") as mock_dt:
            mock_dt.utcnow.return_value = timestamp
            analyzer.update_orderbook("BTCUSDT", sample_bids, sample_asks)
    
    history = analyzer.get_pressure_history("BTCUSDT", "5m")
    
    assert history is not None
    assert history.trend in ["bullish", "bearish", "neutral"]
    assert 0.0 <= history.trend_strength <= 1.0
    assert history.avg_pressure is not None
    assert history.max_pressure is not None
    assert history.min_pressure is not None


def test_market_pressure_history_creation(analyzer):
    """Test MarketPressureHistory creation."""
    symbol = "BTCUSDT"
    timeframe = "5m"
    pressure_data = [
        (datetime.utcnow() - timedelta(minutes=5), 10.0),
        (datetime.utcnow() - timedelta(minutes=3), 20.0),
        (datetime.utcnow(), 30.0)
    ]
    imbalance_data = [
        (datetime.utcnow() - timedelta(minutes=5), 0.1),
        (datetime.utcnow() - timedelta(minutes=3), 0.2),
        (datetime.utcnow(), 0.3)
    ]
    
    history = MarketPressureHistory(
        symbol=symbol,
        timeframe=timeframe,
        pressure_history=pressure_data,
        imbalance_history=imbalance_data,
        avg_pressure=20.0,
        max_pressure=30.0,
        min_pressure=10.0,
        trend="bullish",
        trend_strength=0.8
    )
    
    assert history.symbol == symbol
    assert history.timeframe == timeframe
    assert len(history.pressure_history) == 3
    assert len(history.imbalance_history) == 3
    assert history.avg_pressure == 20.0
    assert history.trend == "bullish"
    assert history.trend_strength == 0.8
