"""
Edge-case tests for market_data models to raise coverage.
"""

from datetime import datetime

import pytest

from strategies.models.market_data import (
    DepthLevel,
    DepthUpdate,
    MarketDataMessage,
    TickerData,
    TradeData,
)


def test_depthlevel_invalid_numeric_string():
    with pytest.raises(ValueError) as exc_info:
        DepthLevel(price="abc", quantity="1.0")
    assert "price" in str(exc_info.value).lower() or "numeric" in str(exc_info.value).lower()

    with pytest.raises(ValueError) as exc_info:
        DepthLevel(price="50000.0", quantity="x")
    assert "quantity" in str(exc_info.value).lower() or "numeric" in str(exc_info.value).lower()


def test_depthupdate_symbol_validation_and_empty_lists():
    with pytest.raises(ValueError):
        DepthUpdate(
            symbol="BTC",  # too short
            event_time=1234567890000,
            first_update_id=1,
            final_update_id=2,
            bids=[],
            asks=[],
        )

    d = DepthUpdate(
        symbol="btcusdt",
        event_time=1234567890000,
        first_update_id=1,
        final_update_id=2,
        bids=[],
        asks=[],
    )
    # empty bids/asks -> zero spread and mid
    assert d.spread_percent == 0.0
    assert d.mid_price == 0.0
    # timestamp property
    assert d.timestamp == datetime.fromtimestamp(1234567890)


def test_trade_data_numeric_and_timestamp():
    with pytest.raises(ValueError):
        TradeData(
            symbol="BTCUSDT",
            trade_id=1,
            price="n/a",
            quantity="1",
            buyer_order_id=1,
            seller_order_id=2,
            trade_time=1234567890000,
            is_buyer_maker=True,
            event_time=1234567890000,
        )

    t = TradeData(
        symbol="ethusdt",
        trade_id=1,
        price="500.5",
        quantity="2",
        buyer_order_id=1,
        seller_order_id=2,
        trade_time=1234567890000,
        is_buyer_maker=False,
        event_time=1234567890000,
    )
    assert t.timestamp == datetime.fromtimestamp(1234567890)
    assert t.price_float == 500.5
    assert t.quantity_float == 2.0
    assert t.notional_value == 1001.0


def test_ticker_numeric_validator_and_timestamp():
    with pytest.raises(ValueError):
        TickerData(
            symbol="BTCUSDT",
            price_change="x",
            price_change_percent="0.1",
            weighted_avg_price="1",
            prev_close_price="1",
            last_price="1",
            last_qty="1",
            bid_price="1",
            bid_qty="1",
            ask_price="1",
            ask_qty="1",
            open_price="1",
            high_price="1",
            low_price="1",
            volume="1",
            quote_volume="1",
            open_time=1,
            close_time=1,
            first_id=1,
            last_id=1,
            count=1,
            event_time=1,
        )

    td = TickerData(
        symbol="btcusdt",
        price_change="100",
        price_change_percent="0.2",
        weighted_avg_price="1",
        prev_close_price="1",
        last_price="50000",
        last_qty="1",
        bid_price="1",
        bid_qty="1",
        ask_price="1",
        ask_qty="1",
        open_price="1",
        high_price="1",
        low_price="1",
        volume="1000",
        quote_volume="50000000",
        open_time=1,
        close_time=1,
        first_id=1,
        last_id=1,
        count=1,
        event_time=1234567890000,
    )
    assert td.timestamp == datetime.fromtimestamp(1234567890)
    assert td.price_change_float == 100.0
    assert td.price_change_percent_float == 0.2
    assert td.last_price_float == 50000.0
    assert td.volume_float == 1000.0
    assert td.quote_volume_float == 50000000.0


def test_market_data_message_stream_validation_and_props():
    with pytest.raises(ValueError):
        MarketDataMessage(stream="invalid", data=None)  # missing '@'

    du = DepthUpdate(
        symbol="BTCUSDT",
        event_time=1,
        first_update_id=1,
        final_update_id=2,
        bids=[DepthLevel(price="1", quantity="1")],
        asks=[DepthLevel(price="2", quantity="1")],
    )
    msg = MarketDataMessage(stream="btcusdt@depth", data=du)
    assert msg.symbol == "BTCUSDT"
    assert msg.stream_type == "depth"
    assert msg.is_depth is True
    assert msg.is_trade is False
    assert msg.is_ticker is False

