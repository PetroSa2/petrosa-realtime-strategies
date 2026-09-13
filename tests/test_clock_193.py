"""
Tests for the injected clock abstraction (#193).

Covers:
- AC5: iceberg classification is stable when wall-clock time advances but
  message time does not (proves the mixed-clock defect is gone).
- AC6: classification is identical under TZ=America/Sao_Paulo and TZ=UTC
  (proves the naive-datetime + local-timezone-offset defect is gone).
"""

import time as time_module
from datetime import UTC, datetime, timedelta

import pytest

from strategies.core.clock import FixedClock, SystemClock
from strategies.market_logic.spread_liquidity import SpreadLiquidityStrategy
from strategies.models.orderbook_tracker import OrderBookTracker
from strategies.models.spread_metrics import SpreadEvent, SpreadMetrics, SpreadSnapshot

BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _orderbook(bid=50000.0, ask=50001.0):
    return {
        "bids": [(bid, 1.0), (bid - 1, 1.0)],
        "asks": [(ask, 1.0), (ask + 1, 1.0)],
    }


class TestFixedClock:
    def test_requires_aware_datetime(self):
        with pytest.raises(ValueError) as exc_info:
            FixedClock(start=datetime(2026, 1, 1))  # naive -> rejected
        assert "timezone-aware" in str(exc_info.value)

    def test_advance_moves_now_and_time(self):
        clock = FixedClock(start=BASE_TIME)
        assert clock.now() == BASE_TIME
        assert clock.time() == BASE_TIME.timestamp()

        clock.advance(60)
        assert clock.now() == BASE_TIME + timedelta(seconds=60)
        assert clock.time() == (BASE_TIME + timedelta(seconds=60)).timestamp()


class TestSystemClockIsAware:
    def test_now_is_timezone_aware(self):
        clock = SystemClock()
        now = clock.now()
        assert now.tzinfo is not None


class TestIcebergPersistenceIsEventTime:
    """AC5: wall-clock advance must not move iceberg classification."""

    def test_wall_clock_advance_does_not_change_classification(self):
        clock = FixedClock(start=BASE_TIME)
        tracker = OrderBookTracker(
            min_refill_count=999, clock=clock
        )  # disable refill path
        ob = _orderbook()

        # Single message at t0: first_seen == last_seen == t0 -> persistence 0.
        tracker.update_orderbook("BTCUSDT", ob["bids"], ob["asks"], timestamp=BASE_TIME)
        before = tracker.detect_icebergs("BTCUSDT", current_price=50000.5)
        assert before == []  # persistence == 0, no anchor yet

        # Advance the WALL CLOCK by 10 minutes (well past the 180s anchor
        # threshold) WITHOUT sending any new message. Prior to #193's fix,
        # persistence was `time.time() - history.first_seen`, so this alone
        # would have flipped the level to an "anchor" pattern.
        clock.advance(600)
        after = tracker.detect_icebergs("BTCUSDT", current_price=50000.5)
        assert after == before == []

    def test_message_time_advance_does_change_classification(self):
        """Control case: advancing MESSAGE time (not wall clock) does move
        persistence, proving detection still works via the correct axis."""
        clock = FixedClock(start=BASE_TIME)
        tracker = OrderBookTracker(min_refill_count=999, clock=clock)
        ob = _orderbook()

        tracker.update_orderbook("BTCUSDT", ob["bids"], ob["asks"], timestamp=BASE_TIME)

        # Wall clock never moves, but the second message carries a
        # message-timestamp 200s later than the first -> persistence > 180.
        later = BASE_TIME + timedelta(seconds=200)
        tracker.update_orderbook("BTCUSDT", ob["bids"], ob["asks"], timestamp=later)

        patterns = tracker.detect_icebergs("BTCUSDT", current_price=50000.5)
        # Persistence (200s) now exceeds both the 120s ("consistent_size")
        # and 180s ("anchor") thresholds; either qualifies as proof that
        # message-time advance (unlike wall-clock advance above) does move
        # classification.
        assert any(p.pattern_type in ("consistent_size", "anchor") for p in patterns)
        assert any(p.persistence_seconds >= 200.0 for p in patterns)


def _make_spread_event(ts: datetime) -> tuple[SpreadEvent, SpreadSnapshot]:
    metrics = SpreadMetrics(
        symbol="BTCUSDT",
        timestamp=ts,
        best_bid=50000.0,
        best_ask=50001.0,
        mid_price=50000.5,
        spread_abs=1.0,
        spread_bps=2.0,
        spread_pct=0.002,
        bid_volume_top5=1.0,
        ask_volume_top5=1.0,
        total_depth=2.0,
    )
    snapshot = SpreadSnapshot(metrics=metrics, spread_ratio=1.0, spread_velocity=0.0)
    return SpreadEvent(
        event_type="narrowing",
        symbol="BTCUSDT",
        timestamp=ts,
        spread_before_bps=5.0,
        spread_current_bps=2.0,
        spread_ratio=1.0,
        spread_velocity=0.0,
        duration_seconds=40.0,
        persistence_above_threshold=True,
        confidence=0.8,
        reasoning="test",
        snapshot=snapshot,
    ), snapshot


class TestSpreadLiquidityRateLimitIsEventTime:
    """AC3: persistence and rate-limiting derive from the same (event) clock."""

    def test_rate_limit_uses_message_time_not_wall_clock(self):
        clock = FixedClock(start=BASE_TIME)
        strategy = SpreadLiquidityStrategy(
            min_signal_interval_seconds=60.0,
            clock=clock,
        )

        event1, snapshot1 = _make_spread_event(BASE_TIME)
        first_signal = strategy._generate_signal(event1, snapshot1)
        assert first_signal is not None  # first signal always allowed

        # A second event only 10s later in MESSAGE time -> still within the
        # 60s rate-limit window -> must be suppressed, REGARDLESS of how far
        # the wall clock (self.clock) has moved.
        clock.advance(99999)  # wall clock jumps far into the future
        event2, snapshot2 = _make_spread_event(BASE_TIME + timedelta(seconds=10))
        second_signal = strategy._generate_signal(event2, snapshot2)
        assert second_signal is None  # still rate-limited by MESSAGE time

        # A third event 61s (message time) after the first -> outside the
        # window -> allowed again, proving the mechanism still works when
        # message time (not wall clock) actually advances far enough.
        event3, snapshot3 = _make_spread_event(BASE_TIME + timedelta(seconds=61))
        third_signal = strategy._generate_signal(event3, snapshot3)
        assert third_signal is not None


class TestTimezoneInvariance:
    """AC6: identical classification under non-UTC and UTC host timezones."""

    def _run_scenario(self):
        clock = SystemClock()
        tracker = OrderBookTracker(min_refill_count=999, clock=clock)
        ob = _orderbook()
        t0 = BASE_TIME
        tracker.update_orderbook("BTCUSDT", ob["bids"], ob["asks"], timestamp=t0)
        t1 = t0 + timedelta(seconds=200)
        tracker.update_orderbook("BTCUSDT", ob["bids"], ob["asks"], timestamp=t1)
        patterns = tracker.detect_icebergs("BTCUSDT", current_price=50000.5)
        return [(p.pattern_type, round(p.persistence_seconds, 3)) for p in patterns]

    def test_identical_under_non_utc_and_utc_host_tz(self, monkeypatch):
        monkeypatch.setenv("TZ", "America/Sao_Paulo")
        time_module.tzset()
        try:
            result_sao_paulo = self._run_scenario()
        finally:
            monkeypatch.setenv("TZ", "UTC")
            time_module.tzset()

        result_utc = self._run_scenario()

        # Reset to whatever the environment had (avoid leaking state).
        monkeypatch.delenv("TZ", raising=False)
        time_module.tzset()

        assert result_sao_paulo == result_utc
