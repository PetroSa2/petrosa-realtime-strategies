"""
Signal adapter for transforming signals to TradeEngine format.

This module provides transformation functions to convert internal Signal models
to the format expected by the TradeEngine service.
"""

from typing import Any, Dict

from strategies.models.signals import Signal


def transform_signal_for_tradeengine(signal: Signal) -> dict[str, Any]:
    """
    Transform a Signal object to the format expected by TradeEngine.

    Args:
        signal: Signal object to transform

    Returns:
        Dictionary representation of the signal in TradeEngine format
    """
    # Convert signal to dictionary with JSON-serializable types
    # mode="json" handles datetime, enum, and other special type serialization
    signal_dict = signal.model_dump(mode="json")

    # Return raw signal format - TradeEngine expects the original field names and enum values
    return signal_dict
