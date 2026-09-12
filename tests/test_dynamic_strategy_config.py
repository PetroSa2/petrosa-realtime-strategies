"""
Tests for #197: live StrategyConfigManager values reaching strategy instances,
and the real market-data price field extraction (was gated on nonexistent
`c`/`p` hasattr checks).
"""

from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from strategies.core.consumer import NATSConsumer
from strategies.core.publisher import TradeOrderPublisher
from strategies.market_logic.btc_dominance import BitcoinDominanceStrategy
from strategies.market_logic.cross_exchange_spread import CrossExchangeSpreadStrategy
from strategies.models.market_data import MarketDataMessage, TickerData


def make_ticker(symbol: str, last_price: str) -> TickerData:
    now_ms = 1_700_000_000_000
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


def make_mdm(symbol: str, last_price: str) -> MarketDataMessage:
    return MarketDataMessage(
        stream=f"{symbol.lower()}@ticker",
        data=make_ticker(symbol, last_price),
        timestamp=datetime.utcnow(),
    )


class TestPriceExtractionFix:
    """#197: hasattr gate must check the real TickerData/TradeData field names."""

    def test_btc_dominance_extracts_real_ticker_price(self):
        strat = BitcoinDominanceStrategy()
        mdm = make_mdm("BTCUSDT", "51000.5")
        strat._update_price_history(mdm)
        assert "BTCUSDT" in strat.price_history
        assert strat.price_history["BTCUSDT"][-1]["price"] == 51000.5

    def test_btc_dominance_zero_price_not_recorded(self):
        """Guard: '0' last_price should still be treated as falsy, no false entry."""
        strat = BitcoinDominanceStrategy()
        mdm = make_mdm("BTCUSDT", "0")
        strat._update_price_history(mdm)
        assert strat.price_history.get("BTCUSDT", []) == []

    @pytest.mark.asyncio
    async def test_cross_exchange_spread_extracts_real_ticker_price(self):
        strat = CrossExchangeSpreadStrategy()
        mdm = make_mdm("BTCUSDT", "50123.4")
        await strat._update_binance_price(mdm)
        assert strat.price_cache["binance_BTCUSDT"]["price"] == 50123.4


class TestDynamicConfigWiring:
    """#197 AC4: config_manager.get_config() values reach the live strategy instance."""

    @pytest.fixture
    def consumer(self):
        publisher = Mock(spec=TradeOrderPublisher)
        publisher.publish_signal = AsyncMock()
        return NATSConsumer(
            nats_url="nats://test:4222",
            topic="test.topic",
            consumer_name="test-consumer",
            consumer_group="test-group",
            publisher=publisher,
        )

    @pytest.mark.asyncio
    async def test_no_config_manager_is_a_noop(self, consumer):
        strat = BitcoinDominanceStrategy()
        original = strat.high_threshold
        assert consumer.config_manager is None
        await consumer._apply_dynamic_config("btc_dominance", strat)
        assert strat.high_threshold == original

    @pytest.mark.asyncio
    async def test_config_manager_overrides_btc_dominance_threshold(self, consumer):
        strat = BitcoinDominanceStrategy()
        assert strat.high_threshold != 55.0

        mock_config_manager = Mock()
        mock_config_manager.get_config = AsyncMock(
            return_value={
                "parameters": {"high_threshold": 55.0, "low_threshold": 20.0},
                "source": "mongodb",
            }
        )
        consumer.config_manager = mock_config_manager

        await consumer._apply_dynamic_config("btc_dominance", strat)

        assert strat.high_threshold == 55.0
        assert strat.low_threshold == 20.0
        mock_config_manager.get_config.assert_awaited_once_with("btc_dominance")

    @pytest.mark.asyncio
    async def test_config_manager_remaps_cross_exchange_spread_key(self, consumer):
        """spread_threshold_percent (config key) -> spread_threshold (attribute)."""
        strat = CrossExchangeSpreadStrategy()
        assert strat.spread_threshold != 1.23

        mock_config_manager = Mock()
        mock_config_manager.get_config = AsyncMock(
            return_value={"parameters": {"spread_threshold_percent": 1.23}}
        )
        consumer.config_manager = mock_config_manager

        await consumer._apply_dynamic_config("cross_exchange_spread", strat)

        assert strat.spread_threshold == 1.23

    @pytest.mark.asyncio
    async def test_unknown_parameter_keys_are_ignored(self, consumer):
        strat = BitcoinDominanceStrategy()
        mock_config_manager = Mock()
        mock_config_manager.get_config = AsyncMock(
            return_value={"parameters": {"totally_unknown_key": 999}}
        )
        consumer.config_manager = mock_config_manager

        # Should not raise despite the unmapped key.
        await consumer._apply_dynamic_config("btc_dominance", strat)
        assert not hasattr(strat, "totally_unknown_key")

    @pytest.mark.asyncio
    async def test_config_manager_error_is_swallowed(self, consumer):
        strat = BitcoinDominanceStrategy()
        original = strat.high_threshold
        mock_config_manager = Mock()
        mock_config_manager.get_config = AsyncMock(side_effect=RuntimeError("boom"))
        consumer.config_manager = mock_config_manager

        await consumer._apply_dynamic_config("btc_dominance", strat)
        assert strat.high_threshold == original
