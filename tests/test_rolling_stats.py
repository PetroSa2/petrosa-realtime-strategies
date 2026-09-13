"""Tests for RollingStats (per #191 AC1/AC2/AC3).

Covers:
- AC2: average matches the previous list+sum() implementation exactly.
- AC3: max is windowed (decays), not a lifetime high-water mark.
- Fixed-size window enforcement (no unbounded growth).
"""

from strategies.utils.rolling_stats import RollingStats


def _reference_avg_and_max(values: list[float], maxlen: int) -> tuple[float, float]:
    """Reproduce the OLD list-slice + sum()/max() implementation, for
    parity comparison (per #191 AC2)."""
    window: list[float] = []
    lifetime_max = 0.0
    for v in values:
        window.append(v)
        if len(window) > maxlen:
            window = window[-maxlen:]
        lifetime_max = max(lifetime_max, v)
    avg = sum(window) / len(window) if window else 0.0
    return avg, lifetime_max


def test_empty_stats_defaults():
    stats = RollingStats(maxlen=1000)
    assert stats.count == 0
    assert stats.average == 0.0
    assert stats.windowed_max == 0.0
    assert len(stats) == 0
    assert stats == []


def test_add_increments_count_and_supports_indexing():
    stats = RollingStats(maxlen=1000)
    stats.add(0.1)
    stats.add(0.2)
    stats.add(0.3)

    assert len(stats) == 3
    assert stats[0] == 0.1
    assert stats.average > 0


def test_ac2_average_matches_previous_implementation_within_tolerance():
    """AC2: avg matches the previous sum()/len() implementation within 0.1%
    on a replayed fixture sequence."""
    import random

    random.seed(1191)
    values = [random.uniform(0.01, 50.0) for _ in range(2500)]

    stats = RollingStats(maxlen=1000)
    for v in values:
        stats.add(v)

    expected_avg, _ = _reference_avg_and_max(values, maxlen=1000)

    assert abs(stats.average - expected_avg) / expected_avg < 0.001


def test_ac3_max_is_windowed_not_lifetime():
    """AC3: feed one 5000ms sample then 1000 samples of 1ms -- the reported
    max must no longer be 5000 once the spike ages out of the window."""
    stats = RollingStats(maxlen=1000)
    stats.add(5000.0)

    for _ in range(1000):
        stats.add(1.0)

    assert stats.windowed_max != 5000.0
    assert stats.windowed_max == 1.0
    assert stats.count == 1000


def test_windowed_max_tracks_current_window_with_duplicates():
    stats = RollingStats(maxlen=3)
    stats.add(5.0)
    stats.add(5.0)
    stats.add(1.0)
    assert stats.windowed_max == 5.0

    # Evicts the first 5.0; one 5.0 remains in the window.
    stats.add(2.0)
    assert list(stats) == [5.0, 1.0, 2.0]
    assert stats.windowed_max == 5.0

    # Evicts the second (last) 5.0; window is now [1.0, 2.0, 3.0].
    stats.add(3.0)
    assert list(stats) == [1.0, 2.0, 3.0]
    assert stats.windowed_max == 3.0


def test_fixed_size_window_no_unbounded_growth():
    stats = RollingStats(maxlen=1000)
    for i in range(2500):
        stats.add(float(i))

    assert stats.count == 1000
    # Only the most recent 1000 values remain (1500..2499).
    assert list(stats)[0] == 1500.0
    assert list(stats)[-1] == 2499.0


def test_invalid_maxlen_rejected():
    import pytest

    with pytest.raises(ValueError) as exc_info:
        RollingStats(maxlen=0)
    assert "maxlen" in str(exc_info.value)
