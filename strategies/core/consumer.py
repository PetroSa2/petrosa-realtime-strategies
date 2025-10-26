"""
NATS Consumer for processing market data messages.

This module handles consuming messages from NATS streams and routing them
to the appropriate strategy processors.
"""

import asyncio
import json
import time
from datetime import datetime
from typing import Any, Optional, Union

import nats
import structlog
from nats.aio.client import Client as NATSClient
from nats.aio.subscription import Subscription
from opentelemetry import trace
from petrosa_otel import extract_trace_context

import constants
from strategies.core.publisher import TradeOrderPublisher
from strategies.market_logic.btc_dominance import BitcoinDominanceStrategy
from strategies.market_logic.cross_exchange_spread import CrossExchangeSpreadStrategy
from strategies.market_logic.iceberg_detector import IcebergDetectorStrategy
from strategies.market_logic.onchain_metrics import OnChainMetricsStrategy
from strategies.market_logic.spread_liquidity import SpreadLiquidityStrategy
from strategies.models.market_data import (
    DepthLevel,
    DepthUpdate,
    MarketDataMessage,
    TickerData,
    TradeData,
)
from strategies.utils.circuit_breaker import CircuitBreaker
from strategies.utils.metrics import (
    MetricsContext,
    RealtimeStrategyMetrics,
    initialize_metrics,
)

# OpenTelemetry tracer
tracer = trace.get_tracer(__name__)


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
        depth_analyzer=None,
    ):
        """Initialize the NATS consumer."""
        self.nats_url = nats_url
        self.topic = topic
        self.consumer_name = consumer_name
        self.consumer_group = consumer_group
        self.publisher = publisher
        self.logger = logger or structlog.get_logger()
        self.depth_analyzer = depth_analyzer

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

        # Initialize OpenTelemetry custom business metrics
        self.metrics = initialize_metrics()
        self.logger.info(
            "Custom business metrics initialized",
            event_type="metrics_initialized",
            meter_name="petrosa.realtime.strategies",
        )

        # Initialize market logic strategies (from QTZD adaptation)
        self.market_logic_strategies = {}
        if constants.STRATEGY_ENABLED_BTC_DOMINANCE:
            self.market_logic_strategies["btc_dominance"] = BitcoinDominanceStrategy(
                logger=self.logger
            )
            self.logger.info(
                "Strategy initialized",
                event_type="strategy_initialized",
                strategy="btc_dominance",
                strategy_type="market_logic",
            )

        if constants.STRATEGY_ENABLED_CROSS_EXCHANGE_SPREAD:
            self.market_logic_strategies[
                "cross_exchange_spread"
            ] = CrossExchangeSpreadStrategy(logger=self.logger)
            self.logger.info(
                "Strategy initialized",
                event_type="strategy_initialized",
                strategy="cross_exchange_spread",
                strategy_type="market_logic",
            )

        if constants.STRATEGY_ENABLED_ONCHAIN_METRICS:
            self.market_logic_strategies["onchain_metrics"] = OnChainMetricsStrategy(
                logger=self.logger
            )
            self.logger.info(
                "Strategy initialized",
                event_type="strategy_initialized",
                strategy="onchain_metrics",
                strategy_type="market_logic",
            )

        # Initialize microstructure strategies
        self.microstructure_strategies = {}
        if constants.STRATEGY_ENABLED_SPREAD_LIQUIDITY:
            self.microstructure_strategies[
                "spread_liquidity"
            ] = SpreadLiquidityStrategy()
            self.logger.info(
                "Strategy initialized",
                event_type="strategy_initialized",
                strategy="spread_liquidity",
                strategy_type="microstructure",
            )

        if constants.STRATEGY_ENABLED_ICEBERG_DETECTOR:
            self.microstructure_strategies[
                "iceberg_detector"
            ] = IcebergDetectorStrategy()
            self.logger.info(
                "Strategy initialized",
                event_type="strategy_initialized",
                strategy="iceberg_detector",
                strategy_type="microstructure",
            )

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
            self.logger.info(
                "NATS consumer started",
                event_type="consumer_started",
                nats_url=self.nats_url,
                topic=self.topic,
            )

        except Exception as e:
            self.logger.error("Failed to start NATS consumer", error=str(e))
            raise

    async def stop(self) -> None:
        """Stop the NATS consumer gracefully."""
        self.logger.info(
            "Stopping NATS consumer",
            event_type="consumer_stopping",
            message_count=self.message_count,
            error_count=self.error_count,
        )

        # Signal shutdown
        self.shutdown_event.set()
        self.is_running = False

        # Close subscription
        if self.subscription:
            await self.subscription.drain()
            self.logger.info(
                "NATS subscription drained",
                event_type="subscription_drained",
                topic=self.topic,
            )

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
            "NATS consumer stopped",
            event_type="consumer_stopped",
            total_messages=self.message_count,
            total_errors=self.error_count,
        )

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
            self.logger.info(
                "Connected to NATS server",
                event_type="nats_connected",
                nats_url=self.nats_url,
                consumer_name=self.consumer_name,
            )

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
                event_type="topic_subscribed",
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
        self.logger.info(
            "Starting message processing loop", event_type="processing_loop_started"
        )

        # For subscription-based approach, the processing is handled by callbacks
        # This loop just keeps the consumer alive
        while self.is_running and not self.shutdown_event.is_set():
            try:
                # Small delay to prevent busy waiting
                await asyncio.sleep(1)
            except Exception as e:
                self.logger.error(
                    "Error in processing loop",
                    event_type="processing_loop_error",
                    error=str(e),
                )
                self.error_count += 1
                await asyncio.sleep(1)  # Back off on error

        self.logger.info(
            "Message processing loop stopped", event_type="processing_loop_stopped"
        )

    async def _process_message(self, msg) -> None:
        """Process a single NATS message with trace context extraction."""
        start_time = time.time()
        processing_time = 0.0
        message_data = None

        try:
            # Parse message data
            message_data = json.loads(msg.data.decode())
            self.logger.debug("Received message", data=message_data)

            # Extract trace context from message (with error handling)
            try:
                ctx = extract_trace_context(message_data)
            except Exception as e:
                self.logger.warning(
                    "Failed to extract trace context, using current context",
                    error=str(e),
                )
                ctx = None

            # Create span with extracted context for distributed tracing
            with tracer.start_as_current_span(
                "process_market_data_message",
                context=ctx,
                kind=trace.SpanKind.CONSUMER,
            ) as span:
                try:
                    # Set messaging attributes for observability
                    span.set_attribute("messaging.system", "nats")
                    span.set_attribute("messaging.destination", self.topic)
                    span.set_attribute("messaging.operation", "receive")
                    span.set_attribute(
                        "market_data.symbol", message_data.get("s", "unknown")
                    )

                    # Validate and parse market data message
                    market_data = self._parse_market_data(message_data)
                    if not market_data:
                        self.logger.warning(
                            "Invalid market data message", data=message_data
                        )
                        self.metrics.record_error("invalid_message")
                        return

                    # Determine message type for metrics
                    message_type = market_data.stream_type or "unknown"
                    symbol = market_data.symbol or "UNKNOWN"

                    # Record message type received
                    self.metrics.record_message_type(message_type)

                    # Process message through strategies
                    await self._process_market_data(market_data)

                    # Update metrics
                    self.message_count += 1
                    self.last_message_time = time.time()
                    processing_time = (
                        time.time() - start_time
                    ) * 1000  # Convert to milliseconds

                    # Update processing time metrics
                    self._update_processing_metrics(processing_time)

                    # Record message processed with OpenTelemetry metrics
                    self.metrics.record_message_processed(symbol, message_type)

                    # Update consumer lag (time since message was created)
                    if hasattr(market_data, "timestamp") and market_data.timestamp:
                        lag_seconds = time.time() - market_data.timestamp.timestamp()
                        self.metrics.update_consumer_lag(max(0, lag_seconds))

                    self.logger.debug(
                        "Message processed successfully",
                        message_count=self.message_count,
                        processing_time_ms=processing_time,
                    )

                    # Mark span as successful
                    span.set_status(trace.Status(trace.StatusCode.OK))

                except Exception as processing_error:
                    # Mark span as error
                    span.set_status(
                        trace.Status(
                            trace.StatusCode.ERROR,
                            description=f"Message processing failed: {processing_error}",
                        )
                    )
                    span.record_exception(processing_error)
                    # Re-raise to be caught by outer handler
                    raise

        except Exception as e:
            self.logger.error(
                "Error processing message",
                error=str(e),
                message_data=message_data if message_data else None,
            )
            self.error_count += 1
            self.metrics.record_error("message_processing")

    def _parse_market_data(
        self, message_data: dict[str, Any]
    ) -> Optional[MarketDataMessage]:
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

            # Create market data message using model_construct to bypass Union validation
            # since we've already validated the specific type in the transformation
            market_data = MarketDataMessage.model_construct(
                stream=stream, data=transformed_data, timestamp=datetime.utcnow()
            )

            return market_data

        except Exception as e:
            self.logger.error("Failed to parse market data", error=str(e))
            return None

    def _transform_binance_data(
        self, stream: str, data: dict[str, Any]
    ) -> Optional[Union[DepthUpdate, TradeData, TickerData]]:
        """Transform raw Binance WebSocket data to expected format."""
        try:
            stream_type = stream.split("@")[1] if "@" in stream else None
            self.logger.debug(
                "Transforming data",
                stream_type=stream_type,
                data_keys=list(data.keys()),
            )

            if "depth" in stream_type:
                return self._transform_depth_data(data)
            elif "trade" in stream_type:
                return self._transform_trade_data(data)
            elif "ticker" in stream_type:
                return self._transform_ticker_data(data)
            else:
                self.logger.warning("Unknown stream type", stream_type=stream_type)
                return None

        except Exception as e:
            self.logger.error(
                "Failed to transform Binance data",
                error=str(e),
                stream=stream,
                data=data,
            )
            return None

    def _transform_depth_data(self, data: dict[str, Any]) -> Optional[DepthUpdate]:
        """Transform depth data to DepthUpdate model."""
        try:
            # Extract symbol from the data if available, otherwise use a default
            symbol = data.get("s", "BTCUSDT")  # Default fallback

            # Transform bids and asks from arrays to DepthLevel objects
            bids = []
            if "bids" in data:
                for bid in data["bids"]:
                    if len(bid) >= 2:
                        bids.append(DepthLevel(price=bid[0], quantity=bid[1]))

            asks = []
            if "asks" in data:
                for ask in data["asks"]:
                    if len(ask) >= 2:
                        asks.append(DepthLevel(price=ask[0], quantity=ask[1]))

            return DepthUpdate(
                symbol=symbol,
                event_time=data.get("E", int(time.time() * 1000)),
                first_update_id=data.get("U", 0),
                final_update_id=data.get("u", 0),
                bids=bids,
                asks=asks,
            )

        except Exception as e:
            self.logger.error("Failed to transform depth data", error=str(e), data=data)
            return None

    def _transform_trade_data(self, data: dict[str, Any]) -> Optional[TradeData]:
        """Transform trade data to TradeData model."""
        try:
            # Map Binance trade fields to our model
            # Binance fields: s=symbol, t=trade_id, p=price, q=quantity, T=trade_time, m=is_buyer_maker, E=event_time
            return TradeData(
                symbol=data.get("s", ""),
                trade_id=data.get("t", 0),
                price=data.get("p", "0"),
                quantity=data.get("q", "0"),
                buyer_order_id=data.get("b", 0),  # Not present in trade data, use 0
                seller_order_id=data.get("a", 0),  # Not present in trade data, use 0
                trade_time=data.get("T", 0),
                is_buyer_maker=data.get("m", False),
                event_time=data.get("E", 0),
            )

        except Exception as e:
            self.logger.error("Failed to transform trade data", error=str(e), data=data)
            return None

    def _transform_ticker_data(self, data: dict[str, Any]) -> Optional[TickerData]:
        """Transform ticker data to TickerData model."""
        try:
            return TickerData(
                symbol=data.get("s", ""),
                price_change=data.get("P", "0"),
                price_change_percent=data.get("P", "0"),
                weighted_avg_price=data.get("w", "0"),
                prev_close_price=data.get("x", "0"),
                last_price=data.get("c", "0"),
                last_qty=data.get("Q", "0"),
                bid_price=data.get("b", "0"),
                bid_qty=data.get("B", "0"),
                ask_price=data.get("a", "0"),
                ask_qty=data.get("A", "0"),
                open_price=data.get("o", "0"),
                high_price=data.get("h", "0"),
                low_price=data.get("l", "0"),
                volume=data.get("v", "0"),
                quote_volume=data.get("q", "0"),
                open_time=data.get("O", 0),
                close_time=data.get("C", 0),
                first_id=data.get("F", 0),
                last_id=data.get("L", 0),
                count=data.get("n", 0),
                event_time=data.get("E", 0),
            )

        except Exception as e:
            self.logger.error("Failed to transform ticker data", error=str(e))
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
                self.logger.warning(
                    "Unknown stream type", stream_type=market_data.stream_type
                )

            # Process through market logic strategies (QTZD-style processing)
            await self._process_market_logic_strategies(market_data)

        except Exception as e:
            self.logger.error("Error processing market data", error=str(e))

    async def _process_depth_data(self, market_data: MarketDataMessage) -> None:
        """Process depth (order book) data."""
        try:
            # Analyze depth data if depth analyzer is available
            if (
                self.depth_analyzer
                and hasattr(market_data.data, "bids")
                and hasattr(market_data.data, "asks")
            ):
                depth_data = market_data.data
                symbol = market_data.symbol or market_data.stream.split("@")[0].upper()

                # Convert DepthLevel objects to tuples for analyzer
                bids = [(float(b.price), float(b.quantity)) for b in depth_data.bids]
                asks = [(float(a.price), float(a.quantity)) for a in depth_data.asks]

                # Analyze and store metrics
                metrics = self.depth_analyzer.analyze_depth(symbol, bids, asks)

                self.logger.debug(
                    "Depth data analyzed",
                    symbol=symbol,
                    net_pressure=round(metrics.net_pressure, 2),
                    imbalance_percent=round(metrics.imbalance_percent, 2),
                )

                # Process microstructure strategies
                await self._process_microstructure_strategies(symbol, bids, asks)
            else:
                self.logger.debug(
                    "Processing depth data (no analyzer)", symbol=market_data.symbol
                )
        except Exception as e:
            self.logger.error(f"Error analyzing depth data: {e}", error=str(e))

    async def _process_microstructure_strategies(
        self, symbol: str, bids: list, asks: list
    ) -> None:
        """Process microstructure strategies (spread liquidity, iceberg detector)."""
        try:
            for strategy_name, strategy in self.microstructure_strategies.items():
                # Use metrics context for timing and signal recording
                with MetricsContext(
                    strategy=strategy_name, symbol=symbol, metrics=self.metrics
                ) as ctx:
                    try:
                        # Analyze order book
                        signal = strategy.analyze(symbol=symbol, bids=bids, asks=asks)

                        if signal:
                            # Record signal in metrics
                            ctx.record_signal(signal.action, signal.confidence)

                            # Publish signal
                            await self.publisher.publish_signal(signal)

                            self.logger.info(
                                f"Microstructure signal: {strategy_name}",
                                symbol=symbol,
                                action=signal.action,
                                confidence=round(signal.confidence, 2),
                            )
                    except Exception as e:
                        self.logger.error(
                            f"Error in {strategy_name} strategy",
                            error=str(e),
                            symbol=symbol,
                        )
                        # Error is automatically recorded by MetricsContext
        except Exception as e:
            self.logger.error(f"Error processing microstructure strategies: {e}")
            self.metrics.record_error("microstructure_processing")

    async def _process_trade_data(self, market_data: MarketDataMessage) -> None:
        """Process trade data."""
        # This will be implemented by the strategy processor
        self.logger.debug("Processing trade data", symbol=market_data.symbol)

    async def _process_ticker_data(self, market_data: MarketDataMessage) -> None:
        """Process ticker data."""
        # This will be implemented by the strategy processor
        self.logger.debug("Processing ticker data", symbol=market_data.symbol)

    async def _process_market_logic_strategies(
        self, market_data: MarketDataMessage
    ) -> None:
        """
        Process market data through market logic strategies.

        Adapted from QTZD MS Cash NoSQL service processing logic.
        """
        try:
            signals_to_publish = []
            symbol = market_data.symbol or "UNKNOWN"

            # Process through each enabled market logic strategy
            for strategy_name, strategy in self.market_logic_strategies.items():
                # Use metrics context for timing and signal recording
                with MetricsContext(
                    strategy=strategy_name, symbol=symbol, metrics=self.metrics
                ) as ctx:
                    try:
                        if strategy_name == "btc_dominance":
                            # Bitcoin Dominance Strategy
                            signal = await strategy.process_market_data(market_data)
                            if signal:
                                ctx.record_signal(
                                    signal.signal_type, signal.confidence_score
                                )
                                signals_to_publish.append(signal)

                        elif strategy_name == "cross_exchange_spread":
                            # Cross-Exchange Spread Strategy (can return multiple signals)
                            signals = await strategy.process_market_data(market_data)
                            if signals:
                                if isinstance(signals, list):
                                    for sig in signals:
                                        ctx.record_signal(
                                            sig.signal_type, sig.confidence_score
                                        )
                                    signals_to_publish.extend(signals)
                                else:
                                    ctx.record_signal(
                                        signals.signal_type, signals.confidence_score
                                    )
                                    signals_to_publish.append(signals)

                        elif strategy_name == "onchain_metrics":
                            # On-Chain Metrics Strategy
                            signal = await strategy.process_market_data(market_data)
                            if signal:
                                ctx.record_signal(
                                    signal.signal_type, signal.confidence_score
                                )
                                signals_to_publish.append(signal)

                    except Exception as e:
                        self.logger.error(
                            f"Error in {strategy_name} strategy", error=str(e)
                        )
                        # Error is automatically recorded by MetricsContext

            # Publish generated signals (QTZD-style batch publishing)
            if signals_to_publish:
                await self._publish_market_logic_signals(signals_to_publish)

        except Exception as e:
            self.logger.error("Error processing market logic strategies", error=str(e))
            self.metrics.record_error("market_logic_processing")

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

                self.logger.info(
                    "Market logic signal published",
                    strategy=signal.strategy_name,
                    symbol=signal.symbol,
                    signal_type=signal.signal_type,
                    confidence=signal.confidence_score,
                )

        except Exception as e:
            self.logger.error("Error publishing market logic signals", error=str(e))

    def _signal_to_order(self, signal) -> dict[str, Any]:
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

        # CRITICAL FIX: Calculate stop_loss and take_profit based on risk management parameters
        current_price = signal.price

        # Get risk management parameters from constants
        stop_loss_pct = (
            constants.RISK_STOP_LOSS_PERCENT / 100.0
        )  # Convert from percentage to decimal
        take_profit_pct = constants.RISK_TAKE_PROFIT_PERCENT / 100.0

        # Calculate stop_loss and take_profit based on action
        if action == "buy":
            # For LONG positions
            stop_loss = current_price * (1 - stop_loss_pct)
            take_profit = current_price * (1 + take_profit_pct)
        else:  # action == "sell"
            # For SHORT positions
            stop_loss = current_price * (1 + stop_loss_pct)
            take_profit = current_price * (1 - take_profit_pct)

        # Create order in trade engine format
        order = {
            "strategy_id": f"market_logic_{signal.strategy_name}",
            "strategy_mode": "deterministic",  # Market logic uses deterministic rules
            "symbol": signal.symbol,
            "action": action,
            "confidence": signal.confidence_score,
            "current_price": current_price,
            "order_type": "market",  # Market orders for quick execution
            "position_size_pct": 0.05,  # 5% position size for market logic signals
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "metadata": {
                **signal.metadata,
                "signal_source": "market_logic",
                "original_signal_type": signal.signal_type,
                "original_signal_action": signal.signal_action,
                "stop_loss_pct": stop_loss_pct * 100,
                "take_profit_pct": take_profit_pct * 100,
            },
        }

        self.logger.info(
            "Signal converted to order with risk management",
            symbol=signal.symbol,
            action=action,
            price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            sl_pct=f"{stop_loss_pct*100:.2f}%",
            tp_pct=f"{take_profit_pct*100:.2f}%",
        )

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
        self.avg_processing_time = sum(self.processing_times) / len(
            self.processing_times
        )

    def get_metrics(self) -> dict[str, Any]:
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

    def get_health_status(self) -> dict[str, Any]:
        """Get health status for the consumer."""
        is_healthy = (
            self.is_running
            and self.nats_client
            and self.nats_client.is_connected
            and self.subscription
            and self.error_count < 100  # Allow some errors
        )

        return {
            "healthy": is_healthy,
            "is_running": self.is_running,
            "nats_connected": self.nats_client.is_connected
            if self.nats_client
            else False,
            "subscription_active": self.subscription is not None,
            "message_count": self.message_count,
            "error_count": self.error_count,
            "last_message_time": self.last_message_time,
        }
