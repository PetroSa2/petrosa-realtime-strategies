"""
Pydantic response models for API endpoints.

Provides type-safe request/response models for configuration management.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class APIResponse(BaseModel):
    """Standard API response wrapper."""

    success: bool = Field(..., description="Whether operation succeeded")
    data: Any | None = Field(None, description="Response data")
    error: dict[str, Any] | None = Field(None, description="Error details if failed")
    metadata: dict[str, Any] | None = Field(None, description="Additional metadata")


class ConfigResponse(BaseModel):
    """Configuration response model."""

    strategy_id: str = Field(..., description="Strategy identifier")
    symbol: str | None = Field(None, description="Trading symbol (None for global)")
    parameters: dict[str, Any] = Field(..., description="Configuration parameters")
    version: int = Field(..., description="Configuration version")
    source: str = Field(
        ..., description="Configuration source (mongodb/environment/default)"
    )
    is_override: bool = Field(
        ..., description="Whether this is a symbol-specific override"
    )
    created_at: str | None = Field(None, description="Creation timestamp")
    updated_at: str | None = Field(None, description="Last update timestamp")


class ConfigUpdateRequest(BaseModel):
    """Configuration update request."""

    parameters: dict[str, Any] = Field(
        ..., description="Configuration parameters to update"
    )
    changed_by: str = Field(
        ..., description="Who is making this change (e.g., 'llm_agent_v1', 'admin')"
    )
    reason: str | None = Field(None, description="Reason for the configuration change")
    validate_only: bool = Field(
        False, description="If true, only validate parameters without saving"
    )


class ParameterSchemaItem(BaseModel):
    """Parameter schema definition."""

    name: str = Field(..., description="Parameter name")
    type: str = Field(..., description="Data type (int, float, bool, str, list)")
    description: str = Field(..., description="What this parameter controls")
    default: Any = Field(..., description="Default value")
    min: float | None = Field(None, description="Minimum value (for numeric)")
    max: float | None = Field(None, description="Maximum value (for numeric)")
    allowed_values: list[Any] | None = Field(
        None, description="Allowed values (for enums)"
    )
    example: Any = Field(..., description="Example valid value")


class StrategyListItem(BaseModel):
    """Strategy list item."""

    strategy_id: str = Field(..., description="Strategy identifier")
    name: str = Field(..., description="Human-readable name")
    description: str = Field(..., description="Strategy description")
    has_global_config: bool = Field(False, description="Whether global config exists")
    symbol_overrides: list[str] = Field(
        default_factory=list, description="Symbols with overrides"
    )
    parameter_count: int = Field(0, description="Number of parameters")


class AuditTrailItem(BaseModel):
    """Audit trail record."""

    id: str = Field(..., description="Audit record ID")
    strategy_id: str = Field(..., description="Strategy identifier")
    symbol: str | None = Field(None, description="Symbol (None for global)")
    action: str = Field(..., description="Type of change made")
    old_parameters: dict[str, Any] | None = Field(
        None, description="Previous parameter values"
    )
    new_parameters: dict[str, Any] | None = Field(
        None, description="New parameter values"
    )
    changed_by: str = Field(..., description="Who/what made the change")
    changed_at: str = Field(..., description="When the change occurred")
    reason: str | None = Field(None, description="Reason for the change")


# -------------------------------------------------------------------------
# Configuration Validation Models
# -------------------------------------------------------------------------


class ValidationError(BaseModel):
    """Standardized validation error format."""

    field: str = Field(..., description="Parameter name that failed validation")
    message: str = Field(..., description="Human-readable error message")
    code: str = Field(
        ...,
        description="Error code (e.g., 'INVALID_TYPE', 'OUT_OF_RANGE', 'UNKNOWN_PARAMETER')",
    )
    suggested_value: Any | None = Field(
        None, description="Suggested correct value if applicable"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "field": "buy_threshold",
                "message": "buy_threshold must be >= 1.0, got 0.5",
                "code": "OUT_OF_RANGE",
                "suggested_value": 1.2,
            }
        }


class CrossServiceConflict(BaseModel):
    """Cross-service configuration conflict."""

    service: str = Field(..., description="Service name with conflicting configuration")
    conflict_type: str = Field(
        ..., description="Type of conflict (e.g., 'PARAMETER_CONFLICT')"
    )
    description: str = Field(..., description="Description of the conflict")
    resolution: str = Field(..., description="Suggested resolution")

    class Config:
        json_schema_extra = {
            "example": {
                "service": "tradeengine",
                "conflict_type": "PARAMETER_CONFLICT",
                "description": "Conflicting threshold settings between services",
                "resolution": "Use consistent threshold values across all services",
            }
        }


class ValidationResponse(BaseModel):
    """Standardized validation response across all services."""

    validation_passed: bool = Field(
        ..., description="Whether validation passed without errors"
    )
    errors: list[ValidationError] = Field(
        default_factory=list, description="List of validation errors"
    )
    warnings: list[str] = Field(
        default_factory=list, description="Non-blocking warnings"
    )
    suggested_fixes: list[str] = Field(
        default_factory=list, description="Actionable suggestions to fix errors"
    )
    estimated_impact: dict[str, Any] = Field(
        default_factory=dict,
        description="Estimated impact of configuration changes",
    )
    conflicts: list[CrossServiceConflict] = Field(
        default_factory=list, description="Cross-service conflicts detected"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "validation_passed": True,
                "errors": [],
                "warnings": [],
                "suggested_fixes": [],
                "estimated_impact": {
                    "risk_level": "low",
                    "affected_scope": "strategy:orderbook_skew",
                    "parameter_count": 2,
                },
                "conflicts": [],
            }
        }


class ConfigValidationRequest(BaseModel):
    """Request model for configuration validation."""

    parameters: dict[str, Any] = Field(
        ..., description="Configuration parameters to validate"
    )
    strategy_id: str | None = Field(
        None,
        description="Strategy identifier (required for strategy config validation)",
    )
    symbol: str | None = Field(
        None, description="Trading symbol (optional, for symbol-specific validation)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "parameters": {
                    "buy_threshold": 1.3,
                    "sell_threshold": 0.75,
                },
                "strategy_id": "orderbook_skew",
                "symbol": "BTCUSDT",
            }
        }
