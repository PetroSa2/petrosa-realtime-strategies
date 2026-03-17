"""
Signal adapter for transforming realtime-strategies signals to tradeengine contract.

This module provides transformation functions to convert the internal Signal model
used by realtime-strategies to the Signal contract expected by the tradeengine service.
"""

from datetime import datetime
from typing import Any
from uuid import uuid4

from strategies.models.signals import Signal

# Risk management constants
HIGH_CONFIDENCE_THRESHOLD = 0.8
MEDIUM_CONFIDENCE_THRESHOLD = 0.6

# Stop loss percentages by confidence level
STOP_LOSS_HIGH_CONFIDENCE = 0.02  # 2% for high confidence signals
STOP_LOSS_MEDIUM_CONFIDENCE = 0.03  # 3% for medium confidence signals
STOP_LOSS_LOW_CONFIDENCE = 0.05  # 5% for low confidence signals

# Take profit percentages by confidence level
TAKE_PROFIT_HIGH_CONFIDENCE = 0.05  # 5% for high confidence signals
TAKE_PROFIT_MEDIUM_CONFIDENCE = 0.04  # 4% for medium confidence signals
TAKE_PROFIT_LOW_CONFIDENCE = 0.03  # 3% for low confidence signals


def transform_signal_for_tradeengine(signal: Signal) -> dict[str, Any]:
    """
    Transform a realtime-strategies Signal to tradeengine contract format.

    Args:
        signal: Internal Signal object from realtime-strategies

    Returns:
        Dictionary matching tradeengine Signal contract
    """

    # Generate unique IDs if missing
    signal_id = signal.signal_id or str(uuid4())
    strategy_id = signal.strategy_id

    # Get data using model_dump
    signal_data = signal.model_dump()

    # Map to tradeengine contract
    transformed = {
        # Core signal information
        "id": signal_id,
        "signal_id": signal_id,
        "strategy_id": strategy_id,
        "strategy_mode": signal_data.get("strategy_mode", "deterministic"),
        # Trading parameters
        "symbol": signal.symbol,
        "action": signal.action,
        "confidence": signal.confidence,
        "strength": signal_data.get("strength", "medium"),
        # Price and quantity information
        "price": signal.price,
        "quantity": signal.quantity
        or _calculate_default_quantity(signal.price, signal.confidence),
        "current_price": signal.current_price,
        "target_price": signal_data.get("target_price") or signal.price,
        # Source and metadata
        "source": signal.source,
        "strategy": signal.strategy or strategy_id,
        "metadata": signal.metadata,
        # Timeframe information
        "timeframe": signal.timeframe,
        # Order configuration
        "order_type": signal.order_type,
        "time_in_force": signal.time_in_force,
        # Risk management - ensure they exist
        "stop_loss": signal.stop_loss,
        "stop_loss_pct": signal.stop_loss_pct
        or _calculate_default_stop_loss(signal.confidence),
        "take_profit": signal.take_profit,
        "take_profit_pct": signal.take_profit_pct
        or _calculate_default_take_profit(signal.confidence),
        # Timestamp
        "timestamp": (
            signal.timestamp.isoformat()
            if isinstance(signal.timestamp, datetime)
            else signal.timestamp
        ),
    }

    # MANDATORY: If stop_loss price is missing for buy/sell, calculate it from percentage
    if transformed["action"] in ["buy", "sell"]:
        if transformed["stop_loss"] is None:
            price = transformed["price"]
            pct = transformed["stop_loss_pct"]
            multiplier = 1.0 - pct if transformed["action"] == "buy" else 1.0 + pct
            transformed["stop_loss"] = price * multiplier

        if transformed["take_profit"] is None:
            price = transformed["price"]
            pct = transformed["take_profit_pct"]
            multiplier = 1.0 + pct if transformed["action"] == "buy" else 1.0 - pct
            transformed["take_profit"] = price * multiplier

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
    """Calculate a default quantity based on price and confidence."""
    if price <= 0:
        return 0.0
    if price > 10000:  # BTC, ETH range
        return round(100 / price, 4)  # $100 worth
    elif price > 100:  # Mid-cap coins
        return round(50 / price, 2)  # $50 worth
    else:  # Low-price coins
        return round(20 / price, 2)  # $20 worth


def _calculate_default_stop_loss(confidence_score: float) -> float:
    """Calculate default stop loss percentage based on confidence."""
    if confidence_score >= HIGH_CONFIDENCE_THRESHOLD:
        return STOP_LOSS_HIGH_CONFIDENCE
    elif confidence_score >= MEDIUM_CONFIDENCE_THRESHOLD:
        return STOP_LOSS_MEDIUM_CONFIDENCE
    else:
        return STOP_LOSS_LOW_CONFIDENCE


def _calculate_default_take_profit(confidence_score: float) -> float:
    """Calculate default take profit percentage based on confidence."""
    if confidence_score >= HIGH_CONFIDENCE_THRESHOLD:
        return TAKE_PROFIT_HIGH_CONFIDENCE
    elif confidence_score >= MEDIUM_CONFIDENCE_THRESHOLD:
        return TAKE_PROFIT_MEDIUM_CONFIDENCE
    else:
        return TAKE_PROFIT_LOW_CONFIDENCE
