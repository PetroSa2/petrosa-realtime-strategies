"""
Injectable clock abstraction (per #193).

Background
----------
Prior to this module, strategy classes derived "now" from two different,
uncoordinated sources within a single decision: a message-derived
``datetime`` (event time) and a raw ``time.time()`` / naive-``datetime``
wall-clock call (processing time). The naive-``datetime`` helper
additionally returns a datetime with no timezone attached; calling
``.timestamp()`` on it silently assumes the host's local timezone rather
than UTC, so results only happened to be correct on UTC-configured hosts.

This module gives every strategy exactly one clock to consult. Production
code injects ``SystemClock`` (backed by ``datetime.now(UTC)`` /
``time.time()``, both real and tz-aware). Tests inject ``FixedClock`` so
time comparisons become deterministic and instantly-advanceable without
sleeping.

Each of the four consumers of this module documents, in its own class
docstring, which timeline it uses the clock for ("event time" — derived
from the message-supplied timestamp — or "processing time" — the wall
clock). See ``OrderBookTracker``, ``IcebergDetectorStrategy``,
``SpreadLiquidityStrategy``, and ``DepthAnalyzer``.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    """Minimal clock interface consumed by strategies.

    Implementations MUST return timezone-aware UTC datetimes from
    ``now()`` — never naive datetimes (this is the root cause fixed by
    #193: a naive wall-clock datetime + ``.timestamp()`` silently applies
    the host's local UTC offset).
    """

    def now(self) -> datetime:
        """Return the current time as a timezone-aware UTC datetime."""
        ...

    def time(self) -> float:
        """Return the current time as a Unix timestamp (seconds, UTC)."""
        ...


class SystemClock:
    """Production clock: real wall-clock UTC, always timezone-aware."""

    def now(self) -> datetime:
        return datetime.now(UTC)

    def time(self) -> float:
        return time.time()


class FixedClock:
    """Deterministic clock for unit tests.

    Starts at ``start`` (or ``datetime.now(UTC)`` if omitted) and only
    moves forward when ``advance()``/``set()`` is called explicitly —
    never on its own. This lets tests prove that a computation depends
    on message time and NOT on wall-clock time (or vice versa) by
    advancing one axis while holding the other still — see AC5 of #193.
    """

    def __init__(self, start: datetime | None = None):
        self._current = start if start is not None else datetime.now(UTC)
        if self._current.tzinfo is None:
            raise ValueError("FixedClock requires a timezone-aware datetime")

    def now(self) -> datetime:
        return self._current

    def time(self) -> float:
        return self._current.timestamp()

    def advance(self, seconds: float) -> None:
        """Move the fake clock forward by ``seconds`` (may be negative)."""
        self._current = self._current + timedelta(seconds=seconds)

    def set(self, value: datetime) -> None:
        """Jump the fake clock to an explicit tz-aware datetime."""
        if value.tzinfo is None:
            raise ValueError("FixedClock.set requires a timezone-aware datetime")
        self._current = value


DEFAULT_CLOCK = SystemClock()
