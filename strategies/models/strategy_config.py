"""
Strategy configuration models for runtime parameter management.
"""

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class StrategyConfig(BaseModel):
    """
    Strategy configuration model.

    Represents a complete configuration for a strategy,
    either global (applied to all symbols) or symbol-specific.
    """

    id: str | None = Field(None, description="Configuration ID")
    strategy_id: str = Field(..., description="Strategy identifier")
    symbol: str | None = Field(
        None, description="Trading symbol (None for global configs)"
    )
    parameters: dict[str, Any] = Field(
        ..., description="Strategy parameters as key-value pairs"
    )
    version: int = Field(1, description="Configuration version number")
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="When config was created"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow, description="When config was last updated"
    )
    created_by: str = Field(..., description="Who/what created this config")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "id": "507f1f77bcf86cd799439011",
                "strategy_id": "btc_dominance",
                "symbol": None,
                "parameters": {
                    "high_threshold": 70.0,
                    "low_threshold": 40.0,
                    "change_threshold": 5.0,
                },
                "version": 1,
                "created_at": "2025-10-17T10:30:00Z",
                "updated_at": "2025-10-17T10:30:00Z",
                "created_by": "system",
                "metadata": {},
            }
        }


class StrategyConfigAudit(BaseModel):
    """
    Audit trail record for configuration changes.

    Tracks who changed what, when, and why for full accountability.
    """

    id: str | None = Field(None, description="Audit record ID")
    config_id: str | None = Field(None, description="Configuration ID that was changed")
    strategy_id: str = Field(..., description="Strategy identifier")
    symbol: str | None = Field(None, description="Symbol (None for global)")
    action: Literal["CREATE", "UPDATE", "DELETE"] = Field(
        ..., description="Type of change made"
    )
    old_parameters: dict[str, Any] | None = Field(
        None, description="Previous parameter values"
    )
    new_parameters: dict[str, Any] | None = Field(
        None, description="New parameter values"
    )
    changed_by: str = Field(..., description="Who/what made the change")
    changed_at: datetime = Field(
        default_factory=datetime.utcnow, description="When the change occurred"
    )
    reason: str | None = Field(None, description="Reason for the change")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "507f1f77bcf86cd799439012",
                "config_id": "507f1f77bcf86cd799439011",
                "strategy_id": "btc_dominance",
                "symbol": None,
                "action": "UPDATE",
                "old_parameters": {"high_threshold": 75.0},
                "new_parameters": {"high_threshold": 70.0},
                "changed_by": "llm_agent_v1",
                "changed_at": "2025-10-17T14:45:00Z",
                "reason": "Lower threshold for earlier signals",
            }
        }


class ParameterSchema(BaseModel):
    """
    Schema definition for a strategy parameter.

    Describes type, constraints, and purpose of a configuration parameter.
    """

    name: str = Field(..., description="Parameter name")
    type: str = Field(..., description="Data type (int, float, bool, str)")
    description: str = Field(..., description="What this parameter controls")
    default: Any = Field(..., description="Default value")
    min: float | None = Field(None, description="Minimum value (for numeric)")
    max: float | None = Field(None, description="Maximum value (for numeric)")
    allowed_values: list[Any] | None = Field(
        None, description="Allowed values (for enums)"
    )
    example: Any = Field(..., description="Example valid value")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "high_threshold",
                "type": "float",
                "description": "High dominance threshold percentage",
                "default": 70.0,
                "min": 60.0,
                "max": 90.0,
                "example": 70.0,
            }
        }


class StrategyInfo(BaseModel):
    """
    Strategy information model for listing strategies.
    """

    strategy_id: str = Field(..., description="Strategy identifier")
    name: str = Field(..., description="Human-readable name")
    description: str = Field(..., description="Strategy description")
    has_global_config: bool = Field(False, description="Whether global config exists")
    symbol_overrides: list[str] = Field(
        default_factory=list, description="Symbols with overrides"
    )
    parameter_count: int = Field(0, description="Number of parameters")

    class Config:
        json_schema_extra = {
            "example": {
                "strategy_id": "btc_dominance",
                "name": "Bitcoin Dominance",
                "description": "Monitors BTC market dominance for rotation signals",
                "has_global_config": True,
                "symbol_overrides": [],
                "parameter_count": 5,
            }
        }


class ConfigSource(BaseModel):
    """
    Configuration source metadata.

    Indicates where the configuration was loaded from.
    """

    source: Literal["mongodb", "mysql", "default"] = Field(
        ..., description="Source of configuration"
    )
    is_override: bool = Field(
        False, description="Whether this is a symbol-specific override"
    )
    cache_hit: bool = Field(False, description="Whether this was served from cache")
    load_time_ms: float | None = Field(None, description="Time taken to load config")
