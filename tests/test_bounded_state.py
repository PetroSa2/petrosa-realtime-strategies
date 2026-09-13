"""
Unit tests for strategies.utils.bounded_state (per #189).

Covers TTLBoundedDict (hard max-size LRU + optional TTL sweep) and
SymbolActivityTracker (LRU eviction across companion dicts).
"""

import time

import pytest

from strategies.utils.bounded_state import SymbolActivityTracker, TTLBoundedDict


class TestTTLBoundedDict:
    def test_basic_set_get(self):
        d = TTLBoundedDict(max_size=10)
        d["a"] = 1
        assert d["a"] == 1
        assert len(d) == 1

    def test_max_size_evicts_lru(self):
        d = TTLBoundedDict(max_size=3)
        d["a"] = 1
        d["b"] = 2
        d["c"] = 3
        d["d"] = 4  # evicts "a" (least recently set)

        assert len(d) == 3
        assert "a" not in d
        assert "d" in d

    def test_reinsert_refreshes_lru_order(self):
        d = TTLBoundedDict(max_size=2)
        d["a"] = 1
        d["b"] = 2
        d["a"] = 10  # touch "a" again, "b" is now oldest
        d["c"] = 3  # should evict "b", not "a"

        assert "a" in d
        assert "b" not in d
        assert "c" in d

    def test_sweep_expired_removes_stale_entries(self):
        d = TTLBoundedDict(max_size=100, ttl_seconds=5.0)
        now = time.time()
        d._data["old"] = ("value", now - 10.0)
        d._data["fresh"] = ("value", now)

        removed = d.sweep_expired(now=now)

        assert removed == 1
        assert "old" not in d
        assert "fresh" in d

    def test_sweep_expired_noop_without_ttl(self):
        d = TTLBoundedDict(max_size=100)
        d["a"] = 1
        assert d.sweep_expired() == 0
        assert "a" in d

    def test_max_size_must_be_positive(self):
        with pytest.raises(ValueError) as exc_info:
            TTLBoundedDict(max_size=0)
        assert "max_size" in str(exc_info.value)

    def test_delete_and_iterate(self):
        d = TTLBoundedDict(max_size=10)
        d["a"] = 1
        d["b"] = 2
        del d["a"]
        assert list(d) == ["b"]


class TestSymbolActivityTracker:
    def test_touch_within_cap_no_eviction(self):
        tracker = SymbolActivityTracker(max_symbols=3)
        assert tracker.touch("A") is None
        assert tracker.touch("B") is None
        assert tracker.touch("C") is None
        assert len(tracker) == 3

    def test_touch_over_cap_evicts_lru_symbol(self):
        tracker = SymbolActivityTracker(max_symbols=2)
        tracker.touch("A", now=1.0)
        tracker.touch("B", now=2.0)
        evicted = tracker.touch("C", now=3.0)

        assert evicted == "A"
        assert len(tracker) == 2
        assert "A" not in tracker
        assert "C" in tracker

    def test_touch_refreshes_activity_order(self):
        tracker = SymbolActivityTracker(max_symbols=2)
        tracker.touch("A", now=1.0)
        tracker.touch("B", now=2.0)
        tracker.touch("A", now=3.0)  # A is now most recent
        evicted = tracker.touch("C", now=4.0)

        assert evicted == "B"
        assert "A" in tracker

    def test_discard_removes_symbol(self):
        tracker = SymbolActivityTracker(max_symbols=5)
        tracker.touch("A")
        tracker.discard("A")
        assert "A" not in tracker
        assert len(tracker) == 0

    def test_max_symbols_must_be_positive(self):
        with pytest.raises(ValueError) as exc_info:
            SymbolActivityTracker(max_symbols=0)
        assert "max_symbols" in str(exc_info.value)
