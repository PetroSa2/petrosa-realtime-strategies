"""Equivalence + performance guards for the O(log n) btc_dominance history handling.

The reference functions below are verbatim copies of the pre-optimization logic
(filter + stable sort / full-list rebuild). The optimized strategy must produce
identical results on timestamp-ordered data, which is how production appends it.
"""

import random
import time
import types

import pytest

from strategies.market_logic.btc_dominance import BitcoinDominanceStrategy

# ── verbatim reference implementations (pre-optimization) ────────────────────


def ref_momentum(price_data, window_start):
    recent_data = [e for e in price_data if e["timestamp"] >= window_start]
    if len(recent_data) < 2:
        return 0
    recent_data.sort(key=lambda x: x["timestamp"])
    start_price = recent_data[0]["price"]
    end_price = recent_data[-1]["price"]
    momentum = ((end_price - start_price) / start_price) * 100
    return max(0, momentum + 10)


def ref_prune(history, cutoff):
    return [e for e in history if e["timestamp"] > cutoff]


def ref_change_24h(dominance_history, now):
    if len(dominance_history) < 2:
        return 0
    day_ago = now - 24 * 3600
    past = [e for e in dominance_history if e["timestamp"] <= day_ago]
    if not past:
        return 0
    return dominance_history[-1]["dominance"] - past[-1]["dominance"]


# ── helpers ──────────────────────────────────────────────────────────────────


def sorted_series(n, span_s, key, now, rng, dup_every=7):
    """Timestamp-ordered series with occasional duplicate timestamps."""
    out, t = [], now - span_s
    step = span_s / max(n, 1)
    for i in range(n):
        if i % dup_every:
            t += step
        out.append({"timestamp": t, key: 100.0 + rng.random() * 10})
    return out


def trade_msg(symbol, price):
    m = types.SimpleNamespace(symbol=symbol, is_ticker=False, is_trade=True)
    m.data = types.SimpleNamespace(price=str(price))
    return m


# ── equivalence ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("seed", range(5))
def test_momentum_sorted_and_generic_match_reference(seed):
    rng = random.Random(seed)
    now = 1_800_000_000.0
    strat = BitcoinDominanceStrategy()
    data = sorted_series(500, 30 * 3600, "price", now, rng)
    for window_start in (now - 24 * 3600, now - 3600, now + 1, now - 40 * 3600):
        expected = ref_momentum(data, window_start)
        assert strat._momentum_sorted(data, window_start) == expected
        assert strat._calculate_momentum(data, window_start) == expected
        shuffled = data[:]
        rng.shuffle(shuffled)
        # The generic path must still accept any ordering. With duplicate
        # timestamps, which tied entry is "first" depends on input order in
        # the reference too, so compare against the reference on the same list.
        assert strat._calculate_momentum(shuffled, window_start) == ref_momentum(
            shuffled, window_start
        )


@pytest.mark.parametrize("seed", range(5))
def test_dominance_change_and_prune_match_reference(seed):
    rng = random.Random(100 + seed)
    now = time.time()
    strat = BitcoinDominanceStrategy()
    hist = sorted_series(2000, 50 * 3600, "dominance", now - 1, rng)
    strat.dominance_history = [dict(e) for e in hist]

    expected_hist = ref_prune(
        hist + [{"timestamp": now, "dominance": 55.0}], now - 48 * 3600
    )
    strat._update_dominance_history(55.0)
    # Same surviving entries (timestamps + values), except the new entry's
    # timestamp is taken inside the method.
    got = strat.dominance_history
    assert [e["dominance"] for e in got] == [e["dominance"] for e in expected_hist]
    assert [e["timestamp"] for e in got[:-1]] == [
        e["timestamp"] for e in expected_hist[:-1]
    ]

    assert strat._calculate_dominance_change_24h() == pytest.approx(
        ref_change_24h(got, time.time()), abs=0
    )


def test_price_history_prune_matches_reference():
    rng = random.Random(7)
    now = time.time()
    strat = BitcoinDominanceStrategy()
    hist = sorted_series(3000, 30 * 3600, "price", now - 1, rng)
    strat.price_history["BTCUSDT"] = [dict(e, symbol="BTCUSDT") for e in hist]
    strat._update_price_history(trade_msg("BTCUSDT", 123.0))
    cutoff = time.time() - (strat.window_hours * 3600 + 3600)
    got = strat.price_history["BTCUSDT"]
    assert all(e["timestamp"] > cutoff for e in got)
    assert got[-1]["price"] == 123.0
    expected = ref_prune(hist, cutoff)
    assert [e["timestamp"] for e in got[:-1]] == [e["timestamp"] for e in expected]


def test_out_of_order_entry_is_inserted_sorted():
    strat = BitcoinDominanceStrategy()
    now = time.time()
    strat.dominance_history = [{"timestamp": now + 100, "dominance": 60.0}]
    strat._update_dominance_history(61.0)  # timestamp ~now < now + 100
    ts = [e["timestamp"] for e in strat.dominance_history]
    assert ts == sorted(ts)


# ── performance guard (relative, so it is stable on slow CI runners) ─────────


@pytest.mark.asyncio
async def test_process_market_data_is_much_faster_than_reference():
    rng = random.Random(42)
    now = time.time()
    n_price, n_dom = 30_000, 150_000

    strat = BitcoinDominanceStrategy()
    strat.min_signal_interval = 10**9  # keep signal generation out of the timing
    strat.last_signal_time = None
    for sym in ("BTCUSDT", "ETHUSDT", "BNBUSDT"):
        strat.price_history[sym] = [
            dict(e, symbol=sym)
            for e in sorted_series(n_price, 24.5 * 3600, "price", now - 1, rng)
        ]
    strat.dominance_history = sorted_series(n_dom, 47 * 3600, "dominance", now - 1, rng)

    ref_price = {k: [dict(e) for e in v] for k, v in strat.price_history.items()}
    ref_dom = [dict(e) for e in strat.dominance_history]

    def reference_step(price):
        t = time.time()
        ref_price["BTCUSDT"].append(
            {"timestamp": t, "price": price, "symbol": "BTCUSDT"}
        )
        ref_price["BTCUSDT"] = ref_prune(ref_price["BTCUSDT"], t - 25 * 3600)
        ws = t - 24 * 3600
        b = ref_momentum(ref_price["BTCUSDT"], ws)
        e = ref_momentum(ref_price["ETHUSDT"], ws)
        n = ref_momentum(ref_price["BNBUSDT"], ws)
        nonlocal ref_dom
        ref_dom.append({"timestamp": t, "dominance": 30 + b / (b + e + n) * 50})
        ref_dom = ref_prune(ref_dom, t - 48 * 3600)
        ref_change_24h(ref_dom, t)

    rounds = 5
    t0 = time.perf_counter()
    for i in range(rounds):
        reference_step(100.0 + i)
    ref_elapsed = time.perf_counter() - t0

    t0 = time.perf_counter()
    for i in range(rounds):
        await strat.process_market_data(trade_msg("BTCUSDT", 100.0 + i))
    new_elapsed = time.perf_counter() - t0

    assert new_elapsed * 5 < ref_elapsed, (
        f"optimized {new_elapsed / rounds * 1000:.2f} ms/msg vs "
        f"reference {ref_elapsed / rounds * 1000:.2f} ms/msg"
    )
