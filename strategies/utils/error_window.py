"""Rolling-window error rate tracking for health checks.

Replaces the old "lifetime error_count < N" health cliff, under which a
long-running pod becomes permanently unhealthy once it accumulates N
errors over its entire lifetime — even if the last error happened hours
ago and the service has been clean since. A windowed error-rate check
instead asks "how many errors happened recently?", so a past burst of
errors ages out of the health calculation once it falls outside the
window.
"""

from __future__ import annotations

import time
from collections import deque


class WindowedErrorTracker:
    """Tracks error occurrences within a rolling time window.

    Call :meth:`record_error` whenever an error occurs. Call
    :attr:`is_within_threshold` (or :attr:`count_in_window`) from a health
    check to determine whether the recent error rate is acceptable.
    """

    def __init__(
        self,
        window_seconds: float = 300.0,
        max_errors_in_window: int = 50,
    ) -> None:
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        if max_errors_in_window < 0:
            raise ValueError("max_errors_in_window must not be negative")

        self.window_seconds = window_seconds
        self.max_errors_in_window = max_errors_in_window
        self._timestamps: deque[float] = deque()

    def record_error(self, now: float | None = None) -> None:
        """Record a single error occurrence at the given time (default: now)."""
        self._timestamps.append(now if now is not None else time.time())
        self._prune(now)

    def _prune(self, now: float | None = None) -> None:
        """Drop timestamps that have aged out of the window."""
        cutoff = (now if now is not None else time.time()) - self.window_seconds
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()

    @property
    def count_in_window(self) -> int:
        """Number of errors recorded within the current rolling window."""
        self._prune()
        return len(self._timestamps)

    @property
    def is_within_threshold(self) -> bool:
        """True if the recent error rate is within the acceptable threshold."""
        return self.count_in_window < self.max_errors_in_window
