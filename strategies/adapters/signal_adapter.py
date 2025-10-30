"""
Signal adapter for transforming realtime-strategies signals to tradeengine contract.

This module provides transformation functions to convert the internal Signal model
used by realtime-strategies to the Signal contract expected by the tradeengine service.
"""

from datetime import datetime
from typing import Any
from uuid import uuid4

from strategies.models.signals import Signal, SignalAction, SignalType


def transform_signal_for_tradeengine(signal: Signal) -> dict[str, Any]:
    """
    Transform a realtime-strategies Signal to tradeengine contract format.

    Args:
        signal: Internal Signal object from realtime-strategies

    Returns:
        Dictionary matching tradeengine Signal contract

    Example:
        >>> signal = Signal(
        ...     symbol="BTCUSDT",
        ...     signal_type=SignalType.BUY,
        ...     signal_action=SignalAction.OPEN_LONG,
        ...     confidence=SignalConfidence.HIGH,
        ...     confidence_score=0.85,
        ...     price=50000.0,
        ...     strategy_name="spread_liquidity"
        ... )
        >>> transformed = transform_signal_for_tradeengine(signal)
        >>> assert transformed["action"] == "buy"
        >>> assert transformed["confidence"] == 0.85
    """

    # Map signal_type to lowercase action
    signal_type_mapping = {
        SignalType.BUY: "buy",
        SignalType.SELL: "sell",
        SignalType.HOLD: "hold",
    }

    # Map signal_action to action
    action_mapping = {
        SignalAction.OPEN_LONG: "buy",
        SignalAction.OPEN_SHORT: "sell",
        SignalAction.CLOSE_LONG: "close",
        SignalAction.CLOSE_SHORT: "close",
        SignalAction.HOLD: "hold",
    }

    # Generate unique IDs
    signal_id = str(uuid4())  # Generate UUID for this signal
    strategy_id = f"{signal.strategy_name}_{signal.symbol}"

    # Map to tradeengine contract
    transformed = {
        # Core signal information
        "id": signal_id,
        "signal_id": signal_id,
        "strategy_id": strategy_id,
        "strategy_mode": "deterministic",
        # Trading parameters
        "symbol": signal.symbol,
        "signal_type": signal_type_mapping.get(signal.signal_type, "hold"),
        "action": action_mapping.get(signal.signal_action, "hold"),
        "confidence": signal.confidence_score,  # Use numeric confidence_score
        "strength": _map_confidence_to_strength(signal.confidence_score),
        # Price and quantity information
        "price": signal.price,
        "quantity": _calculate_default_quantity(
            signal.price, signal.confidence_score
        ),
        "current_price": signal.price,
        "target_price": signal.price,
        # Source and metadata
        "source": "realtime-strategies",
        "strategy": signal.strategy_name,
        "metadata": {
            **signal.metadata,
            "original_signal_type": signal.signal_type.value,
            "original_signal_action": signal.signal_action.value,
            "original_confidence": signal.confidence.value,
        },
        # Timeframe information
        "timeframe": signal.metadata.get("timeframe", "tick"),
        # Order configuration
        "order_type": "market",
        "time_in_force": "GTC",
        # Risk management - add defaults
        "stop_loss": None,
        "stop_loss_pct": _calculate_default_stop_loss(signal.confidence_score),
        "take_profit": None,
        "take_profit_pct": _calculate_default_take_profit(signal.confidence_score),
        # Timestamp
        "timestamp": (
            signal.timestamp.isoformat()
            if isinstance(signal.timestamp, datetime)
            else signal.timestamp
        ),
    }

    return transformed


def _map_confidence_to_strength(confidence_score: float) -> str:
    """
    Map confidence score (0-1) to strength level.

    Args:
        confidence_score: Confidence score between 0 and 1

    Returns:
        Strength level: "weak", "medium", "strong", or "extreme"
    """
    if confidence_score >= 0.9:
        return "extreme"
    elif confidence_score >= 0.7:
        return "strong"
    elif confidence_score >= 0.5:
        return "medium"
    else:
        return "weak"


def _calculate_default_quantity(price: float, confidence_score: float) -> float:
    """
    Calculate a default quantity based on price and confidence.

    This is a placeholder implementation. In production, this should
    integrate with portfolio management and position sizing logic.

    Args:
        price: Current asset price
        confidence_score: Signal confidence (0-1)

    Returns:
        Default quantity (minimum viable quantity for now)
    """
    # For now, return a minimal quantity
    # This should be replaced with actual position sizing logic
    # based on portfolio value, risk management, etc.
    if price > 10000:  # BTC, ETH range
        return round(100 / price, 4)  # $100 worth
    elif price > 100:  # Mid-cap coins
        return round(50 / price, 2)  # $50 worth
    else:  # Low-price coins
        return round(20 / price, 2)  # $20 worth


def _calculate_default_stop_loss(confidence_score: float) -> float:
    """
    Calculate default stop loss percentage based on confidence.

    Higher confidence = tighter stop loss

    Args:
        confidence_score: Signal confidence (0-1)

    Returns:
        Stop loss percentage (0-1)
    """
    if confidence_score >= 0.8:
        return 0.02  # 2% for high confidence
    elif confidence_score >= 0.6:
        return 0.03  # 3% for medium confidence
    else:
        return 0.05  # 5% for low confidence


def _calculate_default_take_profit(confidence_score: float) -> float:
    """
    Calculate default take profit percentage based on confidence.

    Higher confidence = higher take profit target

    Args:
        confidence_score: Signal confidence (0-1)

    Returns:
        Take profit percentage (0-1)
    """
    if confidence_score >= 0.8:
        return 0.05  # 5% for high confidence
    elif confidence_score >= 0.6:
        return 0.04  # 4% for medium confidence
    else:
        return 0.03  # 3% for low confidence

