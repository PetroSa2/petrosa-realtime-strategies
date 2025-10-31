"""
Adapters for transforming internal models to external contracts.
"""

from .signal_adapter import transform_signal_for_tradeengine

__all__ = ["transform_signal_for_tradeengine"]
