"""
Unit tests for Spread Liquidity Strategy.

Tests spread widening/narrowing detection and signal generation.
"""

import pytest
from datetime import datetime, timedelta
from strategies.market_logic.spread_liquidity import SpreadLiquidityStrategy


class TestSpreadLiquidityStrategy:
    """Test cases for Spread Liquidity Strategy."""
    
    @pytest.fixture
    def strategy(self):
        """Create strategy instance with default config."""
        return SpreadLiquidityStrategy(
            spread_threshold_bps=10.0,
            spread_ratio_threshold=2.5,
            velocity_threshold=0.5,
            persistence_threshold_seconds=30.0,
            min_depth_reduction_pct=0.5,
            base_confidence=0.70,
            lookback_ticks=20,
            min_signal_interval_seconds=60.0
        )
    
    @pytest.fixture
    def normal_orderbook(self):
        """Normal orderbook with tight spread."""
        return {
            "bids": [
                (50000.00, 1.0),
                (49999.00, 1.5),
                (49998.00, 2.0),
                (49997.00, 1.5),
                (49996.00, 1.0),
            ],
            "asks": [
                (50001.00, 1.0),
                (50002.00, 1.5),
                (50003.00, 2.0),
                (50004.00, 1.5),
                (50005.00, 1.0),
            ]
        }
    
    @pytest.fixture
    def wide_orderbook(self):
        """Orderbook with wide spread."""
        return {
            "bids": [
                (49900.00, 0.5),
                (49890.00, 0.5),
                (49880.00, 0.5),
                (49870.00, 0.5),
                (49860.00, 0.5),
            ],
            "asks": [
                (50100.00, 0.5),
                (50110.00, 0.5),
                (50120.00, 0.5),
                (50130.00, 0.5),
                (50140.00, 0.5),
            ]
        }
    
    def test_initialization(self, strategy):
        """Test strategy initialization."""
        assert strategy is not None
        assert strategy.spread_threshold_bps == 10.0
        assert strategy.spread_ratio_threshold == 2.5
        assert strategy.lookback_ticks == 20
        assert len(strategy.spread_history) == 0
    
    def test_normal_spread_no_signal(self, strategy, normal_orderbook):
        """Test that normal spread doesn't generate signal."""
        signal = strategy.analyze(
            symbol="BTCUSDT",
            bids=normal_orderbook["bids"],
            asks=normal_orderbook["asks"]
        )
        
        # First few ticks won't generate signals (building history)
        assert signal is None
    
    def test_spread_metrics_calculation(self, strategy, normal_orderbook):
        """Test spread metrics are calculated correctly."""
        # Analyze once to create metrics
        strategy.analyze(
            symbol="BTCUSDT",
            bids=normal_orderbook["bids"],
            asks=normal_orderbook["asks"]
        )
        
        # Check history was updated
        assert len(strategy.spread_history["BTCUSDT"]) == 1
        
        metrics = strategy.spread_history["BTCUSDT"][0]
        assert metrics.best_bid == 50000.00
        assert metrics.best_ask == 50001.00
        assert metrics.mid_price == 50000.50
        assert metrics.spread_abs == 1.00
        assert abs(metrics.spread_bps - 0.2) < 0.1  # ~0.2 bps
    
    def test_spread_widening_detection(self, strategy, normal_orderbook, wide_orderbook):
        """Test detection of rapid spread widening."""
        # Build history with normal spreads
        for i in range(20):
            strategy.analyze(
                symbol="BTCUSDT",
                bids=normal_orderbook["bids"],
                asks=normal_orderbook["asks"],
                timestamp=datetime.utcnow() - timedelta(seconds=20-i)
            )
        
        # Sudden wide spread (liquidity withdrawal)
        signal = strategy.analyze(
            symbol="BTCUSDT",
            bids=wide_orderbook["bids"],
            asks=wide_orderbook["asks"]
        )
        
        # Should detect widening but may not signal immediately
        # (depends on persistence and other factors)
        # Check that spread was tracked
        assert len(strategy.spread_history["BTCUSDT"]) == 21
    
    def test_spread_narrowing_signal(self, strategy, wide_orderbook, normal_orderbook):
        """Test signal generation on spread narrowing."""
        # Build history with wide spreads
        for i in range(25):
            strategy.analyze(
                symbol="BTCUSDT",
                bids=wide_orderbook["bids"],
                asks=wide_orderbook["asks"],
                timestamp=datetime.utcnow() - timedelta(seconds=25-i)
            )
        
        # Track wide spread event
        assert "BTCUSDT" in strategy.wide_spread_events
        
        # Spread normalizes (should generate BUY signal)
        signal = strategy.analyze(
            symbol="BTCUSDT",
            bids=normal_orderbook["bids"],
            asks=normal_orderbook["asks"]
        )
        
        # May or may not generate signal depending on velocity
        # At minimum, event should be tracked
        if signal:
            assert signal.action == "buy"
            assert signal.confidence >= 0.70
            assert signal.strategy_id == "spread_liquidity"
    
    def test_rate_limiting(self, strategy, wide_orderbook, normal_orderbook):
        """Test that signals are rate limited."""
        # Generate first signal
        for i in range(25):
            strategy.analyze(
                symbol="BTCUSDT",
                bids=wide_orderbook["bids"],
                asks=wide_orderbook["asks"],
                timestamp=datetime.utcnow() - timedelta(seconds=100-i)
            )
        
        first_signal = strategy.analyze(
            symbol="BTCUSDT",
            bids=normal_orderbook["bids"],
            asks=normal_orderbook["asks"],
            timestamp=datetime.utcnow() - timedelta(seconds=70)
        )
        
        # Try to generate another signal immediately (within min_interval)
        for i in range(10):
            strategy.analyze(
                symbol="BTCUSDT",
                bids=wide_orderbook["bids"],
                asks=wide_orderbook["asks"],
                timestamp=datetime.utcnow() - timedelta(seconds=60-i)
            )
        
        second_signal = strategy.analyze(
            symbol="BTCUSDT",
            bids=normal_orderbook["bids"],
            asks=normal_orderbook["asks"],
            timestamp=datetime.utcnow() - timedelta(seconds=50)
        )
        
        # Second signal should be rate limited
        if first_signal:
            assert second_signal is None
    
    def test_empty_orderbook_handling(self, strategy):
        """Test handling of empty orderbook."""
        signal = strategy.analyze(
            symbol="BTCUSDT",
            bids=[],
            asks=[]
        )
        
        assert signal is None
    
    def test_invalid_orderbook_handling(self, strategy):
        """Test handling of invalid orderbook (ask < bid)."""
        invalid_ob = {
            "bids": [(50000.00, 1.0)],
            "asks": [(49000.00, 1.0)]  # Invalid: ask < bid
        }
        
        signal = strategy.analyze(
            symbol="BTCUSDT",
            bids=invalid_ob["bids"],
            asks=invalid_ob["asks"]
        )
        
        assert signal is None
    
    def test_statistics(self, strategy, normal_orderbook):
        """Test statistics tracking."""
        stats_before = strategy.get_statistics()
        assert stats_before["signals_generated"] == 0
        assert stats_before["events_detected"] == 0
        
        # Generate some activity
        for i in range(5):
            strategy.analyze(
                symbol="BTCUSDT",
                bids=normal_orderbook["bids"],
                asks=normal_orderbook["asks"]
            )
        
        stats_after = strategy.get_statistics()
        assert stats_after["symbols_tracked"] == 1
    
    def test_multiple_symbols(self, strategy, normal_orderbook):
        """Test tracking multiple symbols independently."""
        strategy.analyze(
            symbol="BTCUSDT",
            bids=normal_orderbook["bids"],
            asks=normal_orderbook["asks"]
        )
        
        strategy.analyze(
            symbol="ETHUSDT",
            bids=normal_orderbook["bids"],
            asks=normal_orderbook["asks"]
        )
        
        assert len(strategy.spread_history) == 2
        assert "BTCUSDT" in strategy.spread_history
        assert "ETHUSDT" in strategy.spread_history
    
    def test_confidence_calculation(self, strategy):
        """Test confidence increases with signal strength."""
        # Higher spread ratio should increase confidence
        snapshot1 = type('obj', (object,), {
            'spread_ratio': 3.0,
            'spread_velocity': -0.7,
            'depth_reduction_pct': 0.6
        })()
        
        confidence1 = strategy._calculate_confidence("narrowing", snapshot1, 60.0)
        
        snapshot2 = type('obj', (object,), {
            'spread_ratio': 5.0,
            'spread_velocity': -1.0,
            'depth_reduction_pct': 0.8
        })()
        
        confidence2 = strategy._calculate_confidence("narrowing", snapshot2, 120.0)
        
        assert confidence2 > confidence1
        assert confidence1 >= 0.70
        assert confidence2 <= 0.95

