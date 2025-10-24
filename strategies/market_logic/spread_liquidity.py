"""
Spread Liquidity Strategy.

Detects liquidity events by monitoring bid-ask spread widening and narrowing.
Generates signals when spreads indicate smart money withdrawal or return.

Strategy Type: Market Microstructure
Timeframe: Real-time (tick-by-tick)
Win Rate Target: 55-65%
Signal Frequency: 5-10 per symbol per day
"""

import time
from collections import defaultdict, deque
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import structlog

from strategies.models.market_data import MarketDataMessage
from strategies.models.signals import Signal
from strategies.models.spread_metrics import SpreadMetrics, SpreadSnapshot, SpreadEvent

logger = structlog.get_logger(__name__)


class SpreadLiquidityStrategy:
    """
    Spread Widening/Narrowing Detection Strategy.
    
    Theoretical Basis:
    - Kyle (1985): Spread reflects informed trading probability
    - Glosten & Milgrom (1985): Spread compensates for adverse selection
    - O'Hara (1995): Microstructure signals precede price moves
    
    Signal Logic:
    - BUY: Wide spread normalizing (liquidity returning)
    - SELL: Tight spread widening rapidly (liquidity withdrawal)
    
    Features:
    - 20-tick rolling spread history
    - Spread velocity calculation
    - Persistence detection
    - Depth reduction filtering
    """
    
    def __init__(
        self,
        # Thresholds
        spread_threshold_bps: float = 10.0,
        spread_ratio_threshold: float = 2.5,
        velocity_threshold: float = 0.5,
        persistence_threshold_seconds: float = 30.0,
        min_depth_reduction_pct: float = 0.5,
        
        # Confidence
        base_confidence: float = 0.70,
        
        # History
        lookback_ticks: int = 20,
        
        # Rate limiting
        min_signal_interval_seconds: float = 60.0,
    ):
        """
        Initialize strategy.
        
        Args:
            spread_threshold_bps: Minimum spread in basis points to consider
            spread_ratio_threshold: Minimum ratio vs average spread
            velocity_threshold: Minimum spread velocity (% change per second)
            persistence_threshold_seconds: Minimum time spread must persist
            min_depth_reduction_pct: Minimum depth reduction to trigger signal
            base_confidence: Base confidence for signals
            lookback_ticks: Number of ticks to track for averages
            min_signal_interval_seconds: Minimum time between signals per symbol
        """
        self.spread_threshold_bps = spread_threshold_bps
        self.spread_ratio_threshold = spread_ratio_threshold
        self.velocity_threshold = velocity_threshold
        self.persistence_threshold_seconds = persistence_threshold_seconds
        self.min_depth_reduction_pct = min_depth_reduction_pct
        self.base_confidence = base_confidence
        self.lookback_ticks = lookback_ticks
        self.min_signal_interval = min_signal_interval_seconds
        
        # History tracking: {symbol: deque[SpreadMetrics]}
        self.spread_history: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=lookback_ticks)
        )
        
        # Event tracking: {symbol: {"start_time": timestamp, "spread_bps": value}}
        self.wide_spread_events: Dict[str, Dict] = {}
        self.narrow_spread_events: Dict[str, Dict] = {}
        
        # Last signal time: {symbol: timestamp}
        self.last_signal_time: Dict[str, float] = {}
        
        # Statistics
        self.signals_generated = 0
        self.events_detected = 0
        
        logger.info(
            "Spread Liquidity Strategy initialized",
            spread_threshold_bps=spread_threshold_bps,
            spread_ratio_threshold=spread_ratio_threshold,
            velocity_threshold=velocity_threshold,
            lookback_ticks=lookback_ticks
        )
    
    def analyze(
        self,
        symbol: str,
        bids: List[Tuple[float, float]],
        asks: List[Tuple[float, float]],
        timestamp: Optional[datetime] = None
    ) -> Optional[Signal]:
        """
        Analyze order book spread and generate signal if event detected.
        
        Args:
            symbol: Trading symbol
            bids: [(price, quantity), ...] sorted descending
            asks: [(price, quantity), ...] sorted ascending
            timestamp: Snapshot timestamp
        
        Returns:
            Signal if liquidity event detected, None otherwise
        """
        if timestamp is None:
            timestamp = datetime.utcnow()
        
        # Validate inputs
        if not bids or not asks:
            return None
        
        # Calculate spread metrics
        metrics = self._calculate_spread_metrics(symbol, bids, asks, timestamp)
        if not metrics:
            return None
        
        # Update history
        self.spread_history[symbol].append(metrics)
        
        # Need history for comparison
        if len(self.spread_history[symbol]) < 3:
            return None
        
        # Create snapshot with comparative metrics
        snapshot = self._create_snapshot(symbol, metrics)
        
        # Detect events
        event = self._detect_event(symbol, snapshot, timestamp)
        if event:
            self.events_detected += 1
            
            # Generate signal
            signal = self._generate_signal(event, snapshot)
            if signal:
                self.signals_generated += 1
                return signal
        
        return None
    
    def _calculate_spread_metrics(
        self,
        symbol: str,
        bids: List[Tuple[float, float]],
        asks: List[Tuple[float, float]],
        timestamp: datetime
    ) -> Optional[SpreadMetrics]:
        """Calculate spread metrics from order book."""
        try:
            # Best bid/ask
            best_bid = bids[0][0]
            best_ask = asks[0][0]
            
            # Validation
            if best_bid <= 0 or best_ask <= 0 or best_ask <= best_bid:
                return None
            
            # Mid price
            mid_price = (best_bid + best_ask) / 2
            
            # Spread calculations
            spread_abs = best_ask - best_bid
            spread_bps = (spread_abs / mid_price) * 10000
            spread_pct = (spread_abs / mid_price) * 100
            
            # Top 5 levels depth
            bid_volume_top5 = sum(qty for _, qty in bids[:5])
            ask_volume_top5 = sum(qty for _, qty in asks[:5])
            total_depth = bid_volume_top5 + ask_volume_top5
            
            return SpreadMetrics(
                symbol=symbol,
                timestamp=timestamp,
                best_bid=best_bid,
                best_ask=best_ask,
                mid_price=mid_price,
                spread_abs=spread_abs,
                spread_bps=spread_bps,
                spread_pct=spread_pct,
                bid_volume_top5=bid_volume_top5,
                ask_volume_top5=ask_volume_top5,
                total_depth=total_depth
            )
        except Exception as e:
            logger.error(f"Error calculating spread metrics: {e}", symbol=symbol)
            return None
    
    def _create_snapshot(
        self,
        symbol: str,
        metrics: SpreadMetrics
    ) -> SpreadSnapshot:
        """Create snapshot with comparative metrics."""
        history = list(self.spread_history[symbol])
        
        # Calculate average spread (exclude current)
        avg_spread_bps = sum(m.spread_bps for m in history[:-1]) / max(1, len(history) - 1)
        
        # Spread ratio
        spread_ratio = metrics.spread_bps / avg_spread_bps if avg_spread_bps > 0 else 1.0
        
        # Spread velocity (change over last minute)
        spread_velocity = 0.0
        if len(history) >= 2:
            # Compare to 1 minute ago (approximate with available history)
            old_metric = history[0] if len(history) >= self.lookback_ticks else history[0]
            time_diff = (metrics.timestamp - old_metric.timestamp).total_seconds()
            
            if time_diff > 0:
                spread_change = (metrics.spread_bps - old_metric.spread_bps) / old_metric.spread_bps
                spread_velocity = spread_change / time_diff  # % per second
        
        # Average depth (for reduction calculation)
        avg_depth = sum(m.total_depth for m in history[:-1]) / max(1, len(history) - 1)
        depth_reduction_pct = 1.0 - (metrics.total_depth / avg_depth) if avg_depth > 0 else 0.0
        
        # Flags
        is_widening = spread_velocity > self.velocity_threshold
        is_narrowing = spread_velocity < -self.velocity_threshold
        is_abnormal = spread_ratio > self.spread_ratio_threshold
        
        return SpreadSnapshot(
            metrics=metrics,
            spread_ratio=spread_ratio,
            spread_velocity=spread_velocity,
            persistence_seconds=0.0,  # Will be calculated in event detection
            is_widening=is_widening,
            is_narrowing=is_narrowing,
            is_abnormal=is_abnormal,
            depth_reduction_pct=depth_reduction_pct
        )
    
    def _detect_event(
        self,
        symbol: str,
        snapshot: SpreadSnapshot,
        timestamp: datetime
    ) -> Optional[SpreadEvent]:
        """Detect spread widening or narrowing event."""
        current_time = timestamp.timestamp()
        metrics = snapshot.metrics
        
        # Event 1: Spread Normalization (BUY signal)
        # Wide spread that has been persistent, now narrowing
        if symbol in self.wide_spread_events:
            event = self.wide_spread_events[symbol]
            persistence = current_time - event["start_time"]
            
            # Check if normalizing
            if (
                snapshot.is_narrowing and
                snapshot.spread_ratio < self.spread_ratio_threshold and
                persistence > self.persistence_threshold_seconds
            ):
                # Event complete - liquidity returning
                spread_before = event["spread_bps"]
                
                spread_event = SpreadEvent(
                    event_type="narrowing",
                    symbol=symbol,
                    timestamp=timestamp,
                    spread_before_bps=spread_before,
                    spread_current_bps=metrics.spread_bps,
                    spread_ratio=snapshot.spread_ratio,
                    spread_velocity=snapshot.spread_velocity,
                    duration_seconds=persistence,
                    persistence_above_threshold=True,
                    confidence=self._calculate_confidence("narrowing", snapshot, persistence),
                    reasoning="Liquidity returning after withdrawal (spread normalizing)",
                    snapshot=snapshot
                )
                
                # Clear event
                del self.wide_spread_events[symbol]
                
                return spread_event
        
        # Track wide spread events
        if snapshot.is_abnormal and metrics.spread_bps > self.spread_threshold_bps:
            if symbol not in self.wide_spread_events:
                self.wide_spread_events[symbol] = {
                    "start_time": current_time,
                    "spread_bps": metrics.spread_bps
                }
        
        # Event 2: Liquidity Withdrawal (SELL signal)
        # Rapid widening from tight spread with depth reduction
        if (
            snapshot.is_widening and
            snapshot.spread_ratio > self.spread_ratio_threshold * 1.2 and  # Higher threshold
            snapshot.depth_reduction_pct > self.min_depth_reduction_pct
        ):
            spread_event = SpreadEvent(
                event_type="widening",
                symbol=symbol,
                timestamp=timestamp,
                spread_before_bps=metrics.spread_bps / (1 + snapshot.spread_velocity),  # Approximate
                spread_current_bps=metrics.spread_bps,
                spread_ratio=snapshot.spread_ratio,
                spread_velocity=snapshot.spread_velocity,
                duration_seconds=0.0,  # Immediate event
                persistence_above_threshold=False,
                confidence=self._calculate_confidence("widening", snapshot, 0.0),
                reasoning="Smart money liquidity withdrawal (rapid spread widening + depth reduction)",
                snapshot=snapshot
            )
            
            return spread_event
        
        return None
    
    def _calculate_confidence(
        self,
        event_type: str,
        snapshot: SpreadSnapshot,
        persistence: float
    ) -> float:
        """Calculate signal confidence based on event strength."""
        confidence = self.base_confidence
        
        if event_type == "narrowing":
            # Stronger signal with higher ratio and longer persistence
            confidence += (snapshot.spread_ratio - self.spread_ratio_threshold) * 0.05
            confidence += min(0.10, persistence / 300.0 * 0.10)  # Up to +0.10 for 5min persistence
        
        elif event_type == "widening":
            # Stronger signal with higher velocity and depth reduction
            confidence += abs(snapshot.spread_velocity) * 0.10
            confidence += snapshot.depth_reduction_pct * 0.15
        
        return min(0.95, confidence)
    
    def _generate_signal(
        self,
        event: SpreadEvent,
        snapshot: SpreadSnapshot
    ) -> Optional[Signal]:
        """Generate trading signal from spread event."""
        # Rate limiting
        current_time = time.time()
        if event.symbol in self.last_signal_time:
            time_since_last = current_time - self.last_signal_time[event.symbol]
            if time_since_last < self.min_signal_interval:
                logger.debug(
                    "Signal rate limited",
                    symbol=event.symbol,
                    time_since_last=time_since_last
                )
                return None
        
        metrics = snapshot.metrics
        
        # Determine action
        if event.event_type == "narrowing":
            action = "buy"
        elif event.event_type == "widening":
            action = "sell"
        else:
            return None
        
        # Calculate risk management levels
        atr_proxy = metrics.spread_abs * 2  # Rough ATR approximation
        
        if action == "buy":
            stop_loss = metrics.mid_price - atr_proxy
            take_profit = metrics.mid_price + (atr_proxy * 2)
        else:  # sell
            stop_loss = metrics.mid_price + atr_proxy
            take_profit = metrics.mid_price - (atr_proxy * 2)
        
        # Create signal
        signal = Signal(
            strategy_id="spread_liquidity",
            symbol=event.symbol,
            action=action,
            confidence=event.confidence,
            price=metrics.mid_price,
            current_price=metrics.mid_price,
            quantity=0.001,  # Will be calculated by TradeEngine
            timeframe="tick",
            stop_loss=stop_loss,
            take_profit=take_profit,
            indicators={
                "spread_bps": metrics.spread_bps,
                "spread_ratio": snapshot.spread_ratio,
                "spread_velocity": snapshot.spread_velocity,
                "total_depth": metrics.total_depth,
                "depth_reduction_pct": snapshot.depth_reduction_pct,
            },
            metadata={
                "strategy": "spread_liquidity",
                "event_type": event.event_type,
                "reasoning": event.reasoning,
                "persistence_seconds": event.duration_seconds,
                "best_bid": metrics.best_bid,
                "best_ask": metrics.best_ask,
            }
        )
        
        # Update last signal time
        self.last_signal_time[event.symbol] = current_time
        
        logger.info(
            f"Spread signal generated: {action.upper()}",
            symbol=event.symbol,
            event_type=event.event_type,
            confidence=round(event.confidence, 2),
            spread_bps=round(metrics.spread_bps, 2),
            spread_ratio=round(snapshot.spread_ratio, 2)
        )
        
        return signal
    
    def get_statistics(self) -> Dict:
        """Get strategy statistics."""
        return {
            "signals_generated": self.signals_generated,
            "events_detected": self.events_detected,
            "symbols_tracked": len(self.spread_history),
            "active_wide_events": len(self.wide_spread_events),
        }

