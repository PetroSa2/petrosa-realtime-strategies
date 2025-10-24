"""
Market Logic Strategies Package.

This package contains advanced market logic strategies adapted from the
QTZD MS Cash NoSQL service for cryptocurrency trading, plus microstructure
strategies for order book analysis.
"""

from .btc_dominance import BitcoinDominanceStrategy
from .cross_exchange_spread import CrossExchangeSpreadStrategy
from .iceberg_detector import IcebergDetectorStrategy
from .onchain_metrics import OnChainMetricsStrategy
from .spread_liquidity import SpreadLiquidityStrategy

__all__ = [
    "BitcoinDominanceStrategy",
    "CrossExchangeSpreadStrategy",
    "OnChainMetricsStrategy",
    "IcebergDetectorStrategy",
    "SpreadLiquidityStrategy",
]
