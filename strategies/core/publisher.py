"""
Trade Order Publisher for sending orders to TradeEngine.

This module handles publishing trade orders to NATS for consumption by the TradeEngine service.
"""

import asyncio
import json
import time
from typing import Any, Optional

import nats
import structlog
from nats.aio.client import Client as NATSClient

# Conditional import for CI compatibility
try:
    from petrosa_otel import inject_trace_context
except ImportError:
    # Fallback for CI environments without petrosa_otel
    def inject_trace_context(data):
        return data


import constants
from strategies.adapters.signal_adapter import transform_signal_for_tradeengine
from strategies.utils.error_window import WindowedErrorTracker
from strategies.utils.metrics import initialize_metrics
from strategies.utils.nats_reconnect import (
    DEFAULT_MAX_RECONNECT_WAIT,
    jittered_reconnect_delay,
    make_reconnect_handler,
)
from strategies.utils.rolling_stats import RollingStats


class TradeOrderPublisher:
    """Publisher for trade orders to be sent to TradeEngine."""

    def __init__(
        self,
        nats_url: str,
        topic: str,
        logger: structlog.BoundLogger | None = None,
    ):
        """Initialize the trade order publisher."""
        self.nats_url = nats_url
        self.topic = topic
        self.logger = logger or structlog.get_logger()
        self.metrics = initialize_metrics()

        # NATS client
        self.nats_client: NATSClient | None = None
        self._nats_recovery_task: asyncio.Task | None = None

        # Publishing state
        self.is_running = False
        self.shutdown_event = asyncio.Event()
        self.order_count = 0
        self.signal_count = 0
        self.error_count = 0
        self.error_tracker = WindowedErrorTracker()
        self.last_order_time = None

        # Performance metrics.
        # Per #191 AC1/AC3: fixed-size ring buffer with O(1) running sum and
        # a true windowed max (not a lifetime high-water mark).
        self.publishing_times = RollingStats(maxlen=1000)

    async def start(self) -> None:
        """Start the trade order publisher."""
        self.logger.info(
            "Starting trade order publisher",
            nats_url=self.nats_url,
            topic=self.topic,
        )

        try:
            # Connect to NATS
            await self._connect_to_nats()

            self.is_running = True

            # Return immediately after connecting
            self.logger.info(
                "Trade order publisher started",
                event_type="publisher_started",
                topic=self.topic,
            )

        except Exception as e:
            self.logger.error("Failed to start trade order publisher", error=str(e))
            raise

    async def stop(self) -> None:
        """Stop the trade order publisher gracefully."""
        self.logger.info(
            "Stopping trade order publisher",
            event_type="publisher_stopping",
            order_count=self.order_count,
            error_count=self.error_count,
        )

        # Signal shutdown
        self.shutdown_event.set()
        self.is_running = False

        if self._nats_recovery_task is not None:
            self._nats_recovery_task.cancel()
            await asyncio.gather(self._nats_recovery_task, return_exceptions=True)
            self._nats_recovery_task = None

        # Close NATS connection
        if self.nats_client:
            try:
                await self.nats_client.close()
                self.logger.info(
                    "NATS connection closed",
                    event_type="nats_disconnected",
                    nats_url=self.nats_url,
                )
            except Exception as e:
                self.logger.warning(
                    "Error closing NATS connection",
                    event_type="nats_disconnect_error",
                    error=str(e),
                )

        self.logger.info(
            "Trade order publisher stopped",
            event_type="publisher_stopped",
            total_orders=self.order_count,
            total_errors=self.error_count,
        )

    async def _connect_to_nats(self) -> None:
        """Connect to NATS server."""
        try:
            self.nats_client = nats.NATS()
            await self.nats_client.connect(
                self.nats_url,
                name="trade-order-publisher",
                reconnect_time_wait=2,
                max_reconnect_attempts=-1,  # unlimited: never give up permanently
                connect_timeout=10,
                reconnect_to_server_handler=make_reconnect_handler(),
                error_cb=self._on_nats_error,
                disconnected_cb=self._on_nats_disconnected,
                reconnected_cb=self._on_nats_reconnected,
                closed_cb=self._on_nats_closed,
            )
            self.logger.info(
                "Connected to NATS server",
                event_type="nats_connected",
                nats_url=self.nats_url,
                client_name="trade-order-publisher",
            )

        except Exception as e:
            self.logger.error("Failed to connect to NATS", error=str(e))
            raise

    async def _on_nats_error(self, exception: Exception) -> None:
        """Handle NATS client errors (e.g. slow-consumer drops, protocol errors)."""
        self.logger.warning(
            "NATS client error",
            event_type="nats_error",
            error=str(exception),
            client_name="trade-order-publisher",
        )
        self.metrics.record_error("nats_error")

    async def _on_nats_disconnected(self) -> None:
        """Handle NATS disconnection (client will keep retrying indefinitely)."""
        self.logger.warning(
            "NATS client disconnected",
            event_type="nats_disconnected",
            nats_url=self.nats_url,
            client_name="trade-order-publisher",
        )
        self.metrics.record_error("nats_disconnected")

    async def _on_nats_reconnected(self) -> None:
        """Handle successful NATS reconnection after an outage."""
        self.logger.warning(
            "NATS client reconnected",
            event_type="nats_reconnected",
            nats_url=self.nats_url,
            client_name="trade-order-publisher",
        )
        self.metrics.record_error("nats_reconnected")

    async def _on_nats_closed(self) -> None:
        """Handle NATS connection being permanently closed."""
        self.logger.warning(
            "NATS connection closed permanently",
            event_type="nats_closed",
            nats_url=self.nats_url,
            client_name="trade-order-publisher",
        )
        self.metrics.record_error("nats_closed")
        if self.is_running and not self.shutdown_event.is_set():
            self._schedule_nats_recovery()

    def _schedule_nats_recovery(self) -> None:
        """Schedule recovery after nats-py reaches its terminal closed state."""
        if self._nats_recovery_task is None or self._nats_recovery_task.done():
            self._nats_recovery_task = asyncio.create_task(
                self._recover_nats_connection()
            )

    async def _recover_nats_connection(self) -> None:
        """Replace a terminal NATS client and restore publishing."""
        delay = 2.0
        while self.is_running and not self.shutdown_event.is_set():
            await asyncio.sleep(
                jittered_reconnect_delay(
                    base_seconds=delay,
                    max_seconds=DEFAULT_MAX_RECONNECT_WAIT,
                )
            )
            try:
                await self._connect_to_nats()
                self.logger.info(
                    "Recovered NATS publisher after terminal close",
                    event_type="nats_recovery_succeeded",
                    nats_url=self.nats_url,
                )
                return
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.metrics.record_error("nats_recovery_error")
                self.logger.warning(
                    "NATS publisher recovery attempt failed",
                    event_type="nats_recovery_failed",
                    error=str(e),
                    retry_delay_seconds=delay,
                    nats_url=self.nats_url,
                )
                delay = min(delay * 2, DEFAULT_MAX_RECONNECT_WAIT)

    @property
    def nats_connected(self) -> bool:
        """True connection-state, synchronously readable (no await required).

        Reflects the underlying ``nats_client.is_connected`` value so the
        health server (and any other caller) can poll live connection state
        without needing to await a coroutine.
        """
        return bool(self.nats_client and self.nats_client.is_connected)

    async def publish_signal(self, signal: Any) -> None:
        """Publish a trading signal to NATS.

        Args:
            signal: Trading signal object (Signal or StrategySignal model)

        Raises:
            Exception: If publishing fails
        """
        start_time = time.time()

        try:
            # Transform signal to tradeengine contract format
            signal_dict = transform_signal_for_tradeengine(signal)

            # Inject trace context into signal for distributed tracing
            signal_dict_with_trace = inject_trace_context(signal_dict)
            signal_message = json.dumps(signal_dict_with_trace)

            # Use standardized subject: {NATS_TOPIC_INTENTS}.{strategy_id}
            strategy_id = signal_dict.get("strategy_id", "unknown")
            # Normalize strategy_id for NATS subject
            normalized_strategy_id = strategy_id.replace(" ", "_").replace(".", "_")
            subject = f"{constants.NATS_TOPIC_INTENTS}.{normalized_strategy_id}"

            # Publish message to NATS
            await self.nats_client.publish(
                subject=subject,
                payload=signal_message.encode(),
            )

            # Update metrics
            self.signal_count += 1
            self.last_order_time = time.time()
            publishing_time = (time.time() - start_time) * 1000

            # Update publishing time metrics
            self._update_publishing_metrics(publishing_time)

            self.logger.info(
                "Signal published successfully",
                symbol=signal_dict.get("symbol"),
                action=signal_dict.get("action"),
                confidence=signal_dict.get("confidence"),
                strategy=signal_dict.get("strategy"),
                strategy_id=signal_dict.get("strategy_id"),
                publishing_time_ms=publishing_time,
                signal_count=self.signal_count,
                topic=subject,
            )

        except Exception as e:
            self.logger.error(
                "Error publishing signal",
                error=str(e),
                symbol=(
                    signal_dict.get("symbol")
                    if "signal_dict" in locals()
                    else "unknown"
                ),
            )
            self.error_count += 1
            self.error_tracker.record_error()
            raise

    def _update_publishing_metrics(self, publishing_time: float) -> None:
        """Update publishing time metrics.

        Per #191 AC1: O(1) amortized -- no list slice-rebuild, no `sum()`
        over the window. See `strategies/utils/rolling_stats.py`.
        """
        self.publishing_times.add(publishing_time)

    @property
    def max_publishing_time(self) -> float:
        """Windowed max publishing time (per #191 AC3 -- decays, not lifetime)."""
        return self.publishing_times.windowed_max

    @property
    def avg_publishing_time(self) -> float:
        """Average publishing time over the current window."""
        return self.publishing_times.average

    def get_metrics(self) -> dict[str, Any]:
        """Get publisher metrics."""
        return {
            "order_count": self.order_count,
            "signal_count": self.signal_count,
            "error_count": self.error_count,
            "is_running": self.is_running,
            "last_order_time": self.last_order_time,
            "max_publishing_time_ms": self.max_publishing_time,
            "avg_publishing_time_ms": self.avg_publishing_time,
            "publishing_times_count": self.publishing_times.count,
        }

    def get_health_status(self) -> dict[str, Any]:
        """Get health status for the publisher."""
        is_healthy = (
            self.is_running
            and self.nats_connected
            and self.error_tracker.is_within_threshold
        )

        return {
            "healthy": is_healthy,
            "is_running": self.is_running,
            "nats_connected": self.nats_connected,
            "order_count": self.order_count,
            "error_count": self.error_count,
            "recent_error_count": self.error_tracker.count_in_window,
            "last_order_time": self.last_order_time,
        }
