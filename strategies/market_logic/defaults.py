"""
Market logic strategy default parameters registry.

This module contains all default parameter values for market logic strategies.
These defaults are used when no database configuration exists and are
automatically persisted to MongoDB on first use.
"""

from typing import Any

# =============================================================================
# STRATEGY DEFAULT PARAMETERS
# =============================================================================

STRATEGY_DEFAULTS: dict[str, dict[str, Any]] = {
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
    # ==========================================================================
    # Microstructure Strategies (Order Book Analysis)
    # ==========================================================================
    "spread_liquidity": {
        "spread_threshold_bps": 10.0,
        "spread_ratio_threshold": 2.5,
        "velocity_threshold": 0.5,
        "persistence_threshold_seconds": 30.0,
        "min_depth_reduction_pct": 0.5,
        "base_confidence": 0.70,
        "lookback_ticks": 20,
        "min_signal_interval_seconds": 60.0,
    },
    "iceberg_detector": {
        "min_refill_count": 3,
        "refill_speed_threshold_seconds": 5.0,
        "consistency_threshold": 0.1,
        "persistence_threshold_seconds": 120.0,
        "level_proximity_pct": 1.0,
        "base_confidence": 0.70,
        "history_window_seconds": 300,
        "max_symbols": 100,
        "min_signal_interval_seconds": 120.0,
    },
}


# =============================================================================
# PARAMETER SCHEMAS (for validation)
# =============================================================================

PARAMETER_SCHEMAS: dict[str, dict[str, dict[str, Any]]] = {
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
    # ==========================================================================
    # Spread Liquidity Strategy
    # ==========================================================================
    "spread_liquidity": {
        "spread_threshold_bps": {
            "type": "float",
            "min": 1.0,
            "max": 100.0,
            "description": "Minimum spread in basis points to consider for signals",
            "example": 10.0,
        },
        "spread_ratio_threshold": {
            "type": "float",
            "min": 1.5,
            "max": 10.0,
            "description": "Spread ratio threshold (current / average)",
            "example": 2.5,
        },
        "velocity_threshold": {
            "type": "float",
            "min": 0.1,
            "max": 2.0,
            "description": "Minimum spread velocity (% change per second)",
            "example": 0.5,
        },
        "persistence_threshold_seconds": {
            "type": "float",
            "min": 10.0,
            "max": 300.0,
            "description": "Minimum time spread must persist above threshold",
            "example": 30.0,
        },
        "min_depth_reduction_pct": {
            "type": "float",
            "min": 0.1,
            "max": 0.9,
            "description": "Minimum depth reduction to trigger signal",
            "example": 0.5,
        },
        "base_confidence": {
            "type": "float",
            "min": 0.5,
            "max": 1.0,
            "description": "Base confidence level for signals",
            "example": 0.70,
        },
        "lookback_ticks": {
            "type": "int",
            "min": 5,
            "max": 100,
            "description": "Number of ticks for rolling average calculation",
            "example": 20,
        },
        "min_signal_interval_seconds": {
            "type": "float",
            "min": 30.0,
            "max": 600.0,
            "description": "Minimum time between signals per symbol",
            "example": 60.0,
        },
    },
    # ==========================================================================
    # Iceberg Detector Strategy
    # ==========================================================================
    "iceberg_detector": {
        "min_refill_count": {
            "type": "int",
            "min": 2,
            "max": 10,
            "description": "Minimum number of refills to detect iceberg",
            "example": 3,
        },
        "refill_speed_threshold_seconds": {
            "type": "float",
            "min": 1.0,
            "max": 30.0,
            "description": "Maximum refill time to consider fast refill",
            "example": 5.0,
        },
        "consistency_threshold": {
            "type": "float",
            "min": 0.05,
            "max": 0.5,
            "description": "Maximum std dev ratio for consistent volume",
            "example": 0.1,
        },
        "persistence_threshold_seconds": {
            "type": "float",
            "min": 60.0,
            "max": 600.0,
            "description": "Minimum persistence time for anchoring pattern",
            "example": 120.0,
        },
        "level_proximity_pct": {
            "type": "float",
            "min": 0.1,
            "max": 5.0,
            "description": "Only signal if price within X% of iceberg level",
            "example": 1.0,
        },
        "base_confidence": {
            "type": "float",
            "min": 0.5,
            "max": 1.0,
            "description": "Base confidence level for signals",
            "example": 0.70,
        },
        "history_window_seconds": {
            "type": "int",
            "min": 60,
            "max": 900,
            "description": "Order book history tracking window",
            "example": 300,
        },
        "max_symbols": {
            "type": "int",
            "min": 10,
            "max": 200,
            "description": "Maximum symbols to track simultaneously",
            "example": 100,
        },
        "min_signal_interval_seconds": {
            "type": "float",
            "min": 60.0,
            "max": 600.0,
            "description": "Minimum time between signals per symbol",
            "example": 120.0,
        },
    },
}


# =============================================================================
# STRATEGY METADATA
# =============================================================================

STRATEGY_METADATA: dict[str, dict[str, str]] = {
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
    # Microstructure Strategies
    "spread_liquidity": {
        "name": "Spread Liquidity",
        "description": "Detects liquidity events through bid-ask spread widening and narrowing patterns",
        "category": "Microstructure",
        "type": "liquidity",
    },
    "iceberg_detector": {
        "name": "Iceberg Detector",
        "description": "Identifies large hidden institutional orders through order book pattern analysis",
        "category": "Microstructure",
        "type": "pattern_recognition",
    },
}


def get_strategy_defaults(strategy_id: str) -> dict[str, Any]:
    """
    Get default parameters for a strategy.

    Args:
        strategy_id: Strategy identifier

    Returns:
        Dictionary of default parameters
    """
    return STRATEGY_DEFAULTS.get(strategy_id, {})


def get_parameter_schema(strategy_id: str) -> dict[str, dict[str, Any]]:
    """
    Get parameter schema for a strategy.

    Args:
        strategy_id: Strategy identifier

    Returns:
        Dictionary of parameter schemas
    """
    return PARAMETER_SCHEMAS.get(strategy_id, {})


def get_strategy_metadata(strategy_id: str) -> dict[str, str]:
    """
    Get metadata for a strategy.

    Args:
        strategy_id: Strategy identifier

    Returns:
        Dictionary of strategy metadata
    """
    return STRATEGY_METADATA.get(
        strategy_id,
        {
            "name": strategy_id.replace("_", " ").title(),
            "description": "No description available",
            "category": "Market Logic",
            "type": "unknown",
        },
    )


def list_all_strategies() -> list[str]:
    """Get list of all strategy IDs."""
    return list(STRATEGY_DEFAULTS.keys())


def validate_parameters(
    strategy_id: str, parameters: dict[str, Any]
) -> tuple[bool, list[str]]:
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
