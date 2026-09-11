"""
Integration test for NATS reconnect resilience (#185 AC6).

Spins up a *real* nats-server in a throwaway Docker container, connects a
NATSConsumer to it with the production reconnect configuration
(max_reconnect_attempts=-1, jittered reconnect_to_server_handler, lifecycle
callbacks), kills the container to simulate a broker outage, restarts it,
and asserts the client reconnects and resumes without any process restart.

This is intentionally NOT gated behind ``-m integration`` alone: ``make
test`` / ``make pipeline`` run ``pytest tests/`` with no marker filter (see
Makefile), and this repo's CI test job runs on the self-hosted
``petrosa-org-runners`` pool, which has **no Docker socket** (see AGENTS.md
"Runner policy"). Running `docker` commands there would hang/fail the whole
suite. To stay safe under that constraint, every test in this module
degrades to a clean ``pytest.skip`` whenever Docker is not usable in the
current environment (missing binary, no daemon, no permissions) -- it only
executes as a real integration test on machines where Docker actually works
(e.g. local dev, ubuntu-latest with Docker preinstalled).

Run locally:
    pytest tests/test_nats_reconnect_integration.py -m integration -v
"""

from __future__ import annotations

import asyncio
import shutil
import socket
import subprocess
import time
import uuid

import pytest

from strategies.core.consumer import NATSConsumer
from strategies.core.publisher import TradeOrderPublisher

pytestmark = pytest.mark.integration

_DOCKER_IMAGE = "nats:2-alpine"


def _docker_usable() -> bool:
    """Best-effort check that `docker` is installed AND the daemon is reachable."""
    if shutil.which("docker") is None:
        return False
    try:
        subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
            check=True,
        )
    except Exception:
        return False
    return True


DOCKER_AVAILABLE = _docker_usable()
SKIP_REASON = (
    "docker is not installed/usable in this environment "
    "(self-hosted CI runners have no docker socket per AGENTS.md runner policy)"
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(port: int, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            try:
                s.connect(("127.0.0.1", port))
                return
            except OSError:
                time.sleep(0.25)
    raise TimeoutError(f"nats-server did not open port {port} within {timeout}s")


def _wait_for_port_closed(port: int, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            try:
                s.connect(("127.0.0.1", port))
                time.sleep(0.25)
                continue
            except OSError:
                return
    raise TimeoutError(f"port {port} did not close within {timeout}s")


class _NatsContainer:
    """Throwaway `nats:2-alpine` container on a random free host port."""

    def __init__(self):
        self.name = f"nats-reconnect-test-{uuid.uuid4().hex[:8]}"
        self.port = _free_port()

    def start(self) -> None:
        # Deliberately no --rm: the test stops/starts this same container to
        # simulate a broker outage + recovery, and `docker stop` on a --rm
        # container auto-removes it, making a subsequent `docker start`
        # impossible. Cleanup is handled explicitly via remove().
        subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                self.name,
                "-p",
                f"{self.port}:4222",
                _DOCKER_IMAGE,
            ],
            check=True,
            capture_output=True,
        )
        _wait_for_port(self.port)

    def stop(self) -> None:
        """Simulate a broker outage: stop the container, keep the port free
        for the restart, and let the caller decide when to bring it back."""
        subprocess.run(["docker", "stop", "-t", "0", self.name], capture_output=True)
        _wait_for_port_closed(self.port)

    def restart(self) -> None:
        subprocess.run(["docker", "start", self.name], check=True, capture_output=True)
        _wait_for_port(self.port)

    def remove(self) -> None:
        subprocess.run(["docker", "rm", "-f", self.name], capture_output=True)

    @property
    def url(self) -> str:
        return f"nats://127.0.0.1:{self.port}"


@pytest.fixture
def nats_container():
    if not DOCKER_AVAILABLE:
        pytest.skip(SKIP_REASON)
    container = _NatsContainer()
    container.start()
    try:
        yield container
    finally:
        container.remove()


@pytest.mark.asyncio
async def test_consumer_reconnects_after_real_broker_restart(nats_container):
    """AC6: kill the real broker, restart it, confirm the consumer reconnects
    and resumes -- without a process/pod restart."""
    publisher = TradeOrderPublisher(nats_url=nats_container.url, topic="test.orders")
    consumer = NATSConsumer(
        nats_url=nats_container.url,
        topic="test.subject",
        consumer_name="reconnect-it-consumer",
        consumer_group="reconnect-it-group",
        publisher=publisher,
    )

    reconnected = asyncio.Event()
    original_reconnected_cb = consumer._on_nats_reconnected

    async def _on_reconnected_and_signal():
        await original_reconnected_cb()
        reconnected.set()

    consumer._on_nats_reconnected = _on_reconnected_and_signal

    await consumer._connect_to_nats()
    try:
        assert consumer.nats_connected is True

        # Simulate a broker outage long enough to exceed a naive
        # max_reconnect_attempts=10 / reconnect_time_wait=1 budget (~10s).
        nats_container.stop()
        # nats-py surfaces the drop asynchronously; give it a beat.
        await asyncio.sleep(1.0)

        nats_container.restart()

        await asyncio.wait_for(reconnected.wait(), timeout=30.0)
        assert consumer.nats_connected is True
    finally:
        assert consumer.nats_client is not None
        await consumer.nats_client.close()


@pytest.mark.asyncio
async def test_publisher_reconnects_after_real_broker_restart(nats_container):
    """AC6 (publisher side): same outage/restart cycle for TradeOrderPublisher."""
    publisher = TradeOrderPublisher(nats_url=nats_container.url, topic="test.orders")

    reconnected = asyncio.Event()
    original_reconnected_cb = publisher._on_nats_reconnected

    async def _on_reconnected_and_signal():
        await original_reconnected_cb()
        reconnected.set()

    publisher._on_nats_reconnected = _on_reconnected_and_signal

    await publisher._connect_to_nats()
    try:
        assert publisher.nats_connected is True

        nats_container.stop()
        await asyncio.sleep(1.0)

        nats_container.restart()

        await asyncio.wait_for(reconnected.wait(), timeout=30.0)
        assert publisher.nats_connected is True
    finally:
        assert publisher.nats_client is not None
        await publisher.nats_client.close()
