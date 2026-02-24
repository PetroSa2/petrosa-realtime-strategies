"""
Data Manager client for petrosa-realtime-strategies.

This module provides a client for interacting with the petrosa-data-manager API
for configuration management and market data access.
"""

import os
from datetime import datetime
from typing import Any

from data_manager_client import DataManagerClient as BaseDataManagerClient
from data_manager_client.exceptions import ConnectionError

logger = None


def get_logger():
    """Get logger instance."""
    global logger
    if logger is None:
        import logging

        logger = logging.getLogger(__name__)
    return logger


class DataManagerClient:
    """
    Data Manager client for the Realtime Strategies service.

    Provides methods for configuration management and market data access
    through the petrosa-data-manager API.
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: int = 30,
        max_retries: int = 3,
    ):
        """
        Initialize the Data Manager client.

        Args:
            base_url: Data Manager API base URL
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        """
        self.base_url = base_url or os.getenv(
            "DATA_MANAGER_URL", "http://petrosa-data-manager:8000"
        )
        self.timeout = timeout
        self.max_retries = max_retries

        # Initialize the base client
        self._client = BaseDataManagerClient(
            base_url=self.base_url,
            timeout=self.timeout,
            max_retries=self.max_retries,
        )

        self._logger = get_logger()
        self._logger.info(f"Initialized Data Manager client: {self.base_url}")

    async def connect(self):
        """Connect to the Data Manager service."""
        try:
            # Test connection with health check
            health = await self._client.health()
            if health.get("status") != "healthy":
                raise ConnectionError(f"Data Manager health check failed: {health}")

            self._logger.info("Connected to Data Manager service")

        except Exception as e:
            self._logger.error(f"Failed to connect to Data Manager: {e}")
            raise

    async def disconnect(self):
        """Disconnect from the Data Manager service."""
        try:
            await self._client.close()
            self._logger.info("Disconnected from Data Manager service")
        except Exception as e:
            self._logger.warning(f"Error disconnecting from Data Manager: {e}")

    # Configuration Management Methods

    async def get_global_config(self, strategy_id: str) -> dict[str, Any | None]:
        """
        Get global configuration for a strategy.

        Args:
            strategy_id: Strategy identifier

        Returns:
            Configuration document or None if not found
        """
        try:
            result = await self._client.query(
                database="mongodb",
                collection="strategy_configs_global",
                filter={"strategy_id": strategy_id},
                limit=1,
            )

            if result.get("data") and len(result["data"]) > 0:
                return result["data"][0]
            return None

        except Exception as e:
            self._logger.error(f"Error fetching global config for {strategy_id}: {e}")
            return None

    async def get_symbol_config(
        self, strategy_id: str, symbol: str
    ) -> dict[str, Any | None]:
        """
        Get symbol-specific configuration for a strategy.

        Args:
            strategy_id: Strategy identifier
            symbol: Trading symbol

        Returns:
            Configuration document or None if not found
        """
        try:
            result = await self._client.query(
                database="mongodb",
                collection="strategy_configs_symbol",
                filter={"strategy_id": strategy_id, "symbol": symbol},
                limit=1,
            )

            if result.get("data") and len(result["data"]) > 0:
                return result["data"][0]
            return None

        except Exception as e:
            self._logger.error(
                f"Error fetching symbol config for {strategy_id}/{symbol}: {e}"
            )
            return None

    async def upsert_global_config(
        self, strategy_id: str, parameters: dict[str, Any], metadata: dict[str, Any]
    ) -> str | None:
        """
        Create or update global configuration.

        Args:
            strategy_id: Strategy identifier
            parameters: Parameter key-value pairs
            metadata: Additional metadata

        Returns:
            Configuration ID or None on failure
        """
        try:
            now = datetime.utcnow()

            # Get existing config to check version
            existing = await self.get_global_config(strategy_id)

            doc = {
                "strategy_id": strategy_id,
                "parameters": parameters,
                "updated_at": now,
                "metadata": metadata,
            }

            if existing:
                doc["version"] = existing.get("version", 1) + 1
                doc["created_at"] = existing.get("created_at", now)
            else:
                doc["version"] = 1
                doc["created_at"] = now

            # Use upsert operation
            result = await self._client.update(
                database="mongodb",
                collection="strategy_configs_global",
                filter={"strategy_id": strategy_id},
                data=doc,
                upsert=True,
            )

            if (
                result.get("modified_count", 0) > 0
                or result.get("upserted_count", 0) > 0
            ):
                self._logger.info(f"Upserted global config for {strategy_id}")
                return strategy_id
            else:
                self._logger.warning(
                    f"No changes made to global config for {strategy_id}"
                )
                return None

        except Exception as e:
            self._logger.error(f"Error upserting global config for {strategy_id}: {e}")
            return None

    async def upsert_symbol_config(
        self,
        strategy_id: str,
        symbol: str,
        parameters: dict[str, Any],
        metadata: dict[str, Any],
    ) -> str | None:
        """
        Create or update symbol-specific configuration.

        Args:
            strategy_id: Strategy identifier
            symbol: Trading symbol
            parameters: Parameter key-value pairs
            metadata: Additional metadata

        Returns:
            Configuration ID or None on failure
        """
        try:
            now = datetime.utcnow()

            # Get existing config to check version
            existing = await self.get_symbol_config(strategy_id, symbol)

            doc = {
                "strategy_id": strategy_id,
                "symbol": symbol,
                "parameters": parameters,
                "updated_at": now,
                "metadata": metadata,
            }

            if existing:
                doc["version"] = existing.get("version", 1) + 1
                doc["created_at"] = existing.get("created_at", now)
            else:
                doc["version"] = 1
                doc["created_at"] = now

            # Use upsert operation
            result = await self._client.update(
                database="mongodb",
                collection="strategy_configs_symbol",
                filter={"strategy_id": strategy_id, "symbol": symbol},
                data=doc,
                upsert=True,
            )

            if (
                result.get("modified_count", 0) > 0
                or result.get("upserted_count", 0) > 0
            ):
                self._logger.info(f"Upserted symbol config for {strategy_id}/{symbol}")
                return f"{strategy_id}:{symbol}"
            else:
                self._logger.warning(
                    f"No changes made to symbol config for {strategy_id}/{symbol}"
                )
                return None

        except Exception as e:
            self._logger.error(
                f"Error upserting symbol config for {strategy_id}/{symbol}: {e}"
            )
            return None

    async def delete_global_config(self, strategy_id: str) -> bool:
        """
        Delete global configuration.

        Args:
            strategy_id: Strategy identifier

        Returns:
            True if deleted, False otherwise
        """
        try:
            result = await self._client.delete(
                database="mongodb",
                collection="strategy_configs_global",
                filter={"strategy_id": strategy_id},
            )

            if result.get("deleted_count", 0) > 0:
                self._logger.info(f"Deleted global config for {strategy_id}")
                return True
            return False

        except Exception as e:
            self._logger.error(f"Error deleting global config for {strategy_id}: {e}")
            return False

    async def delete_symbol_config(self, strategy_id: str, symbol: str) -> bool:
        """
        Delete symbol-specific configuration.

        Args:
            strategy_id: Strategy identifier
            symbol: Trading symbol

        Returns:
            True if deleted, False otherwise
        """
        try:
            result = await self._client.delete(
                database="mongodb",
                collection="strategy_configs_symbol",
                filter={"strategy_id": strategy_id, "symbol": symbol},
            )

            if result.get("deleted_count", 0) > 0:
                self._logger.info(f"Deleted symbol config for {strategy_id}/{symbol}")
                return True
            return False

        except Exception as e:
            self._logger.error(
                f"Error deleting symbol config for {strategy_id}/{symbol}: {e}"
            )
            return False

    async def create_audit_record(self, audit_data: dict[str, Any]) -> str | None:
        """
        Create audit trail record for configuration change.

        Args:
            audit_data: Audit information

        Returns:
            Audit record ID or None on failure
        """
        try:
            audit_data["changed_at"] = datetime.utcnow()

            result = await self._client.insert(
                database="mongodb",
                collection="strategy_config_audit",
                data=audit_data,
            )

            if result.get("inserted_count", 0) > 0:
                self._logger.info(
                    f"Created audit record for {audit_data.get('strategy_id')}"
                )
                return str(result.get("inserted_ids", [None])[0])
            return None

        except Exception as e:
            self._logger.error(f"Error creating audit record: {e}")
            return None

    async def get_audit_trail(
        self, strategy_id: str, symbol: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """
        Get configuration change history.

        Args:
            strategy_id: Strategy identifier
            symbol: Optional symbol filter
            limit: Maximum number of records to return

        Returns:
            List of audit records (most recent first)
        """
        try:
            filter_dict = {"strategy_id": strategy_id}
            if symbol:
                filter_dict["symbol"] = symbol

            result = await self._client.query(
                database="mongodb",
                collection="strategy_config_audit",
                filter=filter_dict,
                sort={"changed_at": -1},
                limit=limit,
            )

            return result.get("data", [])

        except Exception as e:
            self._logger.error(f"Error fetching audit trail for {strategy_id}: {e}")
            return []

    async def list_all_strategy_ids(self) -> list[str]:
        """
        Get list of all strategy IDs with configurations.

        Returns:
            List of unique strategy IDs
        """
        try:
            # Get global configs
            global_result = await self._client.query(
                database="mongodb",
                collection="strategy_configs_global",
                fields=["strategy_id"],
            )
            global_ids = [doc["strategy_id"] for doc in global_result.get("data", [])]

            # Get symbol configs
            symbol_result = await self._client.query(
                database="mongodb",
                collection="strategy_configs_symbol",
                fields=["strategy_id"],
            )
            symbol_ids = [doc["strategy_id"] for doc in symbol_result.get("data", [])]

            # Combine and deduplicate
            all_ids = list(set(global_ids + symbol_ids))
            return sorted(all_ids)

        except Exception as e:
            self._logger.error(f"Error listing strategy IDs: {e}")
            return []

    async def list_symbol_overrides(self, strategy_id: str) -> list[str]:
        """
        Get list of symbols with configuration overrides for a strategy.

        Args:
            strategy_id: Strategy identifier

        Returns:
            List of symbols with overrides
        """
        try:
            result = await self._client.query(
                database="mongodb",
                collection="strategy_configs_symbol",
                filter={"strategy_id": strategy_id},
                fields=["symbol"],
            )

            symbols = [doc["symbol"] for doc in result.get("data", [])]
            return sorted(symbols)

        except Exception as e:
            self._logger.error(f"Error listing symbol overrides for {strategy_id}: {e}")
            return []

    async def rollback_strategy_config(
        self,
        strategy_id: str,
        changed_by: str,
        symbol: str | None = None,
        target_version: int | None = None,
        reason: str | None = None,
    ) -> bool:
        """
        Rollback strategy configuration via Data Manager.

        Args:
            strategy_id: Strategy identifier
            changed_by: Who is performing the rollback
            symbol: Optional symbol
            target_version: Optional specific version
            reason: Optional reason

        Returns:
            True if successful, False otherwise
        """
        try:
            payload = {
                "changed_by": changed_by,
                "target_version": target_version,
                "reason": reason,
            }

            url = f"/api/v1/config/rollback/strategies/{strategy_id}"
            params = {}
            if symbol:
                params["symbol"] = symbol

            # Use the internal _client which handles base_url and auth
            response = await self._client.post(url, json=payload, params=params)

            return response is not None
        except Exception as e:
            self._logger.error(f"Failed to rollback config via Data Manager: {e}")
            return False

    # Market Data Methods

    async def get_btc_dominance(self) -> float | None:
        """
        Get current Bitcoin dominance percentage.

        Returns:
            BTC dominance percentage or None if not available
        """
        try:
            # This would need to be implemented in the Data Manager
            # For now, return None as a placeholder
            self._logger.warning("BTC dominance not yet implemented in Data Manager")
            return None

        except Exception as e:
            self._logger.error(f"Error fetching BTC dominance: {e}")
            return None

    async def get_market_metrics(self, symbol: str) -> dict[str, Any]:
        """
        Get market metrics for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Dictionary of market metrics
        """
        try:
            # This would need to be implemented in the Data Manager
            # For now, return empty dict as a placeholder
            self._logger.warning("Market metrics not yet implemented in Data Manager")
            return {}

        except Exception as e:
            self._logger.error(f"Error fetching market metrics for {symbol}: {e}")
            return {}

    async def health_check(self) -> dict[str, Any]:
        """
        Check the health of the Data Manager service.

        Returns:
            Health status information
        """
        try:
            health = await self._client.health()
            self._logger.info(
                f"Data Manager health check: {health.get('status', 'unknown')}"
            )
            return health
        except Exception as e:
            self._logger.error(f"Data Manager health check failed: {e}")
            return {"status": "unhealthy", "error": str(e)}

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()
