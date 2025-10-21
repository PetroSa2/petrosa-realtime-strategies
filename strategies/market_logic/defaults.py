"""
Market logic strategy default parameters registry.

This module contains all default parameter values for market logic strategies.
These defaults are used when no database configuration exists and are
automatically persisted to MongoDB on first use.
"""

from typing import Any, Dict

# =============================================================================
# STRATEGY DEFAULT PARAMETERS
# =============================================================================

STRATEGY_DEFAULTS: Dict[str, Dict[str, Any]] = {
    # ==========================================================================
    # Realtime Data Strategies (WebSocket-based)
    # ==========================================================================
    
    "orderbook_skew": {
        "top_levels": 5,
        "buy_threshold": 1.2,
        "sell_threshold": 0.8,
        "min_spread_percent": 0.1,
        "base_confidence": 0.70,
        "imbalance_weight": 0.6,
        "spread_weight": 0.4,
        "min_total_volume": 0.001,
    },
    
    "trade_momentum": {
        "price_weight": 0.4,
        "quantity_weight": 0.3,
        "maker_weight": 0.3,
        "buy_threshold": 0.7,
        "sell_threshold": -0.7,
        "min_quantity": 0.001,
        "base_confidence": 0.68,
        "time_decay_seconds": 300,
        "momentum_window": 10,
    },
    
    "ticker_velocity": {
        "time_window": 60,
        "buy_threshold": 0.5,
        "sell_threshold": -0.5,
        "min_price_change": 0.1,
        "base_confidence": 0.65,
        "acceleration_weight": 0.5,
        "volume_confirmation": True,
        "min_volume_change": 0.2,
    },
    
    # ==========================================================================
    # Market Logic Strategies (Analysis-based)
    # ==========================================================================
    
    "btc_dominance": {
        "high_threshold": 70.0,
        "low_threshold": 40.0,
        "change_threshold": 5.0,
        "window_hours": 24,
        "min_signal_interval": 14400,  # 4 hours in seconds
        "base_confidence_high": 0.80,
        "base_confidence_low": 0.75,
        "momentum_confidence": 0.70,
    },
    
    "cross_exchange_spread": {
        "spread_threshold_percent": 0.5,
        "min_signal_interval": 300,  # 5 minutes in seconds
        "max_position_size": 500,
        "exchanges": ["binance", "coinbase"],
        "persistent_spread_periods": 3,
        "base_confidence": 0.75,
        "high_spread_threshold": 1.0,
        "high_spread_confidence": 0.85,
    },
    
    "onchain_metrics": {
        "whale_threshold_btc": 100,
        "whale_threshold_eth": 1000,
        "exchange_flow_threshold_percent": 10.0,
        "min_signal_interval": 3600,  # 1 hour in seconds
        "accumulation_periods": 24,
        "distribution_periods": 12,
        "base_confidence": 0.77,
        "strong_signal_confidence": 0.85,
    },
}


# =============================================================================
# PARAMETER SCHEMAS (for validation)
# =============================================================================

PARAMETER_SCHEMAS: Dict[str, Dict[str, Dict[str, Any]]] = {
    # ==========================================================================
    # Orderbook Skew Strategy
    # ==========================================================================
    "orderbook_skew": {
        "top_levels": {
            "type": "int",
            "min": 1,
            "max": 20,
            "description": "Number of top order book levels to analyze",
            "example": 5,
        },
        "buy_threshold": {
            "type": "float",
            "min": 1.0,
            "max": 3.0,
            "description": "Bid/ask ratio threshold for buy signal (>1.0 means more bids)",
            "example": 1.2,
        },
        "sell_threshold": {
            "type": "float",
            "min": 0.3,
            "max": 1.0,
            "description": "Bid/ask ratio threshold for sell signal (<1.0 means more asks)",
            "example": 0.8,
        },
        "min_spread_percent": {
            "type": "float",
            "min": 0.01,
            "max": 1.0,
            "description": "Minimum spread percentage to consider signal valid",
            "example": 0.1,
        },
        "base_confidence": {
            "type": "float",
            "min": 0.5,
            "max": 1.0,
            "description": "Base confidence level for signals",
            "example": 0.70,
        },
        "imbalance_weight": {
            "type": "float",
            "min": 0.0,
            "max": 1.0,
            "description": "Weight given to order book imbalance in signal calculation",
            "example": 0.6,
        },
        "spread_weight": {
            "type": "float",
            "min": 0.0,
            "max": 1.0,
            "description": "Weight given to spread in signal calculation",
            "example": 0.4,
        },
        "min_total_volume": {
            "type": "float",
            "min": 0.0001,
            "max": 10.0,
            "description": "Minimum total volume (bid+ask) to process",
            "example": 0.001,
        },
    },
    
    # ==========================================================================
    # Trade Momentum Strategy
    # ==========================================================================
    "trade_momentum": {
        "price_weight": {
            "type": "float",
            "min": 0.0,
            "max": 1.0,
            "description": "Weight given to price momentum in signal calculation",
            "example": 0.4,
        },
        "quantity_weight": {
            "type": "float",
            "min": 0.0,
            "max": 1.0,
            "description": "Weight given to quantity momentum in signal calculation",
            "example": 0.3,
        },
        "maker_weight": {
            "type": "float",
            "min": 0.0,
            "max": 1.0,
            "description": "Weight given to maker/taker ratio in signal calculation",
            "example": 0.3,
        },
        "buy_threshold": {
            "type": "float",
            "min": 0.3,
            "max": 1.0,
            "description": "Momentum score threshold for buy signal",
            "example": 0.7,
        },
        "sell_threshold": {
            "type": "float",
            "min": -1.0,
            "max": -0.3,
            "description": "Momentum score threshold for sell signal (negative)",
            "example": -0.7,
        },
        "min_quantity": {
            "type": "float",
            "min": 0.0001,
            "max": 1.0,
            "description": "Minimum trade quantity to consider",
            "example": 0.001,
        },
        "base_confidence": {
            "type": "float",
            "min": 0.5,
            "max": 1.0,
            "description": "Base confidence level for signals",
            "example": 0.68,
        },
        "time_decay_seconds": {
            "type": "int",
            "min": 60,
            "max": 600,
            "description": "Time window for momentum decay (seconds)",
            "example": 300,
        },
        "momentum_window": {
            "type": "int",
            "min": 5,
            "max": 50,
            "description": "Number of recent trades to analyze",
            "example": 10,
        },
    },
    
    # ==========================================================================
    # Ticker Velocity Strategy
    # ==========================================================================
    "ticker_velocity": {
        "time_window": {
            "type": "int",
            "min": 30,
            "max": 300,
            "description": "Time window for velocity calculation (seconds)",
            "example": 60,
        },
        "buy_threshold": {
            "type": "float",
            "min": 0.1,
            "max": 2.0,
            "description": "Velocity threshold for buy signal",
            "example": 0.5,
        },
        "sell_threshold": {
            "type": "float",
            "min": -2.0,
            "max": -0.1,
            "description": "Velocity threshold for sell signal (negative)",
            "example": -0.5,
        },
        "min_price_change": {
            "type": "float",
            "min": 0.01,
            "max": 1.0,
            "description": "Minimum price change percentage to generate signal",
            "example": 0.1,
        },
        "base_confidence": {
            "type": "float",
            "min": 0.5,
            "max": 1.0,
            "description": "Base confidence level for signals",
            "example": 0.65,
        },
        "acceleration_weight": {
            "type": "float",
            "min": 0.0,
            "max": 1.0,
            "description": "Weight given to price acceleration in signal calculation",
            "example": 0.5,
        },
        "volume_confirmation": {
            "type": "bool",
            "description": "Whether to require volume confirmation for signals",
            "example": True,
        },
        "min_volume_change": {
            "type": "float",
            "min": 0.1,
            "max": 2.0,
            "description": "Minimum volume change for confirmation (if enabled)",
            "example": 0.2,
        },
    },
    
    # ==========================================================================
    # BTC Dominance Strategy
    # ==========================================================================
    "btc_dominance": {
        "high_threshold": {
            "type": "float",
            "min": 60.0,
            "max": 90.0,
            "description": "High dominance threshold percentage",
            "example": 70.0,
        },
        "low_threshold": {
            "type": "float",
            "min": 30.0,
            "max": 50.0,
            "description": "Low dominance threshold percentage",
            "example": 40.0,
        },
        "change_threshold": {
            "type": "float",
            "min": 1.0,
            "max": 15.0,
            "description": "Minimum dominance change percentage for signal",
            "example": 5.0,
        },
        "window_hours": {
            "type": "int",
            "min": 12,
            "max": 72,
            "description": "Time window for dominance calculation (hours)",
            "example": 24,
        },
        "min_signal_interval": {
            "type": "int",
            "min": 3600,
            "max": 86400,
            "description": "Minimum time between signals (seconds)",
            "example": 14400,
        },
    },
    
    # ==========================================================================
    # Cross-Exchange Spread Strategy
    # ==========================================================================
    "cross_exchange_spread": {
        "spread_threshold_percent": {
            "type": "float",
            "min": 0.1,
            "max": 5.0,
            "description": "Minimum spread percentage for signal",
            "example": 0.5,
        },
        "min_signal_interval": {
            "type": "int",
            "min": 60,
            "max": 3600,
            "description": "Minimum time between signals (seconds)",
            "example": 300,
        },
        "max_position_size": {
            "type": "int",
            "min": 100,
            "max": 10000,
            "description": "Maximum position size in USDT",
            "example": 500,
        },
    },
    
    # ==========================================================================
    # On-Chain Metrics Strategy
    # ==========================================================================
    "onchain_metrics": {
        "whale_threshold_btc": {
            "type": "float",
            "min": 10,
            "max": 1000,
            "description": "Whale transaction threshold (BTC)",
            "example": 100,
        },
        "whale_threshold_eth": {
            "type": "float",
            "min": 100,
            "max": 10000,
            "description": "Whale transaction threshold (ETH)",
            "example": 1000,
        },
        "exchange_flow_threshold_percent": {
            "type": "float",
            "min": 5.0,
            "max": 50.0,
            "description": "Exchange flow change threshold percentage",
            "example": 10.0,
        },
        "min_signal_interval": {
            "type": "int",
            "min": 1800,
            "max": 86400,
            "description": "Minimum time between signals (seconds)",
            "example": 3600,
        },
    },
}


# =============================================================================
# STRATEGY METADATA
# =============================================================================

STRATEGY_METADATA: Dict[str, Dict[str, str]] = {
    # Realtime Data Strategies
    "orderbook_skew": {
        "name": "Order Book Skew",
        "description": "Analyzes order book imbalance to detect buy/sell pressure from depth data",
        "category": "Realtime Data",
        "type": "microstructure",
    },
    
    "trade_momentum": {
        "name": "Trade Momentum",
        "description": "Tracks recent trade flow to identify momentum shifts in market direction",
        "category": "Realtime Data",
        "type": "momentum",
    },
    
    "ticker_velocity": {
        "name": "Ticker Velocity",
        "description": "Measures price velocity and acceleration to capture rapid price movements",
        "category": "Realtime Data",
        "type": "velocity",
    },
    
    # Market Logic Strategies
    "btc_dominance": {
        "name": "Bitcoin Dominance",
        "description": "Monitors Bitcoin market dominance to generate rotation signals between BTC and altcoins",
        "category": "Market Logic",
        "type": "rotation",
    },
    
    "cross_exchange_spread": {
        "name": "Cross-Exchange Spread",
        "description": "Monitors price differences across exchanges to identify arbitrage opportunities",
        "category": "Market Logic",
        "type": "arbitrage",
    },
    
    "onchain_metrics": {
        "name": "On-Chain Metrics",
        "description": "Analyzes blockchain data for whale activity and exchange flows",
        "category": "Market Logic",
        "type": "fundamental",
    },
}


def get_strategy_defaults(strategy_id: str) -> Dict[str, Any]:
    """
    Get default parameters for a strategy.
    
    Args:
        strategy_id: Strategy identifier
        
    Returns:
        Dictionary of default parameters
    """
    return STRATEGY_DEFAULTS.get(strategy_id, {})


def get_parameter_schema(strategy_id: str) -> Dict[str, Dict[str, Any]]:
    """
    Get parameter schema for a strategy.
    
    Args:
        strategy_id: Strategy identifier
        
    Returns:
        Dictionary of parameter schemas
    """
    return PARAMETER_SCHEMAS.get(strategy_id, {})


def get_strategy_metadata(strategy_id: str) -> Dict[str, str]:
    """
    Get metadata for a strategy.
    
    Args:
        strategy_id: Strategy identifier
        
    Returns:
        Dictionary of strategy metadata
    """
    return STRATEGY_METADATA.get(strategy_id, {
        "name": strategy_id.replace("_", " ").title(),
        "description": "No description available",
        "category": "Market Logic",
        "type": "unknown",
    })


def list_all_strategies() -> list[str]:
    """Get list of all strategy IDs."""
    return list(STRATEGY_DEFAULTS.keys())


def validate_parameters(strategy_id: str, parameters: Dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Validate parameters against schema.
    
    Args:
        strategy_id: Strategy identifier
        parameters: Parameters to validate
        
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    schema = get_parameter_schema(strategy_id)
    if not schema:
        # No schema defined, accept all parameters
        return True, []
    
    errors = []
    
    for param_name, param_value in parameters.items():
        if param_name not in schema:
            errors.append(f"Unknown parameter: {param_name}")
            continue
        
        param_schema = schema[param_name]
        param_type = param_schema.get("type")
        
        # Type validation
        if param_type == "int" and not isinstance(param_value, int):
            errors.append(f"{param_name} must be an integer")
            continue
        elif param_type == "float" and not isinstance(param_value, (int, float)):
            errors.append(f"{param_name} must be a number")
            continue
        elif param_type == "bool" and not isinstance(param_value, bool):
            errors.append(f"{param_name} must be a boolean")
            continue
        elif param_type == "str" and not isinstance(param_value, str):
            errors.append(f"{param_name} must be a string")
            continue
        
        # Range validation for numeric types
        if param_type in ("int", "float"):
            if "min" in param_schema and param_value < param_schema["min"]:
                errors.append(
                    f"{param_name} must be >= {param_schema['min']}, got {param_value}"
                )
            if "max" in param_schema and param_value > param_schema["max"]:
                errors.append(
                    f"{param_name} must be <= {param_schema['max']}, got {param_value}"
                )
    
    return len(errors) == 0, errors

