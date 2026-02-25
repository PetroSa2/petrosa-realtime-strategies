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
)
async def list_strategies():
    """List all available trading strategies with their configuration status."""
    try:
        manager = get_config_manager()
        strategies = await manager.list_strategies()
        strategy_list = [StrategyListItem(**strategy) for strategy in strategies]
        return APIResponse(
            success=True,
            data=strategy_list,
            metadata={"total_count": len(strategy_list)},
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
)
async def get_strategy_schema(
    strategy_id: str = Path(..., description="Strategy identifier"),
):
    """Get parameter schema for a strategy."""
    try:
        schema = get_parameter_schema(strategy_id)
        defaults = get_strategy_defaults(strategy_id)

        if not defaults:
            return APIResponse(
                success=False,
                error={"code": "NOT_FOUND", "message": f"Strategy not found: {strategy_id}"},
            )

        schema_items = []
        for param_name, param_value in defaults.items():
            param_schema = schema.get(param_name, {})
            schema_items.append(
                ParameterSchemaItem(
                    name=param_name,
                    type=param_schema.get("type", type(param_value).__name__),
                    description=param_schema.get("description", f"Parameter: {param_name}"),
                    default=param_value,
                    min=param_schema.get("min"),
                    max=param_schema.get("max"),
                    allowed_values=param_schema.get("allowed_values"),
                    example=param_schema.get("example", param_value),
                )
            )

        return APIResponse(success=True, data=schema_items)
    except Exception as e:
        logger.error(f"Error getting schema: {e}")
        return APIResponse(success=False, error={"code": "INTERNAL_ERROR", "message": str(e)})


@router.get(
    "/strategies/{strategy_id}/defaults",
    response_model=APIResponse,
    summary="Get default parameters for a strategy",
)
async def get_strategy_defaults_endpoint(
    strategy_id: str = Path(..., description="Strategy identifier"),
):
    """Get hardcoded default parameters for a strategy."""
    try:
        defaults = get_strategy_defaults(strategy_id)
        if not defaults:
            return APIResponse(
                success=False,
                error={"code": "NOT_FOUND", "message": f"Strategy not found: {strategy_id}"},
            )
        metadata = get_strategy_metadata(strategy_id)
        return APIResponse(
            success=True,
            data=defaults,
            metadata={"strategy_name": metadata.get("name", strategy_id)},
        )
    except Exception as e:
        logger.error(f"Error getting defaults: {e}")
        return APIResponse(success=False, error={"code": "INTERNAL_ERROR", "message": str(e)})


@router.get(
    "/strategies/{strategy_id}/config",
    response_model=APIResponse,
    summary="Get global configuration for a strategy",
)
async def get_global_config(
    strategy_id: str = Path(..., description="Strategy identifier"),
):
    """Get global configuration for a strategy."""
    try:
        manager = get_config_manager()
        config = await manager.get_config(strategy_id, symbol=None)
        return APIResponse(
            success=True,
            data=ConfigResponse(
                strategy_id=strategy_id,
                symbol=None,
                parameters=config.get("parameters", {}),
                version=config.get("version", 0),
                source=config.get("source", "unknown"),
                is_override=False,
                created_at=config.get("created_at"),
                updated_at=config.get("updated_at"),
            ),
        )
    except Exception as e:
        logger.error(f"Error getting global config: {e}")
        return APIResponse(success=False, error={"code": "INTERNAL_ERROR", "message": str(e)})


@router.get(
    "/strategies/{strategy_id}/config/{symbol}",
    response_model=APIResponse,
    summary="Get symbol-specific configuration override",
)
async def get_symbol_config(
    strategy_id: str = Path(..., description="Strategy identifier"),
    symbol: str = Path(..., description="Trading symbol"),
):
    """Get symbol-specific configuration for a strategy."""
    try:
        manager = get_config_manager()
        config = await manager.get_config(strategy_id, symbol=symbol.upper())
        return APIResponse(
            success=True,
            data=ConfigResponse(
                strategy_id=strategy_id,
                symbol=symbol.upper(),
                parameters=config.get("parameters", {}),
                version=config.get("version", 0),
                source=config.get("source", "unknown"),
                is_override=config.get("is_override", False),
                created_at=config.get("created_at"),
                updated_at=config.get("updated_at"),
            ),
        )
    except Exception as e:
        logger.error(f"Error getting symbol config: {e}")
        return APIResponse(success=False, error={"code": "INTERNAL_ERROR", "message": str(e)})


@router.post(
    "/strategies/{strategy_id}/config",
    response_model=APIResponse,
    summary="Create or update global configuration",
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
                error={"code": "VALIDATION_ERROR", "message": "Validation failed", "details": {"errors": errors}},
            )

        if request.validate_only:
            return APIResponse(success=True, data=None, metadata={"validation": "passed"})

        return APIResponse(
            success=True,
            data=ConfigResponse(
                strategy_id=config.strategy_id,
                symbol=None,
                parameters=config.parameters,
                version=config.version,
                source="mongodb",
                is_override=False,
                created_at=config.created_at.isoformat(),
                updated_at=config.updated_at.isoformat(),
            ),
            metadata={"action": "updated"},
        )
    except Exception as e:
        logger.error(f"Error updating global config: {e}")
        return APIResponse(success=False, error={"code": "INTERNAL_ERROR", "message": str(e)})


@router.post(
    "/strategies/{strategy_id}/config/{symbol}",
    response_model=APIResponse,
    summary="Create or update symbol-specific configuration",
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
                error={"code": "VALIDATION_ERROR", "message": "Validation failed", "details": {"errors": errors}},
            )

        if request.validate_only:
            return APIResponse(success=True, data=None, metadata={"validation": "passed"})

        return APIResponse(
            success=True,
            data=ConfigResponse(
                strategy_id=config.strategy_id,
                symbol=symbol.upper(),
                parameters=config.parameters,
                version=config.version,
                source="mongodb",
                is_override=True,
                created_at=config.created_at.isoformat(),
                updated_at=config.updated_at.isoformat(),
            ),
        )
    except Exception as e:
        logger.error(f"Error updating symbol config: {e}")
        return APIResponse(success=False, error={"code": "INTERNAL_ERROR", "message": str(e)})


@router.delete(
    "/strategies/{strategy_id}/config",
    response_model=APIResponse,
    summary="Delete global configuration",
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
                error={"code": "DELETE_FAILED", "message": "Failed to delete", "details": {"errors": errors}},
            )

        return APIResponse(success=True, data={"message": "deleted successfully"})
    except Exception as e:
        logger.error(f"Error deleting global config: {e}")
        return APIResponse(success=False, error={"code": "INTERNAL_ERROR", "message": str(e)})


@router.delete(
    "/strategies/{strategy_id}/config/{symbol}",
    response_model=APIResponse,
    summary="Delete symbol-specific configuration override",
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
            strategy_id=strategy_id, changed_by=changed_by, symbol=symbol.upper(), reason=reason
        )

        if not success:
            return APIResponse(
                success=False,
                error={"code": "DELETE_FAILED", "message": "Failed to delete", "details": {"errors": errors}},
            )

        return APIResponse(
            success=True,
            data={"message": "deleted successfully"},
            metadata={"symbol": symbol.upper()},
        )
    except Exception as e:
        logger.error(f"Error deleting symbol config: {e}")
        return APIResponse(success=False, error={"code": "INTERNAL_ERROR", "message": str(e)})


@router.get(
    "/strategies/{strategy_id}/audit",
    response_model=APIResponse,
    summary="Get configuration change history",
)
async def get_audit_trail(
    strategy_id: str = Path(..., description="Strategy identifier"),
    symbol: str | None = Query(None, description="Optional symbol filter"),
    limit: int = Query(50, ge=1, le=1000, description="Max records to return"),
):
    """Get configuration change history."""
    try:
        manager = get_config_manager()
        audit_trail = await manager.get_audit_trail(strategy_id, symbol, limit)
        
        items = [
            AuditTrailItem(
                id=item.id,
                strategy_id=item.strategy_id,
                symbol=item.symbol,
                action=item.action,
                old_parameters=item.old_parameters,
                new_parameters=item.new_parameters,
                changed_by=item.changed_by,
                changed_at=item.changed_at.isoformat(),
                reason=item.reason,
            )
            for item in audit_trail
        ]
        
        return APIResponse(success=True, data=items, metadata={"count": len(items)})
    except Exception as e:
        logger.error(f"Error getting audit trail: {e}")
        return APIResponse(success=False, error={"code": "INTERNAL_ERROR", "message": str(e)})


@router.post(
    "/strategies/cache/refresh",
    response_model=APIResponse,
    summary="Refresh configuration cache",
)
async def refresh_cache():
    """Force refresh of all cached configurations."""
    try:
        manager = get_config_manager()
        await manager.refresh_cache()
        return APIResponse(
            success=True,
            data={"message": "cache refreshed successfully"},
            metadata={"action": "cache_refresh"},
        )
    except Exception as e:
        logger.error(f"Error refreshing cache: {e}")
        return APIResponse(
            success=False, error={"code": "INTERNAL_ERROR", "message": str(e)}
        )


@router.post(
    "/strategies/{strategy_id}/rollback",
    response_model=APIResponse,
    summary="Rollback strategy configuration",
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
                error={"code": "ROLLBACK_FAILED", "message": "Failed to rollback", "details": {"errors": errors}},
            )

        return APIResponse(
            success=True,
            data=ConfigResponse(
                strategy_id=strategy_id,
                symbol=symbol,
                parameters=config.parameters if config else {},
                version=config.version if config else 0,
                source="mongodb",
                is_override=bool(symbol),
                created_at="",
                updated_at=datetime.utcnow().isoformat(),
            ),
        )
    except Exception as e:
        logger.error(f"Error rolling back config: {e}")
        return APIResponse(success=False, error={"code": "INTERNAL_ERROR", "message": str(e)})


@router.post(
    "/strategies/{strategy_id}/restore",
    response_model=APIResponse,
    summary="Restore strategy configuration",
)
async def restore_config(
    request: RollbackRequest,
    strategy_id: str = Path(..., description="Strategy identifier"),
    symbol: str | None = Query(None, description="Optional symbol filter"),
):
    """Restore configuration (alias for rollback)."""
    return await rollback_config(request, strategy_id, symbol)


@router.post(
    "/config/validate",
    response_model=APIResponse,
    summary="Validate configuration without applying changes",
)
async def validate_config(request: ConfigValidationRequest):
    """Validate configuration without applying changes."""
    try:
        if not request.strategy_id:
            return APIResponse(
                success=False,
                error={"code": "VALIDATION_ERROR", "message": "strategy_id is required"},
            )

        manager = get_config_manager()
        success, config, errors = await manager.set_config(
            strategy_id=request.strategy_id,
            parameters=request.parameters,
            changed_by="validation_api",
            symbol=request.symbol.upper() if request.symbol else None,
            reason="Validation only",
            validate_only=True,
        )

        validation_errors = []
        for error_msg in errors:
            if "Unknown parameter" in error_msg:
                code = "UNKNOWN_PARAMETER"
                field = error_msg.split("Unknown parameter:")[-1].strip() if ":" in error_msg else "unknown"
                validation_errors.append(ValidationError(field=field, message=error_msg, code=code))
            elif "must be" in error_msg:
                field = error_msg.split(" must be")[0].strip()
                code = "INVALID_TYPE" if "type" in error_msg or "integer" in error_msg or "number" in error_msg else "OUT_OF_RANGE"
                validation_errors.append(ValidationError(field=field, message=error_msg, code=code))
            else:
                validation_errors.append(ValidationError(field="unknown", message=error_msg, code="VALIDATION_ERROR"))

        conflicts = await detect_cross_service_conflicts(request.parameters, request.strategy_id, request.symbol)

        return APIResponse(
            success=True,
            data=ValidationResponse(
                validation_passed=success and len(validation_errors) == 0,
                errors=validation_errors,
                conflicts=conflicts,
                estimated_impact={"risk_level": "low", "parameter_count": len(request.parameters)},
            ),
        )
    except Exception as e:
        logger.error(f"Error validating config: {e}")
        return APIResponse(success=False, error={"code": "INTERNAL_ERROR", "message": str(e)})


# Service URLs for cross-service conflict detection
SERVICE_URLS = {
    "tradeengine": os.getenv("TRADEENGINE_URL", "http://petrosa-tradeengine-service:80"),
    "data-manager": os.getenv("DATA_MANAGER_URL", "http://petrosa-data-manager:80"),
    "ta-bot": os.getenv("TA_BOT_URL", "http://petrosa-ta-bot-service:80"),
}


async def detect_cross_service_conflicts(
    parameters: dict[str, Any],
    strategy_id: str | None = None,
    symbol: str | None = None,
) -> list[CrossServiceConflict]:
    """Detect cross-service configuration conflicts."""
    conflicts = []
    async with httpx.AsyncClient(timeout=5.0) as client:
        if strategy_id:
            try:
                resp = await client.post(
                    f"{SERVICE_URLS['ta-bot']}/api/v1/config/validate",
                    json={"parameters": parameters, "strategy_id": strategy_id, "symbol": symbol},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("success") and not data.get("data", {}).get("validation_passed", True):
                        conflicts.append(CrossServiceConflict(
                            service="ta-bot",
                            conflict_type="VALIDATION_CONFLICT",
                            description="ta-bot reported validation errors",
                            resolution="Check ta-bot logs"
                        ))
            except Exception:
                pass

        # Check tradeengine for trading parameters
        trading_params = ["leverage", "stop_loss_pct", "take_profit_pct"]
        if any(p in parameters for p in trading_params):
            try:
                resp = await client.post(
                    f"{SERVICE_URLS['tradeengine']}/api/v1/config/validate",
                    json={"parameters": {k: v for k, v in parameters.items() if k in trading_params}, "symbol": symbol},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("success") and not data.get("data", {}).get("validation_passed", True):
                        conflicts.append(CrossServiceConflict(
                            service="tradeengine",
                            conflict_type="VALIDATION_CONFLICT",
                            description="tradeengine reported validation errors",
                            resolution="Check tradeengine logs"
                        ))
            except Exception:
                pass

    return conflicts
