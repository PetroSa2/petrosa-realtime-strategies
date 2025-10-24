"""
MongoDB client for strategy configuration management.

This client now supports both direct MongoDB connections and Data Manager API
for configuration management. Data Manager is the recommended approach for new deployments.

Provides async MongoDB operations using Motor driver for:
- Strategy configuration storage (global and per-symbol)
- Configuration audit trail
- High availability with connection pooling
"""

import logging
import os
from datetime import datetime
from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import ConnectionFailure

# Import Data Manager client
try:
    from ..services.data_manager_client import DataManagerClient

    DATA_MANAGER_AVAILABLE = True
except ImportError:
    DATA_MANAGER_AVAILABLE = False
    DataManagerClient = None

logger = logging.getLogger(__name__)


class MongoDBClient:
    """
    Async MongoDB client for strategy configuration persistence.

    Supports both direct MongoDB connections and Data Manager API.
    Data Manager is the recommended approach for new deployments.

    Features:
    - Connection pooling with configurable limits
    - Automatic retry with exponential backoff
    - Health check support
    - Graceful degradation on connection failure
    """

    def __init__(
        self,
        uri: Optional[str] = None,
        database: Optional[str] = None,
        max_pool_size: int = 10,
        min_pool_size: int = 1,
        timeout_ms: int = 5000,
        use_data_manager: bool = True,
    ):
        """
        Initialize MongoDB client.

        Args:
            uri: MongoDB connection URI (from env MONGODB_URI if not provided)
            database: Database name (from env MONGODB_DATABASE if not provided)
            max_pool_size: Maximum connection pool size
            min_pool_size: Minimum connection pool size
            timeout_ms: Connection and operation timeout in milliseconds
            use_data_manager: If True, use Data Manager API instead of direct MongoDB
        """
        self.use_data_manager = use_data_manager and DATA_MANAGER_AVAILABLE

        if self.use_data_manager:
            # Initialize Data Manager client
            self.data_manager_client = DataManagerClient()
            self.client = None  # No direct MongoDB connection needed
            self.database = None
            self._connected = False
            logger.info("Using Data Manager for configuration management")
            return

        # Fallback to direct MongoDB connection
        logger.info("Using direct MongoDB connection")
        self.uri = uri or os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        self.database_name = database or os.getenv("MONGODB_DATABASE", "petrosa")
        self.max_pool_size = max_pool_size
        self.min_pool_size = min_pool_size
        self.timeout_ms = timeout_ms

        self.client: Optional[AsyncIOMotorClient] = None
        self.database: Optional[AsyncIOMotorDatabase] = None
        self._connected = False

    async def connect(self) -> bool:
        """
        Establish connection to MongoDB or Data Manager.

        Returns:
            True if connected successfully, False otherwise
        """
        if self.use_data_manager:
            await self.data_manager_client.connect()
            self._connected = True
            return True

        try:
            self.client = AsyncIOMotorClient(
                self.uri,
                maxPoolSize=self.max_pool_size,
                minPoolSize=self.min_pool_size,
                serverSelectionTimeoutMS=self.timeout_ms,
                connectTimeoutMS=self.timeout_ms,
                socketTimeoutMS=self.timeout_ms,
                retryWrites=True,
                retryReads=True,
            )

            # Test connection
            await self.client.admin.command("ping")

            self.database = self.client[self.database_name]
            self._connected = True

            logger.info(
                f"Connected to MongoDB: {self.database_name}",
                extra={"database": self.database_name},
            )

            # Create indexes for performance
            await self._create_indexes()

            return True

        except ConnectionFailure as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            self._connected = False
            return False
        except Exception as e:
            logger.error(f"Unexpected error connecting to MongoDB: {e}")
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Close MongoDB or Data Manager connection gracefully."""
        if self.use_data_manager:
            await self.data_manager_client.disconnect()
            self._connected = False
        else:
            if self.client:
                self.client.close()
                self._connected = False
                logger.info("Disconnected from MongoDB")

    async def _create_indexes(self) -> None:
        """Create indexes for configuration collections."""
        try:
            # Global configs: index on strategy_id
            await self.database.strategy_configs_global.create_index(
                "strategy_id", unique=True
            )

            # Symbol configs: compound index on strategy_id + symbol
            await self.database.strategy_configs_symbol.create_index(
                [("strategy_id", 1), ("symbol", 1)], unique=True
            )

            # Audit trail: indexes for querying
            await self.database.strategy_config_audit.create_index(
                [("strategy_id", 1), ("symbol", 1)]
            )
            await self.database.strategy_config_audit.create_index(
                [("changed_at", -1)]  # Descending for recent-first queries
            )

            logger.info("MongoDB indexes created successfully")

        except Exception as e:
            logger.warning(f"Failed to create MongoDB indexes: {e}")

    @property
    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self._connected

    async def health_check(self) -> bool:
        """
        Perform health check.

        Returns:
            True if MongoDB is healthy, False otherwise
        """
        if not self._connected or not self.client:
            return False

        try:
            await self.client.admin.command("ping")
            return True
        except Exception as e:
            logger.error(f"MongoDB health check failed: {e}")
            return False

    async def get_global_config(self, strategy_id: str) -> Optional[dict[str, Any]]:
        """
        Get global configuration for a strategy.

        Args:
            strategy_id: Strategy identifier

        Returns:
            Configuration document or None if not found
        """
        if self.use_data_manager:
            return await self.data_manager_client.get_global_config(strategy_id)

        if not self._connected:
            return None

        try:
            config = await self.database.strategy_configs_global.find_one(
                {"strategy_id": strategy_id}
            )
            return config
        except Exception as e:
            logger.error(f"Error fetching global config for {strategy_id}: {e}")
            return None

    async def get_symbol_config(
        self, strategy_id: str, symbol: str
    ) -> Optional[dict[str, Any]]:
        """
        Get symbol-specific configuration for a strategy.

        Args:
            strategy_id: Strategy identifier
            symbol: Trading symbol (e.g., 'BTCUSDT')

        Returns:
            Configuration document or None if not found
        """
        if self.use_data_manager:
            return await self.data_manager_client.get_symbol_config(strategy_id, symbol)

        if not self._connected:
            return None

        try:
            config = await self.database.strategy_configs_symbol.find_one(
                {"strategy_id": strategy_id, "symbol": symbol}
            )
            return config
        except Exception as e:
            logger.error(
                f"Error fetching symbol config for {strategy_id}/{symbol}: {e}"
            )
            return None

    async def upsert_global_config(
        self, strategy_id: str, parameters: dict[str, Any], metadata: dict[str, Any]
    ) -> Optional[str]:
        """
        Create or update global configuration.

        Args:
            strategy_id: Strategy identifier
            parameters: Parameter key-value pairs
            metadata: Additional metadata (created_by, reason, etc.)

        Returns:
            Configuration ID or None on failure
        """
        if not self._connected:
            return None

        try:
            now = datetime.utcnow()
            doc = {
                "strategy_id": strategy_id,
                "parameters": parameters,
                "updated_at": now,
                "metadata": metadata,
            }

            # Get existing to check version
            existing = await self.get_global_config(strategy_id)
            if existing:
                doc["version"] = existing.get("version", 1) + 1
                doc["created_at"] = existing.get("created_at", now)
            else:
                doc["version"] = 1
                doc["created_at"] = now

            result = await self.database.strategy_configs_global.update_one(
                {"strategy_id": strategy_id}, {"$set": doc}, upsert=True
            )

            if result.upserted_id:
                logger.info(f"Created global config for {strategy_id}")
                return str(result.upserted_id)
            else:
                logger.info(f"Updated global config for {strategy_id}")
                return strategy_id

        except Exception as e:
            logger.error(f"Error upserting global config for {strategy_id}: {e}")
            return None

    async def upsert_symbol_config(
        self,
        strategy_id: str,
        symbol: str,
        parameters: dict[str, Any],
        metadata: dict[str, Any],
    ) -> Optional[str]:
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
        if not self._connected:
            return None

        try:
            now = datetime.utcnow()
            doc = {
                "strategy_id": strategy_id,
                "symbol": symbol,
                "parameters": parameters,
                "updated_at": now,
                "metadata": metadata,
            }

            # Get existing to check version
            existing = await self.get_symbol_config(strategy_id, symbol)
            if existing:
                doc["version"] = existing.get("version", 1) + 1
                doc["created_at"] = existing.get("created_at", now)
            else:
                doc["version"] = 1
                doc["created_at"] = now

            result = await self.database.strategy_configs_symbol.update_one(
                {"strategy_id": strategy_id, "symbol": symbol},
                {"$set": doc},
                upsert=True,
            )

            if result.upserted_id:
                logger.info(f"Created symbol config for {strategy_id}/{symbol}")
                return str(result.upserted_id)
            else:
                logger.info(f"Updated symbol config for {strategy_id}/{symbol}")
                return f"{strategy_id}:{symbol}"

        except Exception as e:
            logger.error(
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
        if not self._connected:
            return False

        try:
            result = await self.database.strategy_configs_global.delete_one(
                {"strategy_id": strategy_id}
            )
            if result.deleted_count > 0:
                logger.info(f"Deleted global config for {strategy_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting global config for {strategy_id}: {e}")
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
        if not self._connected:
            return False

        try:
            result = await self.database.strategy_configs_symbol.delete_one(
                {"strategy_id": strategy_id, "symbol": symbol}
            )
            if result.deleted_count > 0:
                logger.info(f"Deleted symbol config for {strategy_id}/{symbol}")
                return True
            return False
        except Exception as e:
            logger.error(
                f"Error deleting symbol config for {strategy_id}/{symbol}: {e}"
            )
            return False

    async def create_audit_record(self, audit_data: dict[str, Any]) -> Optional[str]:
        """
        Create audit trail record for configuration change.

        Args:
            audit_data: Audit information (action, old/new values, changed_by, etc.)

        Returns:
            Audit record ID or None on failure
        """
        if not self._connected:
            return None

        try:
            audit_data["changed_at"] = datetime.utcnow()
            result = await self.database.strategy_config_audit.insert_one(audit_data)
            logger.info(
                f"Created audit record for {audit_data.get('strategy_id')}",
                extra={"action": audit_data.get("action")},
            )
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"Error creating audit record: {e}")
            return None

    async def get_audit_trail(
        self, strategy_id: str, symbol: Optional[str] = None, limit: int = 100
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
        if not self._connected:
            return []

        try:
            query = {"strategy_id": strategy_id}
            if symbol:
                query["symbol"] = symbol

            cursor = (
                self.database.strategy_config_audit.find(query)
                .sort("changed_at", -1)
                .limit(limit)
            )

            records = await cursor.to_list(length=limit)
            return records

        except Exception as e:
            logger.error(f"Error fetching audit trail for {strategy_id}: {e}")
            return []

    async def list_all_strategy_ids(self) -> list[str]:
        """
        Get list of all strategy IDs with configurations.

        Returns:
            List of unique strategy IDs
        """
        if not self._connected:
            return []

        try:
            global_ids = await self.database.strategy_configs_global.distinct(
                "strategy_id"
            )
            symbol_ids = await self.database.strategy_configs_symbol.distinct(
                "strategy_id"
            )

            # Combine and deduplicate
            all_ids = list(set(global_ids + symbol_ids))
            return sorted(all_ids)

        except Exception as e:
            logger.error(f"Error listing strategy IDs: {e}")
            return []

    async def list_symbol_overrides(self, strategy_id: str) -> list[str]:
        """
        Get list of symbols with configuration overrides for a strategy.

        Args:
            strategy_id: Strategy identifier

        Returns:
            List of symbols with overrides
        """
        if not self._connected:
            return []

        try:
            symbols = await self.database.strategy_configs_symbol.distinct(
                "symbol", {"strategy_id": strategy_id}
            )
            return sorted(symbols)
        except Exception as e:
            logger.error(f"Error listing symbol overrides for {strategy_id}: {e}")
            return []
