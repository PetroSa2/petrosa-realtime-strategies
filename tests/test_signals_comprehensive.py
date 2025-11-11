"""
Comprehensive tests for Signal models to achieve 100% coverage.

Tests cover:
- All validators and their error paths
- All property methods
- Edge cases and invalid inputs
- Enum values
- Metadata handling
"""

from datetime import datetime

import pytest

from strategies.models.signals import (
    Signal,
    SignalAction,
    SignalAggregation,
    SignalConfidence,
    SignalType,
    StrategySignal,
)


class TestSignalEnums:
    """Test Signal enum values."""

    def test_signal_type_values(self):
        """Test SignalType enum has correct values."""
        assert SignalType.BUY == "BUY"
        assert SignalType.SELL == "SELL"
        assert SignalType.HOLD == "HOLD"

    def test_signal_action_values(self):
        """Test SignalAction enum has correct values."""
        assert SignalAction.OPEN_LONG == "OPEN_LONG"
        assert SignalAction.OPEN_SHORT == "OPEN_SHORT"
        assert SignalAction.CLOSE_LONG == "CLOSE_LONG"
        assert SignalAction.CLOSE_SHORT == "CLOSE_SHORT"
        assert SignalAction.HOLD == "HOLD"

    def test_signal_confidence_values(self):
        """Test SignalConfidence enum has correct values."""
        assert SignalConfidence.HIGH == "HIGH"
        assert SignalConfidence.MEDIUM == "MEDIUM"
        assert SignalConfidence.LOW == "LOW"


class TestSignalValidators:
    """Test Signal model validators."""

    def test_validate_symbol_too_short(self):
        """Test symbol validator rejects short symbols."""
        with pytest.raises(ValueError, match="Invalid symbol format"):
            Signal(
                symbol="BTC",  # Too short
                signal_type=SignalType.BUY,
                signal_action=SignalAction.OPEN_LONG,
                confidence=SignalConfidence.HIGH,
                confidence_score=0.85,
                price=50000.0,
                strategy_name="test",
            )

    def test_validate_symbol_empty(self):
        """Test symbol validator rejects empty symbols."""
        with pytest.raises(ValueError, match="Invalid symbol format"):
            Signal(
                symbol="",  # Empty
                signal_type=SignalType.BUY,
                signal_action=SignalAction.OPEN_LONG,
                confidence=SignalConfidence.HIGH,
                confidence_score=0.85,
                price=50000.0,
                strategy_name="test",
            )

    def test_validate_symbol_uppercase_conversion(self):
        """Test symbol is converted to uppercase."""
        signal = Signal(
            symbol="btcusdt",  # lowercase
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="test",
        )
        assert signal.symbol == "BTCUSDT"

    def test_validate_confidence_score_below_zero(self):
        """Test confidence_score validator rejects negative values."""
        with pytest.raises(ValueError):
            Signal(
                symbol="BTCUSDT",
                signal_type=SignalType.BUY,
                signal_action=SignalAction.OPEN_LONG,
                confidence=SignalConfidence.HIGH,
                confidence_score=-0.1,  # Negative
                price=50000.0,
                strategy_name="test",
            )

    def test_validate_confidence_score_above_one(self):
        """Test confidence_score validator rejects values above 1.0."""
        with pytest.raises(ValueError):
            Signal(
                symbol="BTCUSDT",
                signal_type=SignalType.BUY,
                signal_action=SignalAction.OPEN_LONG,
                confidence=SignalConfidence.HIGH,
                confidence_score=1.5,  # Above 1.0
                price=50000.0,
                strategy_name="test",
            )

    def test_validate_price_zero(self):
        """Test price validator rejects zero price."""
        with pytest.raises(ValueError):
            Signal(
                symbol="BTCUSDT",
                signal_type=SignalType.BUY,
                signal_action=SignalAction.OPEN_LONG,
                confidence=SignalConfidence.HIGH,
                confidence_score=0.85,
                price=0.0,  # Zero price
                strategy_name="test",
            )

    def test_validate_price_negative(self):
        """Test price validator rejects negative price."""
        with pytest.raises(ValueError):
            Signal(
                symbol="BTCUSDT",
                signal_type=SignalType.BUY,
                signal_action=SignalAction.OPEN_LONG,
                confidence=SignalConfidence.HIGH,
                confidence_score=0.85,
                price=-100.0,  # Negative price
                strategy_name="test",
            )


class TestSignalProperties:
    """Test Signal model properties."""

    def test_is_buy_signal_true(self):
        """Test is_buy_signal returns True for BUY signals."""
        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="test",
        )
        assert signal.is_buy_signal is True
        assert signal.is_sell_signal is False
        assert signal.is_hold_signal is False

    def test_is_sell_signal_true(self):
        """Test is_sell_signal returns True for SELL signals."""
        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.SELL,
            signal_action=SignalAction.OPEN_SHORT,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="test",
        )
        assert signal.is_sell_signal is True
        assert signal.is_buy_signal is False
        assert signal.is_hold_signal is False

    def test_is_hold_signal_true(self):
        """Test is_hold_signal returns True for HOLD signals."""
        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.HOLD,
            signal_action=SignalAction.HOLD,
            confidence=SignalConfidence.MEDIUM,
            confidence_score=0.5,
            price=50000.0,
            strategy_name="test",
        )
        assert signal.is_hold_signal is True
        assert signal.is_buy_signal is False
        assert signal.is_sell_signal is False

    def test_is_high_confidence_true(self):
        """Test is_high_confidence returns True for HIGH confidence."""
        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="test",
        )
        assert signal.is_high_confidence is True
        assert signal.is_medium_confidence is False
        assert signal.is_low_confidence is False

    def test_is_medium_confidence_true(self):
        """Test is_medium_confidence returns True for MEDIUM confidence."""
        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.MEDIUM,
            confidence_score=0.65,
            price=50000.0,
            strategy_name="test",
        )
        assert signal.is_medium_confidence is True
        assert signal.is_high_confidence is False
        assert signal.is_low_confidence is False

    def test_is_low_confidence_true(self):
        """Test is_low_confidence returns True for LOW confidence."""
        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.LOW,
            confidence_score=0.45,
            price=50000.0,
            strategy_name="test",
        )
        assert signal.is_low_confidence is True
        assert signal.is_high_confidence is False
        assert signal.is_medium_confidence is False


class TestSignalEdgeCases:
    """Test Signal model edge cases."""

    def test_signal_with_metadata(self):
        """Test Signal with custom metadata."""
        metadata = {"indicator": "RSI", "value": 75.3, "timeframe": "1h"}
        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="test",
            metadata=metadata,
        )
        assert signal.metadata == metadata
        assert signal.metadata["indicator"] == "RSI"

    def test_signal_with_custom_timestamp(self):
        """Test Signal with custom timestamp."""
        custom_time = datetime(2024, 1, 1, 12, 0, 0)
        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="test",
            timestamp=custom_time,
        )
        assert signal.timestamp == custom_time

    def test_signal_minimum_valid_symbol(self):
        """Test Signal with minimum valid symbol length (6 chars)."""
        signal = Signal(
            symbol="BTCUSD",  # Exactly 6 chars
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="test",
        )
        assert signal.symbol == "BTCUSD"

    def test_signal_confidence_score_boundary_zero(self):
        """Test Signal with confidence_score exactly 0.0."""
        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.HOLD,
            signal_action=SignalAction.HOLD,
            confidence=SignalConfidence.LOW,
            confidence_score=0.0,  # Minimum valid
            price=50000.0,
            strategy_name="test",
        )
        assert signal.confidence_score == 0.0

    def test_signal_confidence_score_boundary_one(self):
        """Test Signal with confidence_score exactly 1.0."""
        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=1.0,  # Maximum valid
            price=50000.0,
            strategy_name="test",
        )
        assert signal.confidence_score == 1.0

    def test_signal_very_small_price(self):
        """Test Signal with very small but valid price."""
        signal = Signal(
            symbol="SHIBAINU",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.MEDIUM,
            confidence_score=0.65,
            price=0.00001,  # Very small price
            strategy_name="test",
        )
        assert signal.price == 0.00001

    def test_signal_very_large_price(self):
        """Test Signal with very large price."""
        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=1000000.0,  # Very large price
            strategy_name="test",
        )
        assert signal.price == 1000000.0

    def test_signal_all_signal_actions(self):
        """Test Signal with all possible SignalAction values."""
        actions = [
            SignalAction.OPEN_LONG,
            SignalAction.OPEN_SHORT,
            SignalAction.CLOSE_LONG,
            SignalAction.CLOSE_SHORT,
            SignalAction.HOLD,
        ]

        for action in actions:
            signal = Signal(
                symbol="BTCUSDT",
                signal_type=SignalType.BUY
                if "LONG" in action.value or action == SignalAction.HOLD
                else SignalType.SELL,
                signal_action=action,
                confidence=SignalConfidence.MEDIUM,
                confidence_score=0.65,
                price=50000.0,
                strategy_name="test",
            )
            assert signal.signal_action == action

    def test_signal_empty_metadata_by_default(self):
        """Test Signal has empty metadata dict by default."""
        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="test",
        )
        assert signal.metadata == {}
        assert isinstance(signal.metadata, dict)

    def test_signal_timestamp_auto_generated(self):
        """Test Signal timestamp is auto-generated if not provided."""
        before = datetime.utcnow()
        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="test",
        )
        after = datetime.utcnow()

        assert before <= signal.timestamp <= after


class TestStrategySignal:
    """Test StrategySignal model (wrapper for Signal with strategy metadata)."""

    def test_strategy_signal_creation(self):
        """Test StrategySignal creation - covers lines 108-121."""
        base_signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="test_strategy",
        )

        strategy_signal = StrategySignal(
            signal=base_signal,
            strategy_version="1.0.0",
            processing_time_ms=15.5,
            strategy_parameters={"threshold": 1.5},
            input_data={"rsi": 75},
            strategy_specific_metrics={"confidence_factor": 0.95},
        )

        assert strategy_signal.signal == base_signal
        assert strategy_signal.strategy_version == "1.0.0"
        assert strategy_signal.processing_time_ms == 15.5

    def test_strategy_signal_symbol_property(self):
        """Test StrategySignal.symbol property - covers line 126."""
        base_signal = Signal(
            symbol="ETHUSDT",
            signal_type=SignalType.SELL,
            signal_action=SignalAction.OPEN_SHORT,
            confidence=SignalConfidence.MEDIUM,
            confidence_score=0.65,
            price=3000.0,
            strategy_name="test",
        )

        strategy_signal = StrategySignal(
            signal=base_signal, strategy_version="1.0.0", processing_time_ms=10.0
        )

        assert strategy_signal.symbol == "ETHUSDT"

    def test_strategy_signal_signal_type_property(self):
        """Test StrategySignal.signal_type property - covers line 131."""
        base_signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="test",
        )

        strategy_signal = StrategySignal(
            signal=base_signal, strategy_version="1.0.0", processing_time_ms=10.0
        )

        assert strategy_signal.signal_type == SignalType.BUY

    def test_strategy_signal_confidence_score_property(self):
        """Test StrategySignal.confidence_score property - covers line 136."""
        base_signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.90,
            price=50000.0,
            strategy_name="test",
        )

        strategy_signal = StrategySignal(
            signal=base_signal, strategy_version="1.0.0", processing_time_ms=10.0
        )

        assert strategy_signal.confidence_score == 0.90

    def test_strategy_signal_timestamp_property(self):
        """Test StrategySignal.timestamp property - covers line 141."""
        custom_time = datetime(2024, 6, 1, 12, 0, 0)
        base_signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="test",
            timestamp=custom_time,
        )

        strategy_signal = StrategySignal(
            signal=base_signal, strategy_version="1.0.0", processing_time_ms=10.0
        )

        assert strategy_signal.timestamp == custom_time


class TestSignalAggregation:
    """Test SignalAggregation model for multi-strategy signal aggregation."""

    def test_signal_aggregation_creation(self):
        """Test SignalAggregation creation."""
        base_signal1 = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="strategy1",
        )

        strategy_signal1 = StrategySignal(
            signal=base_signal1, strategy_version="1.0.0", processing_time_ms=10.0
        )

        aggregation = SignalAggregation(
            symbol="BTCUSDT",
            aggregated_signal_type=SignalType.BUY,
            aggregated_signal_action=SignalAction.OPEN_LONG,
            aggregated_confidence_score=0.85,
            aggregated_confidence=SignalConfidence.HIGH,
            strategy_signals={"strategy1": strategy_signal1},
            aggregation_method="weighted_average",
        )

        assert aggregation.symbol == "BTCUSDT"
        assert aggregation.aggregation_method == "weighted_average"

    def test_signal_aggregation_symbol_validator_error(self):
        """Test SignalAggregation symbol validator - covers lines 177-179."""
        base_signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="test",
        )

        strategy_signal = StrategySignal(
            signal=base_signal, strategy_version="1.0.0", processing_time_ms=10.0
        )

        with pytest.raises(ValueError, match="Invalid symbol format"):
            SignalAggregation(
                symbol="BTC",  # Too short
                aggregated_signal_type=SignalType.BUY,
                aggregated_signal_action=SignalAction.OPEN_LONG,
                aggregated_confidence_score=0.85,
                aggregated_confidence=SignalConfidence.HIGH,
                strategy_signals={"test": strategy_signal},
                aggregation_method="test",
            )

    def test_signal_aggregation_confidence_score_validator_error(self):
        """Test SignalAggregation confidence validator - covers lines 184-186."""
        from pydantic import ValidationError

        base_signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="test",
        )

        strategy_signal = StrategySignal(
            signal=base_signal, strategy_version="1.0.0", processing_time_ms=10.0
        )

        with pytest.raises(ValidationError):
            SignalAggregation(
                symbol="BTCUSDT",
                aggregated_signal_type=SignalType.BUY,
                aggregated_signal_action=SignalAction.OPEN_LONG,
                aggregated_confidence_score=1.5,  # Invalid - above 1.0
                aggregated_confidence=SignalConfidence.HIGH,
                strategy_signals={"test": strategy_signal},
                aggregation_method="test",
            )

    def test_signal_aggregation_strategy_count_property(self):
        """Test strategy_count property - covers line 191."""
        base_signal1 = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="strategy1",
        )

        base_signal2 = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.MEDIUM,
            confidence_score=0.75,
            price=50000.0,
            strategy_name="strategy2",
        )

        strategy_signals = {
            "strategy1": StrategySignal(
                signal=base_signal1, strategy_version="1.0.0", processing_time_ms=10.0
            ),
            "strategy2": StrategySignal(
                signal=base_signal2, strategy_version="1.0.0", processing_time_ms=12.0
            ),
        }

        aggregation = SignalAggregation(
            symbol="BTCUSDT",
            aggregated_signal_type=SignalType.BUY,
            aggregated_signal_action=SignalAction.OPEN_LONG,
            aggregated_confidence_score=0.80,
            aggregated_confidence=SignalConfidence.HIGH,
            strategy_signals=strategy_signals,
            aggregation_method="weighted",
        )

        assert aggregation.strategy_count == 2

    def test_signal_aggregation_average_confidence_empty(self):
        """Test average_confidence_score with empty signals - covers lines 196-198."""
        aggregation = SignalAggregation(
            symbol="BTCUSDT",
            aggregated_signal_type=SignalType.BUY,
            aggregated_signal_action=SignalAction.OPEN_LONG,
            aggregated_confidence_score=0.0,
            aggregated_confidence=SignalConfidence.LOW,
            strategy_signals={},  # Empty
            aggregation_method="test",
        )

        assert aggregation.average_confidence_score == 0.0

    def test_signal_aggregation_consensus_signal_type_empty(self):
        """Test consensus_signal_type with empty signals - covers lines 204-205."""
        aggregation = SignalAggregation(
            symbol="BTCUSDT",
            aggregated_signal_type=SignalType.BUY,
            aggregated_signal_action=SignalAction.OPEN_LONG,
            aggregated_confidence_score=0.0,
            aggregated_confidence=SignalConfidence.LOW,
            strategy_signals={},  # Empty
            aggregation_method="test",
        )

        assert aggregation.consensus_signal_type is None

    def test_signal_aggregation_is_strong_consensus_empty(self):
        """Test is_strong_consensus with empty signals - covers lines 217-218."""
        aggregation = SignalAggregation(
            symbol="BTCUSDT",
            aggregated_signal_type=SignalType.BUY,
            aggregated_signal_action=SignalAction.OPEN_LONG,
            aggregated_confidence_score=0.0,
            aggregated_confidence=SignalConfidence.LOW,
            strategy_signals={},  # Empty
            aggregation_method="test",
        )

        assert aggregation.is_strong_consensus is False
