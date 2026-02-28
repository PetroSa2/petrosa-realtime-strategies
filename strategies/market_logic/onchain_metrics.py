"""
On-Chain Metrics Strategy.

Adapted from QTZD MS Cash NoSQL service's metrics processing logic.
Analyzes on-chain data to generate fundamental trading signals.

Strategy Logic:
- Network growth (active addresses, transactions) = Bullish
- Hash rate increases = Network security improving = Bullish
- Exchange inflows = Selling pressure = Bearish
- Exchange outflows = Hodling behavior = Bullish
"""

import time
from datetime import datetime
from typing import Any, Optional

import structlog
from opentelemetry import trace

import constants
from strategies.models.market_data import MarketDataMessage
from strategies.models.signals import Signal, SignalAction, SignalConfidence, SignalType

# OpenTelemetry tracer for manual spans
tracer = trace.get_tracer(__name__)


class OnChainMetricsStrategy:
    """
    On-Chain Metrics Strategy for fundamental analysis signals.

    This strategy analyzes blockchain metrics to identify fundamental
    shifts in network usage and adoption.
    """

    def __init__(self, logger: structlog.BoundLogger | None = None):
        """Initialize the On-Chain Metrics Strategy."""
        self.logger = logger or structlog.get_logger()

        # Configuration from constants (QTZD-style thresholds)
        self.network_growth_threshold = (
            constants.ONCHAIN_NETWORK_GROWTH_THRESHOLD
        )  # 10%
        self.volume_threshold = constants.ONCHAIN_VOLUME_THRESHOLD  # 15%
        self.min_signal_interval = constants.ONCHAIN_MIN_SIGNAL_INTERVAL  # 24 hours

        # Metrics cache (QTZD-style data storage)
        self.metrics_cache: dict[str, dict[str, Any]] = {}
        self.metrics_history: dict[str, list] = {}
        self.last_signal_times: dict[str, datetime] = {}

        # On-chain data sources (would need API keys in production)
        self.data_sources = {
            "glassnode": "https://api.glassnode.com/v1/metrics/",
            "messari": "https://data.messari.io/api/v1/assets/",
            "coinmetrics": "https://community-api.coinmetrics.io/v4/",
        }

        # Strategy metrics
        self.signals_generated = 0
        self.last_update_time = time.time()
        self.last_fetch_time = 0
        self.fetch_interval = 3600  # 1 hour between on-chain data fetches

        self.logger.info(
            "On-Chain Metrics Strategy initialized",
            network_growth_threshold=self.network_growth_threshold,
            volume_threshold=self.volume_threshold,
        )

    async def process_market_data(
        self, market_data: MarketDataMessage
    ) -> Signal | None:
        """
        Process market data and generate on-chain based signals.

        Note: On-chain data is fetched periodically, not on every market data update.

        Args:
            market_data: Real-time market data from Binance WebSocket

        Returns:
            Signal if on-chain conditions are met, None otherwise
        """
        with tracer.start_as_current_span(
            "onchain_metrics.process_market_data"
        ) as span:
            span.set_attribute("symbol", market_data.symbol or "UNKNOWN")
            try:
                current_time = time.time()

                # Fetch on-chain metrics periodically (QTZD-style batch processing)
                if current_time - self.last_fetch_time > self.fetch_interval:
                    with tracer.start_as_current_span(
                        "onchain_metrics.fetch_metrics"
                    ) as fetch_span:
                        fetch_span.set_attribute(
                            "time_since_last_fetch", current_time - self.last_fetch_time
                        )
                        await self._fetch_onchain_metrics()
                        self.last_fetch_time = current_time
                        fetch_span.set_attribute("result", "metrics_fetched")

                # Generate signals based on cached metrics
                signal = await self._analyze_onchain_metrics(market_data)

                if signal:
                    self.signals_generated += 1
                    span.set_attribute("result", "signal_generated")
                    span.set_attribute("signal_type", signal.signal_type.value)
                    span.set_attribute("signal_confidence", signal.confidence_score)
                    self.logger.info(
                        "On-chain metrics signal generated",
                        signal_type=signal.signal_type,
                        symbol=market_data.symbol,
                    )
                else:
                    span.set_attribute("result", "no_signal")

                return signal

            except Exception as e:
                span.set_attribute("error", str(e))
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                self.logger.error("Error processing on-chain metrics", error=str(e))
                return None

    async def _fetch_onchain_metrics(self) -> None:
        """
        Fetch on-chain metrics from various sources.

        QTZD-style external data fetching with batching.
        """
        try:
            self.logger.debug("Fetching on-chain metrics")

            # Simplified on-chain metrics (in production, use real APIs)
            current_time = time.time()

            # Simulate fetching Bitcoin network metrics
            btc_metrics = await self._simulate_btc_metrics()
            # Simulate fetching Ethereum network metrics
            eth_metrics = await self._simulate_eth_metrics()

            # Update cache (QTZD-style data storage)
            self.metrics_cache.update(
                {"BTC": btc_metrics, "ETH": eth_metrics, "last_updated": current_time}
            )

            # Update history for trend analysis
            self._update_metrics_history("BTC", btc_metrics)
            self._update_metrics_history("ETH", eth_metrics)

            self.logger.debug("On-chain metrics updated successfully")

        except Exception as e:
            self.logger.error("Error fetching on-chain metrics", error=str(e))

    async def _simulate_btc_metrics(self) -> dict[str, Any]:
        """
        Simulate Bitcoin on-chain metrics.

        In production, this would fetch real data from Glassnode, etc.
        """
        import random

        # Simulate realistic Bitcoin network metrics
        base_addresses = 1000000
        base_volume = 500000
        base_hash_rate = 200

        return {
            "active_addresses": base_addresses + random.randint(-50000, 50000),  # nosec B311
            "transaction_volume_btc": base_volume + random.randint(-100000, 100000),  # nosec B311
            "hash_rate_eh": base_hash_rate + random.randint(-20, 20),  # nosec B311
            "exchange_inflow_btc": random.randint(1000, 5000),  # nosec B311
            "exchange_outflow_btc": random.randint(1000, 5000),  # nosec B311
            "network_value_usd": random.randint(800000000000, 1200000000000),  # nosec B311
            "timestamp": time.time(),
        }

    async def _simulate_eth_metrics(self) -> dict[str, Any]:
        """
        Simulate Ethereum on-chain metrics.

        In production, this would fetch real data from various sources.
        """
        import random

        # Simulate realistic Ethereum network metrics
        base_addresses = 800000
        base_volume = 300000
        base_gas = 50

        return {
            "active_addresses": base_addresses + random.randint(-40000, 40000),  # nosec B311
            "transaction_volume_eth": base_volume + random.randint(-50000, 50000),  # nosec B311
            "avg_gas_price": base_gas + random.randint(-20, 20),  # nosec B311
            "defi_tvl_usd": random.randint(50000000000, 100000000000),  # nosec B311
            "exchange_inflow_eth": random.randint(50000, 200000),  # nosec B311
            "exchange_outflow_eth": random.randint(50000, 200000),  # nosec B311
            "timestamp": time.time(),
        }

    def _update_metrics_history(self, asset: str, metrics: dict[str, Any]) -> None:
        """Update metrics history for trend analysis."""
        if asset not in self.metrics_history:
            self.metrics_history[asset] = []

        self.metrics_history[asset].append(metrics)

        # Keep only recent history (7 days worth of hourly data)
        max_entries = 7 * 24  # 7 days * 24 hours
        if len(self.metrics_history[asset]) > max_entries:
            self.metrics_history[asset] = self.metrics_history[asset][-max_entries:]

    async def _analyze_onchain_metrics(
        self, market_data: MarketDataMessage
    ) -> Signal | None:
        """
        Analyze on-chain metrics and generate fundamental signals.

        Uses QTZD-style threshold analysis and rate limiting.
        """
        with tracer.start_as_current_span("onchain_metrics.analyze_metrics") as span:
            span.set_attribute("symbol", market_data.symbol)
            symbol = market_data.symbol

            # Determine which asset metrics to use
            if symbol.startswith("BTC"):
                asset_metrics = self.metrics_cache.get("BTC")
                asset_key = "BTC"
            elif symbol.startswith("ETH"):
                asset_metrics = self.metrics_cache.get("ETH")
                asset_key = "ETH"
            else:
                span.set_attribute("result", "unsupported_symbol")
                return None  # Only support BTC/ETH for now

            span.set_attribute("asset_key", asset_key)

            if not asset_metrics:
                span.set_attribute("result", "no_asset_metrics")
                return None

            # Rate limiting (QTZD-style minimum intervals)
            signal_key = f"{asset_key}_onchain"
            if not self._should_generate_signal(signal_key):
                span.set_attribute("result", "rate_limited")
                return None

            # Calculate growth rates
            growth_metrics = self._calculate_growth_metrics(asset_key)
            if not growth_metrics:
                span.set_attribute("result", "no_growth_metrics")
                return None

            # Analyze metrics for signals (QTZD-style threshold logic)
            signal = self._evaluate_fundamental_conditions(
                asset_key, asset_metrics, growth_metrics, market_data
            )

            if signal:
                self.last_signal_times[signal_key] = datetime.utcnow()
                span.set_attribute("result", "signal_generated")
                span.set_attribute("signal_type", signal.signal_type.value)
                span.set_attribute("confidence_score", signal.confidence_score)
            else:
                span.set_attribute("result", "no_signal")

            return signal

    def _calculate_growth_metrics(self, asset_key: str) -> dict[str, float] | None:
        """Calculate growth rates from historical data."""
        history = self.metrics_history.get(asset_key, [])

        if len(history) < 24:  # Need at least 24 hours of data
            return None

        current = history[-1]
        day_ago = history[-24] if len(history) >= 24 else history[0]
        week_ago = (
            history[-168] if len(history) >= 168 else history[0]
        )  # 7 days * 24 hours

        try:
            growth_metrics = {}

            # Calculate 24-hour growth rates
            if asset_key == "BTC":
                growth_metrics[
                    "active_addresses_24h"
                ] = self._calculate_percentage_change(
                    day_ago.get("active_addresses", 0),
                    current.get("active_addresses", 0),
                )
                growth_metrics[
                    "transaction_volume_24h"
                ] = self._calculate_percentage_change(
                    day_ago.get("transaction_volume_btc", 0),
                    current.get("transaction_volume_btc", 0),
                )
                growth_metrics["hash_rate_24h"] = self._calculate_percentage_change(
                    day_ago.get("hash_rate_eh", 0), current.get("hash_rate_eh", 0)
                )

                # Exchange flow analysis
                inflow = current.get("exchange_inflow_btc", 0)
                outflow = current.get("exchange_outflow_btc", 0)
                growth_metrics["net_exchange_flow"] = (
                    inflow - outflow
                )  # Positive = net inflow (bearish)

            elif asset_key == "ETH":
                growth_metrics[
                    "active_addresses_24h"
                ] = self._calculate_percentage_change(
                    day_ago.get("active_addresses", 0),
                    current.get("active_addresses", 0),
                )
                growth_metrics[
                    "transaction_volume_24h"
                ] = self._calculate_percentage_change(
                    day_ago.get("transaction_volume_eth", 0),
                    current.get("transaction_volume_eth", 0),
                )
                growth_metrics["defi_tvl_24h"] = self._calculate_percentage_change(
                    day_ago.get("defi_tvl_usd", 0), current.get("defi_tvl_usd", 0)
                )

                # Exchange flow analysis
                inflow = current.get("exchange_inflow_eth", 0)
                outflow = current.get("exchange_outflow_eth", 0)
                growth_metrics["net_exchange_flow"] = inflow - outflow

            return growth_metrics

        except Exception as e:
            self.logger.error("Error calculating growth metrics", error=str(e))
            return None

    def _calculate_percentage_change(self, old_value: float, new_value: float) -> float:
        """Calculate percentage change between two values."""
        if old_value == 0:
            return 0
        return ((new_value - old_value) / old_value) * 100

    def _evaluate_fundamental_conditions(
        self,
        asset_key: str,
        current_metrics: dict[str, Any],
        growth_metrics: dict[str, float],
        market_data: MarketDataMessage,
    ) -> Signal | None:
        """
        Evaluate fundamental conditions and generate signals.

        QTZD-style multi-condition analysis.
        """
        # Network growth analysis (QTZD-style threshold evaluation)
        active_addresses_growth = growth_metrics.get("active_addresses_24h", 0)
        transaction_volume_growth = growth_metrics.get("transaction_volume_24h", 0)
        net_exchange_flow = growth_metrics.get("net_exchange_flow", 0)

        # Strong network fundamentals = Bullish signal
        if (
            active_addresses_growth > self.network_growth_threshold
            and transaction_volume_growth > self.volume_threshold
        ):
            # Additional confirmation for Bitcoin
            if asset_key == "BTC":
                hash_rate_growth = growth_metrics.get("hash_rate_24h", 0)
                if (
                    hash_rate_growth > 0
                ):  # Hash rate increasing = network security improving
                    confidence_score = min(
                        0.8, (active_addresses_growth + transaction_volume_growth) / 30
                    )

                    return self._create_onchain_signal(
                        signal_type=SignalType.BUY,
                        action=SignalAction.OPEN_LONG,
                        symbol=market_data.symbol,
                        confidence_score=confidence_score,
                        reasoning=f"Strong {asset_key} network fundamentals: {active_addresses_growth:.1f}% address growth",
                        market_data=market_data,
                        metadata={
                            "active_addresses_growth_24h": active_addresses_growth,
                            "transaction_volume_growth_24h": transaction_volume_growth,
                            "hash_rate_growth_24h": hash_rate_growth,
                            "net_exchange_flow": net_exchange_flow,
                            "signal_type": "network_growth",
                            "asset": asset_key,
                        },
                    )

            # Additional confirmation for Ethereum
            elif asset_key == "ETH":
                defi_tvl_growth = growth_metrics.get("defi_tvl_24h", 0)
                if defi_tvl_growth > 5:  # DeFi TVL growing = ecosystem usage increasing
                    confidence_score = min(
                        0.75, (active_addresses_growth + transaction_volume_growth) / 35
                    )

                    return self._create_onchain_signal(
                        signal_type=SignalType.BUY,
                        action=SignalAction.OPEN_LONG,
                        symbol=market_data.symbol,
                        confidence_score=confidence_score,
                        reasoning=f"Strong {asset_key} ecosystem growth: {defi_tvl_growth:.1f}% DeFi TVL growth",
                        market_data=market_data,
                        metadata={
                            "active_addresses_growth_24h": active_addresses_growth,
                            "transaction_volume_growth_24h": transaction_volume_growth,
                            "defi_tvl_growth_24h": defi_tvl_growth,
                            "net_exchange_flow": net_exchange_flow,
                            "signal_type": "ecosystem_growth",
                            "asset": asset_key,
                        },
                    )

        # Large exchange inflows = Selling pressure (bearish)
        elif (
            net_exchange_flow > 0 and abs(net_exchange_flow) > 1000
        ):  # Significant inflow threshold
            confidence_score = min(0.7, abs(net_exchange_flow) / 5000)

            return self._create_onchain_signal(
                signal_type=SignalType.SELL,
                action=SignalAction.OPEN_SHORT,
                symbol=market_data.symbol,
                confidence_score=confidence_score,
                reasoning=f"Large {asset_key} exchange inflows indicate selling pressure",
                market_data=market_data,
                metadata={
                    "active_addresses_growth_24h": active_addresses_growth,
                    "transaction_volume_growth_24h": transaction_volume_growth,
                    "net_exchange_flow": net_exchange_flow,
                    "signal_type": "exchange_inflow_pressure",
                    "asset": asset_key,
                },
            )

        return None

    def _should_generate_signal(self, signal_key: str) -> bool:
        """Check if enough time has passed since last signal."""
        if signal_key not in self.last_signal_times:
            return True

        time_since_last = datetime.utcnow() - self.last_signal_times[signal_key]
        return time_since_last.total_seconds() >= self.min_signal_interval

    def _create_onchain_signal(
        self,
        signal_type: SignalType,
        action: SignalAction,
        symbol: str,
        confidence_score: float,
        reasoning: str,
        market_data: MarketDataMessage,
        metadata: dict[str, Any],
    ) -> Signal:
        """Create an on-chain based trading signal."""

        # Map confidence score to confidence level
        if confidence_score >= 0.7:
            confidence = SignalConfidence.HIGH
        elif confidence_score >= 0.5:
            confidence = SignalConfidence.MEDIUM
        else:
            confidence = SignalConfidence.LOW

        # Get current price from market data
        current_price = 0.0
        if market_data.is_ticker and hasattr(market_data.data, "c"):
            current_price = float(market_data.data.c)
        elif market_data.is_trade and hasattr(market_data.data, "p"):
            current_price = float(market_data.data.p)

        return Signal(
            symbol=symbol,
            signal_type=signal_type,
            signal_action=action,
            confidence=confidence,
            confidence_score=confidence_score,
            price=current_price,
            strategy_name="onchain_metrics",
            metadata={
                **metadata,
                "reasoning": reasoning,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    def get_metrics(self) -> dict[str, Any]:
        """Get strategy metrics."""
        return {
            "strategy_name": "onchain_metrics",
            "signals_generated": self.signals_generated,
            "cached_metrics_count": len(self.metrics_cache),
            "metrics_history_assets": list(self.metrics_history.keys()),
            "last_fetch_time": datetime.fromtimestamp(self.last_fetch_time).isoformat(),
            "uptime_seconds": time.time() - self.last_update_time,
        }
