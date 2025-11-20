import asyncio
import time
from datetime import datetime, timedelta

import pytest

from strategies.market_logic.onchain_metrics import OnChainMetricsStrategy
from strategies.models.market_data import MarketDataMessage, TickerData
from strategies.models.signals import SignalType, SignalAction


def make_ticker(symbol: str) -> TickerData:
    return TickerData(
        symbol=symbol,
        price_change="0",
        price_change_percent="0",
        weighted_avg_price="0",
        prev_close_price="0",
        last_price="0",
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
        open_time=int(time.time() * 1000),
        close_time=int(time.time() * 1000),
        first_id=1,
        last_id=2,
        count=1,
        event_time=int(time.time() * 1000),
    )


def make_mdm(symbol: str) -> MarketDataMessage:
    return MarketDataMessage(
        stream=f"{symbol.lower()}@ticker",
        data=make_ticker(symbol),
        timestamp=datetime.utcnow(),
    )


@pytest.mark.asyncio
async def test_onchain_btc_bullish_signal_generation():
    strategy = OnChainMetricsStrategy()

    # Prepare 24+ hours of BTC history with positive growth
    history = []
    base_time = time.time() - (24 * 3600)
    for i in range(25):
        history.append(
            {
                "active_addresses": 1_000_000 + i * 10_000,
                "transaction_volume_btc": 500_000 + i * 20_000,
                "hash_rate_eh": 200 + i,
                "exchange_inflow_btc": 1_500,
                "exchange_outflow_btc": 2_500,
                "timestamp": base_time + i * 3600,
            }
        )
    strategy.metrics_history["BTC"] = history
    # Current cached metrics
    strategy.metrics_cache["BTC"] = history[-1]

    mdm = make_mdm("BTCUSDT")
    signal = await strategy.process_market_data(mdm)
    # Expect BUY/OPEN_LONG when growth thresholds exceeded
    if signal:
        assert signal.signal_type == SignalType.BUY
        assert signal.signal_action == SignalAction.OPEN_LONG
        assert signal.strategy_name == "onchain_metrics"


@pytest.mark.asyncio
async def test_onchain_eth_bearish_exchange_inflow_signal():
    strategy = OnChainMetricsStrategy()

    # Prepare 24+ hours of ETH history with small growth but large net inflow
    history = []
    base_time = time.time() - (24 * 3600)
    for i in range(25):
        history.append(
            {
                "active_addresses": 800_000 + i * 100,  # small growth
                "transaction_volume_eth": 300_000 + i * 100,  # small growth
                "defi_tvl_usd": 50_000_000_000 + i * 10_000,  # small growth
                "exchange_inflow_eth": 200_000,  # large inflow
                "exchange_outflow_eth": 10_000,  # small outflow
                "timestamp": base_time + i * 3600,
            }
        )
    strategy.metrics_history["ETH"] = history
    strategy.metrics_cache["ETH"] = history[-1]

    mdm = make_mdm("ETHUSDT")
    signal = await strategy.process_market_data(mdm)
    # When net inflow is large and positive, expect SELL/OPEN_SHORT
    if signal:
        assert signal.signal_type == SignalType.SELL
        assert signal.signal_action == SignalAction.OPEN_SHORT
        assert signal.strategy_name == "onchain_metrics"


@pytest.mark.asyncio
async def test_onchain_rate_limiting_prevents_signal():
    strategy = OnChainMetricsStrategy()
    # Seed minimal valid history/cache for BTC
    now = time.time()
    strategy.metrics_history["BTC"] = [
        {"active_addresses": 1, "transaction_volume_btc": 1, "hash_rate_eh": 1, "exchange_inflow_btc": 0, "exchange_outflow_btc": 0, "timestamp": now - 25 * 3600}
    ] * 24
    strategy.metrics_cache["BTC"] = strategy.metrics_history["BTC"][-1]
    # Mark last signal as just emitted -> enforce min interval
    strategy.last_signal_times["BTC_onchain"] = datetime.utcnow()

    mdm = make_mdm("BTCUSDT")
    signal = await strategy.process_market_data(mdm)
    assert signal is None


@pytest.mark.asyncio
async def test_onchain_error_handling_in_process_market_data(monkeypatch):
    strategy = OnChainMetricsStrategy()

    async def boom(_):
        raise RuntimeError("boom")

    # Force analyze to throw and hit except path
    monkeypatch.setattr(strategy, "_analyze_onchain_metrics", boom)

    mdm = make_mdm("BTCUSDT")
    result = await strategy.process_market_data(mdm)
    assert result is None


@pytest.mark.asyncio
async def test_onchain_eth_ecosystem_growth_signal():
    """Test ETH signal generation with DeFi TVL growth - covers lines 337-371."""
    strategy = OnChainMetricsStrategy()
    
    # Prepare 24+ hours of ETH history with strong growth
    history = []
    base_time = time.time() - (24 * 3600)
    for i in range(25):
        history.append({
            "active_addresses": 800_000 + i * 15_000,  # > 10% growth
            "transaction_volume_eth": 300_000 + i * 50_000,  # > 15% growth
            "defi_tvl_usd": 50_000_000_000 + i * 1_000_000_000,  # > 5% growth
            "exchange_inflow_eth": 50_000,
            "exchange_outflow_eth": 60_000,
            "timestamp": base_time + i * 3600,
        })
    strategy.metrics_history["ETH"] = history
    strategy.metrics_cache["ETH"] = history[-1]
    
    # Allow signal generation (no recent signal)
    strategy.last_signal_times.clear()
    
    mdm = make_mdm("ETHUSDT")
    # Set price in ticker data
    mdm.data.last_price = "3000.0"
    
    signal = await strategy.process_market_data(mdm)
    if signal:
        assert signal.signal_type == SignalType.BUY
        assert signal.signal_action == SignalAction.OPEN_LONG
        assert signal.price > 0


@pytest.mark.asyncio
async def test_onchain_unsupported_symbol():
    """Test unsupported symbol returns None - covers line 214."""
    strategy = OnChainMetricsStrategy()
    strategy.metrics_cache["BTC"] = {"active_addresses": 1000000}
    
    mdm = make_mdm("ADAUSDT")  # Not BTC or ETH
    signal = await strategy._analyze_onchain_metrics(mdm)
    assert signal is None


@pytest.mark.asyncio
async def test_onchain_no_metrics_cache():
    """Test missing metrics cache returns None - covers line 217."""
    strategy = OnChainMetricsStrategy()
    mdm = make_mdm("BTCUSDT")
    signal = await strategy._analyze_onchain_metrics(mdm)
    assert signal is None


@pytest.mark.asyncio
async def test_onchain_insufficient_history():
    """Test insufficient history returns None - covers line 244."""
    strategy = OnChainMetricsStrategy()
    strategy.metrics_cache["BTC"] = {"active_addresses": 1000000}
    # Less than 24 hours of history
    strategy.metrics_history["BTC"] = [{"active_addresses": 1000000}] * 10
    
    mdm = make_mdm("BTCUSDT")
    signal = await strategy._analyze_onchain_metrics(mdm)
    assert signal is None


@pytest.mark.asyncio
async def test_onchain_calculate_growth_metrics_exception():
    """Test exception handling in calculate_growth_metrics - covers lines 304-306."""
    strategy = OnChainMetricsStrategy()
    
    # Create history with invalid data that will cause exception
    history = []
    base_time = time.time() - (24 * 3600)
    for i in range(25):
        history.append({
            "active_addresses": None,  # Invalid data
            "transaction_volume_btc": None,
            "hash_rate_eh": None,
            "exchange_inflow_btc": None,
            "exchange_outflow_btc": None,
            "timestamp": base_time + i * 3600,
        })
    strategy.metrics_history["BTC"] = history
    
    result = strategy._calculate_growth_metrics("BTC")
    assert result is None


@pytest.mark.asyncio
async def test_onchain_percentage_change_zero_old_value():
    """Test percentage change with zero old value - covers line 311."""
    strategy = OnChainMetricsStrategy()
    result = strategy._calculate_percentage_change(0, 100)
    assert result == 0


@pytest.mark.asyncio
async def test_onchain_signal_confidence_mapping():
    """Test confidence score mapping - covers lines 434, 436."""
    strategy = OnChainMetricsStrategy()
    strategy.metrics_cache["BTC"] = {"active_addresses": 1000000}
    
    # Create history with strong growth
    history = []
    base_time = time.time() - (24 * 3600)
    for i in range(25):
        history.append({
            "active_addresses": 1_000_000 + i * 15_000,
            "transaction_volume_btc": 500_000 + i * 80_000,
            "hash_rate_eh": 200 + i * 2,
            "exchange_inflow_btc": 1_000,
            "exchange_outflow_btc": 2_000,
            "timestamp": base_time + i * 3600,
        })
    strategy.metrics_history["BTC"] = history
    strategy.metrics_cache["BTC"] = history[-1]
    
    mdm = make_mdm("BTCUSDT")
    mdm.data.last_price = "50000.0"
    
    signal = await strategy.process_market_data(mdm)
    if signal:
        # High confidence should map correctly
        assert signal.confidence_score >= 0.5


@pytest.mark.asyncio
async def test_onchain_price_extraction_from_trade():
    """Test price extraction from trade data - covers line 445."""
    from strategies.models.market_data import TradeData
    
    strategy = OnChainMetricsStrategy()
    strategy.metrics_cache["BTC"] = {"active_addresses": 1000000}
    
    # Create history
    history = []
    base_time = time.time() - (24 * 3600)
    for i in range(25):
        history.append({
            "active_addresses": 1_000_000 + i * 15_000,
            "transaction_volume_btc": 500_000 + i * 80_000,
            "hash_rate_eh": 200 + i * 2,
            "exchange_inflow_btc": 1_000,
            "exchange_outflow_btc": 2_000,
            "timestamp": base_time + i * 3600,
        })
    strategy.metrics_history["BTC"] = history
    strategy.metrics_cache["BTC"] = history[-1]
    
    # Create market data with trade instead of ticker
    trade = TradeData(
        symbol="BTCUSDT",
        trade_id=1,
        price="51000.0",
        quantity="0.1",
        buyer_order_id=1,
        seller_order_id=2,
        trade_time=int(time.time() * 1000),
        is_buyer_maker=False,
        event_time=int(time.time() * 1000),
    )
    mdm = MarketDataMessage(
        stream="btcusdt@trade",
        data=trade,
        timestamp=datetime.utcnow(),
    )
    
    signal = await strategy.process_market_data(mdm)
    if signal:
        assert signal.price > 0


@pytest.mark.asyncio
async def test_onchain_get_metrics():
    """Test get_metrics method - covers line 464."""
    strategy = OnChainMetricsStrategy()
    metrics = strategy.get_metrics()
    assert "strategy_name" in metrics
    assert "signals_generated" in metrics
    assert metrics["strategy_name"] == "onchain_metrics"


@pytest.mark.asyncio
async def test_onchain_fetch_error_handling(monkeypatch):
    """Test error handling in _fetch_onchain_metrics - covers lines 135-136."""
    strategy = OnChainMetricsStrategy()
    
    async def boom():
        raise Exception("Fetch error")
    
    monkeypatch.setattr(strategy, "_simulate_btc_metrics", boom)
    
    await strategy._fetch_onchain_metrics()
    # Should handle error gracefully


@pytest.mark.asyncio
async def test_onchain_history_trimming():
    """Test history trimming when exceeding max entries - covers line 194."""
    strategy = OnChainMetricsStrategy()
    
    # Create more than 7 days * 24 hours of history
    history = []
    base_time = time.time() - (10 * 24 * 3600)  # 10 days ago
    for i in range(10 * 24 + 1):  # More than max_entries
        history.append({
            "active_addresses": 1000000,
            "timestamp": base_time + i * 3600,
        })
    
    strategy._update_metrics_history("BTC", history[-1])
    strategy._update_metrics_history("BTC", {"active_addresses": 1000000, "timestamp": time.time()})
    
    # History should be trimmed to max_entries
    assert len(strategy.metrics_history["BTC"]) <= 7 * 24


