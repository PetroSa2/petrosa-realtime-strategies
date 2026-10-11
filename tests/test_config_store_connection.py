import pytest

from strategies.health.server import HealthServer


@pytest.mark.asyncio
async def test_health_exposes_config_store_connection_state():
    client = type("Client", (), {"is_connected": True})()
    manager = type("Manager", (), {"mongodb_client": client})()
    server = HealthServer(config_manager=manager)
    server.is_running = True

    status = await server._compute_health_status()

    assert status["config_store_connected"] is True
    assert status["checks"]["config_store_connected"] is True
