"""
NATS Consumer for processing market data messages.

This module handles consuming messages from NATS streams and routing them
to the appropriate strategy processors.
"""

import asyncio
import json
import time
from typing import Any, Dict, Optional
import structlog

import nats
from nats.aio.client import Client as NATSClient
from nats.aio.subscription import Subscription

import constants
from strategies.core.publisher import TradeOrderPublisher
from strategies.models.market_data import MarketDataMessage
from strategies.utils.circuit_breaker import CircuitBreaker
from strategies.market_logic.btc_dominance import BitcoinDominanceStrategy
from strategies.market_logic.cross_exchange_spread import CrossExchangeSpreadStrategy
from strategies.market_logic.onchain_metrics import OnChainMetricsStrategy


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
        
        # Initialize market logic strategies (from QTZD adaptation)
        self.market_logic_strategies = {}
        if constants.STRATEGY_ENABLED_BTC_DOMINANCE:
            self.market_logic_strategies['btc_dominance'] = BitcoinDominanceStrategy(logger=self.logger)
            self.logger.info("Bitcoin Dominance Strategy enabled")
            
        if constants.STRATEGY_ENABLED_CROSS_EXCHANGE_SPREAD:
            self.market_logic_strategies['cross_exchange_spread'] = CrossExchangeSpreadStrategy(logger=self.logger)
            self.logger.info("Cross-Exchange Spread Strategy enabled")
            
        if constants.STRATEGY_ENABLED_ONCHAIN_METRICS:
            self.market_logic_strategies['onchain_metrics'] = OnChainMetricsStrategy(logger=self.logger)
            self.logger.info("On-Chain Metrics Strategy enabled")

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
            await self.nats_client.close()
            self.logger.info("NATS connection closed")

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

            # Create market data message
            market_data = MarketDataMessage(
                stream=stream,
                data=data,
            )

            return market_data

        except Exception as e:
            self.logger.error("Failed to parse market data", error=str(e))
            return None

    async def _process_market_data(self, market_data: MarketDataMessage) -> None:
        """Process market data through strategies."""
        try:
            # Process through existing stream-based strategies
            if market_data.is_depth:
                await self._process_depth_data(market_data)
            elif market_data.is_trade:
                await self._process_trade_data(market_data)
            elif market_data.is_ticker:
                await self._process_ticker_data(market_data)
            else:
                self.logger.warning("Unknown stream type", stream_type=market_data.stream_type)
            
            # Process through market logic strategies (QTZD-style processing)
            await self._process_market_logic_strategies(market_data)

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
    
    async def _process_market_logic_strategies(self, market_data: MarketDataMessage) -> None:
        """
        Process market data through market logic strategies.
        
        Adapted from QTZD MS Cash NoSQL service processing logic.
        """
        try:
            signals_to_publish = []
            
            # Process through each enabled market logic strategy
            for strategy_name, strategy in self.market_logic_strategies.items():
                try:
                    if strategy_name == 'btc_dominance':
                        # Bitcoin Dominance Strategy
                        signal = await strategy.process_market_data(market_data)
                        if signal:
                            signals_to_publish.append(signal)
                            
                    elif strategy_name == 'cross_exchange_spread':
                        # Cross-Exchange Spread Strategy (can return multiple signals)
                        signals = await strategy.process_market_data(market_data)
                        if signals:
                            if isinstance(signals, list):
                                signals_to_publish.extend(signals)
                            else:
                                signals_to_publish.append(signals)
                                
                    elif strategy_name == 'onchain_metrics':
                        # On-Chain Metrics Strategy
                        signal = await strategy.process_market_data(market_data)
                        if signal:
                            signals_to_publish.append(signal)
                            
                except Exception as e:
                    self.logger.error(f"Error in {strategy_name} strategy", error=str(e))
                    
            # Publish generated signals (QTZD-style batch publishing)
            if signals_to_publish:
                await self._publish_market_logic_signals(signals_to_publish)
                
        except Exception as e:
            self.logger.error("Error processing market logic strategies", error=str(e))
    
    async def _publish_market_logic_signals(self, signals) -> None:
        """
        Publish market logic signals to the trade engine.
        
        Converts signals to order format and publishes via NATS.
        """
        try:
            for signal in signals:
                # Convert signal to order format
                order_data = self._signal_to_order(signal)
                
                # Publish to trade engine
                await self.publisher.publish_order(order_data)
                
                self.logger.info("Market logic signal published",
                               strategy=signal.strategy_name,
                               symbol=signal.symbol,
                               signal_type=signal.signal_type,
                               confidence=signal.confidence_score)
                               
        except Exception as e:
            self.logger.error("Error publishing market logic signals", error=str(e))
    
    def _signal_to_order(self, signal) -> Dict[str, Any]:
        """
        Convert a market logic signal to a trade order format.
        
        Compatible with existing Petrosa trade engine format.
        """
        # Map signal to order action
        if signal.signal_action == "OPEN_LONG":
            action = "buy"
        elif signal.signal_action == "OPEN_SHORT":
            action = "sell"
        else:
            action = signal.signal_type.lower()  # BUY -> buy, SELL -> sell
            
        # Create order in trade engine format
        order = {
            "strategy_id": f"market_logic_{signal.strategy_name}",
            "strategy_mode": "deterministic",  # Market logic uses deterministic rules
            "symbol": signal.symbol,
            "action": action,
            "confidence": signal.confidence_score,
            "current_price": signal.price,
            "order_type": "market",  # Market orders for quick execution
            "position_size_pct": 0.05,  # 5% position size for market logic signals
            "metadata": {
                **signal.metadata,
                "signal_source": "market_logic",
                "original_signal_type": signal.signal_type,
                "original_signal_action": signal.signal_action
            }
        }
        
        return order

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
