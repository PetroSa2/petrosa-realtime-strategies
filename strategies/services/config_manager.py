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
from typing import Any

import constants
from strategies.db.mongodb_client import MongoDBClient
from strategies.market_logic.defaults import (
    get_strategy_defaults,
    get_strategy_metadata,
    list_all_strategies,
    validate_parameters,
)
from strategies.models.strategy_config import StrategyConfig, StrategyConfigAudit
from strategies.utils.metrics import initialize_metrics

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
        mongodb_client: MongoDBClient | None = None,
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
        self._cache_refresh_task: asyncio.Task | None = None
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

    def _make_cache_key(self, strategy_id: str, symbol: str | None) -> str:
        """Generate cache key for config lookup."""
        symbol_part = symbol or "global"
        return f"{strategy_id}:{symbol_part}"

    def _get_from_cache(self, cache_key: str) -> dict[str, Any | None]:
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
        self, strategy_id: str, symbol: str | None = None
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
        symbol: str | None = None,
        reason: str | None = None,
        validate_only: bool = False,
    ) -> tuple[bool, StrategyConfig | None, list[str]]:
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
                    {
                        **existing_config.get("parameters"),
                        "version": existing_config.get("version"),
                    }
                    if existing_config and existing_config.get("parameters")
                    else None
                ),
                new_parameters={**parameters, "version": version},
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

            # Record configuration change metric
            metrics = initialize_metrics()
            if metrics:
                action = "UPDATE" if existing_config else "CREATE"
                metrics.record_config_change(strategy_id, symbol, action)

            logger.info(
                f"Config updated: {strategy_id}"
                f"{' (' + symbol + ')' if symbol else ''} by {changed_by}"
            )

            return True, new_config, []

        except Exception as e:
            logger.error(f"Error setting config: {e}")
            return False, None, [str(e)]

    async def rollback_config(
        self,
        strategy_id: str,
        changed_by: str,
        symbol: str | None = None,
        target_version: int | None = None,
        rollback_id: str | None = None,
        reason: str | None = None,
    ) -> tuple[bool, StrategyConfig | None, list[str]]:
        """
        Rollback strategy configuration to a previous version.

        Args:
            strategy_id: Strategy identifier
            changed_by: Who is performing the rollback
            symbol: Optional symbol for symbol-specific config
            target_version: Optional specific version to rollback to
            rollback_id: Optional specific audit ID to rollback to
            reason: Optional reason for the rollback

        Returns:
            Tuple of (success, config, errors)
        """
        # Determine configuration to restore
        config_to_restore = None

        if rollback_id:
            config_to_restore = await self.get_config_by_id(strategy_id, rollback_id)
            if not config_to_restore:
                return (
                    False,
                    None,
                    [
                        f"Configuration with ID {rollback_id} not found for strategy {strategy_id}"
                    ],
                )
        elif target_version is not None:
            if target_version < 1:
                return False, None, ["Invalid version number (must be >= 1)"]
            config_to_restore = await self.get_config_by_version(
                strategy_id, target_version, symbol
            )
            if not config_to_restore:
                return (
                    False,
                    None,
                    [
                        f"Configuration version {target_version} not found for {strategy_id}"
                    ],
                )
        else:
            # Default to previous
            config_to_restore = await self.get_previous_config(strategy_id, symbol)
            if not config_to_restore:
                return (
                    False,
                    None,
                    [
                        f"No previous configuration found for {strategy_id} to rollback to"
                    ],
                )

        # Ensure we don't persist metadata like "version" as strategy parameters
        clean_parameters = (
            {k: v for k, v in config_to_restore.items() if k != "version"}
            if isinstance(config_to_restore, dict)
            else config_to_restore
        )

        # Perform rollback using set_config
        rollback_reason = (
            reason
            or f"Rollback to {'version ' + str(target_version) if target_version is not None else ('ID ' + rollback_id if rollback_id else 'previous')}"
        )

        success, config, errors = await self.set_config(
            strategy_id=strategy_id,
            parameters=clean_parameters,
            changed_by=changed_by,
            symbol=symbol,
            reason=rollback_reason,
        )

        # Explicit cache invalidation on success
        if success:
            cache_key = self._make_cache_key(strategy_id, symbol)
            if cache_key in self._cache:
                del self._cache[cache_key]

            # Record configuration change metric
            metrics = initialize_metrics()
            if metrics:
                metrics.record_config_change(strategy_id, symbol, "ROLLBACK")

        return success, config, errors

    async def delete_config(
        self,
        strategy_id: str,
        changed_by: str,
        symbol: str | None = None,
        reason: str | None = None,
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
                    "old_parameters": {
                        **existing_config.get("parameters"),
                        "version": existing_config.get("version"),
                    },
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

            # Record configuration change metric
            metrics = initialize_metrics()
            if metrics:
                metrics.record_config_change(strategy_id, symbol, "DELETE")

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
        symbol: str | None = None,
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

    async def get_previous_config(
        self, strategy_id: str, symbol: str | None = None
    ) -> dict[str, Any] | None:
        """
        Get the immediately preceding configuration version.

        Args:
            strategy_id: Strategy identifier
            symbol: Optional symbol filter

        Returns:
            Dictionary of configuration values or None if no history exists
        """
        history = await self.get_audit_history(strategy_id, symbol, limit=2)
        if len(history) < 1:
            return None

        latest = history[0]
        prev_params: dict[str, Any] | None = None

        # If the latest action is an UPDATE, use the previous parameters
        if latest.action == "UPDATE" and latest.old_parameters:
            # Copy to avoid mutating the stored audit record
            prev_params = dict(latest.old_parameters)

        # Otherwise, if we have at least two records, fall back to the
        # parameters from the immediately preceding audit entry.
        elif len(history) >= 2 and history[1].new_parameters:
            # Copy to avoid mutating the stored audit record
            prev_params = dict(history[1].new_parameters)

        if prev_params is None:
            return None

        # Ensure we return parameters consistently without version metadata.
        # We strip it here for consistency since new_parameters includes it.
        return {k: v for k, v in prev_params.items() if k != "version"}

    async def get_audit_history(
        self, strategy_id: str, symbol: str | None = None, limit: int = 100
    ) -> list[StrategyConfigAudit]:
        """
        Get configuration change history. Alias for get_audit_trail.

        Args:
            strategy_id: Strategy identifier
            symbol: Optional symbol filter
            limit: Maximum number of records to return

        Returns:
            List of audit records
        """
        return await self.get_audit_trail(strategy_id, symbol, limit)

    async def get_config_by_version(
        self, strategy_id: str, version: int, symbol: str | None = None
    ) -> dict[str, Any] | None:
        """
        Get a specific configuration version from audit history.

        Args:
            version: Version number to find
            strategy_id: Strategy identifier
            symbol: Optional symbol filter

        Returns:
            Dictionary of configuration values or None if not found
        """
        if version < 1:
            return None

        # Direct MongoDB optimization
        if (
            self.mongodb_client
            and self.mongodb_client.is_connected
            and not self.mongodb_client.use_data_manager
        ):
            try:
                query = {
                    "strategy_id": strategy_id,
                    "new_parameters.version": version,
                }
                if symbol:
                    query["symbol"] = symbol

                cursor = self.mongodb_client.database.strategy_config_audit.find(
                    query
                ).limit(1)
                records = await cursor.to_list(length=1)
                if records:
                    params = records[0].get("new_parameters")
                    return {k: v for k, v in params.items() if k != "version"}
                return None
            except Exception as e:
                logger.error(f"Error fetching version {version} for {strategy_id}: {e}")
                return None

        # Data Manager or Fallback
        history = await self.get_audit_trail(strategy_id, symbol, limit=1000)
        for record in history:
            if (
                record.new_parameters
                and record.new_parameters.get("version") == version
            ):
                return {
                    k: v for k, v in record.new_parameters.items() if k != "version"
                }

        return None

    async def get_config_by_id(
        self, strategy_id: str, audit_id: str
    ) -> dict[str, Any] | None:
        """
        Get a specific configuration from a specific audit record.

        Args:
            strategy_id: Strategy identifier (for security validation)
            audit_id: Audit record unique identifier

        Returns:
            Dictionary of configuration values or None if not found
        """
        # Search history for the ID
        history = await self.get_audit_trail(strategy_id, limit=1000)
        for record in history:
            if record.id == audit_id:
                # Explicit security validation to ensure audit record belongs to requested strategy
                if record.strategy_id != strategy_id:
                    logger.warning(
                        f"Security: Audit ID {audit_id} belongs to {record.strategy_id}, not {strategy_id}"
                    )
                    return None
                return {k: v for k, v in record.new_parameters.items() if k != "version"}

        return None
