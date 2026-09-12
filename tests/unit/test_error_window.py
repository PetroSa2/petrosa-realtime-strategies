"""Unit tests for the windowed error-rate tracker (#186 AC4).

Covers the replacement of the old "lifetime error_count < 100" health
cliff with a rolling time-window error rate check.
"""

import time

import pytest

from strategies.utils.error_window import WindowedErrorTracker


def test_starts_empty_and_within_threshold():
    tracker = WindowedErrorTracker(window_seconds=60, max_errors_in_window=5)
    assert tracker.count_in_window == 0
    assert tracker.is_within_threshold is True


def test_records_errors_within_window():
    tracker = WindowedErrorTracker(window_seconds=60, max_errors_in_window=5)
    for _ in range(3):
        tracker.record_error()
    assert tracker.count_in_window == 3
    assert tracker.is_within_threshold is True


def test_exceeding_threshold_becomes_unhealthy():
    tracker = WindowedErrorTracker(window_seconds=60, max_errors_in_window=3)
    for _ in range(3):
        tracker.record_error()
    assert tracker.count_in_window == 3
    assert tracker.is_within_threshold is False


def test_old_errors_age_out_of_the_window():
    """The core fix: errors from long ago must not permanently fail health."""
    tracker = WindowedErrorTracker(window_seconds=60, max_errors_in_window=3)

    now = time.time()
    # Burst of errors well outside the window (an hour ago).
    for i in range(10):
        tracker.record_error(now=now - 3600 + i)

    # All of them have aged out by "now".
    assert tracker.count_in_window == 0
    assert tracker.is_within_threshold is True

    # A single recent error is still counted.
    tracker.record_error(now=now)
    assert tracker.count_in_window == 1
    assert tracker.is_within_threshold is True


def test_mixed_old_and_recent_errors_only_counts_recent():
    tracker = WindowedErrorTracker(window_seconds=60, max_errors_in_window=3)
    now = time.time()

    # Two errors long before the window (an hour ago).
    tracker.record_error(now=now - 3600)
    tracker.record_error(now=now - 3600 + 1)

    # Three errors inside the 60s window.
    tracker.record_error(now=now - 50)
    tracker.record_error(now=now - 30)
    tracker.record_error(now=now)

    assert tracker.count_in_window == 3
    assert tracker.is_within_threshold is False


def test_rejects_non_positive_window():
    with pytest.raises(ValueError) as exc_info:
        WindowedErrorTracker(window_seconds=0)
    assert "window_seconds" in str(exc_info.value)


def test_rejects_negative_threshold():
    with pytest.raises(ValueError) as exc_info:
        WindowedErrorTracker(max_errors_in_window=-1)
    assert "max_errors_in_window" in str(exc_info.value)


def test_threshold_of_one_means_a_single_error_is_unhealthy():
    tracker = WindowedErrorTracker(window_seconds=60, max_errors_in_window=1)
    assert tracker.is_within_threshold is True
    tracker.record_error()
    assert tracker.is_within_threshold is False
