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
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="spread_liquidity",
            metadata={"timeframe": "tick"},
        )

        result = transform_signal_for_tradeengine(signal)

        assert result["symbol"] == "BTCUSDT"
        assert result["action"] == "buy"
        assert result["signal_type"] == "buy"
        assert result["confidence"] == 0.85
        assert result["price"] == 50000.0
        assert result["current_price"] == 50000.0
        assert result["source"] == "realtime-strategies"
        assert result["strategy"] == "spread_liquidity"
        assert result["strategy_id"] == "spread_liquidity_BTCUSDT"
        assert result["timeframe"] == "tick"
        assert result["strength"] == "strong"
        assert "id" in result
        assert "signal_id" in result

    def test_transform_sell_signal(self):
        """Test transformation of SELL signal to tradeengine format."""
        signal = Signal(
            symbol="ETHUSDT",
            signal_type=SignalType.SELL,
            signal_action=SignalAction.OPEN_SHORT,
            confidence=SignalConfidence.MEDIUM,
            confidence_score=0.65,
            price=3000.0,
            strategy_name="iceberg_detector",
            metadata={"timeframe": "1m"},
        )

        result = transform_signal_for_tradeengine(signal)

        assert result["symbol"] == "ETHUSDT"
        assert result["action"] == "sell"
        assert result["signal_type"] == "sell"
        assert result["confidence"] == 0.65
        assert result["price"] == 3000.0
        assert result["source"] == "realtime-strategies"
        assert result["strategy"] == "iceberg_detector"
        assert result["timeframe"] == "1m"
        assert result["strength"] == "medium"

    def test_transform_close_long_signal(self):
        """Test transformation of CLOSE_LONG signal to tradeengine format."""
        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.SELL,
            signal_action=SignalAction.CLOSE_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.9,
            price=51000.0,
            strategy_name="spread_liquidity",
        )

        result = transform_signal_for_tradeengine(signal)

        assert result["action"] == "close"
        assert result["signal_type"] == "sell"
        assert result["confidence"] == 0.9

    def test_transform_hold_signal(self):
        """Test transformation of HOLD signal to tradeengine format."""
        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.HOLD,
            signal_action=SignalAction.HOLD,
            confidence=SignalConfidence.LOW,
            confidence_score=0.3,
            price=50000.0,
            strategy_name="onchain_metrics",
        )

        result = transform_signal_for_tradeengine(signal)

        assert result["action"] == "hold"
        assert result["signal_type"] == "hold"
        assert result["confidence"] == 0.3
        assert result["strength"] == "weak"

    def test_timestamp_conversion(self):
        """Test that timestamp is properly converted to ISO format."""
        now = datetime.utcnow()
        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.8,
            price=50000.0,
            strategy_name="test",
            timestamp=now,
        )

        result = transform_signal_for_tradeengine(signal)

        assert "timestamp" in result
        assert isinstance(result["timestamp"], str)
        assert result["timestamp"] == now.isoformat()

    def test_metadata_preservation(self):
        """Test that original metadata is preserved and augmented."""
        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.8,
            price=50000.0,
            strategy_name="test",
            metadata={"custom_field": "custom_value", "indicator_value": 123.45},
        )

        result = transform_signal_for_tradeengine(signal)

        assert result["metadata"]["custom_field"] == "custom_value"
        assert result["metadata"]["indicator_value"] == 123.45
        assert result["metadata"]["original_signal_type"] == "BUY"
        assert result["metadata"]["original_signal_action"] == "OPEN_LONG"
        assert result["metadata"]["original_confidence"] == "HIGH"

    def test_risk_management_defaults(self):
        """Test that risk management defaults are added."""
        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="test",
        )

        result = transform_signal_for_tradeengine(signal)

        assert "stop_loss_pct" in result
        assert "take_profit_pct" in result
        assert result["stop_loss_pct"] == 0.02  # 2% for high confidence
        assert result["take_profit_pct"] == 0.05  # 5% for high confidence

    def test_order_configuration_defaults(self):
        """Test that order configuration defaults are added."""
        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.8,
            price=50000.0,
            strategy_name="test",
        )

        result = transform_signal_for_tradeengine(signal)

        assert result["order_type"] == "market"
        assert result["time_in_force"] == "GTC"
        assert "quantity" in result
        assert result["quantity"] > 0


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


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_missing_timeframe_in_metadata(self):
        """Test that missing timeframe defaults to 'tick'."""
        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.8,
            price=50000.0,
            strategy_name="test",
            metadata={},
        )

        result = transform_signal_for_tradeengine(signal)

        assert result["timeframe"] == "tick"

    def test_boundary_confidence_values(self):
        """Test boundary confidence values."""
        # Test minimum confidence (0.0)
        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.HOLD,
            signal_action=SignalAction.HOLD,
            confidence=SignalConfidence.LOW,
            confidence_score=0.0,
            price=50000.0,
            strategy_name="test",
        )
        result = transform_signal_for_tradeengine(signal)
        assert result["confidence"] == 0.0
        assert result["strength"] == "weak"

        # Test maximum confidence (1.0)
        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=1.0,
            price=50000.0,
            strategy_name="test",
        )
        result = transform_signal_for_tradeengine(signal)
        assert result["confidence"] == 1.0
        assert result["strength"] == "extreme"

    def test_all_signal_actions(self):
        """Test all signal action mappings."""
        actions = [
            (SignalAction.OPEN_LONG, "buy"),
            (SignalAction.OPEN_SHORT, "sell"),
            (SignalAction.CLOSE_LONG, "close"),
            (SignalAction.CLOSE_SHORT, "close"),
            (SignalAction.HOLD, "hold"),
        ]

        for signal_action, expected_action in actions:
            signal = Signal(
                symbol="BTCUSDT",
                signal_type=SignalType.BUY,
                signal_action=signal_action,
                confidence=SignalConfidence.HIGH,
                confidence_score=0.8,
                price=50000.0,
                strategy_name="test",
            )

            result = transform_signal_for_tradeengine(signal)
            assert result["action"] == expected_action


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

