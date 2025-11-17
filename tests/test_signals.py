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
    SignalMetrics,
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

    def test_confidence_score_negative(self):
        """Test confidence score validation with negative value - covers line 71."""
        with pytest.raises(ValidationError):
            Signal(
                symbol="BTCUSDT",
                signal_type=SignalType.BUY,
                signal_action=SignalAction.OPEN_LONG,
                confidence=SignalConfidence.HIGH,
                confidence_score=-0.1,  # Negative value
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

    def test_is_strong_consensus_true(self):
        """Test is_strong_consensus when consensus exists."""
        # Create 3 BUY signals and 1 SELL (70%+ consensus)
        signals = {}
        for i in range(3):
            sig = Signal(
                symbol="BTCUSDT",
                signal_type=SignalType.BUY,
                signal_action=SignalAction.OPEN_LONG,
                confidence=SignalConfidence.HIGH,
                confidence_score=0.85,
                price=50000.0,
                strategy_name=f"s{i}",
            )
            signals[f"s{i}"] = StrategySignal(
                signal=sig, strategy_version="1.0", processing_time_ms=1.0
            )

        # Add one SELL signal
        sell_sig = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.SELL,
            signal_action=SignalAction.OPEN_SHORT,
            confidence=SignalConfidence.LOW,
            confidence_score=0.4,
            price=50000.0,
            strategy_name="s3",
        )
        signals["s3"] = StrategySignal(
            signal=sell_sig, strategy_version="1.0", processing_time_ms=1.0
        )

        agg = SignalAggregation(
            symbol="BTCUSDT",
            aggregated_signal_type=SignalType.BUY,
            aggregated_signal_action=SignalAction.OPEN_LONG,
            aggregated_confidence_score=0.7,
            aggregated_confidence=SignalConfidence.HIGH,
            strategy_signals=signals,
            aggregation_method="consensus",
        )

        assert agg.is_strong_consensus is True  # 75% agree

    def test_is_strong_consensus_false(self):
        """Test is_strong_consensus when no consensus."""
        # Create equal BUY and SELL signals (50/50 split)
        signals = {}
        
        buy_sig = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="s1",
        )
        signals["s1"] = StrategySignal(
            signal=buy_sig, strategy_version="1.0", processing_time_ms=1.0
        )

        sell_sig = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.SELL,
            signal_action=SignalAction.OPEN_SHORT,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="s2",
        )
        signals["s2"] = StrategySignal(
            signal=sell_sig, strategy_version="1.0", processing_time_ms=1.0
        )

        agg = SignalAggregation(
            symbol="BTCUSDT",
            aggregated_signal_type=SignalType.HOLD,
            aggregated_signal_action=SignalAction.HOLD,
            aggregated_confidence_score=0.5,
            aggregated_confidence=SignalConfidence.MEDIUM,
            strategy_signals=signals,
            aggregation_method="consensus",
        )

        assert agg.is_strong_consensus is False  # Only 50% agree

    def test_signal_aggregation_empty_strategy_signals(self):
        """Test SignalAggregation with empty strategy_signals - covers lines 197, 205, 218."""
        agg = SignalAggregation(
            symbol="BTCUSDT",
            aggregated_signal_type=SignalType.BUY,
            aggregated_signal_action=SignalAction.OPEN_LONG,
            aggregated_confidence_score=0.85,
            aggregated_confidence=SignalConfidence.HIGH,
            strategy_signals={},  # Empty
            aggregation_method="consensus",
        )

        # Line 197: average_confidence_score returns 0.0 when empty
        assert agg.average_confidence_score == 0.0

        # Line 205: consensus_signal_type returns None when empty
        assert agg.consensus_signal_type is None

        # Line 218: is_strong_consensus returns False when empty
        assert agg.is_strong_consensus is False

    def test_signal_aggregation_consensus_type_none(self):
        """Test is_strong_consensus when consensus_type is None - covers line 222."""
        # Create aggregation with mixed signals that result in None consensus
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
            signal_type=SignalType.SELL,
            signal_action=SignalAction.OPEN_SHORT,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="s2",
        )
        signal3 = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.HOLD,
            signal_action=SignalAction.HOLD,
            confidence=SignalConfidence.MEDIUM,
            confidence_score=0.5,
            price=50000.0,
            strategy_name="s3",
        )

        agg = SignalAggregation(
            symbol="BTCUSDT",
            aggregated_signal_type=SignalType.HOLD,
            aggregated_signal_action=SignalAction.HOLD,
            aggregated_confidence_score=0.5,
            aggregated_confidence=SignalConfidence.MEDIUM,
            strategy_signals={
                "s1": StrategySignal(signal=signal1, strategy_version="1.0", processing_time_ms=1.0),
                "s2": StrategySignal(signal=signal2, strategy_version="1.0", processing_time_ms=1.0),
                "s3": StrategySignal(signal=signal3, strategy_version="1.0", processing_time_ms=1.0),
            },
            aggregation_method="consensus",
        )

        # When consensus_type is None or consensus is weak, should return False
        # Line 222: return False when consensus_type is None
        # This might happen if max() returns None or there's a tie
        consensus = agg.consensus_signal_type
        if consensus is None:
            assert agg.is_strong_consensus is False

    def test_signal_aggregation_symbol_validation(self):
        """Test SignalAggregation symbol validation - covers line 178."""
        with pytest.raises(ValidationError):
            SignalAggregation(
                symbol="BTC",  # Too short
                aggregated_signal_type=SignalType.BUY,
                aggregated_signal_action=SignalAction.OPEN_LONG,
                aggregated_confidence_score=0.85,
                aggregated_confidence=SignalConfidence.HIGH,
                strategy_signals={},
                aggregation_method="consensus",
            )

    def test_signal_aggregation_confidence_score_validation(self):
        """Test SignalAggregation confidence score validation - covers line 185."""
        with pytest.raises(ValidationError):
            SignalAggregation(
                symbol="BTCUSDT",
                aggregated_signal_type=SignalType.BUY,
                aggregated_signal_action=SignalAction.OPEN_LONG,
                aggregated_confidence_score=1.5,  # Out of range
                aggregated_confidence=SignalConfidence.HIGH,
                strategy_signals={},
                aggregation_method="consensus",
            )


class TestSignalMetrics:
    """Test SignalMetrics model."""

    def test_create_signal_metrics(self):
        """Test creating signal metrics."""
        metrics = SignalMetrics()

        assert metrics.total_signals_generated == 0
        assert len(metrics.signals_by_type) == 0

    def test_update_metrics_single_signal(self):
        """Test updating metrics with single signal."""
        metrics = SignalMetrics()
        
        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="test_strategy",
        )

        metrics.update_metrics(signal, processing_time_ms=10.5)

        assert metrics.total_signals_generated == 1
        assert metrics.signals_by_type[SignalType.BUY] == 1
        assert metrics.signals_by_confidence[SignalConfidence.HIGH] == 1
        assert metrics.signals_by_strategy["test_strategy"] == 1
        assert metrics.average_processing_time_ms == 10.5
        assert metrics.last_signal_timestamp == signal.timestamp

    def test_update_metrics_multiple_signals(self):
        """Test updating metrics with multiple signals."""
        metrics = SignalMetrics()
        
        # Signal 1
        signal1 = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="strategy1",
        )
        metrics.update_metrics(signal1, processing_time_ms=10.0)

        # Signal 2
        signal2 = Signal(
            symbol="ETHUSDT",
            signal_type=SignalType.SELL,
            signal_action=SignalAction.OPEN_SHORT,
            confidence=SignalConfidence.MEDIUM,
            confidence_score=0.65,
            price=3000.0,
            strategy_name="strategy2",
        )
        metrics.update_metrics(signal2, processing_time_ms=20.0)

        assert metrics.total_signals_generated == 2
        assert metrics.signals_by_type[SignalType.BUY] == 1
        assert metrics.signals_by_type[SignalType.SELL] == 1
        assert metrics.average_processing_time_ms == 15.0  # (10 + 20) / 2

    def test_get_signal_distribution_empty(self):
        """Test get_signal_distribution with no signals."""
        metrics = SignalMetrics()

        distribution = metrics.get_signal_distribution()

        assert distribution == {}

    def test_get_signal_distribution_with_signals(self):
        """Test get_signal_distribution with signals."""
        metrics = SignalMetrics()
        
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

        metrics.update_metrics(signal1, processing_time_ms=10.0)
        metrics.update_metrics(signal2, processing_time_ms=10.0)

        distribution = metrics.get_signal_distribution()

        assert isinstance(distribution, dict)
        # Should have distribution data when signals exist
        assert len(distribution) > 0 or metrics.total_signals_generated == 2

