"""Tests for CrossExchangeSpreadStrategy (#187).

Covers:
- Real price extraction from ticker/trade data (regression for the
  `hasattr(data, "c"/"p")` bug fixed in #197/#201 — this strategy shares the
  same extraction pattern as btc_dominance).
- Full process_market_data flow producing arbitrage signals from a realistic
  short-key-equivalent MarketDataMessage (TickerData/TradeData built via the
  real pydantic models, not raw dict fixtures).
- The #187 fix itself: the external exchange fetch is rate-limited to
  min_signal_interval and reuses a single shared aiohttp.ClientSession instead
  of opening a new session and issuing a live HTTP call on every message.
"""

import time
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from strategies.market_logic.cross_exchange_spread import CrossExchangeSpreadStrategy
from strategies.models.market_data import MarketDataMessage, TickerData, TradeData


def make_ticker(symbol: str, last_price: str) -> TickerData:
    now_ms = int(time.time() * 1000)
    return TickerData(
        symbol=symbol,
        price_change="0",
        price_change_percent="0",
        weighted_avg_price="0",
        prev_close_price="0",
        last_price=last_price,
        last_qty="0",
        bid_price="0",
        bid_qty="0",
        ask_price="0",
        ask_qty="0",
        open_price="0",
        high_price="0",
        low_price="0",
        volume="0",
        quote_volume="0",
        open_time=now_ms,
        close_time=now_ms,
        first_id=1,
        last_id=2,
        count=1,
        event_time=now_ms,
    )


def make_ticker_mdm(symbol: str, last_price: str) -> MarketDataMessage:
    return MarketDataMessage(
        stream=f"{symbol.lower()}@ticker",
        data=make_ticker(symbol, last_price),
        timestamp=datetime.utcnow(),
    )


def make_trade_mdm(symbol: str, price: str) -> MarketDataMessage:
    now_ms = int(time.time() * 1000)
    trade = TradeData(
        symbol=symbol,
        trade_id=1,
        price=price,
        quantity="0.1",
        buyer_order_id=1,
        seller_order_id=2,
        trade_time=now_ms,
        is_buyer_maker=False,
        event_time=now_ms,
    )
    return MarketDataMessage(
        stream=f"{symbol.lower()}@trade",
        data=trade,
        timestamp=datetime.utcnow(),
    )


@pytest.mark.asyncio
async def test_update_binance_price_from_ticker_uses_real_field():
    """Regression: hasattr must match real model fields (last_price), not 'c'."""
    strat = CrossExchangeSpreadStrategy()
    mdm = make_ticker_mdm("BTCUSDT", "50000.0")

    await strat._update_binance_price(mdm)

    assert "binance_BTCUSDT" in strat.price_cache
    assert strat.price_cache["binance_BTCUSDT"]["price"] == 50000.0
    assert strat.price_cache["binance_BTCUSDT"]["exchange"] == "binance"


@pytest.mark.asyncio
async def test_update_binance_price_from_trade_uses_real_field():
    """Regression: hasattr must match real model fields (price), not 'p'."""
    strat = CrossExchangeSpreadStrategy()
    mdm = make_trade_mdm("BTCUSDT", "50500.0")

    await strat._update_binance_price(mdm)

    assert "binance_BTCUSDT" in strat.price_cache
    assert strat.price_cache["binance_BTCUSDT"]["price"] == 50500.0


@pytest.mark.asyncio
async def test_process_market_data_full_flow_emits_arbitrage_signals():
    """Full flow: with binance + a second exchange price cached and spread
    above threshold, process_market_data must emit buy+sell signals."""
    strat = CrossExchangeSpreadStrategy()
    strat.spread_threshold = 0.5

    now = time.time()
    strat.price_cache["binance_BTCUSDT"] = {
        "price": 50000.0,
        "timestamp": now,
        "exchange": "binance",
        "symbol": "BTCUSDT",
    }
    strat.price_cache["coinbase_BTCUSDT"] = {
        "price": 50500.0,  # 1% spread, above the 0.5% threshold
        "timestamp": now,
        "exchange": "coinbase",
        "symbol": "BTCUSDT",
    }

    # External fetch is patched to a no-op so this test exercises only the
    # signal-generation path deterministically (no real HTTP calls).
    with patch.object(strat, "_fetch_external_exchange_prices", new=AsyncMock()):
        mdm = make_ticker_mdm("BTCUSDT", "50000.0")
        signals = await strat.process_market_data(mdm)

    assert signals is not None
    assert len(signals) == 2
    assert {s.signal_type for s in signals} == {
        signals[0].signal_type,
        signals[1].signal_type,
    }
    assert all(s.strategy_name == "cross_exchange_spread" for s in signals)
    assert strat.signals_generated == 2


@pytest.mark.asyncio
async def test_fetch_external_prices_is_rate_limited():
    """#187: the external HTTP fetch must not fire on every single message —
    only once per min_signal_interval."""
    strat = CrossExchangeSpreadStrategy()
    strat.min_signal_interval = 300

    with patch.object(strat, "_fetch_exchange_price", new=AsyncMock()) as mock_fetch:
        await strat._fetch_external_exchange_prices()
        await strat._fetch_external_exchange_prices()
        await strat._fetch_external_exchange_prices()

    # Only the first call should have actually dispatched fetch tasks; the
    # next two are within the rate-limit window and must be no-ops.
    assert mock_fetch.call_count == len([e for e in strat.exchanges if e != "binance"])
    await strat.close()


@pytest.mark.asyncio
async def test_fetch_external_prices_refires_after_interval_elapses():
    strat = CrossExchangeSpreadStrategy()
    strat.min_signal_interval = 300

    with patch.object(strat, "_fetch_exchange_price", new=AsyncMock()) as mock_fetch:
        await strat._fetch_external_exchange_prices()
        first_call_count = mock_fetch.call_count

        # Simulate time passing beyond the rate-limit window.
        strat._last_external_fetch_time = time.time() - (strat.min_signal_interval + 1)
        await strat._fetch_external_exchange_prices()

    assert mock_fetch.call_count == first_call_count * 2
    await strat.close()


@pytest.mark.asyncio
async def test_get_session_reuses_shared_session():
    """#187: a single aiohttp.ClientSession must be reused, not recreated
    per external fetch call."""
    strat = CrossExchangeSpreadStrategy()

    session_a = strat._get_session()
    session_b = strat._get_session()

    assert session_a is session_b
    assert strat._session is session_a

    await strat.close()


@pytest.mark.asyncio
async def test_close_closes_shared_session():
    strat = CrossExchangeSpreadStrategy()
    session = strat._get_session()
    assert not session.closed

    await strat.close()

    assert session.closed


@pytest.mark.asyncio
async def test_close_is_a_noop_when_session_never_created():
    strat = CrossExchangeSpreadStrategy()
    assert strat._session is None

    await strat.close()  # must not raise

    assert strat._session is None


@pytest.mark.asyncio
async def test_generate_spread_signals_returns_none_with_single_exchange():
    strat = CrossExchangeSpreadStrategy()
    strat.price_cache["binance_BTCUSDT"] = {
        "price": 50000.0,
        "timestamp": time.time(),
        "exchange": "binance",
        "symbol": "BTCUSDT",
    }

    mdm = make_ticker_mdm("BTCUSDT", "50000.0")
    signals = await strat._generate_spread_signals(mdm)

    assert signals is None


def test_get_metrics_reports_expected_shape():
    strat = CrossExchangeSpreadStrategy()
    metrics = strat.get_metrics()

    assert metrics["strategy_name"] == "cross_exchange_spread"
    assert "signals_generated" in metrics
    assert "cached_prices_count" in metrics
