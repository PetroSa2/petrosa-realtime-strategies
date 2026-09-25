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

import bisect
import time
from array import array
from datetime import UTC, datetime
from operator import itemgetter
from typing import Any, Optional

import structlog
from opentelemetry import trace

import constants
from strategies.models.market_data import MarketDataMessage
from strategies.models.signals import Signal, SignalAction, SignalConfidence, SignalType

# Histories are kept sorted by "timestamp" so pruning and window lookups are
# O(log n) bisects instead of full-list rebuilds on every message. Before this,
# every message rebuilt price_history[symbol] and the 48h dominance_history
# (~10^5 dicts) and sorted three 24h price windows; with ~12 msg/s inbound the
# strategy saturated a CPU core (~0.95 cores, ~670 ms/msg) and the consumer
# fell >30 h behind real time.
_TS = itemgetter("timestamp")


class _TimeSeries:
    """Compact timestamp/value series with dict-shaped compatibility views."""

    def __init__(
        self, entries: list[dict[str, Any]] | None = None, value_key: str = "price"
    ):
        self.ts = array("d")
        self.val = array("d")
        self.value_key = value_key
        if entries:
            for entry in entries:
                self.insert(float(entry["timestamp"]), float(entry[value_key]))

    def insert(self, timestamp: float, value: float) -> None:
        index = bisect.bisect_right(self.ts, timestamp)
        self.ts.insert(index, timestamp)
        self.val.insert(index, value)

    def __len__(self) -> int:
        return len(self.ts)

    def __iter__(self):
        for timestamp, value in zip(self.ts, self.val, strict=True):
            yield {"timestamp": timestamp, self.value_key: value}

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(len(self)))]
        return {"timestamp": self.ts[index], self.value_key: self.val[index]}

    def __eq__(self, other) -> bool:
        if isinstance(other, _TimeSeries):
            return self.value_key == other.value_key and list(self) == list(other)
        if isinstance(other, list):
            return list(self) == other
        return NotImplemented

    def last(self) -> dict[str, float]:
        return self[-1]

    def first_at_or_after(self, timestamp: float) -> int:
        return bisect.bisect_left(self.ts, timestamp)

    def last_at_or_before(self, timestamp: float) -> int:
        return bisect.bisect_right(self.ts, timestamp) - 1

    def prune_before_or_at(self, cutoff: float) -> None:
        index = bisect.bisect_right(self.ts, cutoff)
        if index:
            del self.ts[:index]
            del self.val[:index]


class _PriceHistory(dict[str, _TimeSeries]):
    def __setitem__(self, symbol: str, history) -> None:
        if isinstance(history, _TimeSeries):
            super().__setitem__(symbol, history)
        else:
            super().__setitem__(symbol, _TimeSeries(history, "price"))


def _append_sorted(history: list[dict[str, Any]], entry: dict[str, Any]) -> None:
    """Append ``entry`` keeping ``history`` sorted by timestamp.

    Entries normally arrive in time order (O(1) append). An out-of-order
    timestamp (e.g. a wall-clock step) is inserted after any equal timestamps,
    which preserves the stable-sort order the previous implementation relied on.
    """
    if history and history[-1]["timestamp"] > entry["timestamp"]:
        bisect.insort_right(history, entry, key=_TS)
    else:
        history.append(entry)


def _prune_before_or_at(history: list[dict[str, Any]], cutoff: float) -> None:
    """Drop entries with timestamp <= cutoff from a timestamp-sorted list."""
    if history and history[0]["timestamp"] <= cutoff:
        del history[: bisect.bisect_right(history, cutoff, key=_TS)]


# Get tracer for this module
def get_tracer():
    """Get tracer, always using current provider."""
    return trace.get_tracer(__name__)


class BitcoinDominanceStrategy:
    """
    Bitcoin Dominance Strategy for crypto market rotation signals.

    This strategy tracks Bitcoin's market dominance and generates signals
    for rotating between Bitcoin and altcoins based on dominance trends.
    """

    def __init__(self, logger: structlog.BoundLogger | None = None):
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
        self.price_history: _PriceHistory = _PriceHistory()
        self.dominance_history = _TimeSeries(value_key="dominance")
        self.last_signal_time: datetime | None = None
        self.last_dominance_calculation: float | None = None

        # Strategy metrics
        self.signals_generated = 0
        self.last_update_time = time.time()

        self.logger.info(
            "Bitcoin Dominance Strategy initialized",
            high_threshold=self.high_threshold,
            low_threshold=self.low_threshold,
        )

    @property
    def dominance_history(self) -> _TimeSeries:
        return self._dominance_history

    @dominance_history.setter
    def dominance_history(self, history) -> None:
        if isinstance(history, _TimeSeries):
            self._dominance_history = history
        else:
            self._dominance_history = _TimeSeries(history, "dominance")

    async def process_market_data(
        self, market_data: MarketDataMessage
    ) -> Signal | None:
        """
        Process market data and generate dominance-based signals.

        Args:
            market_data: Real-time market data from Binance WebSocket

        Returns:
            Signal if dominance conditions are met, None otherwise
        """
        with get_tracer().start_as_current_span(
            "strategy.btc_dominance.process"
        ) as span:
            span.set_attribute("symbol", market_data.symbol)
            try:
                # Update price history (QTZD-style data accumulation)
                self._update_price_history(market_data)

                # Calculate current Bitcoin dominance
                current_dominance = await self._calculate_btc_dominance()
                if current_dominance is None:
                    span.set_attribute("result", "insufficient_data")
                    return None

                # Update dominance history (QTZD-style time series)
                self._update_dominance_history(current_dominance)

                # Generate signal based on dominance analysis
                signal = await self._generate_dominance_signal(
                    current_dominance, market_data
                )

                if signal:
                    self.signals_generated += 1
                    span.set_attribute("result", "signal_generated")
                    span.set_attribute("signal.type", signal.signal_type.value)
                    self.logger.info(
                        "Bitcoin dominance signal generated",
                        signal_type=signal.signal_type,
                        dominance=current_dominance,
                        confidence=signal.confidence_score,
                    )
                else:
                    span.set_attribute("result", "no_signal")

                return signal

            except Exception as e:
                self.logger.error(
                    "Error processing Bitcoin dominance data", error=str(e)
                )
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR))
                return None

    def _update_price_history(self, market_data: MarketDataMessage) -> None:
        """Update price history for dominance calculation."""
        symbol = market_data.symbol
        current_time = time.time()

        if symbol not in self.price_history:
            self.price_history[symbol] = _TimeSeries(value_key="price")

        # Extract price from market data.
        # NOTE (#197): TickerData/TradeData (strategies/models/market_data.py) expose
        # `last_price`/`price`, never Binance's raw `c`/`p` keys — this previously made
        # the hasattr gate always False and price never populated.
        price = None
        if market_data.is_ticker and hasattr(market_data.data, "last_price"):
            price = float(market_data.data.last_price)  # Close price from ticker
        elif market_data.is_trade and hasattr(market_data.data, "price"):
            price = float(market_data.data.price)  # Trade price

        if price:
            history = self.price_history[symbol]
            history.insert(current_time, price)

            # Keep only recent history (24 hours + buffer)
            cutoff_time = current_time - (self.window_hours * 3600 + 3600)
            history.prune_before_or_at(cutoff_time)

    async def _calculate_btc_dominance(self) -> float | None:
        """
        Calculate Bitcoin dominance from available price data.

        Simplified calculation using price momentum as proxy for market cap changes.
        In production, this would use actual market cap data.
        """
        with get_tracer().start_as_current_span(
            "strategy.btc_dominance.calculate"
        ) as span:
            try:
                # Get recent prices for BTC and major altcoins
                btc_data = self.price_history.get("BTCUSDT", [])
                eth_data = self.price_history.get("ETHUSDT", [])
                bnb_data = self.price_history.get("BNBUSDT", [])

                span.set_attribute("data_points.btc", len(btc_data))
                span.set_attribute("data_points.eth", len(eth_data))
                span.set_attribute("data_points.bnb", len(bnb_data))

                if not btc_data or len(btc_data) < 2:
                    return None

                current_time = time.time()
                window_start = current_time - (self.window_hours * 3600)

                # Calculate price momentum for each asset. The histories are
                # maintained timestamp-sorted, so use the O(log n) window lookup.
                btc_momentum = self._momentum_sorted(btc_data, window_start)
                eth_momentum = (
                    self._momentum_sorted(eth_data, window_start) if eth_data else 0
                )
                bnb_momentum = (
                    self._momentum_sorted(bnb_data, window_start) if bnb_data else 0
                )

                # Simplified dominance calculation
                # In reality, this would use actual market caps
                total_momentum = btc_momentum + eth_momentum + bnb_momentum
                if total_momentum <= 0:
                    return None

                # Calculate dominance proxy (normalized between 30-80%)
                btc_ratio = btc_momentum / total_momentum
                dominance_proxy = 30 + (btc_ratio * 50)  # Scale to 30-80% range

                self.last_dominance_calculation = dominance_proxy
                return dominance_proxy

            except Exception as e:
                self.logger.error("Error calculating BTC dominance", error=str(e))
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR))
                return None

    @staticmethod
    def _momentum_score(start_price: float, end_price: float) -> float:
        # Calculate momentum (percentage change)
        momentum = ((end_price - start_price) / start_price) * 100
        # Convert to positive momentum score (higher = stronger performance)
        return max(0, momentum + 10)  # Add base to avoid negative values

    def _momentum_sorted(
        self, price_data: _TimeSeries | list[dict[str, Any]], window_start: float
    ) -> float:
        """Momentum over the window for a timestamp-sorted list, in O(log n)."""
        if isinstance(price_data, _TimeSeries):
            start = price_data.first_at_or_after(window_start)
            if len(price_data) - start < 2:
                return 0
            return self._momentum_score(price_data.val[start], price_data.val[-1])
        start = bisect.bisect_left(price_data, window_start, key=_TS)
        if len(price_data) - start < 2:
            return 0
        return self._momentum_score(price_data[start]["price"], price_data[-1]["price"])

    def _calculate_momentum(
        self, price_data: list[dict[str, Any]], window_start: float
    ) -> float:
        """Calculate price momentum over the specified window.

        Accepts any ordering. One pass, no copy and no sort: the earliest and
        latest in-window entries are the same ones the previous filter +
        stable-sort picked (first of equal-earliest, last of equal-latest).
        """
        first = last = None
        count = 0
        for entry in price_data:
            ts = entry["timestamp"]
            if ts < window_start:
                continue
            count += 1
            if first is None or ts < first["timestamp"]:
                first = entry
            if last is None or ts >= last["timestamp"]:
                last = entry

        if count < 2:
            return 0

        return self._momentum_score(first["price"], last["price"])

    def _update_dominance_history(self, dominance: float) -> None:
        """Update dominance history for trend analysis."""
        current_time = time.time()

        self.dominance_history.insert(current_time, dominance)

        # Keep only recent history (48 hours for trend analysis)
        cutoff_time = current_time - (48 * 3600)
        self.dominance_history.prune_before_or_at(cutoff_time)

    async def _generate_dominance_signal(
        self, current_dominance: float, market_data: MarketDataMessage
    ) -> Signal | None:
        """
        Generate trading signals based on dominance analysis.

        Uses QTZD-style thresholds and rate limiting.
        """
        # Rate limiting (QTZD-style minimum intervals)
        if self.last_signal_time:
            time_since_last = datetime.now(UTC) - self.last_signal_time
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
            self.last_signal_time = datetime.now(UTC)

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

        # Most recent entry at or before 24 hours ago (history is timestamp-sorted)
        idx = self.dominance_history.last_at_or_before(day_ago) + 1
        if idx == 0:
            return 0

        past_dominance = self.dominance_history[idx - 1]["dominance"]
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
            current_price = self.price_history[symbol].last()["price"]

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
                "timestamp": datetime.now(UTC).isoformat(),
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
            "last_signal_time": (
                self.last_signal_time.isoformat() if self.last_signal_time else None
            ),
            "uptime_seconds": time.time() - self.last_update_time,
        }
