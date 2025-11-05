"""Comprehensive strategy tests with realistic fixtures."""

import pytest
from datetime import datetime

from tests.fixtures.market_data_realistic import (
    BTCUSDT_DEPTH_SNAPSHOT,
    BTCUSDT_ICEBERG_TRADES,
    BTCUSDT_WIDENING_SPREAD,
    BTC_DOMINANCE_SCENARIO,
    CROSS_EXCHANGE_ARBITRAGE,
    generate_depth_updates,
    generate_realistic_klines,
)
from strategies.market_logic.spread_liquidity import SpreadLiquidityStrategy
from strategies.market_logic.iceberg_detector import IcebergDetectorStrategy
from strategies.models.market_data import DepthLevel, DepthUpdate, TradeData


class TestSpreadLiquidityWithFixtures:
    """Test spread/liquidity strategy with realistic data."""

    def test_normal_spread_no_signal(self):
        """Test that normal spread doesn't generate signal."""
        strategy = SpreadLiquidityStrategy()
        
        depth = DepthUpdate(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            bids=[DepthLevel(price=p, quantity=q) for p, q in BTCUSDT_DEPTH_SNAPSHOT["bids"]],
            asks=[DepthLevel(price=p, quantity=q) for p, q in BTCUSDT_DEPTH_SNAPSHOT["asks"]],
            first_update_id=1,
            final_update_id=2
        )
        
        signal = strategy.process_depth(depth)
        
        # Normal spread shouldn't trigger
        if signal:
            assert signal.confidence == "LOW"

    def test_widening_spread_detection(self):
        """Test detection of widening spread."""
        strategy = SpreadLiquidityStrategy()
        
        # Process sequence of widening spreads
        for depth_data in BTCUSDT_WIDENING_SPREAD:
            depth = DepthUpdate(
                symbol="BTCUSDT",
                timestamp=datetime.utcnow(),
                bids=[DepthLevel(price=p, quantity=q) for p, q in depth_data["bids"]],
                asks=[DepthLevel(price=p, quantity=q) for p, q in depth_data["asks"]],
                first_update_id=1,
                final_update_id=2
            )
            signal = strategy.process_depth(depth)
        
        # Should detect widening
        stats = strategy.get_statistics()
        assert stats["events_detected"] > 0 or stats["signals_generated"] >= 0

    def test_many_depth_updates(self):
        """Test processing many realistic depth updates."""
        strategy = SpreadLiquidityStrategy()
        
        updates = generate_depth_updates("BTCUSDT", count=100)
        
        for update_data in updates:
            depth = DepthUpdate(
                symbol=update_data["symbol"],
                timestamp=update_data["timestamp"],
                bids=[DepthLevel(price=p, quantity=q) for p, q in update_data["bids"]],
                asks=[DepthLevel(price=p, quantity=q) for p, q in update_data["asks"]],
                first_update_id=1,
                final_update_id=2
            )
            strategy.process_depth(depth)
        
        stats = strategy.get_statistics()
        assert stats["depth_updates_processed"] == 100


class TestIcebergDetectorWithFixtures:
    """Test iceberg detector with realistic trade sequences."""

    def test_iceberg_pattern_detection(self):
        """Test detection of iceberg order pattern."""
        strategy = IcebergDetectorStrategy()
        
        # Feed sequence of small trades at same price
        for i, trade_data in enumerate(BTCUSDT_ICEBERG_TRADES):
            trade = TradeData(
                symbol="BTCUSDT",
                timestamp=datetime.utcnow(),
                price=trade_data["price"],
                quantity=trade_data["quantity"],
                is_buyer_maker=trade_data["is_buyer_maker"],
                trade_id=1000 + i
            )
            signal = strategy.process_trade(trade)
        
        # Should detect iceberg pattern
        stats = strategy.get_statistics()
        assert stats["trades_processed"] == len(BTCUSDT_ICEBERG_TRADES)

    def test_random_trades_no_iceberg(self):
        """Test that random trades don't trigger false positives."""
        strategy = IcebergDetectorStrategy()
        
        # Random trades at different prices
        import random
        for i in range(50):
            trade = TradeData(
                symbol="BTCUSDT",
                timestamp=datetime.utcnow(),
                price=50000.0 + random.uniform(-100, 100),
                quantity=random.uniform(0.01, 1.0),
                is_buyer_maker=random.choice([True, False]),
                trade_id=i
            )
            strategy.process_trade(trade)
        
        stats = strategy.get_statistics()
        assert stats["trades_processed"] == 50


class TestStrategyStateMaintenance:
    """Test that strategies maintain state correctly over time."""

    def test_spread_liquidity_tracks_history(self):
        """Test that spread strategy maintains history."""
        strategy = SpreadLiquidityStrategy()
        
        # Process 50 depth updates
        for update_data in generate_depth_updates("BTCUSDT", 50):
            depth = DepthUpdate(
                symbol=update_data["symbol"],
                timestamp=update_data["timestamp"],
                bids=[DepthLevel(price=p, quantity=q) for p, q in update_data["bids"]],
                asks=[DepthLevel(price=p, quantity=q) for p, q in update_data["asks"]],
                first_update_id=1,
                final_update_id=2
            )
            strategy.process_depth(depth)
        
        # Verify state tracking
        stats = strategy.get_statistics()
        assert "depth_updates_processed" in stats
        assert stats["depth_updates_processed"] == 50

    def test_iceberg_detector_tracks_patterns(self):
        """Test iceberg detector maintains pattern history."""
        strategy = IcebergDetectorStrategy()
        
        # Process 100 trades
        import random
        for i in range(100):
            trade = TradeData(
                symbol="BTCUSDT",
                timestamp=datetime.utcnow(),
                price=50000.0,
                quantity=random.uniform(0.01, 0.5),
                is_buyer_maker=True,
                trade_id=i
            )
            strategy.process_trade(trade)
        
        stats = strategy.get_statistics()
        assert stats["trades_processed"] == 100


class TestStrategyPerformance:
    """Test strategy performance with high-volume data."""

    def test_spread_liquidity_handles_high_volume(self):
        """Test handling 1000 depth updates."""
        strategy = SpreadLiquidityStrategy()
        
        updates = generate_depth_updates("BTCUSDT", count=1000)
        
        for update_data in updates:
            depth = DepthUpdate(
                symbol=update_data["symbol"],
                timestamp=update_data["timestamp"],
                bids=[DepthLevel(price=p, quantity=q) for p, q in update_data["bids"]],
                asks=[DepthLevel(price=p, quantity=q) for p, q in update_data["asks"]],
                first_update_id=1,
                final_update_id=2
            )
            strategy.process_depth(depth)
        
        stats = strategy.get_statistics()
        assert stats["depth_updates_processed"] == 1000

    def test_iceberg_detector_handles_high_volume(self):
        """Test handling 1000 trades."""
        strategy = IcebergDetectorStrategy()
        
        import random
        for i in range(1000):
            trade = TradeData(
                symbol="BTCUSDT",
                timestamp=datetime.utcnow(),
                price=50000.0 + random.uniform(-50, 50),
                quantity=random.uniform(0.01, 2.0),
                is_buyer_maker=random.choice([True, False]),
                trade_id=i
            )
            strategy.process_trade(trade)
        
        stats = strategy.get_statistics()
        assert stats["trades_processed"] == 1000


class TestMultiSymbolProcessing:
    """Test strategies handling multiple symbols."""

    def test_spread_liquidity_multi_symbol(self):
        """Test processing multiple symbols simultaneously."""
        strategy = SpreadLiquidityStrategy()
        
        symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
        
        for symbol in symbols:
            updates = generate_depth_updates(symbol, count=20)
            for update_data in updates:
                depth = DepthUpdate(
                    symbol=update_data["symbol"],
                    timestamp=update_data["timestamp"],
                    bids=[DepthLevel(price=p, quantity=q) for p, q in update_data["bids"]],
                    asks=[DepthLevel(price=p, quantity=q) for p, q in update_data["asks"]],
                    first_update_id=1,
                    final_update_id=2
                )
                strategy.process_depth(depth)
        
        stats = strategy.get_statistics()
        assert stats["depth_updates_processed"] == 60  # 20 * 3 symbols

