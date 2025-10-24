"""
Order Book Level Tracker.

Tracks individual price levels in the order book over time to detect
iceberg order patterns (repeated refills, consistent sizing, price anchoring).
"""

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple


@dataclass
class LevelSnapshot:
    """Single snapshot of an order book level."""
    
    price: float
    quantity: float
    timestamp: float  # Unix timestamp for performance
    side: str  # "bid" or "ask"


@dataclass
class LevelHistory:
    """
    Historical tracking for a single price level.
    
    Tracks volume changes over time to detect iceberg patterns:
    - Refills: Volume depletes then restores quickly
    - Consistency: Similar volumes repeatedly appear
    - Persistence: Level remains active despite market movement
    """
    
    price: float
    side: str
    snapshots: deque  # deque of LevelSnapshot
    
    # Pattern detection
    refill_count: int = 0
    last_refill_time: Optional[float] = None
    avg_refill_speed_seconds: float = 0.0
    
    # Volume statistics
    avg_volume: float = 0.0
    volume_std_dev: float = 0.0
    consistent_volume: bool = False  # Low std dev = consistent sizing
    
    # Persistence tracking
    first_seen: float = 0.0
    last_seen: float = 0.0
    total_appearances: int = 0
    
    def __post_init__(self):
        """Initialize timestamps."""
        if self.first_seen == 0.0:
            self.first_seen = time.time()
        if self.last_seen == 0.0:
            self.last_seen = time.time()


@dataclass
class IcebergPattern:
    """
    Detected iceberg order pattern.
    
    Represents a high-confidence detection of a large hidden order
    at a specific price level.
    """
    
    symbol: str
    price: float
    side: str  # "bid" or "ask"
    
    # Detection evidence
    refill_count: int
    avg_refill_speed_seconds: float
    volume_consistency_score: float  # 0-1, higher = more consistent
    persistence_seconds: float
    
    # Pattern strength
    confidence: float
    pattern_type: str  # "refill", "consistent_size", "anchor"
    
    # Context
    detected_at: datetime
    level_history: LevelHistory


class OrderBookTracker:
    """
    Tracks order book levels over time to detect iceberg patterns.
    
    Features:
    - Per-level history tracking (5-minute rolling window)
    - Refill detection (volume depletes then restores)
    - Consistency detection (same volume sizes)
    - Persistence detection (level stays active)
    - Configurable thresholds and windows
    
    Memory: ~60MB for 50 symbols with 300-second history
    """
    
    def __init__(
        self,
        history_window_seconds: int = 300,  # 5 minutes
        max_symbols: int = 100,
        refill_speed_threshold_seconds: float = 5.0,
        consistency_threshold: float = 0.1,  # Low std dev = consistent
        min_refill_count: int = 3,
    ):
        """
        Initialize tracker.
        
        Args:
            history_window_seconds: How long to track each level
            max_symbols: Maximum symbols to track simultaneously
            refill_speed_threshold_seconds: Max time for refill to be considered fast
            consistency_threshold: Max std dev ratio for consistent sizing
            min_refill_count: Minimum refills to consider iceberg
        """
        self.history_window = history_window_seconds
        self.max_symbols = max_symbols
        self.refill_speed_threshold = refill_speed_threshold_seconds
        self.consistency_threshold = consistency_threshold
        self.min_refill_count = min_refill_count
        
        # Storage: {symbol: {price: LevelHistory}}
        self.bid_levels: Dict[str, Dict[float, LevelHistory]] = defaultdict(dict)
        self.ask_levels: Dict[str, Dict[float, LevelHistory]] = defaultdict(dict)
        
        # Statistics
        self.total_levels_tracked = 0
        self.total_icebergs_detected = 0
    
    def update_orderbook(
        self,
        symbol: str,
        bids: List[Tuple[float, float]],
        asks: List[Tuple[float, float]],
        timestamp: Optional[datetime] = None
    ) -> None:
        """
        Update tracker with new orderbook snapshot.
        
        Args:
            symbol: Trading symbol
            bids: [(price, quantity), ...]
            asks: [(price, quantity), ...]
            timestamp: Snapshot timestamp
        """
        if timestamp is None:
            timestamp = datetime.utcnow()
        
        unix_ts = timestamp.timestamp()
        
        # Update bid levels
        for price, qty in bids:
            self._update_level(symbol, price, qty, unix_ts, "bid")
        
        # Update ask levels
        for price, qty in asks:
            self._update_level(symbol, price, qty, unix_ts, "ask")
        
        # Cleanup old levels
        self._cleanup_old_levels(symbol, unix_ts)
    
    def _update_level(
        self,
        symbol: str,
        price: float,
        quantity: float,
        timestamp: float,
        side: str
    ) -> None:
        """Update a single price level."""
        levels = self.bid_levels if side == "bid" else self.ask_levels
        
        # Get or create level history
        if price not in levels[symbol]:
            levels[symbol][price] = LevelHistory(
                price=price,
                side=side,
                snapshots=deque(maxlen=100),  # Limit snapshots
                first_seen=timestamp,
                last_seen=timestamp,
                total_appearances=0
            )
            self.total_levels_tracked += 1
        
        history = levels[symbol][price]
        
        # Add snapshot
        snapshot = LevelSnapshot(
            price=price,
            quantity=quantity,
            timestamp=timestamp,
            side=side
        )
        history.snapshots.append(snapshot)
        history.last_seen = timestamp
        history.total_appearances += 1
        
        # Detect refill
        if self._is_refill(history, quantity):
            history.refill_count += 1
            history.last_refill_time = timestamp
            
            # Update refill speed
            if history.refill_count > 1:
                time_since_first = timestamp - history.first_seen
                history.avg_refill_speed_seconds = time_since_first / history.refill_count
        
        # Update statistics
        self._update_statistics(history)
    
    def _is_refill(self, history: LevelHistory, current_qty: float) -> bool:
        """
        Detect if current quantity represents a refill.
        
        Pattern: Volume drops significantly then restores quickly.
        """
        if len(history.snapshots) < 3:
            return False
        
        # Get recent snapshots
        recent = list(history.snapshots)[-3:]
        
        # Check for depletion then restoration
        # Pattern: high -> low -> high
        if len(recent) == 3:
            vol_0, vol_1, vol_2 = recent[0].quantity, recent[1].quantity, recent[2].quantity
            
            # Volume dropped by >50% then restored by >80%
            if vol_1 < vol_0 * 0.5 and vol_2 > vol_0 * 0.8:
                # Check speed (fast refill)
                time_elapsed = recent[2].timestamp - recent[0].timestamp
                if time_elapsed < self.refill_speed_threshold:
                    return True
        
        return False
    
    def _update_statistics(self, history: LevelHistory) -> None:
        """Update volume statistics for level."""
        if len(history.snapshots) < 2:
            return
        
        volumes = [s.quantity for s in history.snapshots]
        
        # Calculate mean and std dev
        mean_vol = sum(volumes) / len(volumes)
        variance = sum((v - mean_vol) ** 2 for v in volumes) / len(volumes)
        std_dev = variance ** 0.5
        
        history.avg_volume = mean_vol
        history.volume_std_dev = std_dev
        
        # Check consistency (low std dev relative to mean)
        if mean_vol > 0:
            cv = std_dev / mean_vol  # Coefficient of variation
            history.consistent_volume = cv < self.consistency_threshold
    
    def _cleanup_old_levels(self, symbol: str, current_time: float) -> None:
        """Remove levels outside history window."""
        cutoff_time = current_time - self.history_window
        
        # Clean bids
        to_remove = [
            price for price, hist in self.bid_levels[symbol].items()
            if hist.last_seen < cutoff_time
        ]
        for price in to_remove:
            del self.bid_levels[symbol][price]
        
        # Clean asks
        to_remove = [
            price for price, hist in self.ask_levels[symbol].items()
            if hist.last_seen < cutoff_time
        ]
        for price in to_remove:
            del self.ask_levels[symbol][price]
    
    def detect_icebergs(
        self,
        symbol: str,
        current_price: float,
        proximity_pct: float = 1.0
    ) -> List[IcebergPattern]:
        """
        Detect iceberg patterns near current price.
        
        Args:
            symbol: Trading symbol
            current_price: Current mid price
            proximity_pct: Only detect icebergs within X% of price
        
        Returns:
            List of detected iceberg patterns
        """
        icebergs = []
        
        # Price range to check
        price_range = current_price * (proximity_pct / 100.0)
        min_price = current_price - price_range
        max_price = current_price + price_range
        
        # Check bid levels
        for price, history in self.bid_levels[symbol].items():
            if min_price <= price <= max_price:
                pattern = self._check_iceberg_pattern(symbol, price, history)
                if pattern:
                    icebergs.append(pattern)
        
        # Check ask levels
        for price, history in self.ask_levels[symbol].items():
            if min_price <= price <= max_price:
                pattern = self._check_iceberg_pattern(symbol, price, history)
                if pattern:
                    icebergs.append(pattern)
        
        return icebergs
    
    def _check_iceberg_pattern(
        self,
        symbol: str,
        price: float,
        history: LevelHistory
    ) -> Optional[IcebergPattern]:
        """Check if level exhibits iceberg pattern."""
        current_time = time.time()
        persistence = current_time - history.first_seen
        
        # Pattern 1: Repeated Refills (strongest signal)
        if history.refill_count >= self.min_refill_count:
            confidence = min(0.85, 0.65 + history.refill_count * 0.05)
            
            pattern = IcebergPattern(
                symbol=symbol,
                price=price,
                side=history.side,
                refill_count=history.refill_count,
                avg_refill_speed_seconds=history.avg_refill_speed_seconds,
                volume_consistency_score=1.0 - (history.volume_std_dev / history.avg_volume) if history.avg_volume > 0 else 0.0,
                persistence_seconds=persistence,
                confidence=confidence,
                pattern_type="refill",
                detected_at=datetime.utcnow(),
                level_history=history
            )
            
            self.total_icebergs_detected += 1
            return pattern
        
        # Pattern 2: Consistent Volume + Persistence
        if history.consistent_volume and persistence > 120:  # 2+ minutes
            confidence = 0.70
            
            pattern = IcebergPattern(
                symbol=symbol,
                price=price,
                side=history.side,
                refill_count=history.refill_count,
                avg_refill_speed_seconds=history.avg_refill_speed_seconds,
                volume_consistency_score=1.0 - (history.volume_std_dev / history.avg_volume) if history.avg_volume > 0 else 0.0,
                persistence_seconds=persistence,
                confidence=confidence,
                pattern_type="consistent_size",
                detected_at=datetime.utcnow(),
                level_history=history
            )
            
            self.total_icebergs_detected += 1
            return pattern
        
        # Pattern 3: Price Anchoring (very persistent level)
        if persistence > 180:  # 3+ minutes
            confidence = 0.75
            
            pattern = IcebergPattern(
                symbol=symbol,
                price=price,
                side=history.side,
                refill_count=history.refill_count,
                avg_refill_speed_seconds=history.avg_refill_speed_seconds,
                volume_consistency_score=1.0 - (history.volume_std_dev / history.avg_volume) if history.avg_volume > 0 else 0.0,
                persistence_seconds=persistence,
                confidence=confidence,
                pattern_type="anchor",
                detected_at=datetime.utcnow(),
                level_history=history
            )
            
            self.total_icebergs_detected += 1
            return pattern
        
        return None
    
    def get_statistics(self) -> Dict[str, any]:
        """Get tracker statistics."""
        total_bid_levels = sum(len(levels) for levels in self.bid_levels.values())
        total_ask_levels = sum(len(levels) for levels in self.ask_levels.values())
        
        return {
            "total_levels_tracked": self.total_levels_tracked,
            "active_bid_levels": total_bid_levels,
            "active_ask_levels": total_ask_levels,
            "total_icebergs_detected": self.total_icebergs_detected,
            "symbols_tracked": len(self.bid_levels),
        }

