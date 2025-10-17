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
    "btc_dominance": {
        "high_threshold": {
            "type": "float",
            "min": 60.0,
            "max": 90.0,
            "description": "High dominance threshold percentage"
        },
        "low_threshold": {
            "type": "float",
            "min": 30.0,
            "max": 50.0,
            "description": "Low dominance threshold percentage"
        },
        "change_threshold": {
            "type": "float",
            "min": 1.0,
            "max": 15.0,
            "description": "Minimum dominance change percentage for signal"
        },
        "window_hours": {
            "type": "int",
            "min": 12,
            "max": 72,
            "description": "Time window for dominance calculation (hours)"
        },
        "min_signal_interval": {
            "type": "int",
            "min": 3600,
            "max": 86400,
            "description": "Minimum time between signals (seconds)"
        },
    },
    
    "cross_exchange_spread": {
        "spread_threshold_percent": {
            "type": "float",
            "min": 0.1,
            "max": 5.0,
            "description": "Minimum spread percentage for signal"
        },
        "min_signal_interval": {
            "type": "int",
            "min": 60,
            "max": 3600,
            "description": "Minimum time between signals (seconds)"
        },
        "max_position_size": {
            "type": "int",
            "min": 100,
            "max": 10000,
            "description": "Maximum position size in USDT"
        },
    },
    
    "onchain_metrics": {
        "whale_threshold_btc": {
            "type": "float",
            "min": 10,
            "max": 1000,
            "description": "Whale transaction threshold (BTC)"
        },
        "whale_threshold_eth": {
            "type": "float",
            "min": 100,
            "max": 10000,
            "description": "Whale transaction threshold (ETH)"
        },
        "exchange_flow_threshold_percent": {
            "type": "float",
            "min": 5.0,
            "max": 50.0,
            "description": "Exchange flow change threshold percentage"
        },
        "min_signal_interval": {
            "type": "int",
            "min": 1800,
            "max": 86400,
            "description": "Minimum time between signals (seconds)"
        },
    },
}


# =============================================================================
# STRATEGY METADATA
# =============================================================================

STRATEGY_METADATA: Dict[str, Dict[str, str]] = {
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

