"""
Strategy Configuration Manager.

Manages runtime configuration for trading strategies with:
- MongoDB persistence
- Configuration inheritance (global + per-symbol overrides)
- TTL-based caching for performance
- Full audit trail
- Automatic default persistence
- Environment variable fallback for backward compatibility
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Optional

import constants
from strategies.db.mongodb_client import MongoDBClient
from strategies.market_logic.defaults import (
    get_strategy_defaults,
    get_strategy_metadata,
    list_all_strategies,
    validate_parameters,
)
from strategies.models.strategy_config import StrategyConfig, StrategyConfigAudit

logger = logging.getLogger(__name__)


class StrategyConfigManager:
    """
    Strategy configuration manager with MongoDB persistence and caching.

    Configuration Resolution Priority:
    1. Cache (if not expired)
    2. MongoDB symbol-specific config
    3. MongoDB global config
    4. Environment variables (backward compatibility)
    5. Hardcoded defaults
    """

    def __init__(
        self,
        mongodb_client: Optional[MongoDBClient] = None,
        cache_ttl_seconds: int = 60,
    ):
        """
        Initialize configuration manager.

        Args:
            mongodb_client: MongoDB client (will create if None)
            cache_ttl_seconds: Cache TTL in seconds (default: 60)
        """
        self.mongodb_client = mongodb_client
        self.cache_ttl_seconds = cache_ttl_seconds

        # Cache: key = f"{strategy_id}:{symbol or 'global'}", value = (config, timestamp)
        self._cache: dict[str, tuple[dict[str, Any], float]] = {}

        # Background tasks
        self._cache_refresh_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        """Start the configuration manager and background tasks."""
        # Initialize database connections
        if self.mongodb_client:
            await self.mongodb_client.connect()
            logger.info("Configuration manager MongoDB connection established")
        else:
            logger.warning(
                "Configuration manager running without MongoDB (env vars + defaults only)"
            )

        # Start cache refresh task
        self._running = True
        self._cache_refresh_task = asyncio.create_task(self._cache_refresh_loop())

        logger.info(
            f"Configuration manager started (cache_ttl={self.cache_ttl_seconds}s)"
        )

    async def stop(self) -> None:
        """Stop the configuration manager and clean up."""
        self._running = False

        if self._cache_refresh_task:
            self._cache_refresh_task.cancel()
            try:
                await self._cache_refresh_task
            except asyncio.CancelledError:
                pass

        if self.mongodb_client:
            await self.mongodb_client.disconnect()

        logger.info("Configuration manager stopped")

    async def _cache_refresh_loop(self) -> None:
        """Background task to refresh cache periodically."""
        while self._running:
            try:
                await asyncio.sleep(self.cache_ttl_seconds)
                # Clear expired cache entries
                current_time = time.time()
                expired_keys = [
                    key
                    for key, (_, timestamp) in self._cache.items()
                    if current_time - timestamp > self.cache_ttl_seconds
                ]
                for key in expired_keys:
                    del self._cache[key]

                if expired_keys:
                    logger.debug(f"Cleared {len(expired_keys)} expired cache entries")
            except Exception as e:
                logger.error(f"Cache refresh loop error: {e}")
                await asyncio.sleep(10)

    def _make_cache_key(self, strategy_id: str, symbol: Optional[str]) -> str:
        """Generate cache key for config lookup."""
        symbol_part = symbol or "global"
        return f"{strategy_id}:{symbol_part}"

    def _get_from_cache(self, cache_key: str) -> Optional[dict[str, Any]]:
        """Get configuration from cache if not expired."""
        if cache_key in self._cache:
            config, timestamp = self._cache[cache_key]
            if time.time() - timestamp < self.cache_ttl_seconds:
                return config.copy()
        return None

    def _set_cache(self, cache_key: str, config: dict[str, Any]) -> None:
        """Store configuration in cache with current timestamp."""
        self._cache[cache_key] = (config.copy(), time.time())

    async def get_config(
        self, strategy_id: str, symbol: Optional[str] = None
    ) -> dict[str, Any]:
        """
        Get configuration for a strategy.

        Implements priority resolution:
        1. Check cache
        2. MongoDB symbol-specific (if symbol provided)
        3. MongoDB global
        4. Environment variables (backward compatibility)
        5. Hardcoded defaults

        Args:
            strategy_id: Strategy identifier
            symbol: Optional trading symbol for symbol-specific config

        Returns:
            Dictionary containing:
                - parameters: Dict of parameter values
                - version: Config version
                - source: Where config came from
                - is_override: Whether this is a symbol-specific override
        """
        start_time = time.time()

        # Check cache first
        cache_key = self._make_cache_key(strategy_id, symbol)
        cached = self._get_from_cache(cache_key)
        if cached:
            cached["cache_hit"] = True
            cached["load_time_ms"] = (time.time() - start_time) * 1000
            return cached

        # Try MongoDB symbol-specific
        if symbol and self.mongodb_client and self.mongodb_client.is_connected:
            config_doc = await self.mongodb_client.get_symbol_config(
                strategy_id, symbol
            )
            if config_doc:
                result = self._doc_to_config_result(config_doc, "mongodb", True)
                self._set_cache(cache_key, result)
                result["cache_hit"] = False
                result["load_time_ms"] = (time.time() - start_time) * 1000
                return result

        # Try MongoDB global
        if self.mongodb_client and self.mongodb_client.is_connected:
            config_doc = await self.mongodb_client.get_global_config(strategy_id)
            if config_doc:
                result = self._doc_to_config_result(config_doc, "mongodb", False)
                self._set_cache(cache_key, result)
                result["cache_hit"] = False
                result["load_time_ms"] = (time.time() - start_time) * 1000
                return result

        # Try environment variables (backward compatibility)
        env_params = self._get_from_environment(strategy_id)
        if env_params:
            result = {
                "parameters": env_params,
                "version": 0,
                "source": "environment",
                "is_override": False,
                "created_at": None,
                "updated_at": None,
            }
            self._set_cache(cache_key, result)
            result["cache_hit"] = False
            result["load_time_ms"] = (time.time() - start_time) * 1000
            return result

        # Use hardcoded defaults
        defaults = get_strategy_defaults(strategy_id)
        result = {
            "parameters": defaults,
            "version": 0,
            "source": "default",
            "is_override": False,
            "created_at": None,
            "updated_at": None,
        }
        self._set_cache(cache_key, result)
        result["cache_hit"] = False
        result["load_time_ms"] = (time.time() - start_time) * 1000
        return result

    def _doc_to_config_result(
        self, doc: dict[str, Any], source: str, is_override: bool
    ) -> dict[str, Any]:
        """Convert MongoDB document to config result format."""
        return {
            "parameters": doc.get("parameters", {}),
            "version": doc.get("version", 1),
            "source": source,
            "is_override": is_override,
            "created_at": (
                doc.get("created_at").isoformat() if doc.get("created_at") else None
            ),
            "updated_at": (
                doc.get("updated_at").isoformat() if doc.get("updated_at") else None
            ),
        }

    def _get_from_environment(self, strategy_id: str) -> dict[str, Any]:
        """
        Get configuration from environment variables (backward compatibility).

        Reads from constants.py which loads from environment.
        """
        env_params = {}

        if strategy_id == "orderbook_skew":
            env_params = {
                "top_levels": constants.ORDERBOOK_SKEW_TOP_LEVELS,
                "buy_threshold": constants.ORDERBOOK_SKEW_BUY_THRESHOLD,
                "sell_threshold": constants.ORDERBOOK_SKEW_SELL_THRESHOLD,
                "min_spread_percent": constants.ORDERBOOK_SKEW_MIN_SPREAD_PERCENT,
            }
        elif strategy_id == "trade_momentum":
            env_params = {
                "price_weight": constants.TRADE_MOMENTUM_PRICE_WEIGHT,
                "quantity_weight": constants.TRADE_MOMENTUM_QUANTITY_WEIGHT,
                "maker_weight": constants.TRADE_MOMENTUM_MAKER_WEIGHT,
                "buy_threshold": constants.TRADE_MOMENTUM_BUY_THRESHOLD,
                "sell_threshold": constants.TRADE_MOMENTUM_SELL_THRESHOLD,
                "min_quantity": constants.TRADE_MOMENTUM_MIN_QUANTITY,
            }
        elif strategy_id == "ticker_velocity":
            env_params = {
                "time_window": constants.TICKER_VELOCITY_TIME_WINDOW,
                "buy_threshold": constants.TICKER_VELOCITY_BUY_THRESHOLD,
                "sell_threshold": constants.TICKER_VELOCITY_SELL_THRESHOLD,
                "min_price_change": constants.TICKER_VELOCITY_MIN_PRICE_CHANGE,
            }
        elif strategy_id == "btc_dominance":
            env_params = {
                "high_threshold": constants.BTC_DOMINANCE_HIGH_THRESHOLD,
                "low_threshold": constants.BTC_DOMINANCE_LOW_THRESHOLD,
                "change_threshold": constants.BTC_DOMINANCE_CHANGE_THRESHOLD,
                "window_hours": constants.BTC_DOMINANCE_WINDOW_HOURS,
                "min_signal_interval": constants.BTC_DOMINANCE_MIN_SIGNAL_INTERVAL,
            }
        elif strategy_id == "cross_exchange_spread":
            env_params = {
                "spread_threshold_percent": constants.SPREAD_THRESHOLD_PERCENT,
                "min_signal_interval": constants.SPREAD_MIN_SIGNAL_INTERVAL,
                "max_position_size": constants.SPREAD_MAX_POSITION_SIZE,
                "exchanges": constants.SPREAD_EXCHANGES,
            }
        elif strategy_id == "onchain_metrics":
            env_params = {
                "network_growth_threshold": constants.ONCHAIN_NETWORK_GROWTH_THRESHOLD,
                "volume_threshold": constants.ONCHAIN_VOLUME_THRESHOLD,
                "min_signal_interval": constants.ONCHAIN_MIN_SIGNAL_INTERVAL,
            }

        # Only return if we found env vars (not empty dict)
        return env_params if env_params else {}

    async def set_config(
        self,
        strategy_id: str,
        parameters: dict[str, Any],
        changed_by: str,
        symbol: Optional[str] = None,
        reason: Optional[str] = None,
        validate_only: bool = False,
    ) -> tuple[bool, Optional[StrategyConfig], list[str]]:
        """
        Set strategy configuration.

        Args:
            strategy_id: Strategy identifier
            parameters: Configuration parameters to set
            changed_by: Who is making the change
            symbol: Trading symbol (None for global)
            reason: Reason for the change
            validate_only: If True, only validate without saving

        Returns:
            Tuple of (success, config, errors)
        """
        # Validate parameters
        is_valid, errors = validate_parameters(strategy_id, parameters)
        if not is_valid:
            return False, None, errors

        if validate_only:
            return True, None, []

        if not self.mongodb_client or not self.mongodb_client.is_connected:
            return False, None, ["MongoDB not available - cannot save configuration"]

        try:
            # Get existing config for version increment
            existing_config = None
            if symbol:
                existing_config = await self.mongodb_client.get_symbol_config(
                    strategy_id, symbol
                )
            else:
                existing_config = await self.mongodb_client.get_global_config(
                    strategy_id
                )

            # Create new config
            version = (existing_config.get("version", 0) + 1) if existing_config else 1
            now = datetime.utcnow()

            new_config = StrategyConfig(
                strategy_id=strategy_id,
                symbol=symbol,
                parameters=parameters,
                version=version,
                created_at=(
                    existing_config.get("created_at", now) if existing_config else now
                ),
                updated_at=now,
                created_by=changed_by,
                metadata={"reason": reason} if reason else {},
            )

            # Save to MongoDB
            metadata = {
                "changed_by": changed_by,
                "reason": reason,
            }

            if symbol:
                config_id = await self.mongodb_client.upsert_symbol_config(
                    strategy_id, symbol, parameters, metadata
                )
            else:
                config_id = await self.mongodb_client.upsert_global_config(
                    strategy_id, parameters, metadata
                )

            if not config_id:
                return False, None, ["Failed to save configuration"]

            # Create audit record
            audit = StrategyConfigAudit(
                strategy_id=strategy_id,
                symbol=symbol,
                action="UPDATE" if existing_config else "CREATE",
                old_parameters=(
                    existing_config.get("parameters") if existing_config else None
                ),
                new_parameters=parameters,
                changed_by=changed_by,
                changed_at=now,
                reason=reason,
            )

            audit_data = {
                "strategy_id": audit.strategy_id,
                "symbol": audit.symbol,
                "action": audit.action,
                "old_parameters": audit.old_parameters,
                "new_parameters": audit.new_parameters,
                "changed_by": audit.changed_by,
                "changed_at": audit.changed_at,
                "reason": audit.reason,
            }
            await self.mongodb_client.create_audit_record(audit_data)

            # Invalidate cache
            cache_key = self._make_cache_key(strategy_id, symbol)
            if cache_key in self._cache:
                del self._cache[cache_key]

            logger.info(
                f"Config updated: {strategy_id}"
                f"{' (' + symbol + ')' if symbol else ''} by {changed_by}"
            )

            return True, new_config, []

        except Exception as e:
            logger.error(f"Error setting config: {e}")
            return False, None, [str(e)]

    async def delete_config(
        self,
        strategy_id: str,
        changed_by: str,
        symbol: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> tuple[bool, list[str]]:
        """
        Delete strategy configuration.

        Args:
            strategy_id: Strategy identifier
            changed_by: Who is making the change
            symbol: Trading symbol (None for global)
            reason: Reason for deletion

        Returns:
            Tuple of (success, errors)
        """
        if not self.mongodb_client or not self.mongodb_client.is_connected:
            return False, ["MongoDB not available - cannot delete configuration"]

        try:
            # Get existing config for audit
            existing_config = None
            if symbol:
                existing_config = await self.mongodb_client.get_symbol_config(
                    strategy_id, symbol
                )
            else:
                existing_config = await self.mongodb_client.get_global_config(
                    strategy_id
                )

            # Delete from MongoDB
            if symbol:
                success = await self.mongodb_client.delete_symbol_config(
                    strategy_id, symbol
                )
            else:
                success = await self.mongodb_client.delete_global_config(strategy_id)

            if not success:
                return False, ["Failed to delete configuration"]

            # Create audit record
            if existing_config:
                audit_data = {
                    "strategy_id": strategy_id,
                    "symbol": symbol,
                    "action": "DELETE",
                    "old_parameters": existing_config.get("parameters"),
                    "new_parameters": None,
                    "changed_by": changed_by,
                    "changed_at": datetime.utcnow(),
                    "reason": reason,
                }
                await self.mongodb_client.create_audit_record(audit_data)

            # Invalidate cache
            cache_key = self._make_cache_key(strategy_id, symbol)
            if cache_key in self._cache:
                del self._cache[cache_key]

            logger.info(
                f"Config deleted: {strategy_id}"
                f"{' (' + symbol + ')' if symbol else ''} by {changed_by}"
            )

            return True, []

        except Exception as e:
            logger.error(f"Error deleting config: {e}")
            return False, [str(e)]

    async def list_strategies(self) -> list[dict[str, Any]]:
        """
        List all available strategies with their configuration status.

        Returns:
            List of strategy info dictionaries
        """
        all_strategy_ids = list_all_strategies()
        result = []

        for strategy_id in all_strategy_ids:
            metadata = get_strategy_metadata(strategy_id)
            defaults = get_strategy_defaults(strategy_id)

            # Check if has global config
            has_global = False
            if self.mongodb_client and self.mongodb_client.is_connected:
                global_config = await self.mongodb_client.get_global_config(strategy_id)
                has_global = global_config is not None

            # Get symbol overrides
            symbol_overrides = []
            if self.mongodb_client and self.mongodb_client.is_connected:
                symbol_overrides = await self.mongodb_client.list_symbol_overrides(
                    strategy_id
                )

            result.append(
                {
                    "strategy_id": strategy_id,
                    "name": metadata.get("name", strategy_id),
                    "description": metadata.get("description", ""),
                    "has_global_config": has_global,
                    "symbol_overrides": symbol_overrides,
                    "parameter_count": len(defaults),
                }
            )

        return result

    async def get_audit_trail(
        self,
        strategy_id: str,
        symbol: Optional[str] = None,
        limit: int = 100,
    ) -> list[StrategyConfigAudit]:
        """
        Get configuration change history.

        Args:
            strategy_id: Strategy identifier
            symbol: Optional symbol filter
            limit: Maximum number of records to return

        Returns:
            List of audit records (most recent first)
        """
        if not self.mongodb_client or not self.mongodb_client.is_connected:
            return []

        try:
            records = await self.mongodb_client.get_audit_trail(
                strategy_id, symbol, limit
            )

            # Convert to StrategyConfigAudit objects
            audit_list = []
            for record in records:
                audit = StrategyConfigAudit(
                    id=str(record.get("_id", "")),
                    strategy_id=record["strategy_id"],
                    symbol=record.get("symbol"),
                    action=record["action"],
                    old_parameters=record.get("old_parameters"),
                    new_parameters=record.get("new_parameters"),
                    changed_by=record["changed_by"],
                    changed_at=record["changed_at"],
                    reason=record.get("reason"),
                )
                audit_list.append(audit)

            return audit_list

        except Exception as e:
            logger.error(f"Error getting audit trail: {e}")
            return []

    async def refresh_cache(self) -> None:
        """Force immediate cache invalidation."""
        self._cache.clear()
        logger.info("Configuration cache cleared")

    async def get_config_history(
        self, strategy_id: str, symbol: Optional[str] = None, limit: int = 20
    ) -> list[StrategyConfigAudit]:
        """
        Get configuration version history.

        Args:
            strategy_id: Strategy identifier
            symbol: Optional symbol filter
            limit: Maximum number of historical versions

        Returns:
            List of audit records (most recent first)
        """
        return await self.get_audit_trail(
            strategy_id=strategy_id, symbol=symbol, limit=limit
        )

    async def get_previous_config(
        self, strategy_id: str, symbol: Optional[str] = None
    ) -> StrategyConfigAudit | None:
        """
        Get the immediately previous configuration version.

        Args:
            strategy_id: Strategy identifier
            symbol: Optional symbol filter

        Returns:
            Previous audit record or None if no history
        """
        history = await self.get_config_history(strategy_id, symbol, limit=2)
        # Index 0 is current, index 1 is previous
        return history[1] if len(history) >= 2 else None

    async def get_config_by_version(
        self, strategy_id: str, version_number: int, symbol: Optional[str] = None
    ) -> StrategyConfigAudit | None:
        """
        Get configuration at a specific version number.

        Args:
            strategy_id: Strategy identifier
            version_number: Version number (1 = oldest, N = newest)
            symbol: Optional symbol filter

        Returns:
            Audit record for that version or None
        """
        all_history = await self.get_config_history(strategy_id, symbol, limit=1000)
        if not all_history:
            return None

        # Reverse to chronological order (oldest first)
        chronological = list(reversed(all_history))

        # Return version at index (1-based)
        if 1 <= version_number <= len(chronological):
            return chronological[version_number - 1]
        return None

    async def get_config_by_id(self, config_id: str) -> StrategyConfigAudit | None:
        """
        Get configuration by audit record ID.

        Args:
            config_id: Audit record ID

        Returns:
            Audit record or None
        """
        if not self.mongodb_client or not self.mongodb_client.is_connected:
            return None

        try:
            from bson import ObjectId

            record = await self.mongodb_client.database.strategy_config_audit.find_one(
                {"_id": ObjectId(config_id)}
            )
            if not record:
                return None

            return StrategyConfigAudit(
                id=str(record.get("_id")),
                config_id=record.get("config_id"),
                strategy_id=record["strategy_id"],
                symbol=record.get("symbol"),
                action=record["action"],
                old_parameters=record.get("old_parameters"),
                new_parameters=record.get("new_parameters"),
                changed_by=record["changed_by"],
                changed_at=record["changed_at"],
                reason=record.get("reason"),
            )
        except Exception as e:
            logger.error(f"Failed to get config by ID {config_id}: {e}")
            return None

    async def rollback_config(
        self,
        strategy_id: str,
        target_version: str,
        reason: str,
        symbol: Optional[str] = None,
        changed_by: str = "system_rollback",
    ) -> tuple[bool, StrategyConfig | None, list[str]]:
        """
        Rollback strategy configuration to a previous version.

        Args:
            strategy_id: Strategy identifier
            target_version: "previous", version number, or audit ID
            reason: Reason for rollback
            symbol: Optional symbol for symbol-specific rollback
            changed_by: Who is performing rollback

        Returns:
            Tuple of (success, restored_config, errors)
        """
        errors = []

        # Resolve target version
        target_audit = None

        if target_version == "previous":
            target_audit = await self.get_previous_config(strategy_id, symbol)
            if not target_audit:
                return False, None, ["No previous configuration found"]

        elif target_version.isdigit():
            target_audit = await self.get_config_by_version(
                strategy_id, int(target_version), symbol
            )
            if not target_audit:
                return False, None, [f"Version {target_version} not found"]

        else:
            target_audit = await self.get_config_by_id(target_version)
            if not target_audit:
                return False, None, [f"Configuration ID {target_version} not found"]

        # Extract config to restore
        config_to_restore = target_audit.new_parameters
        if not config_to_restore:
            return False, None, ["Target configuration has no parameters"]

        # Validate before restoring
        is_valid, _, validation_errors = await self.set_config(
            strategy_id=strategy_id,
            parameters=config_to_restore,
            changed_by=changed_by,
            symbol=symbol,
            reason=f"Rollback validation: {reason}",
            validate_only=True,
        )

        if not is_valid:
            return (
                False,
                None,
                [f"Rollback validation failed: {', '.join(validation_errors)}"],
            )

        # Perform rollback
        success, restored_config, set_errors = await self.set_config(
            strategy_id=strategy_id,
            parameters=config_to_restore,
            changed_by=changed_by,
            symbol=symbol,
            reason=f"Rollback: {reason} (from audit {target_audit.id})",
            validate_only=False,
        )

        if not success:
            return False, None, set_errors

        logger.info(
            f"Configuration rolled back for {strategy_id}",
            extra={"symbol": symbol, "reason": reason, "audit_id": target_audit.id},
        )

        return True, restored_config, []
