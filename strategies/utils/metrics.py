"""
Custom business metrics for realtime strategies monitoring.

This module provides OpenTelemetry-based metrics for monitoring:
- Message processing rates
- Strategy execution latency
- Signal generation
- Consumer lag
"""

import time
from collections import defaultdict
from statistics import quantiles

from opentelemetry import metrics

# Import get_meter from petrosa_otel package
try:
    from petrosa_otel import get_meter
except ImportError:
    # Fallback if petrosa_otel not available
    def get_meter(name: str) -> metrics.Meter:
        return metrics.get_meter(name)


class RealtimeStrategyMetrics:
    """
    OpenTelemetry metrics for realtime strategies.

    Provides counters, histograms, and gauges for monitoring strategy performance.
    """

    def __init__(self, meter_name: str = "petrosa.realtime.strategies"):
        """
        Initialize metrics.

        Args:
            meter_name: Name for the OpenTelemetry meter
        """
        self.meter = get_meter(meter_name)

        self.messages_total = self.meter.create_counter(
            name="petrosa_realtime_messages_total",
            description="Realtime messages by bounded stream and outcome",
            unit="1",
        )
        self.lag_seconds = self.meter.create_histogram(
            name="petrosa_realtime_lag_seconds",
            description="Realtime message lag in seconds by bounded stream",
            unit="s",
        )
        # Compatibility handles for callers from the pre-catalog API.  They all
        # point at one of the two bounded instruments above.
        self.messages_processed = self.messages_total
        self.message_latency = self.lag_seconds
        self.consumer_lag = self.lag_seconds
        self.strategy_latency = self.lag_seconds
        self.signals_generated = self.messages_total
        self.errors_total = self.messages_total
        self.message_types = self.messages_total
        self.strategy_executions = self.messages_total
        self.config_changes = self.messages_total
        self.market_metrics_processed = self.messages_total
        self._consumer_lag_value = 0.0
        self._counts: defaultdict[tuple[str, str], int] = defaultdict(int)
        self._latencies: defaultdict[str, list[float]] = defaultdict(list)
        self._last_summary = time.monotonic()

    _STREAMS = frozenset({"depth", "trade", "ticker", "mark_price", "unknown"})
    _OUTCOMES = frozenset({"processed", "invalid", "error", "skipped"})

    @classmethod
    def _stream(cls, value: str | None) -> str:
        value = str(value or "unknown").lower()
        return value if value in cls._STREAMS else "unknown"

    @classmethod
    def _outcome(cls, value: str) -> str:
        value = str(value).lower()
        return value if value in cls._OUTCOMES else "error"

    def _count(self, stream: str | None, outcome: str) -> None:
        bounded_stream = self._stream(stream)
        bounded_outcome = self._outcome(outcome)
        self.messages_total.add(
            1, attributes={"stream": bounded_stream, "outcome": bounded_outcome}
        )
        self._counts[(bounded_stream, bounded_outcome)] += 1

    def _get_consumer_lag(self, options: metrics.CallbackOptions):
        """Compatibility callback for health consumers of the old gauge."""
        yield metrics.Observation(self._consumer_lag_value)

    def record_message_processed(
        self, symbol: str, message_type: str, strategy: str | None = None
    ):
        """
        Record a processed message.

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            message_type: Type of message ("depth", "trade", "ticker")
            strategy: Strategy name (optional)
        """
        self._count(message_type, "processed")

    def record_message_type(self, message_type: str):
        """
        Record message type received.

        Args:
            message_type: Type of message ("depth", "trade", "ticker")
        """
        # Stream classification is folded into the processed event so one
        # incoming message contributes exactly once to the catalog counter.
        return None

    def record_message_latency(self, latency_ms: float, message_type: str):
        """
        Record NATS message processing latency.

        Args:
            latency_ms: Latency in milliseconds
            message_type: Type of message ("depth", "trade", "ticker")
        """
        stream = self._stream(message_type)
        self.lag_seconds.record(
            max(0.0, latency_ms / 1000), attributes={"stream": stream}
        )
        self._latencies[stream].append(max(0.0, latency_ms / 1000))

    def record_strategy_latency(
        self, strategy: str, latency_ms: float, symbol: str | None = None
    ):
        """
        Record strategy execution latency.

        Args:
            strategy: Strategy name
            latency_ms: Latency in milliseconds
            symbol: Trading symbol (optional)
        """
        self.record_message_latency(latency_ms, "unknown")

    def record_strategy_execution(self, strategy: str, result: str, symbol: str):
        """
        Record strategy execution result.

        Args:
            strategy: Strategy name
            result: Execution result ("success", "failure", "no_signal")
            symbol: Trading symbol
        """
        self._count("unknown", "processed" if result == "success" else "skipped")

    def record_signal_generated(
        self,
        strategy: str,
        signal_type: str,
        symbol: str,
        confidence: float,
        action: str | None = None,
    ):
        """
        Record a generated signal.

        Args:
            strategy: Strategy name
            signal_type: Signal type ("buy", "sell", "hold")
            symbol: Trading symbol
            confidence: Signal confidence (0.0-1.0)
            action: Specific action (optional)
        """
        self._count("unknown", "processed")

    def record_config_change(self, strategy_id: str, symbol: str | None, action: str):
        """
        Record a configuration change.

        Args:
            strategy_id: Strategy identifier
            symbol: Trading symbol (optional)
            action: Action type ("CREATE", "UPDATE", "DELETE", "ROLLBACK")
        """
        self._count("unknown", "processed")

    def record_market_metrics_processed(self, symbol: str, metric_type: str = "depth"):
        """
        Record market metrics calculation.

        Args:
            symbol: Trading symbol
            metric_type: Type of metric ("depth", "pressure", etc.)
        """
        self._count(metric_type, "processed")

    def record_error(self, error_type: str, strategy: str | None = None):
        """
        Record an error.

        Args:
            error_type: Type of error
            strategy: Strategy name (optional)
        """
        self._count("unknown", "error")

    def update_consumer_lag(self, lag_seconds: float):
        """
        Update consumer lag value.

        Args:
            lag_seconds: Consumer lag in seconds
        """
        self._consumer_lag_value = lag_seconds
        self.lag_seconds.record(max(0.0, lag_seconds), attributes={"stream": "unknown"})

    def summary(self, window_seconds: int = 300) -> dict:
        """Return the bounded structured summary used by the periodic log."""
        latencies = [value for values in self._latencies.values() for value in values]
        if latencies:
            ordered = sorted(latencies)
            p50 = ordered[len(ordered) // 2]
            p95 = (
                quantiles(ordered, n=20, method="inclusive")[18]
                if len(ordered) > 1
                else p50
            )
        else:
            p50 = p95 = 0.0
        return {
            "event": "SUMMARY",
            "window_seconds": window_seconds,
            "service": "petrosa-realtime-strategies",
            "messages": {
                f"{stream}:{outcome}": count
                for (stream, outcome), count in sorted(self._counts.items())
            },
            "outcomes": {
                outcome: sum(
                    count
                    for (stream, item), count in self._counts.items()
                    if item == outcome
                )
                for outcome in sorted(self._OUTCOMES)
            },
            "latency_seconds_p50": round(p50, 6),
            "latency_seconds_p95": round(p95, 6),
        }

    @staticmethod
    def _get_confidence_bucket(confidence: float) -> str:
        """
        Get confidence bucket for grouping signals.

        Args:
            confidence: Signal confidence (0.0-1.0)

        Returns:
            Confidence bucket label
        """
        if confidence >= 0.9:
            return "very_high"
        elif confidence >= 0.75:
            return "high"
        elif confidence >= 0.5:
            return "medium"
        else:
            return "low"


# Global metrics instance (initialized by consumer)
_metrics: RealtimeStrategyMetrics | None = None


def initialize_metrics() -> RealtimeStrategyMetrics:
    """
    Initialize global metrics instance.

    Returns:
        Metrics instance
    """
    global _metrics
    if _metrics is None:
        _metrics = RealtimeStrategyMetrics()
    return _metrics


def get_metrics() -> RealtimeStrategyMetrics | None:
    """
    Get global metrics instance.

    Returns:
        Metrics instance or None if not initialized
    """
    return _metrics


class MetricsContext:
    """
    Context manager for timing strategy execution.

    Example:
        with MetricsContext(strategy="orderbook_skew", symbol="BTCUSDT") as ctx:
            # Process strategy
            signal = process_orderbook_skew(data)

            # Record signal if generated
            if signal:
                ctx.record_signal(
                    signal.signal_type.value,
                    signal.confidence_score,
                    signal.signal_action.value
                )
    """

    def __init__(
        self,
        strategy: str,
        symbol: str,
        metrics: RealtimeStrategyMetrics | None = None,
    ):
        """
        Initialize metrics context.

        Args:
            strategy: Strategy name
            symbol: Trading symbol
            metrics: Metrics instance (uses global if not provided)
        """
        self.strategy = strategy
        self.symbol = symbol
        self.metrics = metrics or get_metrics()
        self.start_time: float | None = None
        self.signal_recorded = False

    def __enter__(self):
        """Start timing."""
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Record latency and execution result."""
        if self.metrics and self.start_time:
            latency_ms = (time.time() - self.start_time) * 1000

            # Record latency
            self.metrics.record_strategy_latency(self.strategy, latency_ms, self.symbol)

            # Record execution result
            if exc_type:
                self.metrics.record_strategy_execution(
                    self.strategy, "failure", self.symbol
                )
                self.metrics.record_error("strategy_execution", self.strategy)
            elif self.signal_recorded:
                self.metrics.record_strategy_execution(
                    self.strategy, "success", self.symbol
                )
            else:
                self.metrics.record_strategy_execution(
                    self.strategy, "no_signal", self.symbol
                )

        # Don't suppress exceptions
        return False

    def record_signal(
        self, signal_type: str, confidence: float, action: str | None = None
    ):
        """
        Record signal generation.

        Args:
            signal_type: Signal type ("buy", "sell", "hold")
            confidence: Signal confidence (0.0-1.0)
            action: Specific action (optional)
        """
        if self.metrics:
            self.metrics.record_signal_generated(
                self.strategy, signal_type, self.symbol, confidence, action
            )
            self.signal_recorded = True
