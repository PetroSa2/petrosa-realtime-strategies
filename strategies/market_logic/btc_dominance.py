"""
Bitcoin Dominance Strategy.

Adapted from QTZD MS Cash NoSQL service's index tracking logic.
Monitors Bitcoin market dominance to generate rotation signals between BTC and altcoins.

Strategy Logic:
- High dominance (>70%) = Money flowing to BTC (buy BTC, sell alts)
- Low dominance (<40%) = Alt season (sell BTC, buy alts)
- Rising dominance = Early BTC strength (rotate from alts)
- Falling dominance = Alt season beginning (rotate to alts)
"""

import time
from datetime import datetime
from typing import Any, Optional

import structlog

import constants
from strategies.models.market_data import MarketDataMessage
from strategies.models.signals import Signal, SignalAction, SignalConfidence, SignalType


class BitcoinDominanceStrategy:
    """
    Bitcoin Dominance Strategy for crypto market rotation signals.

    This strategy tracks Bitcoin's market dominance and generates signals
    for rotating between Bitcoin and altcoins based on dominance trends.
    """

    def __init__(self, logger: Optional[structlog.BoundLogger] = None):
        """Initialize the Bitcoin Dominance Strategy."""
        self.logger = logger or structlog.get_logger()

        # Configuration from constants (QTZD-style thresholds)
        self.high_threshold = constants.BTC_DOMINANCE_HIGH_THRESHOLD  # 70%
        self.low_threshold = constants.BTC_DOMINANCE_LOW_THRESHOLD  # 40%
        self.change_threshold = constants.BTC_DOMINANCE_CHANGE_THRESHOLD  # 5%
        self.window_hours = constants.BTC_DOMINANCE_WINDOW_HOURS  # 24 hours
        self.min_signal_interval = (
            constants.BTC_DOMINANCE_MIN_SIGNAL_INTERVAL
        )  # 4 hours

        # State tracking (QTZD-style data accumulation)
        self.price_history: dict[str, list[dict[str, Any]]] = {}
        self.dominance_history: list[dict[str, Any]] = []
        self.last_signal_time: Optional[datetime] = None
        self.last_dominance_calculation: Optional[float] = None

        # Strategy metrics
        self.signals_generated = 0
        self.last_update_time = time.time()

        self.logger.info(
            "Bitcoin Dominance Strategy initialized",
            high_threshold=self.high_threshold,
            low_threshold=self.low_threshold,
        )

    async def process_market_data(
        self, market_data: MarketDataMessage
    ) -> Optional[Signal]:
        """
        Process market data and generate dominance-based signals.

        Args:
            market_data: Real-time market data from Binance WebSocket

        Returns:
            Signal if dominance conditions are met, None otherwise
        """
        try:
            # Update price history (QTZD-style data accumulation)
            self._update_price_history(market_data)

            # Calculate current Bitcoin dominance
            current_dominance = await self._calculate_btc_dominance()
            if current_dominance is None:
                return None

            # Update dominance history (QTZD-style time series)
            self._update_dominance_history(current_dominance)

            # Generate signal based on dominance analysis
            signal = await self._generate_dominance_signal(
                current_dominance, market_data
            )

            if signal:
                self.signals_generated += 1
                self.logger.info(
                    "Bitcoin dominance signal generated",
                    signal_type=signal.signal_type,
                    dominance=current_dominance,
                    confidence=signal.confidence_score,
                )

            return signal

        except Exception as e:
            self.logger.error("Error processing Bitcoin dominance data", error=str(e))
            return None

    def _update_price_history(self, market_data: MarketDataMessage) -> None:
        """Update price history for dominance calculation."""
        symbol = market_data.symbol
        current_time = time.time()

        if symbol not in self.price_history:
            self.price_history[symbol] = []

        # Extract price from market data
        price = None
        if market_data.is_ticker and hasattr(market_data.data, "c"):
            price = float(market_data.data.c)  # Close price from ticker
        elif market_data.is_trade and hasattr(market_data.data, "p"):
            price = float(market_data.data.p)  # Trade price

        if price:
            price_entry = {"timestamp": current_time, "price": price, "symbol": symbol}

            self.price_history[symbol].append(price_entry)

            # Keep only recent history (24 hours + buffer)
            cutoff_time = current_time - (self.window_hours * 3600 + 3600)
            self.price_history[symbol] = [
                entry
                for entry in self.price_history[symbol]
                if entry["timestamp"] > cutoff_time
            ]

    async def _calculate_btc_dominance(self) -> Optional[float]:
        """
        Calculate Bitcoin dominance from available price data.

        Simplified calculation using price momentum as proxy for market cap changes.
        In production, this would use actual market cap data.
        """
        try:
            # Get recent prices for BTC and major altcoins
            btc_data = self.price_history.get("BTCUSDT", [])
            eth_data = self.price_history.get("ETHUSDT", [])
            bnb_data = self.price_history.get("BNBUSDT", [])

            if not btc_data or len(btc_data) < 2:
                return None

            current_time = time.time()
            window_start = current_time - (self.window_hours * 3600)

            # Calculate price momentum for each asset
            btc_momentum = self._calculate_momentum(btc_data, window_start)
            eth_momentum = (
                self._calculate_momentum(eth_data, window_start) if eth_data else 0
            )
            bnb_momentum = (
                self._calculate_momentum(bnb_data, window_start) if bnb_data else 0
            )

            # Simplified dominance calculation
            # In reality, this would use actual market caps
            total_momentum = btc_momentum + eth_momentum + bnb_momentum
            if total_momentum <= 0:
                return None

            # Calculate dominance proxy (normalized between 30-80%)
            btc_ratio = btc_momentum / total_momentum if total_momentum > 0 else 0.5
            dominance_proxy = 30 + (btc_ratio * 50)  # Scale to 30-80% range

            self.last_dominance_calculation = dominance_proxy
            return dominance_proxy

        except Exception as e:
            self.logger.error("Error calculating BTC dominance", error=str(e))
            return None

    def _calculate_momentum(
        self, price_data: list[dict[str, Any]], window_start: float
    ) -> float:
        """Calculate price momentum over the specified window."""
        recent_data = [
            entry for entry in price_data if entry["timestamp"] >= window_start
        ]

        if len(recent_data) < 2:
            return 0

        # Sort by timestamp
        recent_data.sort(key=lambda x: x["timestamp"])

        start_price = recent_data[0]["price"]
        end_price = recent_data[-1]["price"]

        # Calculate momentum (percentage change)
        momentum = ((end_price - start_price) / start_price) * 100

        # Convert to positive momentum score (higher = stronger performance)
        return max(0, momentum + 10)  # Add base to avoid negative values

    def _update_dominance_history(self, dominance: float) -> None:
        """Update dominance history for trend analysis."""
        current_time = time.time()

        dominance_entry = {"timestamp": current_time, "dominance": dominance}

        self.dominance_history.append(dominance_entry)

        # Keep only recent history (48 hours for trend analysis)
        cutoff_time = current_time - (48 * 3600)
        self.dominance_history = [
            entry
            for entry in self.dominance_history
            if entry["timestamp"] > cutoff_time
        ]

    async def _generate_dominance_signal(
        self, current_dominance: float, market_data: MarketDataMessage
    ) -> Optional[Signal]:
        """
        Generate trading signals based on dominance analysis.

        Uses QTZD-style thresholds and rate limiting.
        """
        # Rate limiting (QTZD-style minimum intervals)
        if self.last_signal_time:
            time_since_last = datetime.utcnow() - self.last_signal_time
            if time_since_last.total_seconds() < self.min_signal_interval:
                return None

        # Calculate dominance trend
        dominance_trend = self._calculate_dominance_trend()
        dominance_change_24h = self._calculate_dominance_change_24h()

        signal = None

        # High dominance scenarios (QTZD-style threshold logic)
        if current_dominance > self.high_threshold:
            if (
                dominance_trend == "rising"
                or dominance_change_24h > self.change_threshold
            ):
                signal = self._create_signal(
                    signal_type=SignalType.BUY,
                    action=SignalAction.OPEN_LONG,
                    symbol="BTCUSDT",  # Rotate TO Bitcoin
                    confidence_score=0.8,
                    reasoning=f"High BTC dominance ({current_dominance:.1f}%) with rising trend",
                    market_data=market_data,
                    metadata={
                        "dominance": current_dominance,
                        "trend": dominance_trend,
                        "change_24h": dominance_change_24h,
                        "strategy_type": "dominance_rotation",
                        "rotation_direction": "to_btc",
                    },
                )

        # Low dominance scenarios (QTZD-style threshold logic)
        elif current_dominance < self.low_threshold:
            if (
                dominance_trend == "falling"
                or dominance_change_24h < -self.change_threshold
            ):
                # Alt season signal - this would ideally target specific altcoins
                signal = self._create_signal(
                    signal_type=SignalType.SELL,
                    action=SignalAction.OPEN_SHORT,
                    symbol="BTCUSDT",  # Rotate FROM Bitcoin (sell BTC)
                    confidence_score=0.75,
                    reasoning=f"Low BTC dominance ({current_dominance:.1f}%) - alt season",
                    market_data=market_data,
                    metadata={
                        "dominance": current_dominance,
                        "trend": dominance_trend,
                        "change_24h": dominance_change_24h,
                        "strategy_type": "dominance_rotation",
                        "rotation_direction": "to_alts",
                        "suggested_alts": ["ETHUSDT", "BNBUSDT"],
                    },
                )

        # Momentum-based signals (regardless of absolute level)
        elif abs(dominance_change_24h) > self.change_threshold:
            confidence = min(0.7, abs(dominance_change_24h) / 10)  # Scale confidence

            if dominance_change_24h > 0:  # BTC gaining dominance
                signal = self._create_signal(
                    signal_type=SignalType.BUY,
                    action=SignalAction.OPEN_LONG,
                    symbol="BTCUSDT",
                    confidence_score=confidence,
                    reasoning=f"BTC dominance momentum: {dominance_change_24h:.1f}% change",
                    market_data=market_data,
                    metadata={
                        "dominance": current_dominance,
                        "trend": dominance_trend,
                        "change_24h": dominance_change_24h,
                        "strategy_type": "dominance_momentum",
                    },
                )
            else:  # BTC losing dominance
                signal = self._create_signal(
                    signal_type=SignalType.SELL,
                    action=SignalAction.OPEN_SHORT,
                    symbol="BTCUSDT",
                    confidence_score=confidence,
                    reasoning=f"BTC dominance decline: {dominance_change_24h:.1f}% change",
                    market_data=market_data,
                    metadata={
                        "dominance": current_dominance,
                        "trend": dominance_trend,
                        "change_24h": dominance_change_24h,
                        "strategy_type": "dominance_momentum",
                    },
                )

        if signal:
            self.last_signal_time = datetime.utcnow()

        return signal

    def _calculate_dominance_trend(self) -> str:
        """Calculate dominance trend from history."""
        if len(self.dominance_history) < 3:
            return "unknown"

        # Get recent dominance values
        recent = self.dominance_history[-3:]
        values = [entry["dominance"] for entry in recent]

        # Simple trend calculation
        if values[-1] > values[0] + 1:
            return "rising"
        elif values[-1] < values[0] - 1:
            return "falling"
        else:
            return "stable"

    def _calculate_dominance_change_24h(self) -> float:
        """Calculate 24-hour dominance change."""
        if len(self.dominance_history) < 2:
            return 0

        current_time = time.time()
        day_ago = current_time - (24 * 3600)

        # Find closest entry to 24 hours ago
        past_entries = [
            entry for entry in self.dominance_history if entry["timestamp"] <= day_ago
        ]

        if not past_entries:
            return 0

        past_dominance = past_entries[-1]["dominance"]  # Most recent past entry
        current_dominance = self.dominance_history[-1]["dominance"]

        return current_dominance - past_dominance

    def _create_signal(
        self,
        signal_type: SignalType,
        action: SignalAction,
        symbol: str,
        confidence_score: float,
        reasoning: str,
        market_data: MarketDataMessage,
        metadata: dict[str, Any],
    ) -> Signal:
        """Create a trading signal with proper formatting."""

        # Map confidence score to confidence level
        if confidence_score >= 0.75:
            confidence = SignalConfidence.HIGH
        elif confidence_score >= 0.6:
            confidence = SignalConfidence.MEDIUM
        else:
            confidence = SignalConfidence.LOW

        # Get current price from market data
        current_price = 0.0
        if market_data.is_ticker and hasattr(market_data.data, "c"):
            current_price = float(market_data.data.c)
        elif market_data.is_trade and hasattr(market_data.data, "p"):
            current_price = float(market_data.data.p)
        elif symbol in self.price_history and self.price_history[symbol]:
            current_price = self.price_history[symbol][-1]["price"]

        return Signal(
            symbol=symbol,
            signal_type=signal_type,
            signal_action=action,
            confidence=confidence,
            confidence_score=confidence_score,
            price=current_price,
            strategy_name="btc_dominance",
            metadata={
                **metadata,
                "reasoning": reasoning,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    def get_metrics(self) -> dict[str, Any]:
        """Get strategy metrics."""
        return {
            "strategy_name": "btc_dominance",
            "signals_generated": self.signals_generated,
            "last_dominance": self.last_dominance_calculation,
            "dominance_history_size": len(self.dominance_history),
            "price_history_symbols": list(self.price_history.keys()),
            "last_signal_time": self.last_signal_time.isoformat()
            if self.last_signal_time
            else None,
            "uptime_seconds": time.time() - self.last_update_time,
        }
