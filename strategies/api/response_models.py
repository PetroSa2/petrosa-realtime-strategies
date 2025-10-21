"""
Pydantic response models for API endpoints.

Provides type-safe request/response models for configuration management.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class APIResponse(BaseModel):
    """Standard API response wrapper."""
    
    success: bool = Field(..., description="Whether operation succeeded")
    data: Optional[Any] = Field(None, description="Response data")
    error: Optional[Dict[str, Any]] = Field(None, description="Error details if failed")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class ConfigResponse(BaseModel):
    """Configuration response model."""
    
    strategy_id: str = Field(..., description="Strategy identifier")
    symbol: Optional[str] = Field(None, description="Trading symbol (None for global)")
    parameters: Dict[str, Any] = Field(..., description="Configuration parameters")
    version: int = Field(..., description="Configuration version")
    source: str = Field(..., description="Configuration source (mongodb/environment/default)")
    is_override: bool = Field(..., description="Whether this is a symbol-specific override")
    created_at: Optional[str] = Field(None, description="Creation timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")


class ConfigUpdateRequest(BaseModel):
    """Configuration update request."""
    
    parameters: Dict[str, Any] = Field(
        ..., description="Configuration parameters to update"
    )
    changed_by: str = Field(
        ..., description="Who is making this change (e.g., 'llm_agent_v1', 'admin')"
    )
    reason: Optional[str] = Field(
        None, description="Reason for the configuration change"
    )
    validate_only: bool = Field(
        False, description="If true, only validate parameters without saving"
    )


class ParameterSchemaItem(BaseModel):
    """Parameter schema definition."""
    
    name: str = Field(..., description="Parameter name")
    type: str = Field(..., description="Data type (int, float, bool, str, list)")
    description: str = Field(..., description="What this parameter controls")
    default: Any = Field(..., description="Default value")
    min: Optional[float] = Field(None, description="Minimum value (for numeric)")
    max: Optional[float] = Field(None, description="Maximum value (for numeric)")
    allowed_values: Optional[List[Any]] = Field(
        None, description="Allowed values (for enums)"
    )
    example: Any = Field(..., description="Example valid value")


class StrategyListItem(BaseModel):
    """Strategy list item."""
    
    strategy_id: str = Field(..., description="Strategy identifier")
    name: str = Field(..., description="Human-readable name")
    description: str = Field(..., description="Strategy description")
    has_global_config: bool = Field(
        False, description="Whether global config exists"
    )
    symbol_overrides: List[str] = Field(
        default_factory=list, description="Symbols with overrides"
    )
    parameter_count: int = Field(0, description="Number of parameters")


class AuditTrailItem(BaseModel):
    """Audit trail record."""
    
    id: str = Field(..., description="Audit record ID")
    strategy_id: str = Field(..., description="Strategy identifier")
    symbol: Optional[str] = Field(None, description="Symbol (None for global)")
    action: str = Field(..., description="Type of change made")
    old_parameters: Optional[Dict[str, Any]] = Field(
        None, description="Previous parameter values"
    )
    new_parameters: Optional[Dict[str, Any]] = Field(
        None, description="New parameter values"
    )
    changed_by: str = Field(..., description="Who/what made the change")
    changed_at: str = Field(..., description="When the change occurred")
    reason: Optional[str] = Field(None, description="Reason for the change")

