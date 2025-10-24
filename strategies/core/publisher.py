"""
Trade Order Publisher for sending orders to TradeEngine.

This module handles publishing trade orders to NATS for consumption by the TradeEngine service.
"""

import asyncio
import json
import time
from typing import Any, Dict, Optional
import structlog

import nats
from nats.aio.client import Client as NATSClient

import constants
from strategies.models.orders import TradeOrder, OrderResponse
from strategies.utils.circuit_breaker import CircuitBreaker


class TradeOrderPublisher:
    """Publisher for trade orders to be sent to TradeEngine."""

    def __init__(
        self,
        nats_url: str,
        topic: str,
        logger: Optional[structlog.BoundLogger] = None,
    ):
        """Initialize the trade order publisher."""
        self.nats_url = nats_url
        self.topic = topic
        self.logger = logger or structlog.get_logger()

        # NATS client
        self.nats_client: Optional[NATSClient] = None

        # Circuit breaker for NATS connection
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=constants.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            recovery_timeout=constants.CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
            expected_exception=Exception,
        )

        # Publishing state
        self.is_running = False
        self.shutdown_event = asyncio.Event()
        self.order_count = 0
        self.error_count = 0
        self.last_order_time = None

        # Performance metrics
        self.publishing_times = []
        self.max_publishing_time = 0.0
        self.avg_publishing_time = 0.0

        # Order queue for batching
        self.order_queue = asyncio.Queue(maxsize=1000)
        self.batch_size = constants.BATCH_SIZE
        self.batch_timeout = constants.BATCH_TIMEOUT

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

            # Start publishing loop as background task
            self.is_running = True
            asyncio.create_task(self._publishing_loop())
            
            # Return immediately after starting the background task
            self.logger.info("Trade order publisher started", event="publisher_started", topic=self.topic)

        except Exception as e:
            self.logger.error("Failed to start trade order publisher", error=str(e))
            raise

    async def stop(self) -> None:
        """Stop the trade order publisher gracefully."""
        self.logger.info("Stopping trade order publisher", event="publisher_stopping", order_count=self.order_count, error_count=self.error_count)

        # Signal shutdown
        self.shutdown_event.set()
        self.is_running = False

        # Close NATS connection
        if self.nats_client:
            try:
                await self.nats_client.close()
                self.logger.info("NATS connection closed", event="nats_disconnected", nats_url=self.nats_url)
            except Exception as e:
                self.logger.warning("Error closing NATS connection", event="nats_disconnect_error", error=str(e))

        self.logger.info("Trade order publisher stopped", event="publisher_stopped", total_orders=self.order_count, total_errors=self.error_count)

    async def _connect_to_nats(self) -> None:
        """Connect to NATS server."""
        try:
            self.nats_client = nats.NATS()
            await self.nats_client.connect(
                self.nats_url,
                name="trade-order-publisher",
                reconnect_time_wait=1,
                max_reconnect_attempts=10,
                connect_timeout=10,
            )
            self.logger.info("Connected to NATS server", event="nats_connected", nats_url=self.nats_url, client_name="trade-order-publisher")

        except Exception as e:
            self.logger.error("Failed to connect to NATS", error=str(e))
            raise

    async def _publishing_loop(self) -> None:
        """Main publishing loop for sending orders."""
        self.logger.info("Starting order publishing loop", event="publishing_loop_started", batch_size=self.batch_size, batch_timeout=self.batch_timeout)

        while self.is_running and not self.shutdown_event.is_set():
            try:
                # Collect orders for batching
                orders = []
                start_time = time.time()

                # Collect orders until batch is full or timeout
                while len(orders) < self.batch_size and (time.time() - start_time) < self.batch_timeout:
                    try:
                        # Try to get order from queue with timeout
                        order = await asyncio.wait_for(
                            self.order_queue.get(),
                            timeout=0.1
                        )
                        orders.append(order)
                    except asyncio.TimeoutError:
                        # No orders available, continue
                        break

                if orders:
                    # Publish orders in batch
                    await self._publish_orders_batch(orders)

                # Small delay to prevent busy waiting
                await asyncio.sleep(0.001)

            except Exception as e:
                self.logger.error("Error in publishing loop", error=str(e))
                self.error_count += 1
                await asyncio.sleep(1)  # Back off on error

        self.logger.info("Order publishing loop stopped")

    async def _publish_orders_batch(self, orders: list[TradeOrder]) -> None:
        """Publish a batch of orders."""
        start_time = time.time()
        publishing_time = 0.0

        try:
            # Convert orders to JSON
            order_messages = []
            for order in orders:
                order_dict = order.to_dict()
                order_messages.append(json.dumps(order_dict))

            # Publish messages to NATS
            for order_message in order_messages:
                await self.nats_client.publish(
                    subject=self.topic,
                    payload=order_message.encode(),
                )

            # Update metrics
            self.order_count += len(orders)
            self.last_order_time = time.time()
            publishing_time = (time.time() - start_time) * 1000  # Convert to milliseconds

            # Update publishing time metrics
            self._update_publishing_metrics(publishing_time)

            self.logger.info(
                "Published orders batch",
                order_count=len(orders),
                total_orders=self.order_count,
                publishing_time_ms=publishing_time,
            )

        except Exception as e:
            self.logger.error(
                "Error publishing orders batch",
                error=str(e),
                order_count=len(orders),
            )
            self.error_count += 1

    async def publish_order(self, order: TradeOrder) -> OrderResponse:
        """Publish a single trade order."""
        start_time = time.time()
        publishing_time = 0.0

        try:
            # Add order to queue
            await self.order_queue.put(order)

            # Wait for order to be processed (with timeout)
            publishing_time = (time.time() - start_time) * 1000

            # Create success response
            response = OrderResponse(
                order_id=order.order_id,
                status="submitted",
                message="Order submitted successfully",
                metadata={
                    "publishing_time_ms": publishing_time,
                    "queue_size": self.order_queue.qsize(),
                }
            )

            self.logger.info(
                "Order submitted for publishing",
                order_id=order.order_id,
                symbol=order.symbol,
                side=order.side.value,
                order_type=order.order_type.value,
                publishing_time_ms=publishing_time,
            )

            return response

        except Exception as e:
            self.logger.error(
                "Error submitting order for publishing",
                error=str(e),
                order_id=order.order_id,
            )
            self.error_count += 1

            # Create error response
            return OrderResponse(
                order_id=order.order_id,
                status="error",
                message=f"Failed to submit order: {str(e)}",
                metadata={
                    "publishing_time_ms": publishing_time,
                    "error": str(e),
                }
            )

    async def publish_order_sync(self, order: TradeOrder) -> OrderResponse:
        """Publish a single trade order synchronously (immediate publish)."""
        start_time = time.time()
        publishing_time = 0.0

        try:
            # Convert order to JSON
            order_dict = order.to_dict()
            order_message = json.dumps(order_dict)

            # Publish message to NATS
            await self.nats_client.publish(
                subject=self.topic,
                payload=order_message.encode(),
            )

            # Update metrics
            self.order_count += 1
            self.last_order_time = time.time()
            publishing_time = (time.time() - start_time) * 1000

            # Update publishing time metrics
            self._update_publishing_metrics(publishing_time)

            # Create success response
            response = OrderResponse(
                order_id=order.order_id,
                status="published",
                message="Order published successfully",
                metadata={
                    "publishing_time_ms": publishing_time,
                    "published_at": self.last_order_time,
                }
            )

            self.logger.info(
                "Order published successfully",
                order_id=order.order_id,
                symbol=order.symbol,
                side=order.side.value,
                order_type=order.order_type.value,
                publishing_time_ms=publishing_time,
            )

            return response

        except Exception as e:
            self.logger.error(
                "Error publishing order",
                error=str(e),
                order_id=order.order_id,
            )
            self.error_count += 1

            # Create error response
            return OrderResponse(
                order_id=order.order_id,
                status="error",
                message=f"Failed to publish order: {str(e)}",
                metadata={
                    "publishing_time_ms": publishing_time,
                    "error": str(e),
                }
            )

    def _update_publishing_metrics(self, publishing_time: float) -> None:
        """Update publishing time metrics."""
        self.publishing_times.append(publishing_time)
        
        # Keep only last 1000 publishing times
        if len(self.publishing_times) > 1000:
            self.publishing_times = self.publishing_times[-1000:]

        # Update max publishing time
        if publishing_time > self.max_publishing_time:
            self.max_publishing_time = publishing_time

        # Update average publishing time
        self.avg_publishing_time = sum(self.publishing_times) / len(self.publishing_times)

    def get_metrics(self) -> Dict[str, Any]:
        """Get publisher metrics."""
        return {
            "order_count": self.order_count,
            "error_count": self.error_count,
            "is_running": self.is_running,
            "last_order_time": self.last_order_time,
            "max_publishing_time_ms": self.max_publishing_time,
            "avg_publishing_time_ms": self.avg_publishing_time,
            "publishing_times_count": len(self.publishing_times),
            "queue_size": self.order_queue.qsize(),
            "circuit_breaker_state": self.circuit_breaker.state.value,
        }

    def get_health_status(self) -> Dict[str, Any]:
        """Get health status for the publisher."""
        is_healthy = (
            self.is_running and
            self.nats_client and
            self.nats_client.is_connected and
            self.error_count < 100  # Allow some errors
        )

        return {
            "healthy": is_healthy,
            "is_running": self.is_running,
            "nats_connected": self.nats_client.is_connected if self.nats_client else False,
            "order_count": self.order_count,
            "error_count": self.error_count,
            "last_order_time": self.last_order_time,
            "queue_size": self.order_queue.qsize(),
        }

    async def get_queue_status(self) -> Dict[str, Any]:
        """Get queue status information."""
        return {
            "queue_size": self.order_queue.qsize(),
            "queue_maxsize": self.order_queue.maxsize,
            "queue_full": self.order_queue.full(),
            "queue_empty": self.order_queue.empty(),
        }
