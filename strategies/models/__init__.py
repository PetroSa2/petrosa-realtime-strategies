"""
Data models for the Petrosa Realtime Strategies service.

This package contains Pydantic models for market data and trading signals
used throughout the service.
"""

from .market_data import DepthUpdate, MarketDataMessage, TickerData, TradeData
from .signals import Signal, SignalAction, SignalConfidence, SignalType, StrategySignal

__all__ = [
    # Market data models
    "DepthUpdate",
    "TradeData",
    "TickerData",
    "MarketDataMessage",
    # Signal models
    "Signal",
    "SignalType",
    "SignalAction",
    "SignalConfidence",
    "StrategySignal",
]
