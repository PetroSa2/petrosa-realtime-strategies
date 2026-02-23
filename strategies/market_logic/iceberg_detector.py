"""
Iceberg Order Detection Strategy.

Detects large hidden institutional orders (icebergs) by analyzing order book
patterns: repeated refills, consistent sizing, and price anchoring.

Strategy Type: Market Microstructure
Timeframe: Real-time (tick-by-tick)
Win Rate Target: 60-70%
Signal Frequency: 2-5 per symbol per day
"""

import time
from datetime import datetime
from typing import Optional

import structlog
from opentelemetry import trace

from strategies.models.orderbook_tracker import IcebergPattern, OrderBookTracker
from strategies.models.signals import Signal, SignalAction, SignalConfidence, SignalType

logger = structlog.get_logger(__name__)


# Get tracer for this module
def get_tracer():
    """Get tracer, always using current provider."""
    return trace.get_tracer(__name__)


class IcebergDetectorStrategy:
    """
    Iceberg Order Detection Strategy.

    Detection Patterns:
    1. **Repeated Refills**: Volume depletes then restores quickly (3+ times)
    2. **Consistent Sizing**: Low volume variance at price level
    3. **Price Anchoring**: Level persists despite market movement (2+ min)

    Signal Logic:
    - BUY: Large hidden bid detected (support level)
    - SELL: Large hidden ask detected (resistance level)

    Features:
    - 5-minute order book level tracking
    - Refill speed detection (<5s)
    - Volume consistency analysis
    - Proximity-based filtering (1% from price)
    """

    def __init__(
        self,
        # Detection thresholds
        min_refill_count: int = 3,
        refill_speed_threshold_seconds: float = 5.0,
        consistency_threshold: float = 0.1,
        persistence_threshold_seconds: float = 120.0,
        # Signal generation
        level_proximity_pct: float = 1.0,
        base_confidence: float = 0.70,
        # Tracking
        history_window_seconds: int = 300,
        max_symbols: int = 100,
        # Rate limiting
        min_signal_interval_seconds: float = 120.0,
    ):
        """
        Initialize strategy.

        Args:
            min_refill_count: Minimum refills to consider iceberg
            refill_speed_threshold_seconds: Max time for fast refill
            consistency_threshold: Max std dev ratio for consistent volume
            persistence_threshold_seconds: Minimum persistence for anchoring
            level_proximity_pct: Only signal if price within X% of iceberg
            base_confidence: Base confidence for signals
            history_window_seconds: Order book history window
            max_symbols: Maximum symbols to track
            min_signal_interval_seconds: Minimum time between signals per symbol
        """
        self.min_refill_count = min_refill_count
        self.refill_speed_threshold = refill_speed_threshold_seconds
        self.consistency_threshold = consistency_threshold
        self.persistence_threshold = persistence_threshold_seconds
        self.level_proximity_pct = level_proximity_pct
        self.base_confidence = base_confidence
        self.history_window = history_window_seconds
        self.max_symbols = max_symbols
        self.min_signal_interval = min_signal_interval_seconds

        # Order book tracker
        self.tracker = OrderBookTracker(
            history_window_seconds=history_window_seconds,
            max_symbols=max_symbols,
            refill_speed_threshold_seconds=refill_speed_threshold_seconds,
            consistency_threshold=consistency_threshold,
            min_refill_count=min_refill_count,
        )

        # Last signal time: {(symbol, price, side): timestamp}
        self.last_signal_time: dict[tuple[str, float, str], float] = {}

        # Statistics
        self.signals_generated = 0
        self.icebergs_detected = 0

        logger.info(
            "Iceberg Detector Strategy initialized",
            min_refill_count=min_refill_count,
            refill_speed_threshold=refill_speed_threshold_seconds,
            history_window=history_window_seconds,
            level_proximity_pct=level_proximity_pct,
        )

    def analyze(
        self,
        symbol: str,
        bids: list[tuple[float, float]],
        asks: list[tuple[float, float]],
        timestamp: Optional[datetime] = None,
    ) -> Optional[Signal]:
        """
        Analyze order book for iceberg patterns and generate signal.

        Args:
            symbol: Trading symbol
            bids: [(price, quantity), ...] sorted descending
            asks: [(price, quantity), ...] sorted ascending
            timestamp: Snapshot timestamp

        Returns:
            Signal if iceberg detected near price, None otherwise
        """
        with get_tracer().start_as_current_span("strategy.iceberg_detector.analyze") as span:
            span.set_attribute("symbol", symbol)
            
            if timestamp is None:
                timestamp = datetime.utcnow()

            # Validate inputs
            if not bids or not asks:
                span.set_attribute("result", "skipped_empty_data")
                return None

            # Update tracker with order book
            self.tracker.update_orderbook(symbol, bids, asks, timestamp)

            # Calculate current mid price
            mid_price = (bids[0][0] + asks[0][0]) / 2

            # Detect icebergs near current price
            icebergs = self.tracker.detect_icebergs(
                symbol=symbol,
                current_price=mid_price,
                proximity_pct=self.level_proximity_pct,
            )

            if not icebergs:
                span.set_attribute("result", "no_icebergs")
                return None

            # Log detection
            for iceberg in icebergs:
                self.icebergs_detected += 1
                logger.debug(
                    f"Iceberg detected: {iceberg.side.upper()}",
                    symbol=symbol,
                    price=iceberg.price,
                    pattern_type=iceberg.pattern_type,
                    refill_count=iceberg.refill_count,
                    confidence=round(iceberg.confidence, 2),
                )

            # Generate signal from strongest iceberg
            strongest_iceberg = max(icebergs, key=lambda x: x.confidence)
            signal = self._generate_signal(strongest_iceberg, mid_price)

            if signal:
                self.signals_generated += 1
                span.set_attribute("result", "signal_generated")
                span.set_attribute("signal.type", signal.signal_type.value)
            else:
                span.set_attribute("result", "signal_suppressed")

            return signal

    def _generate_signal(
        self, iceberg: IcebergPattern, current_price: float
    ) -> Optional[Signal]:
        """Generate trading signal from iceberg pattern."""
        with get_tracer().start_as_current_span("strategy.iceberg_detector.generate_signal") as span:
            span.set_attribute("symbol", iceberg.symbol)
            span.set_attribute("iceberg.price", iceberg.price)
            span.set_attribute("iceberg.side", iceberg.side)
            
            # Rate limiting per (symbol, price, side)
            signal_key = (iceberg.symbol, round(iceberg.price, 2), iceberg.side)
            current_time = time.time()

            if signal_key in self.last_signal_time:
                time_since_last = current_time - self.last_signal_time[signal_key]
                if time_since_last < self.min_signal_interval:
                    logger.debug(
                        "Signal rate limited",
                        symbol=iceberg.symbol,
                        price=iceberg.price,
                        side=iceberg.side,
                        time_since_last=round(time_since_last, 1),
                    )
                    span.set_attribute("result", "rate_limited")
                    return None

            # Determine signal type and action based on iceberg side
            if iceberg.side == "bid":
                # Hidden buyer (support) → BUY signal
                signal_type = SignalType.BUY
                signal_action = SignalAction.OPEN_LONG
                reasoning = f"Large hidden buyer detected at {iceberg.price} ({iceberg.pattern_type})"
            elif iceberg.side == "ask":
                # Hidden seller (resistance) → SELL signal
                signal_type = SignalType.SELL
                signal_action = SignalAction.OPEN_SHORT
                reasoning = f"Large hidden seller detected at {iceberg.price} ({iceberg.pattern_type})"
            else:
                span.set_attribute("result", "invalid_side")
                return None

            # Calculate confidence score and map to enum
            confidence_score = iceberg.confidence
            if confidence_score >= 0.8:
                confidence_level = SignalConfidence.HIGH
            elif confidence_score >= 0.6:
                confidence_level = SignalConfidence.MEDIUM
            else:
                confidence_level = SignalConfidence.LOW

            # Calculate risk management levels
            # Use distance to iceberg level as ATR proxy
            distance_to_level = abs(current_price - iceberg.price)
            atr_proxy = max(distance_to_level, current_price * 0.005)  # Min 0.5%

            if signal_type == SignalType.BUY:
                # Enter near support, stop below iceberg
                entry_price = current_price
                stop_loss = iceberg.price - atr_proxy
                take_profit = entry_price + (atr_proxy * 2.5)
            else:  # SELL
                # Enter near resistance, stop above iceberg
                entry_price = current_price
                stop_loss = iceberg.price + atr_proxy
                take_profit = entry_price - (atr_proxy * 2.5)

            # Create signal with all required fields
            signal = Signal(
                symbol=iceberg.symbol,
                signal_type=signal_type,
                signal_action=signal_action,
                confidence=confidence_level,
                confidence_score=confidence_score,
                price=entry_price,
                strategy_name="Iceberg Order Detector",
                metadata={
                    "strategy_id": "iceberg_detector",
                    "pattern_type": iceberg.pattern_type,
                    "reasoning": reasoning,
                    "distance_to_level_pct": (distance_to_level / current_price) * 100,
                    "iceberg_price": iceberg.price,
                    "iceberg_side": iceberg.side,
                    "refill_count": iceberg.refill_count,
                    "avg_refill_speed": iceberg.avg_refill_speed_seconds,
                    "volume_consistency": iceberg.volume_consistency_score,
                    "persistence_seconds": iceberg.persistence_seconds,
                    "current_price": current_price,
                    "stop_loss": stop_loss,
                    "take_profit": take_profit,
                    "quantity": 0.001,
                    "timeframe": "tick",
                },
            )

            # Update last signal time
            self.last_signal_time[signal_key] = current_time

            logger.info(
                f"Iceberg signal generated: {signal_type.value}",
                symbol=iceberg.symbol,
                iceberg_price=round(iceberg.price, 2),
                current_price=round(current_price, 2),
                pattern_type=iceberg.pattern_type,
                confidence=confidence_level.value,
                confidence_score=round(confidence_score, 2),
                refill_count=iceberg.refill_count,
            )

            span.set_attribute("result", "success")
            span.set_attribute("order.stop_loss", stop_loss)
            span.set_attribute("order.take_profit", take_profit)

            return signal

    def get_statistics(self) -> dict:
        """Get strategy statistics."""
        tracker_stats = self.tracker.get_statistics()

        return {
            "signals_generated": self.signals_generated,
            "icebergs_detected": self.icebergs_detected,
            "tracker_stats": tracker_stats,
        }
