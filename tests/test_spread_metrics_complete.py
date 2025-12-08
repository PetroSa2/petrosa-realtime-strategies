"""
Complete coverage tests for spread_metrics module.

Current coverage: 95.56% → Target: 100%
Missing lines: 53, 58 (validator error paths in __post_init__)
"""

from datetime import datetime

import pytest

from strategies.models.spread_metrics import SpreadEvent, SpreadMetrics, SpreadSnapshot


def test_spread_metrics_valid_creation():
    """Test SpreadMetrics creation with valid data."""
    metrics = SpreadMetrics(
        symbol="BTCUSDT",
        timestamp=datetime.utcnow(),
        best_bid=50000.0,
        best_ask=50010.0,
        mid_price=50005.0,
        spread_abs=10.0,
        spread_bps=2.0,
        spread_pct=0.02,
        bid_volume_top5=1000.0,
        ask_volume_top5=950.0,
        total_depth=1950.0,
    )

    assert metrics.symbol == "BTCUSDT"
    assert metrics.best_bid == 50000.0
    assert metrics.best_ask == 50010.0


def test_spread_metrics_invalid_bid_zero():
    """Test SpreadMetrics validation rejects zero bid price - covers line 53."""
    with pytest.raises(ValueError, match="Invalid bid/ask prices") as exc_info:
        SpreadMetrics(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            best_bid=0.0,  # Invalid - zero
            best_ask=50010.0,
            mid_price=25005.0,
            spread_abs=10.0,
            spread_bps=2.0,
            spread_pct=0.02,
            bid_volume_top5=1000.0,
            ask_volume_top5=950.0,
            total_depth=1950.0,
        )
    assert exc_info.value is not None


def test_spread_metrics_invalid_ask_zero():
    """Test SpreadMetrics validation rejects zero ask price - covers line 53."""
    with pytest.raises(ValueError, match="Invalid bid/ask prices") as exc_info:
        SpreadMetrics(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            best_bid=50000.0,
            best_ask=0.0,  # Invalid - zero
            mid_price=25000.0,
            spread_abs=10.0,
            spread_bps=2.0,
            spread_pct=0.02,
            bid_volume_top5=1000.0,
            ask_volume_top5=950.0,
            total_depth=1950.0,
        )
    assert exc_info.value is not None


def test_spread_metrics_invalid_ask_less_than_bid():
    """Test SpreadMetrics validation rejects ask <= bid - covers line 58."""
    with pytest.raises(ValueError, match="Ask must be greater than bid") as exc_info:
        SpreadMetrics(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            best_bid=50010.0,
            best_ask=50000.0,  # Invalid - less than bid
            mid_price=50005.0,
            spread_abs=10.0,
            spread_bps=2.0,
            spread_pct=0.02,
            bid_volume_top5=1000.0,
            ask_volume_top5=950.0,
            total_depth=1950.0,
        )
    assert exc_info.value is not None


def test_spread_metrics_invalid_ask_equal_to_bid():
    """Test SpreadMetrics validation rejects ask = bid - covers line 58."""
    with pytest.raises(ValueError, match="Ask must be greater than bid") as exc_info:
        SpreadMetrics(
            symbol="BTCUSDT",
            timestamp=datetime.utcnow(),
            best_bid=50000.0,
            best_ask=50000.0,  # Invalid - equal to bid
            mid_price=50000.0,
            spread_abs=0.0,
            spread_bps=0.0,
            spread_pct=0.0,
            bid_volume_top5=1000.0,
            ask_volume_top5=950.0,
            total_depth=1950.0,
        )
    assert exc_info.value is not None


def test_spread_snapshot_creation():
    """Test SpreadSnapshot creation."""
    metrics = SpreadMetrics(
        symbol="BTCUSDT",
        timestamp=datetime.utcnow(),
        best_bid=50000.0,
        best_ask=50010.0,
        mid_price=50005.0,
        spread_abs=10.0,
        spread_bps=2.0,
        spread_pct=0.02,
        bid_volume_top5=1000.0,
        ask_volume_top5=950.0,
        total_depth=1950.0,
    )

    snapshot = SpreadSnapshot(metrics=metrics, spread_ratio=1.5, is_widening=True)

    assert snapshot.metrics == metrics
    assert snapshot.spread_ratio == 1.5
    assert snapshot.is_widening is True


def test_spread_event_creation():
    """Test SpreadEvent creation."""
    metrics = SpreadMetrics(
        symbol="BTCUSDT",
        timestamp=datetime.utcnow(),
        best_bid=50000.0,
        best_ask=50010.0,
        mid_price=50005.0,
        spread_abs=10.0,
        spread_bps=2.0,
        spread_pct=0.02,
        bid_volume_top5=1000.0,
        ask_volume_top5=950.0,
        total_depth=1950.0,
    )

    snapshot = SpreadSnapshot(metrics=metrics)

    event = SpreadEvent(
        event_type="widening",
        symbol="BTCUSDT",
        timestamp=datetime.utcnow(),
        spread_before_bps=1.5,
        spread_current_bps=2.5,
        spread_ratio=1.67,
        spread_velocity=0.5,
        duration_seconds=30.0,
        persistence_above_threshold=True,
        confidence=0.85,
        reasoning="Rapid spread widening detected",
        snapshot=snapshot,
    )

    assert event.event_type == "widening"
    assert event.confidence == 0.85
