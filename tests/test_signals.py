"""
Tests for strategies/models/signals.py.
"""

from datetime import datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from strategies.models.signals import (
    Signal,
    SignalAction,
    SignalAggregation,
    SignalConfidence,
    SignalType,
    StrategySignal,
)


class TestSignal:
    """Test Signal model."""

    def test_create_buy_signal(self):
        """Test creating a buy signal."""
        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="iceberg_detector",
        )

        assert signal.symbol == "BTCUSDT"
        assert signal.signal_type == SignalType.BUY
        assert signal.signal_action == SignalAction.OPEN_LONG
        assert signal.confidence == SignalConfidence.HIGH
        assert signal.confidence_score == 0.85

    def test_create_sell_signal(self):
        """Test creating a sell signal."""
        signal = Signal(
            symbol="ETHUSDT",
            signal_type=SignalType.SELL,
            signal_action=SignalAction.OPEN_SHORT,
            confidence=SignalConfidence.MEDIUM,
            confidence_score=0.65,
            price=3000.0,
            strategy_name="spread_liquidity",
        )

        assert signal.signal_type == SignalType.SELL
        assert signal.signal_action == SignalAction.OPEN_SHORT
        assert signal.confidence == SignalConfidence.MEDIUM

    def test_create_hold_signal(self):
        """Test creating a hold signal."""
        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.HOLD,
            signal_action=SignalAction.HOLD,
            confidence=SignalConfidence.LOW,
            confidence_score=0.45,
            price=50000.0,
            strategy_name="btc_dominance",
        )

        assert signal.signal_type == SignalType.HOLD
        assert signal.signal_action == SignalAction.HOLD

    def test_create_close_long_signal(self):
        """Test creating a close long signal."""
        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.SELL,
            signal_action=SignalAction.CLOSE_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.9,
            price=51000.0,
            strategy_name="spread_liquidity",
        )

        assert signal.signal_action == SignalAction.CLOSE_LONG

    def test_create_close_short_signal(self):
        """Test creating a close short signal."""
        signal = Signal(
            symbol="ETHUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.CLOSE_SHORT,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.88,
            price=3100.0,
            strategy_name="iceberg_detector",
        )

        assert signal.signal_action == SignalAction.CLOSE_SHORT

    def test_signal_with_metadata(self):
        """Test signal with metadata."""
        metadata = {
            "spread_ratio": 2.5,
            "liquidity_imbalance": 0.3,
            "iceberg_detected": True,
        }

        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="spread_liquidity",
            metadata=metadata,
        )

        assert signal.metadata == metadata
        assert signal.metadata["spread_ratio"] == 2.5

    def test_symbol_validation(self):
        """Test symbol validation."""
        with pytest.raises(ValidationError):
            Signal(
                symbol="BTC",  # Too short
                signal_type=SignalType.BUY,
                signal_action=SignalAction.OPEN_LONG,
                confidence=SignalConfidence.HIGH,
                confidence_score=0.85,
                price=50000.0,
                strategy_name="test_strategy",
            )

    def test_symbol_uppercase_conversion(self):
        """Test symbol is converted to uppercase."""
        signal = Signal(
            symbol="btcusdt",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="test_strategy",
        )

        assert signal.symbol == "BTCUSDT"

    def test_confidence_score_range(self):
        """Test confidence score must be 0-1."""
        with pytest.raises(ValidationError):
            Signal(
                symbol="BTCUSDT",
                signal_type=SignalType.BUY,
                signal_action=SignalAction.OPEN_LONG,
                confidence=SignalConfidence.HIGH,
                confidence_score=1.5,  # Out of range
                price=50000.0,
                strategy_name="test_strategy",
            )

    def test_price_positive(self):
        """Test price must be positive."""
        with pytest.raises(ValidationError):
            Signal(
                symbol="BTCUSDT",
                signal_type=SignalType.BUY,
                signal_action=SignalAction.OPEN_LONG,
                confidence=SignalConfidence.HIGH,
                confidence_score=0.85,
                price=-50000.0,  # Negative
                strategy_name="test_strategy",
            )

    def test_timestamp_default(self):
        """Test timestamp defaults to current time."""
        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="test_strategy",
        )

        assert signal.timestamp is not None
        assert isinstance(signal.timestamp, datetime)

    def test_metadata_default(self):
        """Test metadata defaults to empty dict."""
        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="test_strategy",
        )

        assert signal.metadata == {}

    def test_all_signal_types(self):
        """Test all signal type enums."""
        assert SignalType.BUY == SignalType.BUY
        assert SignalType.SELL == SignalType.SELL
        assert SignalType.HOLD == SignalType.HOLD

    def test_all_signal_actions(self):
        """Test all signal action enums."""
        assert SignalAction.OPEN_LONG == SignalAction.OPEN_LONG
        assert SignalAction.OPEN_SHORT == SignalAction.OPEN_SHORT
        assert SignalAction.CLOSE_LONG == SignalAction.CLOSE_LONG
        assert SignalAction.CLOSE_SHORT == SignalAction.CLOSE_SHORT
        assert SignalAction.HOLD == SignalAction.HOLD

    def test_all_confidence_levels(self):
        """Test all confidence level enums."""
        assert SignalConfidence.LOW == SignalConfidence.LOW
        assert SignalConfidence.MEDIUM == SignalConfidence.MEDIUM
        assert SignalConfidence.HIGH == SignalConfidence.HIGH

    def test_is_buy_signal_property(self):
        """Test is_buy_signal property."""
        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="test_strategy",
        )

        assert signal.is_buy_signal is True
        assert signal.is_sell_signal is False
        assert signal.is_hold_signal is False

    def test_is_sell_signal_property(self):
        """Test is_sell_signal property."""
        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.SELL,
            signal_action=SignalAction.OPEN_SHORT,
            confidence=SignalConfidence.MEDIUM,
            confidence_score=0.65,
            price=50000.0,
            strategy_name="test_strategy",
        )

        assert signal.is_sell_signal is True
        assert signal.is_buy_signal is False
        assert signal.is_hold_signal is False

    def test_is_hold_signal_property(self):
        """Test is_hold_signal property."""
        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.HOLD,
            signal_action=SignalAction.HOLD,
            confidence=SignalConfidence.LOW,
            confidence_score=0.45,
            price=50000.0,
            strategy_name="test_strategy",
        )

        assert signal.is_hold_signal is True
        assert signal.is_buy_signal is False
        assert signal.is_sell_signal is False

    def test_is_high_confidence_property(self):
        """Test is_high_confidence property."""
        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="test_strategy",
        )

        assert signal.is_high_confidence is True
        assert signal.is_medium_confidence is False
        assert signal.is_low_confidence is False

    def test_is_medium_confidence_property(self):
        """Test is_medium_confidence property."""
        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.MEDIUM,
            confidence_score=0.65,
            price=50000.0,
            strategy_name="test_strategy",
        )

        assert signal.is_medium_confidence is True
        assert signal.is_high_confidence is False
        assert signal.is_low_confidence is False

    def test_is_low_confidence_property(self):
        """Test is_low_confidence property."""
        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.LOW,
            confidence_score=0.45,
            price=50000.0,
            strategy_name="test_strategy",
        )

        assert signal.is_low_confidence is True
        assert signal.is_high_confidence is False
        assert signal.is_medium_confidence is False


class TestStrategySignal:
    """Test StrategySignal model."""

    def test_create_strategy_signal(self):
        """Test creating a strategy signal."""
        base_signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="iceberg_detector",
        )

        strategy_signal = StrategySignal(
            signal=base_signal,
            strategy_version="1.0.0",
            processing_time_ms=10.5,
            strategy_parameters={"threshold": 0.5},
            input_data={"orderbook": "data"},
            strategy_specific_metrics={"iceberg_score": 0.9},
        )

        assert strategy_signal.symbol == "BTCUSDT"
        assert strategy_signal.signal_type == SignalType.BUY
        assert strategy_signal.confidence_score == 0.85

    def test_strategy_signal_properties(self):
        """Test StrategySignal properties access base signal."""
        base_signal = Signal(
            symbol="ETHUSDT",
            signal_type=SignalType.SELL,
            signal_action=SignalAction.OPEN_SHORT,
            confidence=SignalConfidence.MEDIUM,
            confidence_score=0.65,
            price=3000.0,
            strategy_name="spread_liquidity",
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
        )

        strategy_signal = StrategySignal(
            signal=base_signal,
            strategy_version="2.0.0",
            processing_time_ms=5.2,
        )

        assert strategy_signal.symbol == "ETHUSDT"
        assert strategy_signal.signal_type == SignalType.SELL
        assert strategy_signal.timestamp == base_signal.timestamp


class TestSignalAggregation:
    """Test SignalAggregation model."""

    def test_create_signal_aggregation(self):
        """Test creating a signal aggregation."""
        signal1 = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="strategy1",
        )

        strategy_signal1 = StrategySignal(
            signal=signal1,
            strategy_version="1.0.0",
            processing_time_ms=10.0,
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
        assert aggregation.strategy_count == 1

    def test_average_confidence_score(self):
        """Test average_confidence_score calculation."""
        signal1 = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.9,
            price=50000.0,
            strategy_name="s1",
        )

        signal2 = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.MEDIUM,
            confidence_score=0.7,
            price=50000.0,
            strategy_name="s2",
        )

        agg = SignalAggregation(
            symbol="BTCUSDT",
            aggregated_signal_type=SignalType.BUY,
            aggregated_signal_action=SignalAction.OPEN_LONG,
            aggregated_confidence_score=0.8,
            aggregated_confidence=SignalConfidence.HIGH,
            strategy_signals={
                "s1": StrategySignal(
                    signal=signal1, strategy_version="1.0", processing_time_ms=1.0
                ),
                "s2": StrategySignal(
                    signal=signal2, strategy_version="1.0", processing_time_ms=2.0
                ),
            },
            aggregation_method="average",
        )

        assert agg.average_confidence_score == 0.8  # (0.9 + 0.7) / 2

    def test_consensus_signal_type(self):
        """Test consensus_signal_type property."""
        signal_buy = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="s_buy",
        )

        agg = SignalAggregation(
            symbol="BTCUSDT",
            aggregated_signal_type=SignalType.BUY,
            aggregated_signal_action=SignalAction.OPEN_LONG,
            aggregated_confidence_score=0.85,
            aggregated_confidence=SignalConfidence.HIGH,
            strategy_signals={
                "s1": StrategySignal(
                    signal=signal_buy, strategy_version="1.0", processing_time_ms=1.0
                )
            },
            aggregation_method="consensus",
        )

        assert agg.consensus_signal_type == SignalType.BUY

    def test_strategy_count(self):
        """Test strategy_count property."""
        signal1 = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="s1",
        )

        signal2 = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="s2",
        )

        agg = SignalAggregation(
            symbol="BTCUSDT",
            aggregated_signal_type=SignalType.BUY,
            aggregated_signal_action=SignalAction.OPEN_LONG,
            aggregated_confidence_score=0.85,
            aggregated_confidence=SignalConfidence.HIGH,
            strategy_signals={
                "s1": StrategySignal(
                    signal=signal1, strategy_version="1.0", processing_time_ms=1.0
                ),
                "s2": StrategySignal(
                    signal=signal2, strategy_version="1.0", processing_time_ms=1.0
                ),
            },
            aggregation_method="consensus",
        )

        assert agg.strategy_count == 2

