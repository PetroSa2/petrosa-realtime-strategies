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
from unittest.mock import patch

import pytest

from strategies.core.consumer import NATSConsumer
from strategies.core.publisher import TradeOrderPublisher

# NOTE: no module-level `pytestmark = pytest.mark.integration` here on
# purpose. Only the two real-broker tests at the bottom of this file need
# Docker and are marked individually; the helper-level tests above them
# (docker-availability check, port-wait helpers, _NatsContainer's docker CLI
# invocations) are pure unit tests with subprocess/socket mocked out, so they
# always run -- including in CI, where Docker is unavailable and the two
# integration tests self-skip. This keeps real coverage of this file's own
# logic (not just the skip guard) regardless of Docker availability.

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


# ---------------------------------------------------------------------------
# Unit tests for the helpers above: no Docker, no real broker -- always run.
# ---------------------------------------------------------------------------


def test_docker_usable_false_when_binary_missing():
    with patch("shutil.which", return_value=None):
        assert _docker_usable() is False


def test_docker_usable_false_when_daemon_unreachable():
    with (
        patch("shutil.which", return_value="/usr/bin/docker"),
        patch(
            "subprocess.run",
            side_effect=subprocess.CalledProcessError(1, ["docker", "info"]),
        ),
    ):
        assert _docker_usable() is False


def test_docker_usable_true_when_binary_and_daemon_ok():
    with (
        patch("shutil.which", return_value="/usr/bin/docker"),
        patch("subprocess.run") as mock_run,
    ):
        assert _docker_usable() is True
    mock_run.assert_called_once()
    assert mock_run.call_args.kwargs["check"] is True


def test_free_port_returns_a_bindable_port():
    port = _free_port()
    assert 1 <= port <= 65535
    # The port must be free immediately after release -- rebind to confirm.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", port))


def test_wait_for_port_returns_once_listening():
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        result = _wait_for_port(port, timeout=2.0)  # must not raise
        assert result is None
    finally:
        listener.close()


def test_wait_for_port_raises_timeout_when_never_open():
    # Reserve a free port, then release it immediately -- nothing listens.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        closed_port = s.getsockname()[1]

    with pytest.raises(TimeoutError) as exc_info:
        _wait_for_port(closed_port, timeout=0.5)
    assert str(closed_port) in str(exc_info.value)


def test_wait_for_port_closed_returns_once_port_closes():
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    listener.close()

    result = _wait_for_port_closed(port, timeout=2.0)  # must not raise
    assert result is None


def test_wait_for_port_closed_raises_timeout_when_still_open():
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        with pytest.raises(TimeoutError) as exc_info:
            _wait_for_port_closed(port, timeout=0.5)
        assert str(port) in str(exc_info.value)
    finally:
        listener.close()


def test_nats_container_start_invokes_docker_run_and_waits_for_port():
    with (
        patch("subprocess.run") as mock_run,
        patch(f"{__name__}._wait_for_port") as mock_wait,
    ):
        container = _NatsContainer()
        container.start()

    args = mock_run.call_args.args[0]
    assert args[:3] == ["docker", "run", "-d"]
    assert "--rm" not in args
    assert container.name in args
    assert f"{container.port}:4222" in args
    assert args[-1] == _DOCKER_IMAGE
    mock_run.assert_called_once_with(args, check=True, capture_output=True)
    mock_wait.assert_called_once_with(container.port)


def test_nats_container_stop_invokes_docker_stop_and_waits_for_close():
    with (
        patch("subprocess.run") as mock_run,
        patch(f"{__name__}._wait_for_port_closed") as mock_wait_closed,
    ):
        container = _NatsContainer()
        container.stop()

    mock_run.assert_called_once_with(
        ["docker", "stop", "-t", "0", container.name], capture_output=True
    )
    mock_wait_closed.assert_called_once_with(container.port)


def test_nats_container_restart_invokes_docker_start_and_waits_for_port():
    with (
        patch("subprocess.run") as mock_run,
        patch(f"{__name__}._wait_for_port") as mock_wait,
    ):
        container = _NatsContainer()
        container.restart()

    mock_run.assert_called_once_with(
        ["docker", "start", container.name], check=True, capture_output=True
    )
    mock_wait.assert_called_once_with(container.port)


def test_nats_container_remove_invokes_docker_rm_f():
    with patch("subprocess.run") as mock_run:
        container = _NatsContainer()
        container.remove()

    mock_run.assert_called_once_with(
        ["docker", "rm", "-f", container.name], capture_output=True
    )


def test_nats_container_url_property():
    with patch(f"{__name__}._free_port", return_value=12345):
        container = _NatsContainer()
    assert container.url == "nats://127.0.0.1:12345"


def test_nats_container_fixture_skips_when_docker_unavailable():
    # `nats_container.__wrapped__` is the plain generator function pytest's
    # @pytest.fixture decorator wraps (functools.wraps-preserved); calling it
    # directly exercises the skip branch without needing the full fixture
    # machinery.
    unwrapped = nats_container.__wrapped__  # type: ignore[attr-defined]
    with patch(f"{__name__}.DOCKER_AVAILABLE", False):
        with pytest.raises(pytest.skip.Exception) as exc_info:
            next(unwrapped())
    assert SKIP_REASON in str(exc_info.value)


# ---------------------------------------------------------------------------
# Real Docker + real broker integration tests (self-skip without Docker).
# ---------------------------------------------------------------------------


@pytest.mark.integration
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
