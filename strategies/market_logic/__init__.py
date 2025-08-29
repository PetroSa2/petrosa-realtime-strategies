"""
Market Logic Strategies Package.

This package contains advanced market logic strategies adapted from the 
QTZD MS Cash NoSQL service for cryptocurrency trading.
"""

from .btc_dominance import BitcoinDominanceStrategy
from .cross_exchange_spread import CrossExchangeSpreadStrategy
from .onchain_metrics import OnChainMetricsStrategy

__all__ = [
    "BitcoinDominanceStrategy",
    "CrossExchangeSpreadStrategy", 
    "OnChainMetricsStrategy",
]
