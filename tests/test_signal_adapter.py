"""
Tests for signal adapter transformations.

This module tests the transformation of realtime-strategies Signal objects
to tradeengine contract format.
"""

from datetime import datetime

import pytest

from strategies.adapters.signal_adapter import (
    _calculate_default_quantity,
    _calculate_default_stop_loss,
    _calculate_default_take_profit,
    _map_confidence_to_strength,
    transform_signal_for_tradeengine,
)
from strategies.models.signals import Signal, SignalAction, SignalConfidence, SignalType


class TestSignalAdapter:
    """Tests for signal adapter transformations."""

    def test_transform_buy_signal(self):
        """Test transformation of BUY signal to tradeengine format."""
        signal = Signal(
            strategy_id="spread_liquidity",
            symbol="BTCUSDT",
            action="buy",
            confidence=0.85,
            price=50000.0,
            current_price=50000.0,
            timeframe="tick",
        )

        result = transform_signal_for_tradeengine(signal)

        assert result["symbol"] == "BTCUSDT"
        assert result["action"] == "buy"
        assert result["confidence"] == 0.85
        assert result["price"] == 50000.0
        assert result["current_price"] == 50000.0
        assert result["source"] == "realtime_strategies"
        assert result["strategy"] == "spread_liquidity"
        assert result["strategy_id"] == "spread_liquidity"
        assert result["timeframe"] == "tick"
        assert result["strength"] == "strong"
        assert "id" in result
        assert "signal_id" in result

    def test_transform_sell_signal(self):
        """Test transformation of SELL signal to tradeengine format."""
        signal = Signal(
            strategy_id="iceberg_detector",
            symbol="ETHUSDT",
            action="sell",
            confidence=0.65,
            price=3000.0,
            current_price=3000.0,
            timeframe="1m",
        )

        result = transform_signal_for_tradeengine(signal)

        assert result["symbol"] == "ETHUSDT"
        assert result["action"] == "sell"
        assert result["confidence"] == 0.65
        assert result["price"] == 3000.0
        assert result["source"] == "realtime_strategies"
        assert result["strategy"] == "iceberg_detector"
        assert result["timeframe"] == "1m"
        assert result["strength"] == "medium"

    def test_transform_close_signal(self):
        """Test transformation of CLOSE signal to tradeengine format."""
        signal = Signal(
            strategy_id="spread_liquidity",
            symbol="BTCUSDT",
            action="close",
            confidence=0.9,
            price=51000.0,
            current_price=51000.0,
        )

        result = transform_signal_for_tradeengine(signal)

        assert result["action"] == "close"
        assert result["confidence"] == 0.9

    def test_transform_hold_signal(self):
        """Test transformation of HOLD signal to tradeengine format."""
        signal = Signal(
            strategy_id="onchain_metrics",
            symbol="BTCUSDT",
            action="hold",
            confidence=0.3,
            price=50000.0,
            current_price=50000.0,
        )

        result = transform_signal_for_tradeengine(signal)

        assert result["action"] == "hold"
        assert result["confidence"] == 0.3
        assert result["strength"] == "weak"

    def test_timestamp_conversion(self):
        """Test that timestamp is properly converted to ISO format."""
        now = datetime.utcnow()
        signal = Signal(
            strategy_id="test",
            symbol="BTCUSDT",
            action="buy",
            confidence=0.8,
            price=50000.0,
            current_price=50000.0,
            timestamp=now,
        )

        result = transform_signal_for_tradeengine(signal)

        assert "timestamp" in result
        assert isinstance(result["timestamp"], str)
        # Pydantic v2 might add Z or +00:00 depending on config
        assert result["timestamp"].startswith(now.isoformat()[:19])

    def test_risk_management_defaults(self):
        """Test that risk management defaults are added."""
        signal = Signal(
            strategy_id="test",
            symbol="BTCUSDT",
            action="buy",
            confidence=0.85,
            price=50000.0,
            current_price=50000.0,
        )

        result = transform_signal_for_tradeengine(signal)

        assert "stop_loss_pct" in result
        assert "take_profit_pct" in result
        assert result["stop_loss_pct"] == 0.02  # 2% for high confidence
        assert result["take_profit_pct"] == 0.05  # 5% for high confidence
        assert result["stop_loss"] == 50000.0 * 0.98
        assert result["take_profit"] == 50000.0 * 1.05


class TestConfidenceToStrengthMapping:
    """Tests for confidence to strength mapping."""

    def test_extreme_confidence(self):
        """Test mapping of extreme confidence (>= 0.9)."""
        assert _map_confidence_to_strength(0.95) == "extreme"
        assert _map_confidence_to_strength(0.9) == "extreme"

    def test_strong_confidence(self):
        """Test mapping of strong confidence (0.7-0.89)."""
        assert _map_confidence_to_strength(0.85) == "strong"
        assert _map_confidence_to_strength(0.7) == "strong"

    def test_medium_confidence(self):
        """Test mapping of medium confidence (0.5-0.69)."""
        assert _map_confidence_to_strength(0.65) == "medium"
        assert _map_confidence_to_strength(0.5) == "medium"

    def test_weak_confidence(self):
        """Test mapping of weak confidence (< 0.5)."""
        assert _map_confidence_to_strength(0.45) == "weak"
        assert _map_confidence_to_strength(0.1) == "weak"


class TestQuantityCalculation:
    """Tests for default quantity calculation."""

    def test_high_price_asset(self):
        """Test quantity calculation for high-priced assets (BTC, ETH)."""
        quantity = _calculate_default_quantity(50000.0, 0.8)
        assert quantity > 0
        assert quantity == round(100 / 50000.0, 4)  # $100 worth

    def test_mid_price_asset(self):
        """Test quantity calculation for mid-priced assets."""
        quantity = _calculate_default_quantity(500.0, 0.8)
        assert quantity > 0
        assert quantity == round(50 / 500.0, 2)  # $50 worth

    def test_low_price_asset(self):
        """Test quantity calculation for low-priced assets."""
        quantity = _calculate_default_quantity(5.0, 0.8)
        assert quantity > 0
        assert quantity == round(20 / 5.0, 2)  # $20 worth


class TestRiskManagement:
    """Tests for risk management calculations."""

    def test_stop_loss_high_confidence(self):
        """Test stop loss for high confidence signals."""
        stop_loss = _calculate_default_stop_loss(0.85)
        assert stop_loss == 0.02  # 2%

    def test_stop_loss_medium_confidence(self):
        """Test stop loss for medium confidence signals."""
        stop_loss = _calculate_default_stop_loss(0.65)
        assert stop_loss == 0.03  # 3%

    def test_stop_loss_low_confidence(self):
        """Test stop loss for low confidence signals."""
        stop_loss = _calculate_default_stop_loss(0.45)
        assert stop_loss == 0.05  # 5%

    def test_take_profit_high_confidence(self):
        """Test take profit for high confidence signals."""
        take_profit = _calculate_default_take_profit(0.85)
        assert take_profit == 0.05  # 5%

    def test_take_profit_medium_confidence(self):
        """Test take profit for medium confidence signals."""
        take_profit = _calculate_default_take_profit(0.65)
        assert take_profit == 0.04  # 4%

    def test_take_profit_low_confidence(self):
        """Test take profit for low confidence signals."""
        take_profit = _calculate_default_take_profit(0.45)
        assert take_profit == 0.03  # 3%


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
