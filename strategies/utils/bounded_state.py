"""
Bounded, self-evicting in-memory state primitives.

Per #189: several hot-path strategy structures grow monotonically because
they have neither a size cap nor a sweep/eviction policy. These two small,
dependency-free primitives give every affected structure an explicit,
documented bound:

- ``TTLBoundedDict``: a dict bounded by both a hard ``max_size`` (LRU
  eviction on insert) and an optional TTL sweep (``sweep_expired()``,
  called by the owning strategy on its own hot path so no background
  thread/task is required).
- ``SymbolActivityTracker``: tracks last-activity time per symbol and
  reports the least-recently-active symbol to evict once ``max_symbols``
  is exceeded, so a caller can purge that symbol's entries from every
  companion dict it owns (e.g. history + event + last-signal dicts that
  are all keyed by the same symbol).

Both are plain Python (``collections.OrderedDict``) — O(1) touch/insert,
O(k) sweep where k is the number of expired entries.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Iterator, MutableMapping
from typing import Any


class TTLBoundedDict(MutableMapping):
    """Dict bounded by a hard max size (LRU) and an optional TTL sweep.

    Bound today (per #189 AC1):
        - **Max size**: ``max_size`` entries. Exceeding it evicts the
          least-recently-set entry (LRU) immediately on insert.
        - **Eviction policy**: additionally, ``sweep_expired()`` removes
          any entry whose last write is older than ``ttl_seconds`` (if
          set). The caller invokes this on its own hot path (e.g. once
          per ``analyze()`` call) — no background task needed.
    """

    __slots__ = ("max_size", "ttl_seconds", "_data")

    def __init__(self, max_size: int, ttl_seconds: float | None = None):
        if max_size <= 0:
            raise ValueError("max_size must be positive")
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        # key -> (value, last_write_timestamp)
        self._data: OrderedDict[Any, tuple[Any, float]] = OrderedDict()

    def __setitem__(self, key: Any, value: Any) -> None:
        now = time.time()
        if key in self._data:
            self._data.move_to_end(key)
        self._data[key] = (value, now)
        while len(self._data) > self.max_size:
            self._data.popitem(last=False)

    def __getitem__(self, key: Any) -> Any:
        value, _ts = self._data[key]
        return value

    def __delitem__(self, key: Any) -> None:
        del self._data[key]

    def __iter__(self) -> Iterator[Any]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def sweep_expired(self, now: float | None = None) -> int:
        """Remove entries whose last write is older than ``ttl_seconds``.

        No-op (returns 0) if ``ttl_seconds`` was not configured. Returns
        the number of entries evicted, for observability/gauges.
        """
        if self.ttl_seconds is None:
            return 0
        now = now if now is not None else time.time()
        cutoff = now - self.ttl_seconds
        expired = [k for k, (_v, ts) in self._data.items() if ts < cutoff]
        for k in expired:
            del self._data[k]
        return len(expired)


class SymbolActivityTracker:
    """Tracks last-activity time per symbol; evicts LRU symbol past a cap.

    Several strategies key multiple companion dicts by symbol (history,
    event-state, last-signal-time, ...). Rather than bound each dict
    independently (and risk them drifting out of sync), the strategy
    calls :meth:`touch` once per symbol per update; when the cap is
    exceeded this returns the evicted symbol so the caller can purge it
    from every companion dict it owns in one place.
    """

    __slots__ = ("max_symbols", "_last_activity")

    def __init__(self, max_symbols: int):
        if max_symbols <= 0:
            raise ValueError("max_symbols must be positive")
        self.max_symbols = max_symbols
        self._last_activity: OrderedDict[str, float] = OrderedDict()

    def touch(self, symbol: str, now: float | None = None) -> str | None:
        """Record activity for ``symbol``.

        Returns the evicted symbol (LRU) if the cap was exceeded as a
        result of this touch, else ``None``. The caller MUST purge the
        returned symbol from every companion dict it owns.
        """
        now = now if now is not None else time.time()
        if symbol in self._last_activity:
            self._last_activity.move_to_end(symbol)
        self._last_activity[symbol] = now
        if len(self._last_activity) > self.max_symbols:
            evicted, _ts = self._last_activity.popitem(last=False)
            return evicted
        return None

    def discard(self, symbol: str) -> None:
        """Remove a symbol from tracking (e.g. explicit unsubscribe)."""
        self._last_activity.pop(symbol, None)

    def __len__(self) -> int:
        return len(self._last_activity)

    def __contains__(self, symbol: object) -> bool:
        return symbol in self._last_activity
