"""
FastAPI routes for strategy configuration management.

Provides comprehensive REST API for runtime configuration of trading strategies.
All endpoints are LLM-compatible and include detailed documentation.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Path, Query, status

from strategies.api.response_models import (
    APIResponse,
    AuditTrailItem,
    ConfigResponse,
    ConfigUpdateRequest,
    ParameterSchemaItem,
    StrategyListItem,
)
from strategies.market_logic.defaults import (
    get_parameter_schema,
    get_strategy_defaults,
    get_strategy_metadata,
)
from strategies.services.config_manager import StrategyConfigManager

logger = logging.getLogger(__name__)

# Router for configuration endpoints
router = APIRouter(prefix="/api/v1", tags=["configuration"])

# Global config manager instance (will be injected on startup)
_config_manager: Optional[StrategyConfigManager] = None


def set_config_manager(manager: StrategyConfigManager) -> None:
    """Set the global config manager instance."""
    global _config_manager
    _config_manager = manager


def get_config_manager() -> StrategyConfigManager:
    """Get the global config manager instance."""
    if _config_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Configuration manager not initialized",
        )
    return _config_manager


@router.get(
    "/strategies",
    response_model=APIResponse,
    summary="List all trading strategies",
    description="""
    **For LLM Agents**: Use this endpoint to discover all available trading strategies
    and their current configuration status.

    Returns a list of all strategies with:
    - Basic metadata (name, description)
    - Configuration status (has global config, symbol overrides)
    - Parameter count

    **Use Case**: Start here to see what strategies exist before modifying their configurations.

    **Example Response**:
    ```json
    {
      "success": true,
      "data": [
        {
          "strategy_id": "orderbook_skew",
          "name": "Order Book Skew",
          "description": "Analyzes order book imbalance...",
          "has_global_config": true,
          "symbol_overrides": ["BTCUSDT", "ETHUSDT"],
          "parameter_count": 8
        }
      ]
    }
    ```

    **Next Steps**:
    1. Pick a strategy from the list
    2. Use `GET /strategies/{strategy_id}/schema` to see available parameters
    3. Use `GET /strategies/{strategy_id}/config` to see current settings
    4. Use `POST /strategies/{strategy_id}/config` to modify settings
    """,
)
async def list_strategies():
    """
    List all available trading strategies with their configuration status.

    This endpoint provides an overview of all strategies in the system,
    showing which ones have custom configurations and which symbols have
    strategy-specific overrides.
    """
    try:
        manager = get_config_manager()
        strategies = await manager.list_strategies()

        strategy_list = [StrategyListItem(**strategy) for strategy in strategies]

        return APIResponse(
            success=True,
            data=strategy_list,
            metadata={"total_count": len(strategy_list), "endpoint": "list_strategies"},
        )
    except Exception as e:
        logger.error(f"Error listing strategies: {e}")
        return APIResponse(
            success=False, error={"code": "INTERNAL_ERROR", "message": str(e)}
        )


@router.get(
    "/strategies/{strategy_id}/schema",
    response_model=APIResponse,
    summary="Get parameter schema for a strategy",
    description="""
    **For LLM Agents**: Use this endpoint to understand what parameters a strategy accepts
    BEFORE attempting to modify its configuration.

    Returns detailed schema for each parameter including:
    - Data type (int, float, bool, str)
    - Valid range (min/max for numbers)
    - Default value
    - Description of what the parameter controls
    - Example valid value

    **Use Case**: Always check the schema before calling POST /strategies/{strategy_id}/config
    to ensure you provide valid parameter values.

    **Example Request**: `GET /api/v1/strategies/orderbook_skew/schema`

    **Parameter Validation**: The system will reject updates that don't conform to the schema
    (e.g., values outside min/max range, wrong data types).
    """,
)
async def get_strategy_schema(
    strategy_id: str = Path(
        ..., description="Strategy identifier (e.g., 'orderbook_skew')"
    ),
):
    """
    Get parameter schema for a strategy.

    Returns the complete schema definition for all configurable parameters,
    including types, constraints, and descriptions.
    """
    try:
        schema = get_parameter_schema(strategy_id)
        defaults = get_strategy_defaults(strategy_id)

        if not defaults:
            return APIResponse(
                success=False,
                error={
                    "code": "NOT_FOUND",
                    "message": f"Strategy not found: {strategy_id}",
                    "suggestion": "Use GET /api/v1/strategies to see available strategies",
                },
            )

        schema_items = []
        for param_name, param_value in defaults.items():
            param_schema = schema.get(param_name, {})
            schema_items.append(
                ParameterSchemaItem(
                    name=param_name,
                    type=param_schema.get("type", type(param_value).__name__),
                    description=param_schema.get(
                        "description", f"Parameter: {param_name}"
                    ),
                    default=param_value,
                    min=param_schema.get("min"),
                    max=param_schema.get("max"),
                    allowed_values=param_schema.get("allowed_values"),
                    example=param_schema.get("example", param_value),
                )
            )

        return APIResponse(
            success=True,
            data=schema_items,
            metadata={"strategy_id": strategy_id, "parameter_count": len(schema_items)},
        )
    except Exception as e:
        logger.error(f"Error getting schema for {strategy_id}: {e}")
        return APIResponse(
            success=False, error={"code": "INTERNAL_ERROR", "message": str(e)}
        )


@router.get(
    "/strategies/{strategy_id}/defaults",
    response_model=APIResponse,
    summary="Get default parameters for a strategy",
    description="""
    **For LLM Agents**: Use this to see the hardcoded default values for a strategy.

    These are the values that will be used if no configuration exists in the database.
    Useful for understanding the baseline behavior before making changes.

    **Example Request**: `GET /api/v1/strategies/orderbook_skew/defaults`
    """,
)
async def get_strategy_defaults_endpoint(
    strategy_id: str = Path(..., description="Strategy identifier"),
):
    """Get hardcoded default parameters for a strategy."""
    try:
        defaults = get_strategy_defaults(strategy_id)
        metadata = get_strategy_metadata(strategy_id)

        if not defaults:
            return APIResponse(
                success=False,
                error={
                    "code": "NOT_FOUND",
                    "message": f"Strategy not found: {strategy_id}",
                },
            )

        return APIResponse(
            success=True,
            data=defaults,
            metadata={
                "strategy_id": strategy_id,
                "strategy_name": metadata.get("name", strategy_id),
                "note": "These are hardcoded defaults used when no DB config exists",
            },
        )
    except Exception as e:
        logger.error(f"Error getting defaults for {strategy_id}: {e}")
        return APIResponse(
            success=False, error={"code": "INTERNAL_ERROR", "message": str(e)}
        )


@router.get(
    "/strategies/{strategy_id}/config",
    response_model=APIResponse,
    summary="Get global configuration for a strategy",
    description="""
    **For LLM Agents**: Use this to retrieve the current global configuration for a strategy.

    Global configurations apply to all trading symbols unless overridden by symbol-specific configs.

    The response indicates:
    - Current parameter values
    - Configuration version (increments with each update)
    - Source (mongodb, environment, or default)
    - When it was created/updated

    **Example Request**: `GET /api/v1/strategies/orderbook_skew/config`

    **Note**: If source is "default" or "environment", no custom configuration exists yet.
    """,
)
async def get_global_config(
    strategy_id: str = Path(..., description="Strategy identifier"),
):
    """Get global configuration for a strategy."""
    try:
        manager = get_config_manager()
        config = await manager.get_config(strategy_id, symbol=None)

        response_data = ConfigResponse(
            strategy_id=strategy_id,
            symbol=None,
            parameters=config.get("parameters", {}),
            version=config.get("version", 0),
            source=config.get("source", "unknown"),
            is_override=False,
            created_at=config.get("created_at"),
            updated_at=config.get("updated_at"),
        )

        return APIResponse(
            success=True,
            data=response_data,
            metadata={
                "cache_hit": config.get("cache_hit", False),
                "load_time_ms": config.get("load_time_ms", 0),
            },
        )
    except Exception as e:
        logger.error(f"Error getting config for {strategy_id}: {e}")
        return APIResponse(
            success=False, error={"code": "INTERNAL_ERROR", "message": str(e)}
        )


@router.get(
    "/strategies/{strategy_id}/config/{symbol}",
    response_model=APIResponse,
    summary="Get symbol-specific configuration override",
    description="""
    **For LLM Agents**: Use this to retrieve configuration specific to a trading symbol.

    Symbol-specific configurations OVERRIDE global configurations for that symbol.
    This allows different behavior for different trading pairs.

    **Priority**: Symbol config > Global config > Environment > Defaults

    **Example Use Case**:
    - BTCUSDT might need different thresholds than ETHUSDT due to volatility differences
    - You can set global defaults, then override specific symbols as needed

    **Example Request**: `GET /api/v1/strategies/orderbook_skew/config/BTCUSDT`
    """,
)
async def get_symbol_config(
    strategy_id: str = Path(..., description="Strategy identifier"),
    symbol: str = Path(..., description="Trading symbol (e.g., 'BTCUSDT')"),
):
    """Get symbol-specific configuration for a strategy."""
    try:
        manager = get_config_manager()
        config = await manager.get_config(strategy_id, symbol=symbol.upper())

        response_data = ConfigResponse(
            strategy_id=strategy_id,
            symbol=symbol.upper(),
            parameters=config.get("parameters", {}),
            version=config.get("version", 0),
            source=config.get("source", "unknown"),
            is_override=config.get("is_override", False),
            created_at=config.get("created_at"),
            updated_at=config.get("updated_at"),
        )

        return APIResponse(
            success=True,
            data=response_data,
            metadata={
                "cache_hit": config.get("cache_hit", False),
                "load_time_ms": config.get("load_time_ms", 0),
            },
        )
    except Exception as e:
        logger.error(f"Error getting config for {strategy_id}/{symbol}: {e}")
        return APIResponse(
            success=False, error={"code": "INTERNAL_ERROR", "message": str(e)}
        )


@router.post(
    "/strategies/{strategy_id}/config",
    response_model=APIResponse,
    summary="Create or update global configuration",
    description="""
    **For LLM Agents**: Use this to modify the global configuration for a strategy.

    **IMPORTANT STEPS**:
    1. First call `GET /strategies/{strategy_id}/schema` to see valid parameters
    2. Prepare your parameter updates following the schema constraints
    3. POST to this endpoint with parameters, changed_by, and optional reason
    4. Configuration takes effect within 60 seconds (cache TTL)

    **Validation**: Parameters are validated against the schema. Invalid values will be rejected.

    **Audit Trail**: All changes are logged with who/what/when/why for tracking.

    **Example Request**:
    ```json
    POST /api/v1/strategies/orderbook_skew/config
    {
      "parameters": {
        "top_levels": 10,
        "buy_threshold": 1.3,
        "sell_threshold": 0.75
      },
      "changed_by": "admin",
      "reason": "Adjusting sensitivity for current market conditions",
      "validate_only": false
    }
    ```

    **Dry Run**: Set `validate_only: true` to test parameters without saving.
    """,
    status_code=status.HTTP_200_OK,
)
async def update_global_config(
    strategy_id: str = Path(..., description="Strategy identifier"),
    request: ConfigUpdateRequest = ...,
):
    """Create or update global configuration for a strategy."""
    try:
        manager = get_config_manager()

        success, config, errors = await manager.set_config(
            strategy_id=strategy_id,
            parameters=request.parameters,
            changed_by=request.changed_by,
            symbol=None,
            reason=request.reason,
            validate_only=request.validate_only,
        )

        if not success:
            return APIResponse(
                success=False,
                error={
                    "code": "VALIDATION_ERROR",
                    "message": "Parameter validation failed",
                    "details": {"errors": errors},
                },
            )

        if request.validate_only:
            return APIResponse(
                success=True,
                data=None,
                metadata={
                    "validation": "passed",
                    "message": "Parameters are valid but not saved (validate_only=true)",
                },
            )

        response_data = ConfigResponse(
            strategy_id=config.strategy_id,
            symbol=None,
            parameters=config.parameters,
            version=config.version,
            source="mongodb",
            is_override=False,
            created_at=config.created_at.isoformat(),
            updated_at=config.updated_at.isoformat(),
        )

        return APIResponse(
            success=True,
            data=response_data,
            metadata={
                "action": "updated" if config.version > 1 else "created",
                "changes_applied": True,
            },
        )
    except Exception as e:
        logger.error(f"Error updating config for {strategy_id}: {e}")
        return APIResponse(
            success=False, error={"code": "INTERNAL_ERROR", "message": str(e)}
        )


@router.post(
    "/strategies/{strategy_id}/config/{symbol}",
    response_model=APIResponse,
    summary="Create or update symbol-specific configuration",
    description="""
    **For LLM Agents**: Use this to create configuration overrides for specific trading symbols.

    This allows you to customize strategy behavior for individual trading pairs while keeping
    global defaults for all other pairs.

    **Example Scenario**:
    - Global config: buy_threshold = 1.2 (applies to all symbols)
    - BTCUSDT override: buy_threshold = 1.3 (only for BTC)
    - ETHUSDT: uses global (1.2)

    **Best Practice**: Start with global config, then add symbol overrides only when needed.

    **Example Request**:
    ```json
    POST /api/v1/strategies/orderbook_skew/config/BTCUSDT
    {
      "parameters": {
        "buy_threshold": 1.3,
        "sell_threshold": 0.7
      },
      "changed_by": "admin",
      "reason": "BTC requires different thresholds due to higher liquidity"
    }
    ```
    """,
    status_code=status.HTTP_200_OK,
)
async def update_symbol_config(
    strategy_id: str = Path(..., description="Strategy identifier"),
    symbol: str = Path(..., description="Trading symbol"),
    request: ConfigUpdateRequest = ...,
):
    """Create or update symbol-specific configuration for a strategy."""
    try:
        manager = get_config_manager()

        success, config, errors = await manager.set_config(
            strategy_id=strategy_id,
            parameters=request.parameters,
            changed_by=request.changed_by,
            symbol=symbol.upper(),
            reason=request.reason,
            validate_only=request.validate_only,
        )

        if not success:
            return APIResponse(
                success=False,
                error={
                    "code": "VALIDATION_ERROR",
                    "message": "Parameter validation failed",
                    "details": {"errors": errors},
                },
            )

        if request.validate_only:
            return APIResponse(
                success=True,
                data=None,
                metadata={
                    "validation": "passed",
                    "message": "Parameters are valid but not saved (validate_only=true)",
                },
            )

        response_data = ConfigResponse(
            strategy_id=config.strategy_id,
            symbol=symbol.upper(),
            parameters=config.parameters,
            version=config.version,
            source="mongodb",
            is_override=True,
            created_at=config.created_at.isoformat(),
            updated_at=config.updated_at.isoformat(),
        )

        return APIResponse(
            success=True,
            data=response_data,
            metadata={
                "action": "updated" if config.version > 1 else "created",
                "changes_applied": True,
            },
        )
    except Exception as e:
        logger.error(f"Error updating config for {strategy_id}/{symbol}: {e}")
        return APIResponse(
            success=False, error={"code": "INTERNAL_ERROR", "message": str(e)}
        )


@router.delete(
    "/strategies/{strategy_id}/config",
    response_model=APIResponse,
    summary="Delete global configuration",
    description="""
    **For LLM Agents**: Use this to remove a global configuration and revert to defaults.

    **Warning**: This will delete the configuration from MongoDB.
    After deletion, the strategy will use environment variables or hardcoded defaults.

    **Example Request**: `DELETE /api/v1/strategies/orderbook_skew/config?changed_by=admin&reason=Reset to defaults`
    """,
)
async def delete_global_config(
    strategy_id: str = Path(..., description="Strategy identifier"),
    changed_by: str = Query(..., description="Who is deleting the config"),
    reason: str = Query(None, description="Reason for deletion"),
):
    """Delete global configuration for a strategy."""
    try:
        manager = get_config_manager()

        success, errors = await manager.delete_config(
            strategy_id=strategy_id, changed_by=changed_by, symbol=None, reason=reason
        )

        if not success:
            return APIResponse(
                success=False,
                error={
                    "code": "DELETE_FAILED",
                    "message": "Failed to delete configuration",
                    "details": {"errors": errors},
                },
            )

        return APIResponse(
            success=True,
            data={"message": "Configuration deleted successfully"},
            metadata={"strategy_id": strategy_id},
        )
    except Exception as e:
        logger.error(f"Error deleting config for {strategy_id}: {e}")
        return APIResponse(
            success=False, error={"code": "INTERNAL_ERROR", "message": str(e)}
        )


@router.delete(
    "/strategies/{strategy_id}/config/{symbol}",
    response_model=APIResponse,
    summary="Delete symbol-specific configuration",
    description="""
    **For LLM Agents**: Use this to remove a symbol-specific configuration override.

    After deletion, the symbol will use the global configuration.

    **Example Request**: `DELETE /api/v1/strategies/orderbook_skew/config/BTCUSDT?changed_by=admin`
    """,
)
async def delete_symbol_config(
    strategy_id: str = Path(..., description="Strategy identifier"),
    symbol: str = Path(..., description="Trading symbol"),
    changed_by: str = Query(..., description="Who is deleting the config"),
    reason: str = Query(None, description="Reason for deletion"),
):
    """Delete symbol-specific configuration for a strategy."""
    try:
        manager = get_config_manager()

        success, errors = await manager.delete_config(
            strategy_id=strategy_id,
            changed_by=changed_by,
            symbol=symbol.upper(),
            reason=reason,
        )

        if not success:
            return APIResponse(
                success=False,
                error={
                    "code": "DELETE_FAILED",
                    "message": "Failed to delete configuration",
                    "details": {"errors": errors},
                },
            )

        return APIResponse(
            success=True,
            data={"message": "Configuration deleted successfully"},
            metadata={"strategy_id": strategy_id, "symbol": symbol.upper()},
        )
    except Exception as e:
        logger.error(f"Error deleting config for {strategy_id}/{symbol}: {e}")
        return APIResponse(
            success=False, error={"code": "INTERNAL_ERROR", "message": str(e)}
        )


@router.get(
    "/strategies/{strategy_id}/audit",
    response_model=APIResponse,
    summary="Get configuration change history",
    description="""
    **For LLM Agents**: Use this to see the complete history of configuration changes.

    The audit trail shows:
    - What changed (old vs new parameters)
    - Who made the change
    - When it was changed
    - Why it was changed (if reason was provided)

    This is useful for:
    - Tracking performance impact of parameter changes
    - Understanding configuration evolution
    - Debugging issues related to config changes
    - Rolling back to previous configurations

    **Example Request**: `GET /api/v1/strategies/orderbook_skew/audit?limit=50`
    """,
)
async def get_audit_trail(
    strategy_id: str = Path(..., description="Strategy identifier"),
    symbol: str = Query(None, description="Optional symbol filter"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records"),
):
    """Get configuration change history for a strategy."""
    try:
        manager = get_config_manager()

        audit_records = await manager.get_audit_trail(
            strategy_id=strategy_id, symbol=symbol, limit=limit
        )

        audit_items = [
            AuditTrailItem(
                id=record.id or "",
                strategy_id=record.strategy_id,
                symbol=record.symbol,
                action=record.action,
                old_parameters=record.old_parameters,
                new_parameters=record.new_parameters,
                changed_by=record.changed_by,
                changed_at=record.changed_at.isoformat(),
                reason=record.reason,
            )
            for record in audit_records
        ]

        return APIResponse(
            success=True,
            data=audit_items,
            metadata={"count": len(audit_items), "limit": limit},
        )
    except Exception as e:
        logger.error(f"Error getting audit trail for {strategy_id}: {e}")
        return APIResponse(
            success=False, error={"code": "INTERNAL_ERROR", "message": str(e)}
        )


@router.post(
    "/strategies/cache/refresh",
    response_model=APIResponse,
    summary="Force refresh configuration cache",
    description="""
    **For LLM Agents**: Use this to immediately clear the configuration cache.

    Normally, configuration changes take up to 60 seconds to propagate due to caching.
    Call this endpoint after making configuration changes to force immediate refresh.

    **When to use**:
    - After updating multiple configurations
    - When you need changes to take effect immediately
    - For testing configuration changes

    **Example Request**: `POST /api/v1/strategies/cache/refresh`
    """,
)
async def refresh_cache():
    """Force refresh of all cached configurations."""
    try:
        manager = get_config_manager()
        await manager.refresh_cache()

        return APIResponse(
            success=True,
            data={"message": "Cache refreshed successfully"},
            metadata={
                "note": "All configurations will be reloaded from database on next access"
            },
        )
    except Exception as e:
        logger.error(f"Error refreshing cache: {e}")
        return APIResponse(
            success=False, error={"code": "INTERNAL_ERROR", "message": str(e)}
        )
