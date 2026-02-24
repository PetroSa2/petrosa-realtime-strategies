"""
Heartbeat manager for periodic statistics logging.

This module provides a heartbeat system that periodically logs statistics
about message processing performance and system health.
"""

import asyncio
import time
from typing import Any, Optional

import structlog

import constants


class HeartbeatManager:
    """Manages periodic heartbeat logging with system statistics."""

    def __init__(
        self,
        consumer=None,
        publisher=None,
        logger: structlog.BoundLogger | None = None,
        enabled: bool = None,
        interval_seconds: int = None,
        include_detailed_stats: bool = None,
    ):
        """Initialize the heartbeat manager."""
        self.consumer = consumer
        self.publisher = publisher
        self.logger = logger or structlog.get_logger()

        # Configuration
        self.enabled = enabled if enabled is not None else constants.HEARTBEAT_ENABLED
        self.interval_seconds = (
            interval_seconds
            if interval_seconds is not None
            else constants.HEARTBEAT_INTERVAL_SECONDS
        )
        self.include_detailed_stats = (
            include_detailed_stats
            if include_detailed_stats is not None
            else constants.HEARTBEAT_INCLUDE_DETAILED_STATS
        )

        # State
        self.is_running = False
        self.shutdown_event = asyncio.Event()
        self.heartbeat_count = 0
        self.start_time = time.time()

        # Previous stats for calculating deltas
        self.previous_stats = {
            "consumer_messages": 0,
            "consumer_errors": 0,
            "publisher_orders": 0,
            "publisher_errors": 0,
        }

        self.logger.info(
            "Heartbeat manager initialized",
            enabled=self.enabled,
            interval_seconds=self.interval_seconds,
            include_detailed_stats=self.include_detailed_stats,
        )

    async def start(self) -> None:
        """Start the heartbeat manager."""
        if not self.enabled:
            self.logger.info("Heartbeat is disabled, skipping start")
            return

        self.logger.info("Starting heartbeat manager")
        self.is_running = True
        self.start_time = time.time()

        # Start heartbeat loop as background task
        asyncio.create_task(self._heartbeat_loop())

        self.logger.info("Heartbeat manager started successfully")

    async def stop(self) -> None:
        """Stop the heartbeat manager gracefully."""
        if not self.enabled or not self.is_running:
            return

        self.logger.info("Stopping heartbeat manager")

        # Signal shutdown
        self.shutdown_event.set()
        self.is_running = False

        self.logger.info("Heartbeat manager stopped")

    async def _heartbeat_loop(self) -> None:
        """Main heartbeat loop that logs statistics periodically."""
        self.logger.info("Starting heartbeat loop")

        while self.is_running and not self.shutdown_event.is_set():
            try:
                # Wait for next heartbeat interval
                await asyncio.sleep(self.interval_seconds)

                if not self.is_running:
                    break

                # Log heartbeat statistics
                await self._log_heartbeat()

                self.heartbeat_count += 1

            except Exception as e:
                self.logger.error("Error in heartbeat loop", error=str(e))
                # Continue the loop even on error
                await asyncio.sleep(1)

        self.logger.info("Heartbeat loop stopped")

    async def _log_heartbeat(self) -> None:
        """Log heartbeat statistics."""
        try:
            # Collect current statistics
            current_stats = self._collect_current_stats()

            # Calculate deltas since last heartbeat
            delta_stats = self._calculate_deltas(current_stats)

            # Calculate rates (per second)
            rate_stats = self._calculate_rates(delta_stats)

            # Calculate uptime
            uptime_seconds = time.time() - self.start_time
            uptime_minutes = uptime_seconds / 60
            uptime_hours = uptime_minutes / 60

            # Build heartbeat log entry
            heartbeat_data = {
                "heartbeat_count": self.heartbeat_count + 1,
                "uptime_seconds": round(uptime_seconds, 2),
                "uptime_minutes": round(uptime_minutes, 2),
                "uptime_hours": round(uptime_hours, 2),
                "interval_seconds": self.interval_seconds,
                # Delta stats (since last heartbeat)
                "messages_processed_delta": delta_stats["consumer_messages"],
                "consumer_errors_delta": delta_stats["consumer_errors"],
                "orders_published_delta": delta_stats["publisher_orders"],
                "publisher_errors_delta": delta_stats["publisher_errors"],
                # Rate stats (per second)
                "messages_per_second": rate_stats["messages_per_second"],
                "orders_per_second": rate_stats["orders_per_second"],
                "error_rate_per_second": rate_stats["error_rate_per_second"],
                # Total stats (since startup)
                "total_messages_processed": current_stats["consumer_messages"],
                "total_consumer_errors": current_stats["consumer_errors"],
                "total_orders_published": current_stats["publisher_orders"],
                "total_publisher_errors": current_stats["publisher_errors"],
            }

            # Add detailed stats if enabled
            if self.include_detailed_stats:
                detailed_stats = self._collect_detailed_stats()
                heartbeat_data.update(detailed_stats)

            # Log the heartbeat
            self.logger.info("💓 HEARTBEAT - System Statistics", **heartbeat_data)

            # Update previous stats for next delta calculation
            self.previous_stats = current_stats.copy()

        except Exception as e:
            self.logger.error("Error logging heartbeat", error=str(e))

    def _collect_current_stats(self) -> dict[str, Any]:
        """Collect current statistics from consumer and publisher."""
        stats = {
            "consumer_messages": 0,
            "consumer_errors": 0,
            "publisher_orders": 0,
            "publisher_errors": 0,
        }

        # Collect consumer stats
        if self.consumer:
            try:
                consumer_metrics = self.consumer.get_metrics()
                stats["consumer_messages"] = consumer_metrics.get("message_count", 0)
                stats["consumer_errors"] = consumer_metrics.get("error_count", 0)
            except Exception as e:
                self.logger.warning("Failed to get consumer metrics", error=str(e))

        # Collect publisher stats
        if self.publisher:
            try:
                publisher_metrics = self.publisher.get_metrics()
                stats["publisher_orders"] = publisher_metrics.get("order_count", 0)
                stats["publisher_errors"] = publisher_metrics.get("error_count", 0)
            except Exception as e:
                self.logger.warning("Failed to get publisher metrics", error=str(e))

        return stats

    def _calculate_deltas(self, current_stats: dict[str, Any]) -> dict[str, Any]:
        """Calculate deltas since last heartbeat."""
        return {
            "consumer_messages": current_stats["consumer_messages"]
            - self.previous_stats["consumer_messages"],
            "consumer_errors": current_stats["consumer_errors"]
            - self.previous_stats["consumer_errors"],
            "publisher_orders": current_stats["publisher_orders"]
            - self.previous_stats["publisher_orders"],
            "publisher_errors": current_stats["publisher_errors"]
            - self.previous_stats["publisher_errors"],
        }

    def _calculate_rates(self, delta_stats: dict[str, Any]) -> dict[str, Any]:
        """Calculate rates per second."""
        if self.interval_seconds <= 0:
            return {
                "messages_per_second": 0.0,
                "orders_per_second": 0.0,
                "error_rate_per_second": 0.0,
            }

        return {
            "messages_per_second": round(
                delta_stats["consumer_messages"] / self.interval_seconds, 2
            ),
            "orders_per_second": round(
                delta_stats["publisher_orders"] / self.interval_seconds, 2
            ),
            "error_rate_per_second": round(
                (delta_stats["consumer_errors"] + delta_stats["publisher_errors"])
                / self.interval_seconds,
                2,
            ),
        }

    def _collect_detailed_stats(self) -> dict[str, Any]:
        """Collect detailed statistics for comprehensive monitoring."""
        detailed = {}

        # Consumer detailed stats
        if self.consumer:
            try:
                consumer_metrics = self.consumer.get_metrics()
                consumer_health = self.consumer.get_health_status()

                detailed.update(
                    {
                        "consumer_is_running": consumer_metrics.get(
                            "is_running", False
                        ),
                        "consumer_is_healthy": consumer_health.get("healthy", False),
                        "consumer_nats_connected": consumer_health.get(
                            "nats_connected", False
                        ),
                        "consumer_subscription_active": consumer_health.get(
                            "subscription_active", False
                        ),
                        "consumer_last_message_time": consumer_metrics.get(
                            "last_message_time"
                        ),
                        "consumer_avg_processing_time_ms": round(
                            consumer_metrics.get("avg_processing_time_ms", 0), 2
                        ),
                        "consumer_max_processing_time_ms": round(
                            consumer_metrics.get("max_processing_time_ms", 0), 2
                        ),
                        "consumer_circuit_breaker_state": consumer_metrics.get(
                            "circuit_breaker_state", "unknown"
                        ),
                    }
                )
            except Exception as e:
                self.logger.warning(
                    "Failed to get detailed consumer stats", error=str(e)
                )

        # Publisher detailed stats
        if self.publisher:
            try:
                publisher_metrics = self.publisher.get_metrics()
                publisher_health = self.publisher.get_health_status()

                detailed.update(
                    {
                        "publisher_is_running": publisher_metrics.get(
                            "is_running", False
                        ),
                        "publisher_is_healthy": publisher_health.get("healthy", False),
                        "publisher_nats_connected": publisher_health.get(
                            "nats_connected", False
                        ),
                        "publisher_queue_size": publisher_metrics.get("queue_size", 0),
                        "publisher_last_order_time": publisher_metrics.get(
                            "last_order_time"
                        ),
                        "publisher_avg_publishing_time_ms": round(
                            publisher_metrics.get("avg_publishing_time_ms", 0), 2
                        ),
                        "publisher_max_publishing_time_ms": round(
                            publisher_metrics.get("max_publishing_time_ms", 0), 2
                        ),
                        "publisher_circuit_breaker_state": publisher_metrics.get(
                            "circuit_breaker_state", "unknown"
                        ),
                    }
                )
            except Exception as e:
                self.logger.warning(
                    "Failed to get detailed publisher stats", error=str(e)
                )

        return detailed

    def get_heartbeat_status(self) -> dict[str, Any]:
        """Get heartbeat manager status."""
        uptime_seconds = time.time() - self.start_time if self.start_time else 0

        return {
            "enabled": self.enabled,
            "is_running": self.is_running,
            "interval_seconds": self.interval_seconds,
            "heartbeat_count": self.heartbeat_count,
            "uptime_seconds": round(uptime_seconds, 2),
            "include_detailed_stats": self.include_detailed_stats,
        }

    def force_heartbeat(self) -> None:
        """Force an immediate heartbeat log (useful for testing)."""
        if not self.enabled:
            self.logger.warning("Cannot force heartbeat - heartbeat is disabled")
            return

        asyncio.create_task(self._log_heartbeat())
        self.logger.info("Forced heartbeat log requested")
