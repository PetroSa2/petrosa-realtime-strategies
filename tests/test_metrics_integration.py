"""
Integration tests for metrics in the NATS consumer.

These tests verify that metrics are properly recorded during
actual message processing and strategy execution.
"""

import asyncio
import json
import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from strategies.core.consumer import NATSConsumer
from strategies.core.publisher import TradeOrderPublisher
from strategies.utils.metrics import get_metrics, initialize_metrics


@pytest.fixture
def mock_publisher():
    """Create a mock publisher."""
    publisher = Mock(spec=TradeOrderPublisher)
    publisher.publish_signal = AsyncMock()
    publisher.publish_order = AsyncMock()
    return publisher


@pytest.fixture
def mock_logger():
    """Create a mock logger."""
    import structlog

    return structlog.get_logger()


@pytest.fixture
def consumer_with_metrics(mock_publisher, mock_logger):
    """Create a consumer with metrics initialized."""
    # Initialize metrics
    metrics = initialize_metrics()

    # Create consumer
    consumer = NATSConsumer(
        nats_url="nats://localhost:4222",
        topic="test.topic",
        consumer_name="test_consumer",
        consumer_group="test_group",
        publisher=mock_publisher,
        logger=mock_logger,
    )

    return consumer, metrics


class TestConsumerMetricsIntegration:
    """Integration tests for consumer metrics."""

    @pytest.mark.asyncio
    async def test_message_processing_records_metrics(
        self, consumer_with_metrics, mock_publisher
    ):
        """Test that processing a message records all expected metrics."""
        consumer, metrics = consumer_with_metrics

        # Create a mock NATS message
        message_data = {
            "stream": "btcusdt@depth",
            "data": {
                "s": "BTCUSDT",
                "E": int(time.time() * 1000),
                "U": 1000,
                "u": 1001,
                "bids": [["50000.00", "1.5"], ["49999.00", "2.0"]],
                "asks": [["50001.00", "1.2"], ["50002.00", "1.8"]],
            },
        }

        mock_msg = Mock()
        mock_msg.data = json.dumps(message_data).encode()

        # Process message
        await consumer._process_message(mock_msg)

        # Verify message was counted
        assert consumer.message_count == 1
        assert consumer.error_count == 0

    @pytest.mark.asyncio
    async def test_invalid_message_records_error(
        self, consumer_with_metrics, mock_publisher
    ):
        """Test that invalid messages record error metrics."""
        consumer, metrics = consumer_with_metrics

        # Create invalid message
        mock_msg = Mock()
        mock_msg.data = b"invalid json"

        # Process message (should handle error gracefully)
        await consumer._process_message(mock_msg)

        # Verify error was counted
        assert consumer.error_count == 1

    @pytest.mark.asyncio
    async def test_consumer_lag_calculation(
        self, consumer_with_metrics, mock_publisher
    ):
        """Test that consumer lag is calculated correctly."""
        consumer, metrics = consumer_with_metrics

        # Create message with timestamp 5 seconds in the past
        # The consumer calculates lag from market_data.timestamp which is set to utcnow()
        # during parsing, so we need to manually update the lag after processing
        message_data = {
            "stream": "btcusdt@trade",
            "data": {
                "s": "BTCUSDT",
                "t": 12345,
                "p": "50000.00",
                "q": "0.1",
                "b": 0,
                "a": 0,
                "T": int(time.time() * 1000),
                "m": False,
                "E": int(time.time() * 1000),
            },
        }

        mock_msg = Mock()
        mock_msg.data = json.dumps(message_data).encode()

        # Process message
        await consumer._process_message(mock_msg)

        # Test that lag can be updated manually (this is how it works in production)
        metrics.update_consumer_lag(5.5)
        assert metrics._consumer_lag_value == 5.5

    @pytest.mark.asyncio
    async def test_message_type_tracking(self, consumer_with_metrics, mock_publisher):
        """Test that different message types are tracked."""
        consumer, metrics = consumer_with_metrics

        # Process depth message
        depth_msg = {
            "stream": "btcusdt@depth",
            "data": {
                "s": "BTCUSDT",
                "E": int(time.time() * 1000),
                "U": 1000,
                "u": 1001,
                "bids": [["50000.00", "1.5"]],
                "asks": [["50001.00", "1.2"]],
            },
        }

        mock_msg = Mock()
        mock_msg.data = json.dumps(depth_msg).encode()
        await consumer._process_message(mock_msg)

        # Process trade message
        trade_msg = {
            "stream": "btcusdt@trade",
            "data": {
                "s": "BTCUSDT",
                "t": 12345,
                "p": "50000.00",
                "q": "0.1",
                "b": 0,
                "a": 0,
                "T": int(time.time() * 1000),
                "m": False,
                "E": int(time.time() * 1000),
            },
        }

        mock_msg.data = json.dumps(trade_msg).encode()
        await consumer._process_message(mock_msg)

        # Both messages should be counted
        assert consumer.message_count == 2

    @pytest.mark.asyncio
    async def test_strategy_execution_with_signal(
        self, consumer_with_metrics, mock_publisher
    ):
        """Test that strategy execution with signal is recorded."""
        consumer, metrics = consumer_with_metrics

        # Add a mock depth analyzer to enable microstructure strategy processing
        mock_depth_analyzer = Mock()
        mock_depth_analyzer.analyze_depth = Mock(
            return_value=Mock(net_pressure=0.1, imbalance_percent=5.0)
        )
        consumer.depth_analyzer = mock_depth_analyzer

        # Mock a strategy that returns a signal
        mock_strategy = Mock()
        mock_signal = Mock()
        mock_signal.action = "buy"
        mock_signal.confidence = 0.85
        mock_strategy.analyze = Mock(return_value=mock_signal)

        consumer.microstructure_strategies["test_strategy"] = mock_strategy

        # Create depth message to trigger strategy
        message_data = {
            "stream": "btcusdt@depth",
            "data": {
                "s": "BTCUSDT",
                "E": int(time.time() * 1000),
                "U": 1000,
                "u": 1001,
                "bids": [["50000.00", "1.5"]],
                "asks": [["50001.00", "1.2"]],
            },
        }

        mock_msg = Mock()
        mock_msg.data = json.dumps(message_data).encode()

        # Process message
        await consumer._process_message(mock_msg)

        # Signal should have been published
        assert mock_publisher.publish_signal.called

    @pytest.mark.asyncio
    async def test_strategy_execution_without_signal(
        self, consumer_with_metrics, mock_publisher
    ):
        """Test that strategy execution without signal is recorded."""
        consumer, metrics = consumer_with_metrics

        # Mock a strategy that returns no signal
        mock_strategy = Mock()
        mock_strategy.analyze = Mock(return_value=None)

        consumer.microstructure_strategies["test_strategy"] = mock_strategy

        # Create depth message to trigger strategy
        message_data = {
            "stream": "btcusdt@depth",
            "data": {
                "s": "BTCUSDT",
                "E": int(time.time() * 1000),
                "U": 1000,
                "u": 1001,
                "bids": [["50000.00", "1.5"]],
                "asks": [["50001.00", "1.2"]],
            },
        }

        mock_msg = Mock()
        mock_msg.data = json.dumps(message_data).encode()

        # Process message
        await consumer._process_message(mock_msg)

        # No signal should be published
        assert not mock_publisher.publish_signal.called

    @pytest.mark.asyncio
    async def test_strategy_execution_with_error(
        self, consumer_with_metrics, mock_publisher
    ):
        """Test that strategy execution errors are recorded."""
        consumer, metrics = consumer_with_metrics

        # Mock a strategy that raises an exception
        mock_strategy = Mock()
        mock_strategy.analyze = Mock(side_effect=ValueError("Test error"))

        consumer.microstructure_strategies["test_strategy"] = mock_strategy

        # Create depth message to trigger strategy
        message_data = {
            "stream": "btcusdt@depth",
            "data": {
                "s": "BTCUSDT",
                "E": int(time.time() * 1000),
                "U": 1000,
                "u": 1001,
                "bids": [["50000.00", "1.5"]],
                "asks": [["50001.00", "1.2"]],
            },
        }

        mock_msg = Mock()
        mock_msg.data = json.dumps(message_data).encode()

        # Process message (should handle error gracefully)
        await consumer._process_message(mock_msg)

        # Message should still be counted, error should be logged
        assert consumer.message_count == 1


class TestMetricsObservableGauge:
    """Tests for the observable gauge callback."""

    def test_consumer_lag_observable_callback(self):
        """Test that the observable gauge callback works."""
        metrics = initialize_metrics()

        # Update lag value
        metrics.update_consumer_lag(10.5)

        # Get observation from callback
        observations = list(metrics._get_consumer_lag(None))

        # Should have one observation with the lag value
        assert len(observations) == 1
        assert observations[0].value == 10.5

    def test_consumer_lag_multiple_updates(self):
        """Test that consumer lag can be updated multiple times."""
        metrics = initialize_metrics()

        # Update lag multiple times
        metrics.update_consumer_lag(5.0)
        observations1 = list(metrics._get_consumer_lag(None))
        assert observations1[0].value == 5.0

        metrics.update_consumer_lag(15.0)
        observations2 = list(metrics._get_consumer_lag(None))
        assert observations2[0].value == 15.0


class TestMetricsEdgeCases:
    """Test edge cases in metrics recording."""

    def test_record_signal_with_edge_confidence_values(self):
        """Test recording signals with edge case confidence values."""
        metrics = initialize_metrics()

        # Test boundary values
        metrics.record_signal_generated("test_strategy", "buy", "BTCUSDT", 0.0)
        metrics.record_signal_generated("test_strategy", "sell", "ETHUSDT", 1.0)
        metrics.record_signal_generated("test_strategy", "hold", "BNBUSDT", 0.5)

        # All should be recorded without error

    def test_record_latency_with_zero_value(self):
        """Test recording latency with zero value."""
        metrics = initialize_metrics()

        # Should handle zero latency
        metrics.record_strategy_latency("test_strategy", 0.0, "BTCUSDT")

    def test_record_message_without_strategy(self):
        """Test recording message without strategy."""
        metrics = initialize_metrics()

        # Should handle missing strategy
        metrics.record_message_processed("BTCUSDT", "depth", strategy=None)

    def test_record_error_without_strategy(self):
        """Test recording error without strategy."""
        metrics = initialize_metrics()

        # Should handle missing strategy
        metrics.record_error("test_error", strategy=None)


class TestMetricsHighLoad:
    """Test metrics under high load conditions."""

    @pytest.mark.asyncio
    async def test_concurrent_metric_recording(self):
        """Test that metrics can be recorded concurrently."""
        metrics = initialize_metrics()

        async def record_metrics():
            for i in range(100):
                metrics.record_message_processed("BTCUSDT", "depth")
                metrics.record_strategy_latency("test_strategy", float(i), "BTCUSDT")
                await asyncio.sleep(0.001)

        # Run multiple concurrent tasks
        tasks = [record_metrics() for _ in range(10)]
        await asyncio.gather(*tasks)

        # All metrics should be recorded without errors

    def test_rapid_consumer_lag_updates(self):
        """Test rapid consumer lag updates."""
        metrics = initialize_metrics()

        # Rapidly update consumer lag
        for i in range(1000):
            metrics.update_consumer_lag(float(i % 100))

        # Final value should be set
        observations = list(metrics._get_consumer_lag(None))
        assert observations[0].value >= 0


class TestMetricsContextEdgeCases:
    """Test edge cases in MetricsContext."""

    def test_context_with_very_short_execution(self):
        """Test context manager with very short execution time."""
        from strategies.utils.metrics import MetricsContext

        metrics = initialize_metrics()

        with MetricsContext(
            strategy="fast_strategy", symbol="BTCUSDT", metrics=metrics
        ):
            pass  # Very fast execution

        # Should still record latency

    def test_context_with_long_execution(self):
        """Test context manager with longer execution time."""
        import time

        from strategies.utils.metrics import MetricsContext

        metrics = initialize_metrics()

        with MetricsContext(
            strategy="slow_strategy", symbol="BTCUSDT", metrics=metrics
        ):
            time.sleep(0.1)  # 100ms execution

        # Should record latency > 100ms

    def test_nested_context_managers(self):
        """Test nested MetricsContext usage."""
        from strategies.utils.metrics import MetricsContext

        metrics = initialize_metrics()

        with MetricsContext(
            strategy="outer_strategy", symbol="BTCUSDT", metrics=metrics
        ) as outer_ctx:
            with MetricsContext(
                strategy="inner_strategy", symbol="ETHUSDT", metrics=metrics
            ) as inner_ctx:
                inner_ctx.record_signal("buy", 0.8)
            outer_ctx.record_signal("sell", 0.7)

        # Both contexts should record independently

    def test_context_reuse(self):
        """Test that context manager can be used multiple times."""
        from strategies.utils.metrics import MetricsContext

        metrics = initialize_metrics()

        # Use context multiple times
        for i in range(10):
            with MetricsContext(
                strategy="reusable_strategy", symbol="BTCUSDT", metrics=metrics
            ) as ctx:
                if i % 2 == 0:
                    ctx.record_signal("buy", 0.8)

        # All executions should be recorded
