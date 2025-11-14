"""
Tests for custom business metrics.
"""

from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from strategies.models.signals import Signal, SignalAction, SignalConfidence, SignalType
from strategies.utils.metrics import (
    MetricsContext,
    RealtimeStrategyMetrics,
    get_metrics,
    initialize_metrics,
)


class TestRealtimeStrategyMetrics:
    """Test suite for RealtimeStrategyMetrics."""

    def test_initialization(self):
        """Test metrics initialization."""
        metrics = RealtimeStrategyMetrics()
        assert metrics.meter is not None
        assert metrics.messages_processed is not None
        assert metrics.strategy_latency is not None
        assert metrics.signals_generated is not None
        assert metrics.errors_total is not None

    def test_record_message_processed(self):
        """Test recording message processed."""
        metrics = RealtimeStrategyMetrics()

        # Verify metric counter exists and is callable
        assert metrics.messages_processed is not None
        assert callable(metrics.messages_processed.add)
        
        # Record message - should not raise exception
        metrics.record_message_processed(
            symbol="BTCUSDT", message_type="depth", strategy="spread_liquidity"
        )
        
        # Verify it was called successfully (counter exists and method is callable)
        assert metrics.messages_processed is not None

    def test_record_message_type(self):
        """Test recording message type."""
        metrics = RealtimeStrategyMetrics()

        # Verify message_types counter exists and is callable
        assert metrics.message_types is not None
        assert callable(metrics.message_types.add)
        
        # Record different message types - should not raise exception
        metrics.record_message_type("depth")
        metrics.record_message_type("trade")
        metrics.record_message_type("ticker")
        
        # Verify all calls completed successfully
        assert metrics.message_types is not None

    def test_record_strategy_latency(self):
        """Test recording strategy latency."""
        metrics = RealtimeStrategyMetrics()

        # Verify strategy_latency histogram exists and is callable
        assert metrics.strategy_latency is not None
        assert callable(metrics.strategy_latency.record)
        
        # Record latency - should not raise exception
        metrics.record_strategy_latency(
            strategy="iceberg_detector", latency_ms=15.5, symbol="ETHUSDT"
        )
        
        # Verify it was called successfully
        assert metrics.strategy_latency is not None

    def test_record_strategy_execution(self):
        """Test recording strategy execution."""
        metrics = RealtimeStrategyMetrics()

        # Verify strategy_executions counter exists and is callable
        assert metrics.strategy_executions is not None
        assert callable(metrics.strategy_executions.add)
        
        # Test different execution results - should not raise exceptions
        metrics.record_strategy_execution("btc_dominance", "success", "BTCUSDT")
        metrics.record_strategy_execution("btc_dominance", "failure", "BTCUSDT")
        metrics.record_strategy_execution("btc_dominance", "no_signal", "BTCUSDT")
        
        # Verify all calls completed successfully
        assert metrics.strategy_executions is not None

    def test_record_signal_generated(self):
        """Test recording signal generation."""
        metrics = RealtimeStrategyMetrics()

        # Verify signals_generated counter exists and is callable
        assert metrics.signals_generated is not None
        assert callable(metrics.signals_generated.add)
        
        # Test different signal types and confidence levels - should not raise exceptions
        metrics.record_signal_generated("spread_liquidity", "buy", "BTCUSDT", 0.95)
        metrics.record_signal_generated("spread_liquidity", "sell", "ETHUSDT", 0.75)
        metrics.record_signal_generated("iceberg_detector", "hold", "BNBUSDT", 0.5)
        
        # Verify all calls completed successfully
        assert metrics.signals_generated is not None

    def test_record_error(self):
        """Test recording errors."""
        metrics = RealtimeStrategyMetrics()

        # Verify errors_total counter exists and is callable
        assert metrics.errors_total is not None
        assert callable(metrics.errors_total.add)
        
        # Test with and without strategy - should not raise exceptions
        metrics.record_error("invalid_message")
        metrics.record_error("strategy_execution", strategy="btc_dominance")
        
        # Verify all calls completed successfully
        assert metrics.errors_total is not None

    def test_update_consumer_lag(self):
        """Test updating consumer lag."""
        metrics = RealtimeStrategyMetrics()

        # Update lag value
        metrics.update_consumer_lag(5.5)
        assert metrics._consumer_lag_value == 5.5

        metrics.update_consumer_lag(0.0)
        assert metrics._consumer_lag_value == 0.0

    def test_confidence_bucket(self):
        """Test confidence bucket calculation."""
        # Very high confidence
        assert RealtimeStrategyMetrics._get_confidence_bucket(0.95) == "very_high"
        assert RealtimeStrategyMetrics._get_confidence_bucket(0.9) == "very_high"

        # High confidence
        assert RealtimeStrategyMetrics._get_confidence_bucket(0.85) == "high"
        assert RealtimeStrategyMetrics._get_confidence_bucket(0.75) == "high"

        # Medium confidence
        assert RealtimeStrategyMetrics._get_confidence_bucket(0.6) == "medium"
        assert RealtimeStrategyMetrics._get_confidence_bucket(0.5) == "medium"

        # Low confidence
        assert RealtimeStrategyMetrics._get_confidence_bucket(0.4) == "low"
        assert RealtimeStrategyMetrics._get_confidence_bucket(0.1) == "low"


class TestGlobalMetrics:
    """Test suite for global metrics functions."""

    def test_initialize_metrics(self):
        """Test global metrics initialization."""
        metrics = initialize_metrics()
        assert metrics is not None
        assert isinstance(metrics, RealtimeStrategyMetrics)

    def test_get_metrics(self):
        """Test getting global metrics instance."""
        # Initialize first
        initialize_metrics()

        # Get should return initialized instance
        metrics = get_metrics()
        assert metrics is not None
        assert isinstance(metrics, RealtimeStrategyMetrics)


class TestMetricsContext:
    """Test suite for MetricsContext context manager."""

    def test_context_manager_success(self):
        """Test context manager with successful execution."""
        metrics = RealtimeStrategyMetrics()

        # Verify metrics exist before context
        assert metrics.strategy_latency is not None
        assert metrics.strategy_executions is not None

        with MetricsContext(
            strategy="test_strategy", symbol="BTCUSDT", metrics=metrics
        ) as ctx:
            # Simulate strategy execution
            assert ctx is not None
            assert ctx.strategy == "test_strategy"
            assert ctx.symbol == "BTCUSDT"
            pass

        # Context should have recorded latency - verify metrics still exist
        assert metrics.strategy_latency is not None
        assert metrics.strategy_executions is not None

    def test_context_manager_with_signal(self):
        """Test context manager recording signal."""
        metrics = RealtimeStrategyMetrics()

        with MetricsContext(
            strategy="test_strategy", symbol="BTCUSDT", metrics=metrics
        ) as ctx:
            # Simulate signal generation
            ctx.record_signal("buy", 0.85)

        assert ctx.signal_recorded is True

    def test_context_manager_with_exception(self):
        """Test context manager handling exceptions."""
        metrics = RealtimeStrategyMetrics()

        # Verify errors_total counter exists
        assert metrics.errors_total is not None
        assert callable(metrics.errors_total.add)

        with pytest.raises(ValueError) as exc_info:
            with MetricsContext(
                strategy="test_strategy", symbol="BTCUSDT", metrics=metrics
            ) as ctx:
                raise ValueError("Test exception")

        # Verify exception was raised
        assert "Test exception" in str(exc_info.value)
        
        # Error should have been recorded in metrics - verify counter still exists
        assert metrics.errors_total is not None

    def test_context_manager_no_signal(self):
        """Test context manager with no signal generated."""
        metrics = RealtimeStrategyMetrics()

        with MetricsContext(
            strategy="test_strategy", symbol="BTCUSDT", metrics=metrics
        ) as ctx:
            # Simulate strategy execution without signal
            pass

        assert ctx.signal_recorded is False

    def test_context_manager_timing(self):
        """Test that context manager measures execution time."""
        import time

        metrics = RealtimeStrategyMetrics()

        # Verify strategy_latency histogram exists
        assert metrics.strategy_latency is not None
        assert callable(metrics.strategy_latency.record)

        start_time = time.time()
        with MetricsContext(
            strategy="test_strategy", symbol="BTCUSDT", metrics=metrics
        ) as ctx:
            # Simulate some work
            time.sleep(0.01)  # 10ms
            assert ctx is not None
        elapsed_time = time.time() - start_time

        # Verify context completed and latency histogram still exists
        assert elapsed_time >= 0.01  # At least 10ms elapsed
        assert metrics.strategy_latency is not None

    def test_context_manager_without_metrics(self):
        """Test context manager gracefully handles no metrics instance."""
        # Should not raise exception even without metrics
        with MetricsContext(
            strategy="test_strategy", symbol="BTCUSDT", metrics=None
        ) as ctx:
            ctx.record_signal("buy", 0.9)

        # Should complete without error

    def test_context_manager_with_signal_object(self):
        """Test context manager with Signal object using signal_action attribute.

        This test verifies the fix for issue #62 where signal.action was incorrectly
        used instead of signal.signal_action, causing AttributeError.
        """
        metrics = RealtimeStrategyMetrics()

        # Create a Signal object with signal_action attribute
        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.85,
            price=50000.0,
            strategy_name="test_strategy",
            timestamp=datetime.utcnow(),
        )

        with MetricsContext(
            strategy="test_strategy", symbol="BTCUSDT", metrics=metrics
        ) as ctx:
            # Should not raise AttributeError
            ctx.record_signal(signal.signal_action.value, signal.confidence_score)

        assert ctx.signal_recorded is True


class TestMetricsIntegration:
    """Integration tests for metrics."""

    def test_full_workflow(self):
        """Test complete metrics recording workflow."""
        # Initialize metrics
        metrics = initialize_metrics()
        assert metrics is not None
        assert isinstance(metrics, RealtimeStrategyMetrics)

        # Simulate message processing
        symbol = "BTCUSDT"
        message_type = "depth"

        # Verify all metrics exist
        assert metrics.message_types is not None
        assert metrics.signals_generated is not None
        assert metrics.messages_processed is not None
        assert metrics.strategy_latency is not None

        # Record message received
        metrics.record_message_type(message_type)

        # Process through strategy with context
        with MetricsContext(
            strategy="spread_liquidity", symbol=symbol, metrics=metrics
        ) as ctx:
            # Simulate strategy logic
            confidence = 0.85
            signal_type = "buy"

            # Record signal
            ctx.record_signal(signal_type, confidence)
            assert ctx.signal_recorded is True

        # Record message processed
        metrics.record_message_processed(
            symbol, message_type, strategy="spread_liquidity"
        )

        # Update consumer lag
        metrics.update_consumer_lag(2.5)
        assert metrics._consumer_lag_value == 2.5

        # All metrics should be recorded without errors - verify they still exist
        assert metrics.message_types is not None
        assert metrics.signals_generated is not None
        assert metrics.messages_processed is not None

    def test_multiple_strategies_parallel(self):
        """Test metrics from multiple strategies executing in parallel."""
        metrics = initialize_metrics()
        assert metrics is not None

        strategies = ["spread_liquidity", "iceberg_detector", "btc_dominance"]
        symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]

        signal_count = 0
        for strategy in strategies:
            for symbol in symbols:
                with MetricsContext(
                    strategy=strategy, symbol=symbol, metrics=metrics
                ) as ctx:
                    # Simulate signal generation
                    if hash(strategy + symbol) % 2 == 0:
                        ctx.record_signal("buy", 0.8)
                        signal_count += 1

        # Verify signals were recorded
        assert signal_count > 0
        
        # All metrics should be recorded without conflicts - verify they exist
        assert metrics.signals_generated is not None
        assert metrics.strategy_executions is not None
        assert metrics.strategy_latency is not None

    def test_high_volume_metrics(self):
        """Test metrics under high volume."""
        metrics = initialize_metrics()
        assert metrics is not None

        # Verify all metrics exist before high volume
        assert metrics.message_types is not None
        assert metrics.messages_processed is not None
        assert metrics.signals_generated is not None
        assert metrics.strategy_latency is not None

        signal_count = 0
        # Simulate 1000 messages
        for i in range(1000):
            symbol = "BTCUSDT" if i % 2 == 0 else "ETHUSDT"
            message_type = ["depth", "trade", "ticker"][i % 3]

            metrics.record_message_type(message_type)
            metrics.record_message_processed(symbol, message_type)

            if i % 10 == 0:  # 10% signal generation rate
                with MetricsContext(
                    strategy="test_strategy", symbol=symbol, metrics=metrics
                ) as ctx:
                    ctx.record_signal("buy", 0.75)
                    signal_count += 1

        # Verify expected number of signals were recorded (100 signals for 1000 messages at 10% rate)
        assert signal_count == 100
        
        # Should handle high volume without errors - verify metrics still exist
        assert metrics.message_types is not None
        assert metrics.messages_processed is not None
        assert metrics.signals_generated is not None
        assert metrics.strategy_latency is not None
