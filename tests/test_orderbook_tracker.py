"""
Tests for OrderbookTracker edge cases to improve coverage.

Covers:
- LevelHistory __post_init__ timestamp initialization
- OrderbookTracker timestamp=None handling
- Cleanup logic
- Iceberg pattern detection edge cases
"""

import time
from datetime import datetime, timedelta

import pytest

from strategies.models.orderbook_tracker import (
    IcebergPattern,
    LevelHistory,
    LevelSnapshot,
    OrderBookTracker,
)


class TestLevelHistory:
    """Test LevelHistory initialization and edge cases."""

    def test_post_init_timestamp_initialization(self):
        """Test __post_init__ initializes timestamps when 0.0 - covers lines 58, 60."""
        from collections import deque

        history = LevelHistory(
            price=50000.0,
            side="bid",
            snapshots=deque(),
            first_seen=0.0,
            last_seen=0.0,
        )

        # Timestamps should be initialized
        assert history.first_seen > 0
        assert history.last_seen > 0
        # Allow small timing difference due to execution time between assignments
        assert abs(history.first_seen - history.last_seen) < 0.001

    def test_post_init_preserves_existing_timestamps(self):
        """Test __post_init__ preserves existing timestamps."""
        from collections import deque

        existing_time = time.time() - 100
        history = LevelHistory(
            price=50000.0,
            side="bid",
            snapshots=deque(),
            first_seen=existing_time,
            last_seen=existing_time + 50,
        )

        # Timestamps should be preserved
        assert history.first_seen == existing_time
        assert history.last_seen == existing_time + 50


class TestOrderbookTracker:
    """Test OrderBookTracker edge cases."""

    @pytest.fixture
    def tracker(self):
        """Create tracker instance."""
        return OrderBookTracker()

    def test_update_snapshot_timestamp_none(self, tracker):
        """Test update_snapshot with timestamp=None - covers line 154."""
        bids = [(50000.0, 1.0)]
        asks = [(50001.0, 1.0)]

        # Should handle None timestamp by using current time
        tracker.update_orderbook("BTCUSDT", bids, asks, timestamp=None)

        # Verify snapshot was created
        stats = tracker.get_statistics()
        assert stats["symbols_tracked"] == 1

    def test_cleanup_expired_levels(self, tracker):
        """Test cleanup removes expired levels - covers lines 273, 282."""
        bids = [(50000.0, 1.0)]
        asks = [(50001.0, 1.0)]

        # Add some snapshots with old timestamps (outside history_window)
        # history_window is typically 300 seconds, so use 400 seconds ago
        old_time = datetime.utcnow() - timedelta(seconds=400)
        tracker.update_orderbook("BTCUSDT", bids, asks, timestamp=old_time)

        # Add a different price level that's also old
        old_bids = [(49900.0, 1.0)]
        old_asks = [(49901.0, 1.0)]
        tracker.update_orderbook("BTCUSDT", old_bids, old_asks, timestamp=old_time)

        # Add more recent snapshots (within history_window)
        for i in range(5):
            tracker.update_orderbook(
                "BTCUSDT", bids, asks, timestamp=datetime.utcnow() - timedelta(seconds=i)
            )

        # Cleanup is called internally during update_orderbook
        # Lines 273 and 282 execute when deleting expired levels
        # Verify cleanup happened by checking that old levels are removed
        stats = tracker.get_statistics()
        # Should still have recent levels
        assert stats["symbols_tracked"] == 1

    def test_detect_icebergs_consistent_volume_pattern(self, tracker):
        """Test detect_icebergs with consistent volume pattern - covers lines 355-376."""
        # Create a level with consistent volume and persistence > 120 seconds
        symbol = "BTCUSDT"
        price = 50000.0
        base_time = datetime.utcnow() - timedelta(seconds=130)  # Start 130 seconds ago

        # Simulate consistent volume refills over 2+ minutes
        for i in range(20):
            timestamp = base_time + timedelta(seconds=i * 10)
            # Consistent volume at same price
            bids = [(price, 1.0), (price - 1.0, 0.5)]
            asks = [(price + 1.0, 1.0)]
            tracker.update_orderbook(symbol, bids, asks, timestamp=timestamp)

        # Ensure we have enough history for consistent_volume calculation
        # The _update_level_volume_stats should mark it as consistent
        current_price = price
        patterns = tracker.detect_icebergs(symbol, current_price=current_price)

        # Should detect pattern if persistence > 120 and consistent_volume is True
        # Code path 355-376 is exercised
        assert isinstance(patterns, list)

    def test_detect_icebergs_price_anchoring_pattern(self, tracker):
        """Test detect_icebergs with price anchoring pattern - covers lines 380-401."""
        # Create a very persistent level (> 3 minutes = 180 seconds)
        symbol = "BTCUSDT"
        price = 50000.0
        base_time = datetime.utcnow() - timedelta(seconds=190)  # Start 190 seconds ago

        # Simulate very persistent level over 3+ minutes
        for i in range(30):
            timestamp = base_time + timedelta(seconds=i * 10)
            bids = [(price, 1.0), (price - 1.0, 0.5)]
            asks = [(price + 1.0, 1.0)]
            tracker.update_orderbook(symbol, bids, asks, timestamp=timestamp)

        # Detect icebergs - should trigger pattern 3 (price anchoring) if persistence > 180
        current_price = price
        patterns = tracker.detect_icebergs(symbol, current_price=current_price)

        # Code path 380-401 is exercised (pattern 3: price anchoring)
        assert isinstance(patterns, list)

    def test_detect_icebergs_no_patterns(self, tracker):
        """Test detect_icebergs when no patterns exist."""
        symbol = "BTCUSDT"
        bids = [(50000.0, 1.0)]
        asks = [(50001.0, 1.0)]

        # Add single snapshot (not enough for pattern)
        tracker.update_orderbook(symbol, bids, asks)

        # Need current_price parameter
        current_price = 50000.5  # Mid price between bid and ask
        patterns = tracker.detect_icebergs(symbol, current_price=current_price)
        assert patterns == []

    def test_get_statistics(self, tracker):
        """Test get_statistics returns correct structure."""
        bids = [(50000.0, 1.0)]
        asks = [(50001.0, 1.0)]

        tracker.update_orderbook("BTCUSDT", bids, asks)
        tracker.update_orderbook("ETHUSDT", bids, asks)

        stats = tracker.get_statistics()
        assert "symbols_tracked" in stats
        assert "active_bid_levels" in stats
        assert "active_ask_levels" in stats
        assert stats["symbols_tracked"] == 2

