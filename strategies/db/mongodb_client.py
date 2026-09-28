"""Data-manager facade retained for the strategy configuration API."""

import logging
from typing import Any

from ..services.data_manager_client import DataManagerClient

logger = logging.getLogger(__name__)


class MongoDBClient:
    """Compatibility facade backed exclusively by the data-manager service.

    The class name remains part of the configuration manager interface, but this
    service no longer owns MongoDB connections or a direct-storage fallback.
    """

    def __init__(self) -> None:
        self.data_manager_client = DataManagerClient()
        self._connected = False

    async def connect(self) -> bool:
        try:
            await self.data_manager_client.connect()
        except Exception as exc:
            logger.error("Failed to connect to Data Manager: %s", exc)
            self._connected = False
            return False
        self._connected = True
        return True

    async def disconnect(self) -> None:
        await self.data_manager_client.disconnect()
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def health_check(self) -> bool:
        if not self._connected:
            return False
        health = await self.data_manager_client.health_check()
        return health.get("status") == "healthy"

    async def get_lifecycle_state(self, strategy_id: str) -> dict[str, Any] | None:
        return await self.data_manager_client.get_lifecycle_state(strategy_id)

    async def upsert_lifecycle_state(
        self, strategy_id: str, state: dict[str, Any]
    ) -> str | None:
        return await self.data_manager_client.upsert_lifecycle_state(strategy_id, state)

    async def get_global_config(self, strategy_id: str) -> dict[str, Any] | None:
        return await self.data_manager_client.get_global_config(strategy_id)

    async def get_symbol_config(
        self, strategy_id: str, symbol: str
    ) -> dict[str, Any] | None:
        return await self.data_manager_client.get_symbol_config(strategy_id, symbol)

    async def upsert_global_config(
        self, strategy_id: str, parameters: dict[str, Any], metadata: dict[str, Any]
    ) -> str | None:
        return await self.data_manager_client.upsert_global_config(
            strategy_id, parameters, metadata
        )

    async def upsert_symbol_config(
        self,
        strategy_id: str,
        symbol: str,
        parameters: dict[str, Any],
        metadata: dict[str, Any],
    ) -> str | None:
        return await self.data_manager_client.upsert_symbol_config(
            strategy_id, symbol, parameters, metadata
        )

    async def delete_global_config(self, strategy_id: str) -> bool:
        return await self.data_manager_client.delete_global_config(strategy_id)

    async def delete_symbol_config(self, strategy_id: str, symbol: str) -> bool:
        return await self.data_manager_client.delete_symbol_config(strategy_id, symbol)

    async def create_audit_record(self, audit_data: dict[str, Any]) -> str | None:
        return await self.data_manager_client.create_audit_record(audit_data)

    async def get_audit_trail(
        self, strategy_id: str, symbol: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        return await self.data_manager_client.get_audit_trail(
            strategy_id, symbol, limit
        )

    async def get_audit_record_by_id(self, audit_id: str) -> dict[str, Any] | None:
        return await self.data_manager_client.get_audit_record_by_id(audit_id)

    async def get_audit_record_by_version(
        self, strategy_id: str, version: int, symbol: str | None = None
    ) -> dict[str, Any] | None:
        return await self.data_manager_client.get_audit_record_by_version(
            strategy_id, version, symbol
        )

    async def list_all_strategy_ids(self) -> list[str]:
        return await self.data_manager_client.list_all_strategy_ids()

    async def list_symbol_overrides(self, strategy_id: str) -> list[str]:
        return await self.data_manager_client.list_symbol_overrides(strategy_id)

    async def rollback_strategy_config(
        self,
        strategy_id: str,
        changed_by: str,
        symbol: str | None = None,
        target_version: int | None = None,
        reason: str | None = None,
    ) -> bool:
        return await self.data_manager_client.rollback_strategy_config(
            strategy_id, changed_by, symbol, target_version, reason
        )
