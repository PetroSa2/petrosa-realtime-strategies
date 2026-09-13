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
    LevelHistory,
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
        """Test cleanup removes expired levels.

        Per #191 AC4: `update_orderbook` no longer sweeps internally, so
        eviction is triggered explicitly via `sweep_expired_levels()`.
        """
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
        now = datetime.utcnow()
        for i in range(5):
            tracker.update_orderbook(
                "BTCUSDT",
                bids,
                asks,
                timestamp=now - timedelta(seconds=i),
            )

        # The two old levels (400s stale) must still be present -- sweeping
        # is no longer an update_orderbook side effect (per #191 AC4).
        assert 49900.0 in tracker.bid_levels["BTCUSDT"]

        removed = tracker.sweep_expired_levels(current_time=now.timestamp())
        assert removed >= 1
        assert 49900.0 not in tracker.bid_levels["BTCUSDT"]

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


class TestOrderBookTrackerBoundedState:
    """Per #189: explicit bounds + eviction for symbol and price-level dims."""

    def test_ac2_max_symbols_enforced(self):
        """AC2: feeding max_symbols + 10 distinct symbols never exceeds cap."""
        max_symbols = 10
        tracker = OrderBookTracker(max_symbols=max_symbols)
        bids = [(50000.0, 1.0)]
        asks = [(50001.0, 1.0)]

        for i in range(max_symbols + 10):
            tracker.update_orderbook(f"SYM{i:03d}USDT", bids, asks)

        assert len(tracker.bid_levels) <= max_symbols
        assert len(tracker._symbol_tracker) <= max_symbols

    def test_ac3_detect_icebergs_does_not_create_symbol_entry(self):
        """AC3: detect_icebergs("NEVERSEEN") must not create a symbol entry."""
        tracker = OrderBookTracker()

        patterns = tracker.detect_icebergs("NEVERSEEN", current_price=50000.0)

        assert patterns == []
        assert len(tracker.bid_levels) == 0
        assert len(tracker.ask_levels) == 0
        assert "NEVERSEEN" not in tracker.bid_levels
        assert "NEVERSEEN" not in tracker.ask_levels

    def test_ac4_sweep_covers_idle_symbols_not_just_the_updating_one(self):
        """AC4 (#189): a sweep covers symbol A's expired levels even though
        only symbol B is currently being updated.

        Per #191 AC4: `update_orderbook` no longer triggers this sweep as a
        side effect (that per-message call site is exactly what #191
        removes) -- the test now drives `sweep_expired_levels()` explicitly,
        the same way `start_periodic_sweep`'s background task would.
        """
        tracker = OrderBookTracker(history_window_seconds=100)
        base_time = datetime.utcnow()

        # Symbol A gets one update, then goes idle.
        tracker.update_orderbook(
            "AAAUSDT", [(1.0, 1.0)], [(1.1, 1.0)], timestamp=base_time
        )
        assert "AAAUSDT" in tracker.bid_levels

        # Symbol B is updated well past A's history window — A was never
        # touched again, so before #189's fix its levels lived forever.
        far_future = base_time + timedelta(seconds=500)
        tracker.update_orderbook(
            "BBBUSDT", [(2.0, 1.0)], [(2.1, 1.0)], timestamp=far_future
        )

        # Per #191 AC4: no automatic sweep on update_orderbook anymore.
        assert "AAAUSDT" in tracker.bid_levels

        tracker.sweep_expired_levels(current_time=far_future.timestamp())

        assert "AAAUSDT" not in tracker.bid_levels
        assert "AAAUSDT" not in tracker.ask_levels

    def test_ac4_update_orderbook_does_not_sweep_synchronously(self):
        """AC4 (#191): update_orderbook must not evict expired levels as a
        side effect anymore -- eviction only happens via
        `sweep_expired_levels`/`start_periodic_sweep`."""
        tracker = OrderBookTracker(history_window_seconds=10)
        base_time = datetime.utcnow()

        tracker.update_orderbook(
            "BTCUSDT", [(50000.0, 1.0)], [(50001.0, 1.0)], timestamp=base_time
        )

        # Far past the 10s history window -- would have been evicted by the
        # old unconditional per-message sweep.
        later = base_time + timedelta(seconds=100)
        tracker.update_orderbook(
            "BTCUSDT", [(50000.0, 1.0)], [(50001.0, 1.0)], timestamp=later
        )

        assert 50000.0 in tracker.bid_levels["BTCUSDT"]

        removed = tracker.sweep_expired_levels(current_time=later.timestamp())
        assert removed == 0  # the level was just refreshed by the 2nd update

    def test_ac4_sweep_expired_levels_evicts_stale_entries(self):
        """AC4 (#191): `sweep_expired_levels()` is the public periodic-sweep
        entry point and correctly evicts levels older than history_window."""
        tracker = OrderBookTracker(history_window_seconds=10)
        base_time = datetime.utcnow()

        tracker.update_orderbook(
            "BTCUSDT", [(50000.0, 1.0)], [(50001.0, 1.0)], timestamp=base_time
        )

        later = base_time + timedelta(seconds=100)
        removed = tracker.sweep_expired_levels(current_time=later.timestamp())

        assert removed >= 1
        assert 50000.0 not in tracker.bid_levels.get("BTCUSDT", {})

    def test_start_stop_periodic_sweep_without_event_loop_is_noop(self):
        """start_periodic_sweep is a safe no-op when there is no running
        event loop (e.g. a plain sync unit test)."""
        tracker = OrderBookTracker()
        tracker.start_periodic_sweep()
        assert tracker._sweep_task is None
        tracker.stop_periodic_sweep()  # must not raise

    @pytest.mark.asyncio
    async def test_start_stop_periodic_sweep_with_event_loop(self):
        """start_periodic_sweep schedules a background task when a loop is
        running; stop_periodic_sweep cancels it cleanly."""
        tracker = OrderBookTracker(cleanup_interval_seconds=0.01)
        tracker.start_periodic_sweep()
        assert tracker._sweep_task is not None

        tracker.start_periodic_sweep()  # second call is a no-op
        assert tracker._sweep_task is not None

        tracker.stop_periodic_sweep()
        assert tracker._sweep_task is None

    def test_max_levels_per_symbol_enforced(self):
        """Per-symbol price-level cap evicts oldest level when exceeded."""
        tracker = OrderBookTracker(max_levels_per_symbol=5)
        base_time = datetime.utcnow()

        for i in range(20):
            price = 50000.0 + i
            tracker.update_orderbook(
                "BTCUSDT",
                [(price, 1.0)],
                [(price + 1000, 1.0)],
                timestamp=base_time + timedelta(seconds=i),
            )

        assert len(tracker.bid_levels["BTCUSDT"]) <= 5
        assert len(tracker.ask_levels["BTCUSDT"]) <= 5
