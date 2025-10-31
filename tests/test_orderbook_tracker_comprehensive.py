import time
from datetime import datetime, timedelta

import pytest

from strategies.models.orderbook_tracker import LevelHistory, OrderBookTracker


def make_ts(dt: datetime) -> float:
    return dt.timestamp()


def test_refill_detection_increments_count_and_speed():
    tracker = OrderBookTracker(refill_speed_threshold_seconds=10.0, min_refill_count=3)

    symbol = "BTCUSDT"
    now = datetime.utcnow()

    # Sequence: high -> low -> high within threshold window
    tracker.update_orderbook(
        symbol,
        bids=[(30000.0, 100.0)],
        asks=[],
        timestamp=now,
    )
    tracker.update_orderbook(
        symbol,
        bids=[(30000.0, 40.0)],  # drop > 50%
        asks=[],
        timestamp=now + timedelta(seconds=2),
    )
    tracker.update_orderbook(
        symbol,
        bids=[(30000.0, 90.0)],  # restore > 80%
        asks=[],
        timestamp=now + timedelta(seconds=4),
    )

    hist = tracker.bid_levels[symbol][30000.0]
    assert hist.refill_count == 1
    assert hist.last_refill_time == pytest.approx(make_ts(now + timedelta(seconds=4)))

    # Trigger more refills to compute average refill speed
    tracker.update_orderbook(
        symbol,
        bids=[(30000.0, 30.0)],
        asks=[],
        timestamp=now + timedelta(seconds=6),
    )
    tracker.update_orderbook(
        symbol,
        bids=[(30000.0, 85.0)],
        asks=[],
        timestamp=now + timedelta(seconds=7),
    )

    assert hist.refill_count == 2
    # avg_refill_speed_seconds = (last_ts - first_seen) / refill_count
    assert hist.avg_refill_speed_seconds > 0


def test_consistency_statistics_and_flag():
    tracker = OrderBookTracker(consistency_threshold=0.15)
    symbol = "ETHUSDT"
    now = datetime.utcnow()

    # Add several snapshots with very similar quantities -> low std dev
    for i, qty in enumerate([100.0, 102.0, 98.0, 101.0, 99.5], start=0):
        tracker.update_orderbook(
            symbol,
            bids=[(2000.0, qty)],
            asks=[],
            timestamp=now + timedelta(seconds=i),
        )

    hist = tracker.bid_levels[symbol][2000.0]
    assert hist.avg_volume > 0
    assert hist.volume_std_dev >= 0
    assert hist.consistent_volume is True  # CV should be < threshold


def test_detect_icebergs_refill_pattern_priority():
    tracker = OrderBookTracker(min_refill_count=3, refill_speed_threshold_seconds=10.0)
    symbol = "BTCUSDT"
    now = datetime.utcnow()

    # Create 3 refills at same price
    seq = [
        (120.0, 100.0),
        (120.0, 40.0),
        (120.0, 90.0),
        (120.0, 35.0),
        (120.0, 88.0),
        (120.0, 30.0),
        (120.0, 92.0),
    ]
    for i, (price, qty) in enumerate(seq):
        tracker.update_orderbook(
            symbol,
            bids=[(price, qty)],
            asks=[],
            timestamp=now + timedelta(seconds=i * 2),
        )

    icebergs = tracker.detect_icebergs(symbol, current_price=120.0, proximity_pct=1.0)
    assert len(icebergs) == 1
    pat = icebergs[0]
    assert pat.pattern_type == "refill"
    assert pat.refill_count >= 3
    assert tracker.total_icebergs_detected >= 1


def test_detect_icebergs_consistent_size_with_persistence():
    tracker = OrderBookTracker(min_refill_count=10, consistency_threshold=0.2)
    symbol = "ADAUSDT"

    # Seed a history with consistent volume
    tracker.update_orderbook(
        symbol, bids=[(0.5, 100.0)], asks=[], timestamp=datetime.utcnow()
    )
    hist: LevelHistory = tracker.bid_levels[symbol][0.5]

    # Force consistent flag and long persistence without refills
    hist.consistent_volume = True
    hist.first_seen = time.time() - 180  # 3 minutes ago
    hist.refill_count = 0

    icebergs = tracker.detect_icebergs(symbol, current_price=0.5, proximity_pct=1.0)
    assert len(icebergs) == 1
    pat = icebergs[0]
    assert pat.pattern_type == "consistent_size"
    assert 0.0 <= pat.volume_consistency_score <= 1.0


def test_detect_icebergs_anchor_when_persistent_only():
    tracker = OrderBookTracker(min_refill_count=10)
    symbol = "SOLUSDT"

    tracker.update_orderbook(
        symbol, bids=[(150.0, 50.0)], asks=[], timestamp=datetime.utcnow()
    )
    hist: LevelHistory = tracker.bid_levels[symbol][150.0]

    hist.consistent_volume = False
    hist.first_seen = time.time() - 200  # > 180s

    icebergs = tracker.detect_icebergs(symbol, current_price=150.0, proximity_pct=1.0)
    assert len(icebergs) == 1
    assert icebergs[0].pattern_type == "anchor"


def test_cleanup_old_levels_removes_outdated_entries():
    tracker = OrderBookTracker(history_window_seconds=60)
    symbol = "XRPUSDT"
    now = time.time()

    # Create two levels: one old, one recent
    tracker.bid_levels[symbol][1.0] = LevelHistory(
        price=1.0,
        side="bid",
        snapshots=__import__("collections").deque(maxlen=100),
        first_seen=now - 120,
        last_seen=now - 120,
        total_appearances=1,
    )
    tracker.bid_levels[symbol][2.0] = LevelHistory(
        price=2.0,
        side="bid",
        snapshots=__import__("collections").deque(maxlen=100),
        first_seen=now,
        last_seen=now,
        total_appearances=1,
    )

    tracker._cleanup_old_levels(symbol, current_time=now)
    assert 1.0 not in tracker.bid_levels[symbol]
    assert 2.0 in tracker.bid_levels[symbol]


def test_detect_icebergs_respects_proximity_filter():
    tracker = OrderBookTracker(min_refill_count=1, refill_speed_threshold_seconds=10.0)
    symbol = "BTCUSDT"
    now = datetime.utcnow()

    # Create a refill pattern at price 100.0
    for i, qty in enumerate([100.0, 40.0, 90.0]):
        tracker.update_orderbook(
            symbol,
            bids=[(100.0, qty)],
            asks=[],
            timestamp=now + timedelta(seconds=i),
        )

    # Proximity 0.1% around 120.0 should exclude price 100.0
    icebergs_far = tracker.detect_icebergs(
        symbol, current_price=120.0, proximity_pct=0.1
    )
    assert icebergs_far == []

    # Proximity 25% should include 100.0 when current is 120.0
    icebergs_near = tracker.detect_icebergs(
        symbol, current_price=120.0, proximity_pct=25.0
    )
    assert len(icebergs_near) == 1


def test_get_statistics_returns_expected_keys():
    tracker = OrderBookTracker()
    symbol = "BTCUSDT"
    tracker.update_orderbook(symbol, bids=[(30000.0, 10.0)], asks=[(30010.0, 9.0)])
    stats = tracker.get_statistics()
    assert {
        "total_levels_tracked",
        "active_bid_levels",
        "active_ask_levels",
        "total_icebergs_detected",
        "symbols_tracked",
    }.issubset(stats.keys())
