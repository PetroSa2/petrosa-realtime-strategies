"""
NATS Consumer for processing market data messages.

This module handles consuming messages from NATS streams and routing them
to the appropriate strategy processors.
"""

import asyncio
import json
import time
from typing import Any, Dict, Optional, Union
import structlog

import nats
from nats.aio.client import Client as NATSClient
from nats.aio.subscription import Subscription

import constants
from strategies.core.publisher import TradeOrderPublisher
from strategies.models.market_data import MarketDataMessage, DepthUpdate, TradeData, TickerData, DepthLevel
from strategies.utils.circuit_breaker import CircuitBreaker


class NATSConsumer:
    """NATS consumer for processing market data messages."""

    def __init__(
        self,
        nats_url: str,
        topic: str,
        consumer_name: str,
        consumer_group: str,
        publisher: TradeOrderPublisher,
        logger: Optional[structlog.BoundLogger] = None,
    ):
        """Initialize the NATS consumer."""
        self.nats_url = nats_url
        self.topic = topic
        self.consumer_name = consumer_name
        self.consumer_group = consumer_group
        self.publisher = publisher
        self.logger = logger or structlog.get_logger()

        # NATS client and subscription
        self.nats_client: Optional[NATSClient] = None
        self.subscription: Optional[Subscription] = None

        # Circuit breaker for NATS connection
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=constants.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            recovery_timeout=constants.CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
            expected_exception=Exception,
        )

        # Processing state
        self.is_running = False
        self.shutdown_event = asyncio.Event()
        self.message_count = 0
        self.error_count = 0
        self.last_message_time = None

        # Performance metrics
        self.processing_times = []
        self.max_processing_time = 0.0
        self.avg_processing_time = 0.0

    async def start(self) -> None:
        """Start the NATS consumer."""
        self.logger.info(
            "Starting NATS consumer",
            nats_url=self.nats_url,
            topic=self.topic,
            consumer_name=self.consumer_name,
        )

        try:
            # Connect to NATS
            await self._connect_to_nats()

            # Subscribe to topic
            await self._subscribe_to_topic()

            # Start processing loop as background task
            self.is_running = True
            asyncio.create_task(self._processing_loop())
            
            # Return immediately after starting the background task
            self.logger.info("NATS consumer started successfully")

        except Exception as e:
            self.logger.error("Failed to start NATS consumer", error=str(e))
            raise

    async def stop(self) -> None:
        """Stop the NATS consumer gracefully."""
        self.logger.info("Stopping NATS consumer")

        # Signal shutdown
        self.shutdown_event.set()
        self.is_running = False

        # Close subscription
        if self.subscription:
            await self.subscription.drain()
            self.logger.info("NATS subscription drained")

        # Close NATS connection
        if self.nats_client:
            try:
                await self.nats_client.close()
                self.logger.info("NATS connection closed")
            except Exception as e:
                self.logger.warning("Error closing NATS connection", error=str(e))

        self.logger.info("NATS consumer stopped")

    async def _connect_to_nats(self) -> None:
        """Connect to NATS server."""
        try:
            self.nats_client = nats.NATS()
            await self.nats_client.connect(
                self.nats_url,
                name=self.consumer_name,
                reconnect_time_wait=1,
                max_reconnect_attempts=10,
                connect_timeout=10,
            )
            self.logger.info("Connected to NATS server", url=self.nats_url)

        except Exception as e:
            self.logger.error("Failed to connect to NATS", error=str(e))
            raise

    async def _subscribe_to_topic(self) -> None:
        """Subscribe to the specified topic."""
        try:
            # Create subscription with callback
            self.subscription = await self.nats_client.subscribe(
                subject=self.topic,
                queue=self.consumer_group,
                cb=self._message_handler,
            )
            self.logger.info(
                "Subscribed to topic",
                topic=self.topic,
                consumer_name=self.consumer_name,
                consumer_group=self.consumer_group,
            )

        except Exception as e:
            self.logger.error("Failed to subscribe to topic", error=str(e))
            raise

    async def _message_handler(self, msg) -> None:
        """Handle incoming NATS messages."""
        try:
            await self._process_message(msg)
        except Exception as e:
            self.logger.error("Error in message handler", error=str(e))
            self.error_count += 1

    async def _processing_loop(self) -> None:
        """Main processing loop for consuming messages."""
        self.logger.info("Starting message processing loop")

        # For subscription-based approach, the processing is handled by callbacks
        # This loop just keeps the consumer alive
        while self.is_running and not self.shutdown_event.is_set():
            try:
                # Small delay to prevent busy waiting
                await asyncio.sleep(1)
            except Exception as e:
                self.logger.error("Error in processing loop", error=str(e))
                self.error_count += 1
                await asyncio.sleep(1)  # Back off on error

        self.logger.info("Message processing loop stopped")

    async def _process_message(self, msg) -> None:
        """Process a single NATS message."""
        start_time = time.time()
        processing_time = 0.0

        try:
            # Parse message data
            message_data = json.loads(msg.data.decode())
            self.logger.debug("Received message", data=message_data)

            # Validate and parse market data message
            market_data = self._parse_market_data(message_data)
            if not market_data:
                self.logger.warning("Invalid market data message", data=message_data)
                return

            # Process message through strategies
            await self._process_market_data(market_data)

            # Update metrics
            self.message_count += 1
            self.last_message_time = time.time()
            processing_time = (time.time() - start_time) * 1000  # Convert to milliseconds

            # Update processing time metrics
            self._update_processing_metrics(processing_time)

            self.logger.debug(
                "Message processed successfully",
                message_count=self.message_count,
                processing_time_ms=processing_time,
            )

        except Exception as e:
            self.logger.error(
                "Error processing message",
                error=str(e),
                message_data=message_data if 'message_data' in locals() else None,
            )
            self.error_count += 1

    def _parse_market_data(self, message_data: Dict[str, Any]) -> Optional[MarketDataMessage]:
        """Parse and validate market data message."""
        try:
            # Extract stream and data
            stream = message_data.get("stream")
            data = message_data.get("data")

            if not stream or not data:
                return None

            # Transform raw data based on stream type
            transformed_data = self._transform_binance_data(stream, data)
            if not transformed_data:
                return None

            # Create market data message
            market_data = MarketDataMessage(
                stream=stream,
                data=transformed_data,
            )

            return market_data

        except Exception as e:
            self.logger.error("Failed to parse market data", error=str(e))
            return None

    def _transform_binance_data(self, stream: str, data: Dict[str, Any]) -> Optional[Union[DepthUpdate, TradeData, TickerData]]:
        """Transform raw Binance WebSocket data to expected format."""
        try:
            stream_type = stream.split('@')[1] if '@' in stream else None
            self.logger.debug("Transforming data", stream_type=stream_type, data_keys=list(data.keys()))
            
            if 'depth' in stream_type:
                return self._transform_depth_data(data)
            elif 'trade' in stream_type:
                return self._transform_trade_data(data)
            elif 'ticker' in stream_type:
                return self._transform_ticker_data(data)
            else:
                self.logger.warning("Unknown stream type", stream_type=stream_type)
                return None

        except Exception as e:
            self.logger.error("Failed to transform Binance data", error=str(e), stream=stream, data=data)
            return None

    def _transform_depth_data(self, data: Dict[str, Any]) -> Optional[DepthUpdate]:
        """Transform depth data to DepthUpdate model."""
        try:
            # Extract symbol from the data if available, otherwise use a default
            symbol = data.get('s', 'BTCUSDT')  # Default fallback
            
            # Transform bids and asks from arrays to DepthLevel objects
            bids = []
            if 'bids' in data:
                for bid in data['bids']:
                    if len(bid) >= 2:
                        bids.append(DepthLevel(
                            price=bid[0],
                            quantity=bid[1]
                        ))

            asks = []
            if 'asks' in data:
                for ask in data['asks']:
                    if len(ask) >= 2:
                        asks.append(DepthLevel(
                            price=ask[0],
                            quantity=ask[1]
                        ))

            return DepthUpdate(
                symbol=symbol,
                event_time=data.get('E', int(time.time() * 1000)),
                first_update_id=data.get('U', 0),
                final_update_id=data.get('u', 0),
                bids=bids,
                asks=asks
            )

        except Exception as e:
            self.logger.error("Failed to transform depth data", error=str(e), data=data)
            return None

    def _transform_trade_data(self, data: Dict[str, Any]) -> Optional[TradeData]:
        """Transform trade data to TradeData model."""
        try:
            # Map Binance trade fields to our model
            # Binance fields: s=symbol, t=trade_id, p=price, q=quantity, T=trade_time, m=is_buyer_maker, E=event_time
            return TradeData(
                symbol=data.get('s', ''),
                trade_id=data.get('t', 0),
                price=data.get('p', '0'),
                quantity=data.get('q', '0'),
                buyer_order_id=data.get('b', 0),  # Not present in trade data, use 0
                seller_order_id=data.get('a', 0),  # Not present in trade data, use 0
                trade_time=data.get('T', 0),
                is_buyer_maker=data.get('m', False),
                event_time=data.get('E', 0)
            )

        except Exception as e:
            self.logger.error("Failed to transform trade data", error=str(e), data=data)
            return None

    def _transform_ticker_data(self, data: Dict[str, Any]) -> Optional[TickerData]:
        """Transform ticker data to TickerData model."""
        try:
            return TickerData(
                symbol=data.get('s', ''),
                price_change=data.get('P', '0'),
                price_change_percent=data.get('P', '0'),
                weighted_avg_price=data.get('w', '0'),
                prev_close_price=data.get('x', '0'),
                last_price=data.get('c', '0'),
                last_qty=data.get('Q', '0'),
                bid_price=data.get('b', '0'),
                bid_qty=data.get('B', '0'),
                ask_price=data.get('a', '0'),
                ask_qty=data.get('A', '0'),
                open_price=data.get('o', '0'),
                high_price=data.get('h', '0'),
                low_price=data.get('l', '0'),
                volume=data.get('v', '0'),
                quote_volume=data.get('q', '0'),
                open_time=data.get('O', 0),
                close_time=data.get('C', 0),
                first_id=data.get('F', 0),
                last_id=data.get('L', 0),
                count=data.get('n', 0),
                event_time=data.get('E', 0)
            )

        except Exception as e:
            self.logger.error("Failed to transform ticker data", error=str(e))
            return None

    async def _process_market_data(self, market_data: MarketDataMessage) -> None:
        """Process market data through strategies."""
        try:
            # Route to appropriate strategy based on stream type
            if market_data.is_depth:
                await self._process_depth_data(market_data)
            elif market_data.is_trade:
                await self._process_trade_data(market_data)
            elif market_data.is_ticker:
                await self._process_ticker_data(market_data)
            else:
                self.logger.warning("Unknown stream type", stream_type=market_data.stream_type)

        except Exception as e:
            self.logger.error("Error processing market data", error=str(e))

    async def _process_depth_data(self, market_data: MarketDataMessage) -> None:
        """Process depth (order book) data."""
        # This will be implemented by the strategy processor
        self.logger.debug("Processing depth data", symbol=market_data.symbol)

    async def _process_trade_data(self, market_data: MarketDataMessage) -> None:
        """Process trade data."""
        # This will be implemented by the strategy processor
        self.logger.debug("Processing trade data", symbol=market_data.symbol)

    async def _process_ticker_data(self, market_data: MarketDataMessage) -> None:
        """Process ticker data."""
        # This will be implemented by the strategy processor
        self.logger.debug("Processing ticker data", symbol=market_data.symbol)

    def _update_processing_metrics(self, processing_time: float) -> None:
        """Update processing time metrics."""
        self.processing_times.append(processing_time)
        
        # Keep only last 1000 processing times
        if len(self.processing_times) > 1000:
            self.processing_times = self.processing_times[-1000:]

        # Update max processing time
        if processing_time > self.max_processing_time:
            self.max_processing_time = processing_time

        # Update average processing time
        self.avg_processing_time = sum(self.processing_times) / len(self.processing_times)

    def get_metrics(self) -> Dict[str, Any]:
        """Get consumer metrics."""
        return {
            "message_count": self.message_count,
            "error_count": self.error_count,
            "is_running": self.is_running,
            "last_message_time": self.last_message_time,
            "max_processing_time_ms": self.max_processing_time,
            "avg_processing_time_ms": self.avg_processing_time,
            "processing_times_count": len(self.processing_times),
            "circuit_breaker_state": self.circuit_breaker.state.value,
        }

    def get_health_status(self) -> Dict[str, Any]:
        """Get health status for the consumer."""
        is_healthy = (
            self.is_running and
            self.nats_client and
            self.nats_client.is_connected and
            self.subscription and
            self.error_count < 100  # Allow some errors
        )

        return {
            "healthy": is_healthy,
            "is_running": self.is_running,
            "nats_connected": self.nats_client.is_connected if self.nats_client else False,
            "subscription_active": self.subscription is not None,
            "message_count": self.message_count,
            "error_count": self.error_count,
            "last_message_time": self.last_message_time,
        }
