"""
FastAPI routes for strategy configuration management.

Provides comprehensive REST API for runtime configuration of trading strategies.
All endpoints are LLM-compatible and include detailed documentation.
"""

import logging
import os
from datetime import datetime
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Path, Query, status
from pydantic import BaseModel, Field

from strategies.api.response_models import (
    APIResponse,
    AuditTrailItem,
    ConfigResponse,
    ConfigUpdateRequest,
    ConfigValidationRequest,
    CrossServiceConflict,
    ParameterSchemaItem,
    StrategyListItem,
    ValidationError,
    ValidationResponse,
)
from strategies.market_logic.defaults import (
    get_parameter_schema,
    get_strategy_defaults,
    get_strategy_metadata,
)
from strategies.services.config_manager import StrategyConfigManager

logger = logging.getLogger(__name__)


class RollbackRequest(BaseModel):
    """Request model for configuration rollback."""

    target_version: int | None = Field(
        None, ge=1, description="Specific version number to rollback to (must be >= 1)"
    )
    rollback_id: str | None = Field(
        None, description="Specific audit record ID to rollback to"
    )
    changed_by: str = Field(..., description="Who is performing the rollback")
    reason: str | None = Field(None, description="Reason for rollback")


# Router for configuration endpoints
router = APIRouter(prefix="/api/v1", tags=["configuration"])


@router.post(
    "/strategies/{strategy_id}/rollback",
    response_model=APIResponse,
    summary="Rollback strategy configuration",
    description="""
    **For LLM Agents**: Revert strategy configuration to a previous version.

    Reverts global or symbol-specific settings. Supports rollback by version number or specific audit ID.

    **Example Request**: `POST /api/v1/strategies/orderbook_skew/rollback?symbol=BTCUSDT`
    ```json
    {
      "changed_by": "llm_agent_v1",
      "reason": "Previous configuration was more profitable",
      "target_version": 3
    }
    ```
    """,
)
async def rollback_config(
    request: RollbackRequest,
    strategy_id: str = Path(..., description="Strategy identifier"),
    symbol: str | None = Query(None, description="Optional symbol filter"),
):
    """Rollback configuration."""
    try:
        manager = get_config_manager()
        success, config, errors = await manager.rollback_config(
            strategy_id=strategy_id,
            changed_by=request.changed_by,
            symbol=symbol.upper() if symbol else None,
            target_version=request.target_version,
            rollback_id=request.rollback_id,
            reason=request.reason,
        )

        if not success:
            return APIResponse(
                success=False,
                error={
                    "code": "ROLLBACK_FAILED",
                    "message": "Failed to rollback configuration",
                    "details": {"errors": errors},
                },
            )

        return APIResponse(
            success=True,
            data=ConfigResponse(
                strategy_id=strategy_id,
                symbol=symbol,
                parameters=config.parameters if config else {},
                version=config.version if config else 0,
                source="data_manager",
                is_override=bool(symbol),
                created_at="",
                updated_at=datetime.utcnow().isoformat(),
            ),
            metadata={"action": "rollback", "strategy_id": strategy_id},
        )
    except Exception as e:
        logger.error(f"Error rolling back config: {e}")
        return APIResponse(
            success=False, error={"code": "INTERNAL_ERROR", "message": str(e)}
        )


@router.post(
    "/strategies/{strategy_id}/restore",
    response_model=APIResponse,
    summary="Restore strategy configuration",
    description="""
    **For LLM Agents**: Restore a specific previous version of the strategy configuration.
    Alias for the rollback endpoint.
    """,
)
async def restore_config(
    request: RollbackRequest,
    strategy_id: str = Path(..., description="Strategy identifier"),
    symbol: str | None = Query(None, description="Optional symbol filter"),
):
    """Restore configuration."""
    return await rollback_config(request, strategy_id, symbol)


# Global config manager instance (will be injected on startup)
_config_manager: StrategyConfigManager | None = None


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


@router.post(
    "/config/validate",
    response_model=APIResponse,
    summary="Validate configuration without applying changes",
    description="""
    **For LLM Agents**: Validate configuration parameters without persisting changes.

    This endpoint performs comprehensive validation including:
    - Parameter type and constraint validation
    - Dependency validation
    - Cross-service conflict detection (future)
    - Impact assessment

    **Example Request**:
    ```json
    {
      "parameters": {
        "buy_threshold": 1.3,
        "sell_threshold": 0.75
      },
      "strategy_id": "orderbook_skew",
      "symbol": "BTCUSDT"
    }
    ```

    **Example Response**:
    ```json
    {
      "success": true,
      "data": {
        "validation_passed": true,
        "errors": [],
        "warnings": [],
        "suggested_fixes": [],
        "estimated_impact": {
          "risk_level": "low",
          "affected_scope": "strategy:orderbook_skew"
        },
        "conflicts": []
      }
    }
    ```
    """,
    tags=["configuration"],
)
async def validate_config(request: ConfigValidationRequest):
    """Validate configuration without applying changes."""
    try:
        # Validate that strategy_id is provided for strategy config validation
        if not request.strategy_id:
            return APIResponse(
                success=False,
                error={
                    "code": "VALIDATION_ERROR",
                    "message": "strategy_id is required for configuration validation",
                },
            )

        manager = get_config_manager()

        # Perform validation using existing logic
        success, config, errors = await manager.set_config(
            strategy_id=request.strategy_id,
            parameters=request.parameters,
            changed_by="validation_api",
            symbol=request.symbol.upper() if request.symbol else None,
            reason="Validation only - no changes applied",
            validate_only=True,
        )

        # Convert errors to standardized format
        validation_errors = []
        suggested_fixes = []

        for error_msg in errors:
            # Parse error message to extract field and details
            if "Unknown parameter" in error_msg:
                # Handle "Unknown parameter" errors
                code = "UNKNOWN_PARAMETER"
                # Extract parameter name from "Unknown parameter: param_name"
                if "Unknown parameter:" in error_msg:
                    param_name = error_msg.split("Unknown parameter:")[-1].strip()
                    field = param_name
                else:
                    field = "unknown"
                suggested_fixes.append(
                    f"Remove {field} or check parameter name spelling"
                )
                validation_errors.append(
                    ValidationError(
                        field=field,
                        message=error_msg,
                        code=code,
                        suggested_value=None,
                    )
                )
            elif "must be" in error_msg:
                # Extract field name (usually first word before "must")
                parts = error_msg.split(" must be")
                if parts:
                    field = parts[0].strip()
                    message = error_msg

                    # Determine error code
                    suggested_value = None  # Initialize before conditionals
                    if "must be an integer" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to an integer value")
                    elif "must be a number" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to a numeric value")
                    elif "must be a boolean" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to a boolean value")
                    elif "must be a string" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to a string value")
                    elif "must be >=" in error_msg or "must be <=" in error_msg:
                        code = "OUT_OF_RANGE"
                        # Extract suggested value from schema
                        from strategies.market_logic.defaults import (
                            get_parameter_schema,
                        )

                        schema = get_parameter_schema(request.strategy_id)
                        if schema and field in schema:
                            param_schema = schema[field]
                            if "min" in param_schema and "max" in param_schema:
                                suggested_value = (
                                    param_schema["min"] + param_schema["max"]
                                ) / 2
                            elif "min" in param_schema:
                                suggested_value = param_schema["min"]
                            elif "max" in param_schema:
                                suggested_value = param_schema["max"]
                            else:
                                suggested_value = param_schema.get("default")
                        else:
                            suggested_value = None
                    else:
                        code = "VALIDATION_ERROR"
                        suggested_value = None

                    validation_errors.append(
                        ValidationError(
                            field=field,
                            message=message,
                            code=code,
                            suggested_value=suggested_value,
                        )
                    )
            else:
                # Generic error
                validation_errors.append(
                    ValidationError(
                        field="unknown",
                        message=error_msg,
                        code="VALIDATION_ERROR",
                        suggested_value=None,
                    )
                )

        # Estimate impact (simplified for now)
        estimated_impact = {
            "risk_level": "low",
            "affected_scope": (
                f"strategy:{request.strategy_id}"
                if not request.symbol
                else f"strategy:{request.strategy_id}:symbol:{request.symbol}"
            ),
            "parameter_count": len(request.parameters),
        }

        # Add risk assessment based on parameters
        high_risk_params = ["threshold", "multiplier", "risk_factor"]
        if any(param in request.parameters for param in high_risk_params):
            estimated_impact["risk_level"] = "medium"

        # Cross-service conflict detection
        conflicts = await detect_cross_service_conflicts(
            request.parameters, request.strategy_id, request.symbol
        )

        validation_response = ValidationResponse(
            validation_passed=success and len(validation_errors) == 0,
            errors=validation_errors,
            warnings=[],
            suggested_fixes=suggested_fixes,
            estimated_impact=estimated_impact,
            conflicts=conflicts,
        )

        return APIResponse(
            success=True,
            data=validation_response,
            metadata={
                "validation_mode": "dry_run",
                "scope": (
                    f"strategy:{request.strategy_id}"
                    if not request.symbol
                    else f"strategy:{request.strategy_id}:symbol:{request.symbol}"
                ),
            },
        )

    except Exception as e:
        logger.error(f"Error validating config: {e}")
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


@router.post(
    "/config/validate",
    response_model=APIResponse,
    summary="Validate configuration without applying changes",
    description="""
    **For LLM Agents**: Validate configuration parameters without persisting changes.

    This endpoint performs comprehensive validation including:
    - Parameter type and constraint validation
    - Dependency validation
    - Cross-service conflict detection (future)
    - Impact assessment

    **Example Request**:
    ```json
    {
      "parameters": {
        "buy_threshold": 1.3,
        "sell_threshold": 0.75
      },
      "strategy_id": "orderbook_skew",
      "symbol": "BTCUSDT"
    }
    ```

    **Example Response**:
    ```json
    {
      "success": true,
      "data": {
        "validation_passed": true,
        "errors": [],
        "warnings": [],
        "suggested_fixes": [],
        "estimated_impact": {
          "risk_level": "low",
          "affected_scope": "strategy:orderbook_skew"
        },
        "conflicts": []
      }
    }
    ```
    """,
    tags=["configuration"],
)
async def validate_config(request: ConfigValidationRequest):
    """Validate configuration without applying changes."""
    try:
        # Validate that strategy_id is provided for strategy config validation
        if not request.strategy_id:
            return APIResponse(
                success=False,
                error={
                    "code": "VALIDATION_ERROR",
                    "message": "strategy_id is required for configuration validation",
                },
            )

        manager = get_config_manager()

        # Perform validation using existing logic
        success, config, errors = await manager.set_config(
            strategy_id=request.strategy_id,
            parameters=request.parameters,
            changed_by="validation_api",
            symbol=request.symbol.upper() if request.symbol else None,
            reason="Validation only - no changes applied",
            validate_only=True,
        )

        # Convert errors to standardized format
        validation_errors = []
        suggested_fixes = []

        for error_msg in errors:
            # Parse error message to extract field and details
            if "Unknown parameter" in error_msg:
                # Handle "Unknown parameter" errors
                code = "UNKNOWN_PARAMETER"
                # Extract parameter name from "Unknown parameter: param_name"
                if "Unknown parameter:" in error_msg:
                    param_name = error_msg.split("Unknown parameter:")[-1].strip()
                    field = param_name
                else:
                    field = "unknown"
                suggested_fixes.append(
                    f"Remove {field} or check parameter name spelling"
                )
                validation_errors.append(
                    ValidationError(
                        field=field,
                        message=error_msg,
                        code=code,
                        suggested_value=None,
                    )
                )
            elif "must be" in error_msg:
                # Extract field name (usually first word before "must")
                parts = error_msg.split(" must be")
                if parts:
                    field = parts[0].strip()
                    message = error_msg

                    # Determine error code
                    suggested_value = None  # Initialize before conditionals
                    if "must be an integer" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to an integer value")
                    elif "must be a number" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to a numeric value")
                    elif "must be a boolean" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to a boolean value")
                    elif "must be a string" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to a string value")
                    elif "must be >=" in error_msg or "must be <=" in error_msg:
                        code = "OUT_OF_RANGE"
                        # Extract suggested value from schema
                        from strategies.market_logic.defaults import (
                            get_parameter_schema,
                        )

                        schema = get_parameter_schema(request.strategy_id)
                        if schema and field in schema:
                            param_schema = schema[field]
                            if "min" in param_schema and "max" in param_schema:
                                suggested_value = (
                                    param_schema["min"] + param_schema["max"]
                                ) / 2
                            elif "min" in param_schema:
                                suggested_value = param_schema["min"]
                            elif "max" in param_schema:
                                suggested_value = param_schema["max"]
                            else:
                                suggested_value = param_schema.get("default")
                        else:
                            suggested_value = None
                    else:
                        code = "VALIDATION_ERROR"
                        suggested_value = None

                    validation_errors.append(
                        ValidationError(
                            field=field,
                            message=message,
                            code=code,
                            suggested_value=suggested_value,
                        )
                    )
            else:
                # Generic error
                validation_errors.append(
                    ValidationError(
                        field="unknown",
                        message=error_msg,
                        code="VALIDATION_ERROR",
                        suggested_value=None,
                    )
                )

        # Estimate impact (simplified for now)
        estimated_impact = {
            "risk_level": "low",
            "affected_scope": (
                f"strategy:{request.strategy_id}"
                if not request.symbol
                else f"strategy:{request.strategy_id}:symbol:{request.symbol}"
            ),
            "parameter_count": len(request.parameters),
        }

        # Add risk assessment based on parameters
        high_risk_params = ["threshold", "multiplier", "risk_factor"]
        if any(param in request.parameters for param in high_risk_params):
            estimated_impact["risk_level"] = "medium"

        # Cross-service conflict detection
        conflicts = await detect_cross_service_conflicts(
            request.parameters, request.strategy_id, request.symbol
        )

        validation_response = ValidationResponse(
            validation_passed=success and len(validation_errors) == 0,
            errors=validation_errors,
            warnings=[],
            suggested_fixes=suggested_fixes,
            estimated_impact=estimated_impact,
            conflicts=conflicts,
        )

        return APIResponse(
            success=True,
            data=validation_response,
            metadata={
                "validation_mode": "dry_run",
                "scope": (
                    f"strategy:{request.strategy_id}"
                    if not request.symbol
                    else f"strategy:{request.strategy_id}:symbol:{request.symbol}"
                ),
            },
        )

    except Exception as e:
        logger.error(f"Error validating config: {e}")
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


@router.post(
    "/config/validate",
    response_model=APIResponse,
    summary="Validate configuration without applying changes",
    description="""
    **For LLM Agents**: Validate configuration parameters without persisting changes.

    This endpoint performs comprehensive validation including:
    - Parameter type and constraint validation
    - Dependency validation
    - Cross-service conflict detection (future)
    - Impact assessment

    **Example Request**:
    ```json
    {
      "parameters": {
        "buy_threshold": 1.3,
        "sell_threshold": 0.75
      },
      "strategy_id": "orderbook_skew",
      "symbol": "BTCUSDT"
    }
    ```

    **Example Response**:
    ```json
    {
      "success": true,
      "data": {
        "validation_passed": true,
        "errors": [],
        "warnings": [],
        "suggested_fixes": [],
        "estimated_impact": {
          "risk_level": "low",
          "affected_scope": "strategy:orderbook_skew"
        },
        "conflicts": []
      }
    }
    ```
    """,
    tags=["configuration"],
)
async def validate_config(request: ConfigValidationRequest):
    """Validate configuration without applying changes."""
    try:
        # Validate that strategy_id is provided for strategy config validation
        if not request.strategy_id:
            return APIResponse(
                success=False,
                error={
                    "code": "VALIDATION_ERROR",
                    "message": "strategy_id is required for configuration validation",
                },
            )

        manager = get_config_manager()

        # Perform validation using existing logic
        success, config, errors = await manager.set_config(
            strategy_id=request.strategy_id,
            parameters=request.parameters,
            changed_by="validation_api",
            symbol=request.symbol.upper() if request.symbol else None,
            reason="Validation only - no changes applied",
            validate_only=True,
        )

        # Convert errors to standardized format
        validation_errors = []
        suggested_fixes = []

        for error_msg in errors:
            # Parse error message to extract field and details
            if "Unknown parameter" in error_msg:
                # Handle "Unknown parameter" errors
                code = "UNKNOWN_PARAMETER"
                # Extract parameter name from "Unknown parameter: param_name"
                if "Unknown parameter:" in error_msg:
                    param_name = error_msg.split("Unknown parameter:")[-1].strip()
                    field = param_name
                else:
                    field = "unknown"
                suggested_fixes.append(
                    f"Remove {field} or check parameter name spelling"
                )
                validation_errors.append(
                    ValidationError(
                        field=field,
                        message=error_msg,
                        code=code,
                        suggested_value=None,
                    )
                )
            elif "must be" in error_msg:
                # Extract field name (usually first word before "must")
                parts = error_msg.split(" must be")
                if parts:
                    field = parts[0].strip()
                    message = error_msg

                    # Determine error code
                    suggested_value = None  # Initialize before conditionals
                    if "must be an integer" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to an integer value")
                    elif "must be a number" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to a numeric value")
                    elif "must be a boolean" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to a boolean value")
                    elif "must be a string" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to a string value")
                    elif "must be >=" in error_msg or "must be <=" in error_msg:
                        code = "OUT_OF_RANGE"
                        # Extract suggested value from schema
                        from strategies.market_logic.defaults import (
                            get_parameter_schema,
                        )

                        schema = get_parameter_schema(request.strategy_id)
                        if schema and field in schema:
                            param_schema = schema[field]
                            if "min" in param_schema and "max" in param_schema:
                                suggested_value = (
                                    param_schema["min"] + param_schema["max"]
                                ) / 2
                            elif "min" in param_schema:
                                suggested_value = param_schema["min"]
                            elif "max" in param_schema:
                                suggested_value = param_schema["max"]
                            else:
                                suggested_value = param_schema.get("default")
                        else:
                            suggested_value = None
                    else:
                        code = "VALIDATION_ERROR"
                        suggested_value = None

                    validation_errors.append(
                        ValidationError(
                            field=field,
                            message=message,
                            code=code,
                            suggested_value=suggested_value,
                        )
                    )
            else:
                # Generic error
                validation_errors.append(
                    ValidationError(
                        field="unknown",
                        message=error_msg,
                        code="VALIDATION_ERROR",
                        suggested_value=None,
                    )
                )

        # Estimate impact (simplified for now)
        estimated_impact = {
            "risk_level": "low",
            "affected_scope": (
                f"strategy:{request.strategy_id}"
                if not request.symbol
                else f"strategy:{request.strategy_id}:symbol:{request.symbol}"
            ),
            "parameter_count": len(request.parameters),
        }

        # Add risk assessment based on parameters
        high_risk_params = ["threshold", "multiplier", "risk_factor"]
        if any(param in request.parameters for param in high_risk_params):
            estimated_impact["risk_level"] = "medium"

        # Cross-service conflict detection
        conflicts = await detect_cross_service_conflicts(
            request.parameters, request.strategy_id, request.symbol
        )

        validation_response = ValidationResponse(
            validation_passed=success and len(validation_errors) == 0,
            errors=validation_errors,
            warnings=[],
            suggested_fixes=suggested_fixes,
            estimated_impact=estimated_impact,
            conflicts=conflicts,
        )

        return APIResponse(
            success=True,
            data=validation_response,
            metadata={
                "validation_mode": "dry_run",
                "scope": (
                    f"strategy:{request.strategy_id}"
                    if not request.symbol
                    else f"strategy:{request.strategy_id}:symbol:{request.symbol}"
                ),
            },
        )

    except Exception as e:
        logger.error(f"Error validating config: {e}")
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


@router.post(
    "/config/validate",
    response_model=APIResponse,
    summary="Validate configuration without applying changes",
    description="""
    **For LLM Agents**: Validate configuration parameters without persisting changes.

    This endpoint performs comprehensive validation including:
    - Parameter type and constraint validation
    - Dependency validation
    - Cross-service conflict detection (future)
    - Impact assessment

    **Example Request**:
    ```json
    {
      "parameters": {
        "buy_threshold": 1.3,
        "sell_threshold": 0.75
      },
      "strategy_id": "orderbook_skew",
      "symbol": "BTCUSDT"
    }
    ```

    **Example Response**:
    ```json
    {
      "success": true,
      "data": {
        "validation_passed": true,
        "errors": [],
        "warnings": [],
        "suggested_fixes": [],
        "estimated_impact": {
          "risk_level": "low",
          "affected_scope": "strategy:orderbook_skew"
        },
        "conflicts": []
      }
    }
    ```
    """,
    tags=["configuration"],
)
async def validate_config(request: ConfigValidationRequest):
    """Validate configuration without applying changes."""
    try:
        # Validate that strategy_id is provided for strategy config validation
        if not request.strategy_id:
            return APIResponse(
                success=False,
                error={
                    "code": "VALIDATION_ERROR",
                    "message": "strategy_id is required for configuration validation",
                },
            )

        manager = get_config_manager()

        # Perform validation using existing logic
        success, config, errors = await manager.set_config(
            strategy_id=request.strategy_id,
            parameters=request.parameters,
            changed_by="validation_api",
            symbol=request.symbol.upper() if request.symbol else None,
            reason="Validation only - no changes applied",
            validate_only=True,
        )

        # Convert errors to standardized format
        validation_errors = []
        suggested_fixes = []

        for error_msg in errors:
            # Parse error message to extract field and details
            if "Unknown parameter" in error_msg:
                # Handle "Unknown parameter" errors
                code = "UNKNOWN_PARAMETER"
                # Extract parameter name from "Unknown parameter: param_name"
                if "Unknown parameter:" in error_msg:
                    param_name = error_msg.split("Unknown parameter:")[-1].strip()
                    field = param_name
                else:
                    field = "unknown"
                suggested_fixes.append(
                    f"Remove {field} or check parameter name spelling"
                )
                validation_errors.append(
                    ValidationError(
                        field=field,
                        message=error_msg,
                        code=code,
                        suggested_value=None,
                    )
                )
            elif "must be" in error_msg:
                # Extract field name (usually first word before "must")
                parts = error_msg.split(" must be")
                if parts:
                    field = parts[0].strip()
                    message = error_msg

                    # Determine error code
                    suggested_value = None  # Initialize before conditionals
                    if "must be an integer" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to an integer value")
                    elif "must be a number" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to a numeric value")
                    elif "must be a boolean" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to a boolean value")
                    elif "must be a string" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to a string value")
                    elif "must be >=" in error_msg or "must be <=" in error_msg:
                        code = "OUT_OF_RANGE"
                        # Extract suggested value from schema
                        from strategies.market_logic.defaults import (
                            get_parameter_schema,
                        )

                        schema = get_parameter_schema(request.strategy_id)
                        if schema and field in schema:
                            param_schema = schema[field]
                            if "min" in param_schema and "max" in param_schema:
                                suggested_value = (
                                    param_schema["min"] + param_schema["max"]
                                ) / 2
                            elif "min" in param_schema:
                                suggested_value = param_schema["min"]
                            elif "max" in param_schema:
                                suggested_value = param_schema["max"]
                            else:
                                suggested_value = param_schema.get("default")
                        else:
                            suggested_value = None
                    else:
                        code = "VALIDATION_ERROR"
                        suggested_value = None

                    validation_errors.append(
                        ValidationError(
                            field=field,
                            message=message,
                            code=code,
                            suggested_value=suggested_value,
                        )
                    )
            else:
                # Generic error
                validation_errors.append(
                    ValidationError(
                        field="unknown",
                        message=error_msg,
                        code="VALIDATION_ERROR",
                        suggested_value=None,
                    )
                )

        # Estimate impact (simplified for now)
        estimated_impact = {
            "risk_level": "low",
            "affected_scope": (
                f"strategy:{request.strategy_id}"
                if not request.symbol
                else f"strategy:{request.strategy_id}:symbol:{request.symbol}"
            ),
            "parameter_count": len(request.parameters),
        }

        # Add risk assessment based on parameters
        high_risk_params = ["threshold", "multiplier", "risk_factor"]
        if any(param in request.parameters for param in high_risk_params):
            estimated_impact["risk_level"] = "medium"

        # Cross-service conflict detection
        conflicts = await detect_cross_service_conflicts(
            request.parameters, request.strategy_id, request.symbol
        )

        validation_response = ValidationResponse(
            validation_passed=success and len(validation_errors) == 0,
            errors=validation_errors,
            warnings=[],
            suggested_fixes=suggested_fixes,
            estimated_impact=estimated_impact,
            conflicts=conflicts,
        )

        return APIResponse(
            success=True,
            data=validation_response,
            metadata={
                "validation_mode": "dry_run",
                "scope": (
                    f"strategy:{request.strategy_id}"
                    if not request.symbol
                    else f"strategy:{request.strategy_id}:symbol:{request.symbol}"
                ),
            },
        )

    except Exception as e:
        logger.error(f"Error validating config: {e}")
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
    "/config/validate",
    response_model=APIResponse,
    summary="Validate configuration without applying changes",
    description="""
    **For LLM Agents**: Validate configuration parameters without persisting changes.

    This endpoint performs comprehensive validation including:
    - Parameter type and constraint validation
    - Dependency validation
    - Cross-service conflict detection (future)
    - Impact assessment

    **Example Request**:
    ```json
    {
      "parameters": {
        "buy_threshold": 1.3,
        "sell_threshold": 0.75
      },
      "strategy_id": "orderbook_skew",
      "symbol": "BTCUSDT"
    }
    ```

    **Example Response**:
    ```json
    {
      "success": true,
      "data": {
        "validation_passed": true,
        "errors": [],
        "warnings": [],
        "suggested_fixes": [],
        "estimated_impact": {
          "risk_level": "low",
          "affected_scope": "strategy:orderbook_skew"
        },
        "conflicts": []
      }
    }
    ```
    """,
    tags=["configuration"],
)
async def validate_config(request: ConfigValidationRequest):
    """Validate configuration without applying changes."""
    try:
        # Validate that strategy_id is provided for strategy config validation
        if not request.strategy_id:
            return APIResponse(
                success=False,
                error={
                    "code": "VALIDATION_ERROR",
                    "message": "strategy_id is required for configuration validation",
                },
            )

        manager = get_config_manager()

        # Perform validation using existing logic
        success, config, errors = await manager.set_config(
            strategy_id=request.strategy_id,
            parameters=request.parameters,
            changed_by="validation_api",
            symbol=request.symbol.upper() if request.symbol else None,
            reason="Validation only - no changes applied",
            validate_only=True,
        )

        # Convert errors to standardized format
        validation_errors = []
        suggested_fixes = []

        for error_msg in errors:
            # Parse error message to extract field and details
            if "Unknown parameter" in error_msg:
                # Handle "Unknown parameter" errors
                code = "UNKNOWN_PARAMETER"
                # Extract parameter name from "Unknown parameter: param_name"
                if "Unknown parameter:" in error_msg:
                    param_name = error_msg.split("Unknown parameter:")[-1].strip()
                    field = param_name
                else:
                    field = "unknown"
                suggested_fixes.append(
                    f"Remove {field} or check parameter name spelling"
                )
                validation_errors.append(
                    ValidationError(
                        field=field,
                        message=error_msg,
                        code=code,
                        suggested_value=None,
                    )
                )
            elif "must be" in error_msg:
                # Extract field name (usually first word before "must")
                parts = error_msg.split(" must be")
                if parts:
                    field = parts[0].strip()
                    message = error_msg

                    # Determine error code
                    suggested_value = None  # Initialize before conditionals
                    if "must be an integer" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to an integer value")
                    elif "must be a number" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to a numeric value")
                    elif "must be a boolean" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to a boolean value")
                    elif "must be a string" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to a string value")
                    elif "must be >=" in error_msg or "must be <=" in error_msg:
                        code = "OUT_OF_RANGE"
                        # Extract suggested value from schema
                        from strategies.market_logic.defaults import (
                            get_parameter_schema,
                        )

                        schema = get_parameter_schema(request.strategy_id)
                        if schema and field in schema:
                            param_schema = schema[field]
                            if "min" in param_schema and "max" in param_schema:
                                suggested_value = (
                                    param_schema["min"] + param_schema["max"]
                                ) / 2
                            elif "min" in param_schema:
                                suggested_value = param_schema["min"]
                            elif "max" in param_schema:
                                suggested_value = param_schema["max"]
                            else:
                                suggested_value = param_schema.get("default")
                        else:
                            suggested_value = None
                    else:
                        code = "VALIDATION_ERROR"
                        suggested_value = None

                    validation_errors.append(
                        ValidationError(
                            field=field,
                            message=message,
                            code=code,
                            suggested_value=suggested_value,
                        )
                    )
            else:
                # Generic error
                validation_errors.append(
                    ValidationError(
                        field="unknown",
                        message=error_msg,
                        code="VALIDATION_ERROR",
                        suggested_value=None,
                    )
                )

        # Estimate impact (simplified for now)
        estimated_impact = {
            "risk_level": "low",
            "affected_scope": (
                f"strategy:{request.strategy_id}"
                if not request.symbol
                else f"strategy:{request.strategy_id}:symbol:{request.symbol}"
            ),
            "parameter_count": len(request.parameters),
        }

        # Add risk assessment based on parameters
        high_risk_params = ["threshold", "multiplier", "risk_factor"]
        if any(param in request.parameters for param in high_risk_params):
            estimated_impact["risk_level"] = "medium"

        # Cross-service conflict detection
        conflicts = await detect_cross_service_conflicts(
            request.parameters, request.strategy_id, request.symbol
        )

        validation_response = ValidationResponse(
            validation_passed=success and len(validation_errors) == 0,
            errors=validation_errors,
            warnings=[],
            suggested_fixes=suggested_fixes,
            estimated_impact=estimated_impact,
            conflicts=conflicts,
        )

        return APIResponse(
            success=True,
            data=validation_response,
            metadata={
                "validation_mode": "dry_run",
                "scope": (
                    f"strategy:{request.strategy_id}"
                    if not request.symbol
                    else f"strategy:{request.strategy_id}:symbol:{request.symbol}"
                ),
            },
        )

    except Exception as e:
        logger.error(f"Error validating config: {e}")
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
    "/config/validate",
    response_model=APIResponse,
    summary="Validate configuration without applying changes",
    description="""
    **For LLM Agents**: Validate configuration parameters without persisting changes.

    This endpoint performs comprehensive validation including:
    - Parameter type and constraint validation
    - Dependency validation
    - Cross-service conflict detection (future)
    - Impact assessment

    **Example Request**:
    ```json
    {
      "parameters": {
        "buy_threshold": 1.3,
        "sell_threshold": 0.75
      },
      "strategy_id": "orderbook_skew",
      "symbol": "BTCUSDT"
    }
    ```

    **Example Response**:
    ```json
    {
      "success": true,
      "data": {
        "validation_passed": true,
        "errors": [],
        "warnings": [],
        "suggested_fixes": [],
        "estimated_impact": {
          "risk_level": "low",
          "affected_scope": "strategy:orderbook_skew"
        },
        "conflicts": []
      }
    }
    ```
    """,
    tags=["configuration"],
)
async def validate_config(request: ConfigValidationRequest):
    """Validate configuration without applying changes."""
    try:
        # Validate that strategy_id is provided for strategy config validation
        if not request.strategy_id:
            return APIResponse(
                success=False,
                error={
                    "code": "VALIDATION_ERROR",
                    "message": "strategy_id is required for configuration validation",
                },
            )

        manager = get_config_manager()

        # Perform validation using existing logic
        success, config, errors = await manager.set_config(
            strategy_id=request.strategy_id,
            parameters=request.parameters,
            changed_by="validation_api",
            symbol=request.symbol.upper() if request.symbol else None,
            reason="Validation only - no changes applied",
            validate_only=True,
        )

        # Convert errors to standardized format
        validation_errors = []
        suggested_fixes = []

        for error_msg in errors:
            # Parse error message to extract field and details
            if "Unknown parameter" in error_msg:
                # Handle "Unknown parameter" errors
                code = "UNKNOWN_PARAMETER"
                # Extract parameter name from "Unknown parameter: param_name"
                if "Unknown parameter:" in error_msg:
                    param_name = error_msg.split("Unknown parameter:")[-1].strip()
                    field = param_name
                else:
                    field = "unknown"
                suggested_fixes.append(
                    f"Remove {field} or check parameter name spelling"
                )
                validation_errors.append(
                    ValidationError(
                        field=field,
                        message=error_msg,
                        code=code,
                        suggested_value=None,
                    )
                )
            elif "must be" in error_msg:
                # Extract field name (usually first word before "must")
                parts = error_msg.split(" must be")
                if parts:
                    field = parts[0].strip()
                    message = error_msg

                    # Determine error code
                    suggested_value = None  # Initialize before conditionals
                    if "must be an integer" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to an integer value")
                    elif "must be a number" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to a numeric value")
                    elif "must be a boolean" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to a boolean value")
                    elif "must be a string" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to a string value")
                    elif "must be >=" in error_msg or "must be <=" in error_msg:
                        code = "OUT_OF_RANGE"
                        # Extract suggested value from schema
                        from strategies.market_logic.defaults import (
                            get_parameter_schema,
                        )

                        schema = get_parameter_schema(request.strategy_id)
                        if schema and field in schema:
                            param_schema = schema[field]
                            if "min" in param_schema and "max" in param_schema:
                                suggested_value = (
                                    param_schema["min"] + param_schema["max"]
                                ) / 2
                            elif "min" in param_schema:
                                suggested_value = param_schema["min"]
                            elif "max" in param_schema:
                                suggested_value = param_schema["max"]
                            else:
                                suggested_value = param_schema.get("default")
                        else:
                            suggested_value = None
                    else:
                        code = "VALIDATION_ERROR"
                        suggested_value = None

                    validation_errors.append(
                        ValidationError(
                            field=field,
                            message=message,
                            code=code,
                            suggested_value=suggested_value,
                        )
                    )
            else:
                # Generic error
                validation_errors.append(
                    ValidationError(
                        field="unknown",
                        message=error_msg,
                        code="VALIDATION_ERROR",
                        suggested_value=None,
                    )
                )

        # Estimate impact (simplified for now)
        estimated_impact = {
            "risk_level": "low",
            "affected_scope": (
                f"strategy:{request.strategy_id}"
                if not request.symbol
                else f"strategy:{request.strategy_id}:symbol:{request.symbol}"
            ),
            "parameter_count": len(request.parameters),
        }

        # Add risk assessment based on parameters
        high_risk_params = ["threshold", "multiplier", "risk_factor"]
        if any(param in request.parameters for param in high_risk_params):
            estimated_impact["risk_level"] = "medium"

        # Cross-service conflict detection
        conflicts = await detect_cross_service_conflicts(
            request.parameters, request.strategy_id, request.symbol
        )

        validation_response = ValidationResponse(
            validation_passed=success and len(validation_errors) == 0,
            errors=validation_errors,
            warnings=[],
            suggested_fixes=suggested_fixes,
            estimated_impact=estimated_impact,
            conflicts=conflicts,
        )

        return APIResponse(
            success=True,
            data=validation_response,
            metadata={
                "validation_mode": "dry_run",
                "scope": (
                    f"strategy:{request.strategy_id}"
                    if not request.symbol
                    else f"strategy:{request.strategy_id}:symbol:{request.symbol}"
                ),
            },
        )

    except Exception as e:
        logger.error(f"Error validating config: {e}")
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


@router.post(
    "/config/validate",
    response_model=APIResponse,
    summary="Validate configuration without applying changes",
    description="""
    **For LLM Agents**: Validate configuration parameters without persisting changes.

    This endpoint performs comprehensive validation including:
    - Parameter type and constraint validation
    - Dependency validation
    - Cross-service conflict detection (future)
    - Impact assessment

    **Example Request**:
    ```json
    {
      "parameters": {
        "buy_threshold": 1.3,
        "sell_threshold": 0.75
      },
      "strategy_id": "orderbook_skew",
      "symbol": "BTCUSDT"
    }
    ```

    **Example Response**:
    ```json
    {
      "success": true,
      "data": {
        "validation_passed": true,
        "errors": [],
        "warnings": [],
        "suggested_fixes": [],
        "estimated_impact": {
          "risk_level": "low",
          "affected_scope": "strategy:orderbook_skew"
        },
        "conflicts": []
      }
    }
    ```
    """,
    tags=["configuration"],
)
async def validate_config(request: ConfigValidationRequest):
    """Validate configuration without applying changes."""
    try:
        # Validate that strategy_id is provided for strategy config validation
        if not request.strategy_id:
            return APIResponse(
                success=False,
                error={
                    "code": "VALIDATION_ERROR",
                    "message": "strategy_id is required for configuration validation",
                },
            )

        manager = get_config_manager()

        # Perform validation using existing logic
        success, config, errors = await manager.set_config(
            strategy_id=request.strategy_id,
            parameters=request.parameters,
            changed_by="validation_api",
            symbol=request.symbol.upper() if request.symbol else None,
            reason="Validation only - no changes applied",
            validate_only=True,
        )

        # Convert errors to standardized format
        validation_errors = []
        suggested_fixes = []

        for error_msg in errors:
            # Parse error message to extract field and details
            if "Unknown parameter" in error_msg:
                # Handle "Unknown parameter" errors
                code = "UNKNOWN_PARAMETER"
                # Extract parameter name from "Unknown parameter: param_name"
                if "Unknown parameter:" in error_msg:
                    param_name = error_msg.split("Unknown parameter:")[-1].strip()
                    field = param_name
                else:
                    field = "unknown"
                suggested_fixes.append(
                    f"Remove {field} or check parameter name spelling"
                )
                validation_errors.append(
                    ValidationError(
                        field=field,
                        message=error_msg,
                        code=code,
                        suggested_value=None,
                    )
                )
            elif "must be" in error_msg:
                # Extract field name (usually first word before "must")
                parts = error_msg.split(" must be")
                if parts:
                    field = parts[0].strip()
                    message = error_msg

                    # Determine error code
                    suggested_value = None  # Initialize before conditionals
                    if "must be an integer" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to an integer value")
                    elif "must be a number" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to a numeric value")
                    elif "must be a boolean" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to a boolean value")
                    elif "must be a string" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to a string value")
                    elif "must be >=" in error_msg or "must be <=" in error_msg:
                        code = "OUT_OF_RANGE"
                        # Extract suggested value from schema
                        from strategies.market_logic.defaults import (
                            get_parameter_schema,
                        )

                        schema = get_parameter_schema(request.strategy_id)
                        if schema and field in schema:
                            param_schema = schema[field]
                            if "min" in param_schema and "max" in param_schema:
                                suggested_value = (
                                    param_schema["min"] + param_schema["max"]
                                ) / 2
                            elif "min" in param_schema:
                                suggested_value = param_schema["min"]
                            elif "max" in param_schema:
                                suggested_value = param_schema["max"]
                            else:
                                suggested_value = param_schema.get("default")
                        else:
                            suggested_value = None
                    else:
                        code = "VALIDATION_ERROR"
                        suggested_value = None

                    validation_errors.append(
                        ValidationError(
                            field=field,
                            message=message,
                            code=code,
                            suggested_value=suggested_value,
                        )
                    )
            else:
                # Generic error
                validation_errors.append(
                    ValidationError(
                        field="unknown",
                        message=error_msg,
                        code="VALIDATION_ERROR",
                        suggested_value=None,
                    )
                )

        # Estimate impact (simplified for now)
        estimated_impact = {
            "risk_level": "low",
            "affected_scope": (
                f"strategy:{request.strategy_id}"
                if not request.symbol
                else f"strategy:{request.strategy_id}:symbol:{request.symbol}"
            ),
            "parameter_count": len(request.parameters),
        }

        # Add risk assessment based on parameters
        high_risk_params = ["threshold", "multiplier", "risk_factor"]
        if any(param in request.parameters for param in high_risk_params):
            estimated_impact["risk_level"] = "medium"

        # Cross-service conflict detection
        conflicts = await detect_cross_service_conflicts(
            request.parameters, request.strategy_id, request.symbol
        )

        validation_response = ValidationResponse(
            validation_passed=success and len(validation_errors) == 0,
            errors=validation_errors,
            warnings=[],
            suggested_fixes=suggested_fixes,
            estimated_impact=estimated_impact,
            conflicts=conflicts,
        )

        return APIResponse(
            success=True,
            data=validation_response,
            metadata={
                "validation_mode": "dry_run",
                "scope": (
                    f"strategy:{request.strategy_id}"
                    if not request.symbol
                    else f"strategy:{request.strategy_id}:symbol:{request.symbol}"
                ),
            },
        )

    except Exception as e:
        logger.error(f"Error validating config: {e}")
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


@router.post(
    "/config/validate",
    response_model=APIResponse,
    summary="Validate configuration without applying changes",
    description="""
    **For LLM Agents**: Validate configuration parameters without persisting changes.

    This endpoint performs comprehensive validation including:
    - Parameter type and constraint validation
    - Dependency validation
    - Cross-service conflict detection (future)
    - Impact assessment

    **Example Request**:
    ```json
    {
      "parameters": {
        "buy_threshold": 1.3,
        "sell_threshold": 0.75
      },
      "strategy_id": "orderbook_skew",
      "symbol": "BTCUSDT"
    }
    ```

    **Example Response**:
    ```json
    {
      "success": true,
      "data": {
        "validation_passed": true,
        "errors": [],
        "warnings": [],
        "suggested_fixes": [],
        "estimated_impact": {
          "risk_level": "low",
          "affected_scope": "strategy:orderbook_skew"
        },
        "conflicts": []
      }
    }
    ```
    """,
    tags=["configuration"],
)
async def validate_config(request: ConfigValidationRequest):
    """Validate configuration without applying changes."""
    try:
        # Validate that strategy_id is provided for strategy config validation
        if not request.strategy_id:
            return APIResponse(
                success=False,
                error={
                    "code": "VALIDATION_ERROR",
                    "message": "strategy_id is required for configuration validation",
                },
            )

        manager = get_config_manager()

        # Perform validation using existing logic
        success, config, errors = await manager.set_config(
            strategy_id=request.strategy_id,
            parameters=request.parameters,
            changed_by="validation_api",
            symbol=request.symbol.upper() if request.symbol else None,
            reason="Validation only - no changes applied",
            validate_only=True,
        )

        # Convert errors to standardized format
        validation_errors = []
        suggested_fixes = []

        for error_msg in errors:
            # Parse error message to extract field and details
            if "Unknown parameter" in error_msg:
                # Handle "Unknown parameter" errors
                code = "UNKNOWN_PARAMETER"
                # Extract parameter name from "Unknown parameter: param_name"
                if "Unknown parameter:" in error_msg:
                    param_name = error_msg.split("Unknown parameter:")[-1].strip()
                    field = param_name
                else:
                    field = "unknown"
                suggested_fixes.append(
                    f"Remove {field} or check parameter name spelling"
                )
                validation_errors.append(
                    ValidationError(
                        field=field,
                        message=error_msg,
                        code=code,
                        suggested_value=None,
                    )
                )
            elif "must be" in error_msg:
                # Extract field name (usually first word before "must")
                parts = error_msg.split(" must be")
                if parts:
                    field = parts[0].strip()
                    message = error_msg

                    # Determine error code
                    suggested_value = None  # Initialize before conditionals
                    if "must be an integer" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to an integer value")
                    elif "must be a number" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to a numeric value")
                    elif "must be a boolean" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to a boolean value")
                    elif "must be a string" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to a string value")
                    elif "must be >=" in error_msg or "must be <=" in error_msg:
                        code = "OUT_OF_RANGE"
                        # Extract suggested value from schema
                        from strategies.market_logic.defaults import (
                            get_parameter_schema,
                        )

                        schema = get_parameter_schema(request.strategy_id)
                        if schema and field in schema:
                            param_schema = schema[field]
                            if "min" in param_schema and "max" in param_schema:
                                suggested_value = (
                                    param_schema["min"] + param_schema["max"]
                                ) / 2
                            elif "min" in param_schema:
                                suggested_value = param_schema["min"]
                            elif "max" in param_schema:
                                suggested_value = param_schema["max"]
                            else:
                                suggested_value = param_schema.get("default")
                        else:
                            suggested_value = None
                    else:
                        code = "VALIDATION_ERROR"
                        suggested_value = None

                    validation_errors.append(
                        ValidationError(
                            field=field,
                            message=message,
                            code=code,
                            suggested_value=suggested_value,
                        )
                    )
            else:
                # Generic error
                validation_errors.append(
                    ValidationError(
                        field="unknown",
                        message=error_msg,
                        code="VALIDATION_ERROR",
                        suggested_value=None,
                    )
                )

        # Estimate impact (simplified for now)
        estimated_impact = {
            "risk_level": "low",
            "affected_scope": (
                f"strategy:{request.strategy_id}"
                if not request.symbol
                else f"strategy:{request.strategy_id}:symbol:{request.symbol}"
            ),
            "parameter_count": len(request.parameters),
        }

        # Add risk assessment based on parameters
        high_risk_params = ["threshold", "multiplier", "risk_factor"]
        if any(param in request.parameters for param in high_risk_params):
            estimated_impact["risk_level"] = "medium"

        # Cross-service conflict detection
        conflicts = await detect_cross_service_conflicts(
            request.parameters, request.strategy_id, request.symbol
        )

        validation_response = ValidationResponse(
            validation_passed=success and len(validation_errors) == 0,
            errors=validation_errors,
            warnings=[],
            suggested_fixes=suggested_fixes,
            estimated_impact=estimated_impact,
            conflicts=conflicts,
        )

        return APIResponse(
            success=True,
            data=validation_response,
            metadata={
                "validation_mode": "dry_run",
                "scope": (
                    f"strategy:{request.strategy_id}"
                    if not request.symbol
                    else f"strategy:{request.strategy_id}:symbol:{request.symbol}"
                ),
            },
        )

    except Exception as e:
        logger.error(f"Error validating config: {e}")
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


@router.post(
    "/config/validate",
    response_model=APIResponse,
    summary="Validate configuration without applying changes",
    description="""
    **For LLM Agents**: Validate configuration parameters without persisting changes.

    This endpoint performs comprehensive validation including:
    - Parameter type and constraint validation
    - Dependency validation
    - Cross-service conflict detection (future)
    - Impact assessment

    **Example Request**:
    ```json
    {
      "parameters": {
        "buy_threshold": 1.3,
        "sell_threshold": 0.75
      },
      "strategy_id": "orderbook_skew",
      "symbol": "BTCUSDT"
    }
    ```

    **Example Response**:
    ```json
    {
      "success": true,
      "data": {
        "validation_passed": true,
        "errors": [],
        "warnings": [],
        "suggested_fixes": [],
        "estimated_impact": {
          "risk_level": "low",
          "affected_scope": "strategy:orderbook_skew"
        },
        "conflicts": []
      }
    }
    ```
    """,
    tags=["configuration"],
)
async def validate_config(request: ConfigValidationRequest):
    """Validate configuration without applying changes."""
    try:
        # Validate that strategy_id is provided for strategy config validation
        if not request.strategy_id:
            return APIResponse(
                success=False,
                error={
                    "code": "VALIDATION_ERROR",
                    "message": "strategy_id is required for configuration validation",
                },
            )

        manager = get_config_manager()

        # Perform validation using existing logic
        success, config, errors = await manager.set_config(
            strategy_id=request.strategy_id,
            parameters=request.parameters,
            changed_by="validation_api",
            symbol=request.symbol.upper() if request.symbol else None,
            reason="Validation only - no changes applied",
            validate_only=True,
        )

        # Convert errors to standardized format
        validation_errors = []
        suggested_fixes = []

        for error_msg in errors:
            # Parse error message to extract field and details
            if "Unknown parameter" in error_msg:
                # Handle "Unknown parameter" errors
                code = "UNKNOWN_PARAMETER"
                # Extract parameter name from "Unknown parameter: param_name"
                if "Unknown parameter:" in error_msg:
                    param_name = error_msg.split("Unknown parameter:")[-1].strip()
                    field = param_name
                else:
                    field = "unknown"
                suggested_fixes.append(
                    f"Remove {field} or check parameter name spelling"
                )
                validation_errors.append(
                    ValidationError(
                        field=field,
                        message=error_msg,
                        code=code,
                        suggested_value=None,
                    )
                )
            elif "must be" in error_msg:
                # Extract field name (usually first word before "must")
                parts = error_msg.split(" must be")
                if parts:
                    field = parts[0].strip()
                    message = error_msg

                    # Determine error code
                    suggested_value = None  # Initialize before conditionals
                    if "must be an integer" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to an integer value")
                    elif "must be a number" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to a numeric value")
                    elif "must be a boolean" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to a boolean value")
                    elif "must be a string" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to a string value")
                    elif "must be >=" in error_msg or "must be <=" in error_msg:
                        code = "OUT_OF_RANGE"
                        # Extract suggested value from schema
                        from strategies.market_logic.defaults import (
                            get_parameter_schema,
                        )

                        schema = get_parameter_schema(request.strategy_id)
                        if schema and field in schema:
                            param_schema = schema[field]
                            if "min" in param_schema and "max" in param_schema:
                                suggested_value = (
                                    param_schema["min"] + param_schema["max"]
                                ) / 2
                            elif "min" in param_schema:
                                suggested_value = param_schema["min"]
                            elif "max" in param_schema:
                                suggested_value = param_schema["max"]
                            else:
                                suggested_value = param_schema.get("default")
                        else:
                            suggested_value = None
                    else:
                        code = "VALIDATION_ERROR"
                        suggested_value = None

                    validation_errors.append(
                        ValidationError(
                            field=field,
                            message=message,
                            code=code,
                            suggested_value=suggested_value,
                        )
                    )
            else:
                # Generic error
                validation_errors.append(
                    ValidationError(
                        field="unknown",
                        message=error_msg,
                        code="VALIDATION_ERROR",
                        suggested_value=None,
                    )
                )

        # Estimate impact (simplified for now)
        estimated_impact = {
            "risk_level": "low",
            "affected_scope": (
                f"strategy:{request.strategy_id}"
                if not request.symbol
                else f"strategy:{request.strategy_id}:symbol:{request.symbol}"
            ),
            "parameter_count": len(request.parameters),
        }

        # Add risk assessment based on parameters
        high_risk_params = ["threshold", "multiplier", "risk_factor"]
        if any(param in request.parameters for param in high_risk_params):
            estimated_impact["risk_level"] = "medium"

        # Cross-service conflict detection
        conflicts = await detect_cross_service_conflicts(
            request.parameters, request.strategy_id, request.symbol
        )

        validation_response = ValidationResponse(
            validation_passed=success and len(validation_errors) == 0,
            errors=validation_errors,
            warnings=[],
            suggested_fixes=suggested_fixes,
            estimated_impact=estimated_impact,
            conflicts=conflicts,
        )

        return APIResponse(
            success=True,
            data=validation_response,
            metadata={
                "validation_mode": "dry_run",
                "scope": (
                    f"strategy:{request.strategy_id}"
                    if not request.symbol
                    else f"strategy:{request.strategy_id}:symbol:{request.symbol}"
                ),
            },
        )

    except Exception as e:
        logger.error(f"Error validating config: {e}")
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
    "/config/validate",
    response_model=APIResponse,
    summary="Validate configuration without applying changes",
    description="""
    **For LLM Agents**: Validate configuration parameters without persisting changes.

    This endpoint performs comprehensive validation including:
    - Parameter type and constraint validation
    - Dependency validation
    - Cross-service conflict detection (future)
    - Impact assessment

    **Example Request**:
    ```json
    {
      "parameters": {
        "buy_threshold": 1.3,
        "sell_threshold": 0.75
      },
      "strategy_id": "orderbook_skew",
      "symbol": "BTCUSDT"
    }
    ```

    **Example Response**:
    ```json
    {
      "success": true,
      "data": {
        "validation_passed": true,
        "errors": [],
        "warnings": [],
        "suggested_fixes": [],
        "estimated_impact": {
          "risk_level": "low",
          "affected_scope": "strategy:orderbook_skew"
        },
        "conflicts": []
      }
    }
    ```
    """,
    tags=["configuration"],
)
async def validate_config(request: ConfigValidationRequest):
    """Validate configuration without applying changes."""
    try:
        # Validate that strategy_id is provided for strategy config validation
        if not request.strategy_id:
            return APIResponse(
                success=False,
                error={
                    "code": "VALIDATION_ERROR",
                    "message": "strategy_id is required for configuration validation",
                },
            )

        manager = get_config_manager()

        # Perform validation using existing logic
        success, config, errors = await manager.set_config(
            strategy_id=request.strategy_id,
            parameters=request.parameters,
            changed_by="validation_api",
            symbol=request.symbol.upper() if request.symbol else None,
            reason="Validation only - no changes applied",
            validate_only=True,
        )

        # Convert errors to standardized format
        validation_errors = []
        suggested_fixes = []

        for error_msg in errors:
            # Parse error message to extract field and details
            if "Unknown parameter" in error_msg:
                # Handle "Unknown parameter" errors
                code = "UNKNOWN_PARAMETER"
                # Extract parameter name from "Unknown parameter: param_name"
                if "Unknown parameter:" in error_msg:
                    param_name = error_msg.split("Unknown parameter:")[-1].strip()
                    field = param_name
                else:
                    field = "unknown"
                suggested_fixes.append(
                    f"Remove {field} or check parameter name spelling"
                )
                validation_errors.append(
                    ValidationError(
                        field=field,
                        message=error_msg,
                        code=code,
                        suggested_value=None,
                    )
                )
            elif "must be" in error_msg:
                # Extract field name (usually first word before "must")
                parts = error_msg.split(" must be")
                if parts:
                    field = parts[0].strip()
                    message = error_msg

                    # Determine error code
                    suggested_value = None  # Initialize before conditionals
                    if "must be an integer" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to an integer value")
                    elif "must be a number" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to a numeric value")
                    elif "must be a boolean" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to a boolean value")
                    elif "must be a string" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to a string value")
                    elif "must be >=" in error_msg or "must be <=" in error_msg:
                        code = "OUT_OF_RANGE"
                        # Extract suggested value from schema
                        from strategies.market_logic.defaults import (
                            get_parameter_schema,
                        )

                        schema = get_parameter_schema(request.strategy_id)
                        if schema and field in schema:
                            param_schema = schema[field]
                            if "min" in param_schema and "max" in param_schema:
                                suggested_value = (
                                    param_schema["min"] + param_schema["max"]
                                ) / 2
                            elif "min" in param_schema:
                                suggested_value = param_schema["min"]
                            elif "max" in param_schema:
                                suggested_value = param_schema["max"]
                            else:
                                suggested_value = param_schema.get("default")
                        else:
                            suggested_value = None
                    else:
                        code = "VALIDATION_ERROR"
                        suggested_value = None

                    validation_errors.append(
                        ValidationError(
                            field=field,
                            message=message,
                            code=code,
                            suggested_value=suggested_value,
                        )
                    )
            else:
                # Generic error
                validation_errors.append(
                    ValidationError(
                        field="unknown",
                        message=error_msg,
                        code="VALIDATION_ERROR",
                        suggested_value=None,
                    )
                )

        # Estimate impact (simplified for now)
        estimated_impact = {
            "risk_level": "low",
            "affected_scope": (
                f"strategy:{request.strategy_id}"
                if not request.symbol
                else f"strategy:{request.strategy_id}:symbol:{request.symbol}"
            ),
            "parameter_count": len(request.parameters),
        }

        # Add risk assessment based on parameters
        high_risk_params = ["threshold", "multiplier", "risk_factor"]
        if any(param in request.parameters for param in high_risk_params):
            estimated_impact["risk_level"] = "medium"

        # Cross-service conflict detection
        conflicts = await detect_cross_service_conflicts(
            request.parameters, request.strategy_id, request.symbol
        )

        validation_response = ValidationResponse(
            validation_passed=success and len(validation_errors) == 0,
            errors=validation_errors,
            warnings=[],
            suggested_fixes=suggested_fixes,
            estimated_impact=estimated_impact,
            conflicts=conflicts,
        )

        return APIResponse(
            success=True,
            data=validation_response,
            metadata={
                "validation_mode": "dry_run",
                "scope": (
                    f"strategy:{request.strategy_id}"
                    if not request.symbol
                    else f"strategy:{request.strategy_id}:symbol:{request.symbol}"
                ),
            },
        )

    except Exception as e:
        logger.error(f"Error validating config: {e}")
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


@router.post(
    "/config/validate",
    response_model=APIResponse,
    summary="Validate configuration without applying changes",
    description="""
    **For LLM Agents**: Validate configuration parameters without persisting changes.

    This endpoint performs comprehensive validation including:
    - Parameter type and constraint validation
    - Dependency validation
    - Cross-service conflict detection (future)
    - Impact assessment

    **Example Request**:
    ```json
    {
      "parameters": {
        "buy_threshold": 1.3,
        "sell_threshold": 0.75
      },
      "strategy_id": "orderbook_skew",
      "symbol": "BTCUSDT"
    }
    ```

    **Example Response**:
    ```json
    {
      "success": true,
      "data": {
        "validation_passed": true,
        "errors": [],
        "warnings": [],
        "suggested_fixes": [],
        "estimated_impact": {
          "risk_level": "low",
          "affected_scope": "strategy:orderbook_skew"
        },
        "conflicts": []
      }
    }
    ```
    """,
    tags=["configuration"],
)
async def validate_config(request: ConfigValidationRequest):
    """Validate configuration without applying changes."""
    try:
        # Validate that strategy_id is provided for strategy config validation
        if not request.strategy_id:
            return APIResponse(
                success=False,
                error={
                    "code": "VALIDATION_ERROR",
                    "message": "strategy_id is required for configuration validation",
                },
            )

        manager = get_config_manager()

        # Perform validation using existing logic
        success, config, errors = await manager.set_config(
            strategy_id=request.strategy_id,
            parameters=request.parameters,
            changed_by="validation_api",
            symbol=request.symbol.upper() if request.symbol else None,
            reason="Validation only - no changes applied",
            validate_only=True,
        )

        # Convert errors to standardized format
        validation_errors = []
        suggested_fixes = []

        for error_msg in errors:
            # Parse error message to extract field and details
            if "Unknown parameter" in error_msg:
                # Handle "Unknown parameter" errors
                code = "UNKNOWN_PARAMETER"
                # Extract parameter name from "Unknown parameter: param_name"
                if "Unknown parameter:" in error_msg:
                    param_name = error_msg.split("Unknown parameter:")[-1].strip()
                    field = param_name
                else:
                    field = "unknown"
                suggested_fixes.append(
                    f"Remove {field} or check parameter name spelling"
                )
                validation_errors.append(
                    ValidationError(
                        field=field,
                        message=error_msg,
                        code=code,
                        suggested_value=None,
                    )
                )
            elif "must be" in error_msg:
                # Extract field name (usually first word before "must")
                parts = error_msg.split(" must be")
                if parts:
                    field = parts[0].strip()
                    message = error_msg

                    # Determine error code
                    suggested_value = None  # Initialize before conditionals
                    if "must be an integer" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to an integer value")
                    elif "must be a number" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to a numeric value")
                    elif "must be a boolean" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to a boolean value")
                    elif "must be a string" in error_msg:
                        code = "INVALID_TYPE"
                        suggested_fixes.append(f"Change {field} to a string value")
                    elif "must be >=" in error_msg or "must be <=" in error_msg:
                        code = "OUT_OF_RANGE"
                        # Extract suggested value from schema
                        from strategies.market_logic.defaults import (
                            get_parameter_schema,
                        )

                        schema = get_parameter_schema(request.strategy_id)
                        if schema and field in schema:
                            param_schema = schema[field]
                            if "min" in param_schema and "max" in param_schema:
                                suggested_value = (
                                    param_schema["min"] + param_schema["max"]
                                ) / 2
                            elif "min" in param_schema:
                                suggested_value = param_schema["min"]
                            elif "max" in param_schema:
                                suggested_value = param_schema["max"]
                            else:
                                suggested_value = param_schema.get("default")
                        else:
                            suggested_value = None
                    else:
                        code = "VALIDATION_ERROR"
                        suggested_value = None

                    validation_errors.append(
                        ValidationError(
                            field=field,
                            message=message,
                            code=code,
                            suggested_value=suggested_value,
                        )
                    )
            else:
                # Generic error
                validation_errors.append(
                    ValidationError(
                        field="unknown",
                        message=error_msg,
                        code="VALIDATION_ERROR",
                        suggested_value=None,
                    )
                )

        # Estimate impact (simplified for now)
        estimated_impact = {
            "risk_level": "low",
            "affected_scope": (
                f"strategy:{request.strategy_id}"
                if not request.symbol
                else f"strategy:{request.strategy_id}:symbol:{request.symbol}"
            ),
            "parameter_count": len(request.parameters),
        }

        # Add risk assessment based on parameters
        high_risk_params = ["threshold", "multiplier", "risk_factor"]
        if any(param in request.parameters for param in high_risk_params):
            estimated_impact["risk_level"] = "medium"

        # Cross-service conflict detection
        conflicts = await detect_cross_service_conflicts(
            request.parameters, request.strategy_id, request.symbol
        )

        validation_response = ValidationResponse(
            validation_passed=success and len(validation_errors) == 0,
            errors=validation_errors,
            warnings=[],
            suggested_fixes=suggested_fixes,
            estimated_impact=estimated_impact,
            conflicts=conflicts,
        )

        return APIResponse(
            success=True,
            data=validation_response,
            metadata={
                "validation_mode": "dry_run",
                "scope": (
                    f"strategy:{request.strategy_id}"
                    if not request.symbol
                    else f"strategy:{request.strategy_id}:symbol:{request.symbol}"
                ),
            },
        )

    except Exception as e:
        logger.error(f"Error validating config: {e}")
        return APIResponse(
            success=False, error={"code": "INTERNAL_ERROR", "message": str(e)}
        )


# Service URLs for cross-service conflict detection
SERVICE_URLS = {
    "tradeengine": os.getenv(
        "TRADEENGINE_URL", "http://petrosa-tradeengine-service:80"
    ),
    "data-manager": os.getenv("DATA_MANAGER_URL", "http://petrosa-data-manager:80"),
    "ta-bot": os.getenv("TA_BOT_URL", "http://petrosa-ta-bot-service:80"),
}


async def detect_cross_service_conflicts(
    parameters: dict[str, Any],
    strategy_id: str | None = None,
    symbol: str | None = None,
) -> list[CrossServiceConflict]:
    """
    Detect cross-service configuration conflicts.

    Queries other services' /api/v1/config/validate endpoints to check for
    conflicting configurations.

    Args:
        parameters: Configuration parameters to check
        strategy_id: Strategy identifier
        symbol: Trading symbol (optional)

    Returns:
        List of CrossServiceConflict objects
    """
    conflicts = []
    timeout = httpx.Timeout(5.0)  # Short timeout for conflict checks

    async with httpx.AsyncClient(timeout=timeout) as client:
        # Check ta-bot for strategy config conflicts (same strategy)
        if strategy_id:
            try:
                validation_request = {
                    "parameters": parameters,
                    "strategy_id": strategy_id,
                }
                if symbol:
                    validation_request["symbol"] = symbol

                response = await client.post(
                    f"{SERVICE_URLS['ta-bot']}/api/v1/config/validate",
                    json=validation_request,
                )

                if response.status_code == 200:
                    data = response.json()
                    if data.get("success") and data.get("data"):
                        validation_data = data["data"]
                        # Check if the service reports conflicts or validation issues
                        if not validation_data.get("validation_passed", True):
                            errors = validation_data.get("errors", [])
                            if errors:
                                conflicts.append(
                                    CrossServiceConflict(
                                        service="ta-bot",
                                        conflict_type="VALIDATION_CONFLICT",
                                        description=(
                                            f"ta-bot reports validation errors for "
                                            f"strategy {strategy_id}: "
                                            f"{', '.join([e.get('message', '') for e in errors[:2]])}"
                                        ),
                                        resolution=(
                                            "Review ta-bot validation errors and "
                                            "ensure parameter compatibility"
                                        ),
                                    )
                                )

            except httpx.TimeoutException:
                logger.debug("Timeout checking ta-bot for conflicts")
            except Exception as e:
                logger.debug(f"Error checking ta-bot conflicts: {e}")

        # Check tradeengine for trading parameter conflicts
        if any(
            param in parameters
            for param in ["leverage", "stop_loss_pct", "take_profit_pct"]
        ):
            try:
                validation_request = {
                    "parameters": {
                        k: v
                        for k, v in parameters.items()
                        if k in ["leverage", "stop_loss_pct", "take_profit_pct"]
                    },
                }
                if symbol:
                    validation_request["symbol"] = symbol

                response = await client.post(
                    f"{SERVICE_URLS['tradeengine']}/api/v1/config/validate",
                    json=validation_request,
                )

                if response.status_code == 200:
                    data = response.json()
                    if data.get("success") and data.get("data"):
                        validation_data = data["data"]
                        if not validation_data.get("validation_passed", True):
                            errors = validation_data.get("errors", [])
                            if errors:
                                conflicts.append(
                                    CrossServiceConflict(
                                        service="tradeengine",
                                        conflict_type="VALIDATION_CONFLICT",
                                        description=(
                                            f"tradeengine reports validation errors for "
                                            f"trading parameters: "
                                            f"{', '.join([e.get('message', '') for e in errors[:2]])}"
                                        ),
                                        resolution=(
                                            "Review tradeengine validation errors and "
                                            "ensure parameter compatibility"
                                        ),
                                    )
                                )

            except httpx.TimeoutException:
                logger.debug("Timeout checking tradeengine for conflicts")
            except Exception as e:
                logger.debug(f"Error checking tradeengine conflicts: {e}")

    return conflicts
