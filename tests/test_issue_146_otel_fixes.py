"""
Tests for issue #146 fixes:
  - AC1: No 'Attempting to instrument' warning when opentelemetry-instrument is in sys.argv
  - AC2: attach_logging_handler() not called from lifespan (single call via main.py)
"""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from strategies.health.server import HealthServer


def _setup_mock_constants(mock_const) -> None:
    """Configure mock constants required for HealthServer instantiation."""
    mock_const.SERVICE_VERSION = "1.0.0"
    mock_const.SERVICE_NAME = "test-service"
    mock_const.ENVIRONMENT = "test"
    mock_const.get_enabled_strategies.return_value = []
    mock_const.TRADING_SYMBOLS = []
    mock_const.TRADING_ENABLE_SHORTS = False
    mock_const.HEARTBEAT_ENABLED = False
    mock_const.HEARTBEAT_INTERVAL_SECONDS = 30
    mock_const.LOG_LEVEL = "INFO"
    mock_const.ENABLE_OTEL = False
    mock_const.NATS_URL = "nats://localhost:4222"
    mock_const.NATS_CONSUMER_TOPIC = "test"
    mock_const.NATS_PUBLISHER_TOPIC = "test"
    mock_const.HEALTH_CHECK_PORT = 8080
    mock_const.get_strategy_config.return_value = {}
    mock_const.get_trading_config.return_value = {}
    mock_const.get_risk_config.return_value = {}
    mock_const.TRADING_LEVERAGE = 1.0


class TestAutoInstrumentationGuard:
    """AC1: instrument_fastapi() skipped when CLI wrapper already active."""

    def test_instrument_fastapi_not_called_when_auto_instrumented(self):
        """HealthServer.__init__ must skip instrument_fastapi() when opentelemetry-instrument is in sys.argv."""
        mock_instrumentors = MagicMock()

        with (
            patch("strategies.health.server.constants") as mock_const,
            patch.dict(
                "sys.modules", {"petrosa_otel.instrumentors": mock_instrumentors}
            ),
            patch(
                "sys.argv",
                ["opentelemetry-instrument", "python", "-m", "strategies.main"],
            ),
        ):
            _setup_mock_constants(mock_const)
            HealthServer(port=8080)

        mock_instrumentors.instrument_fastapi.assert_not_called()

    def test_instrument_fastapi_called_when_not_auto_instrumented(self):
        """HealthServer.__init__ must call instrument_fastapi() when opentelemetry-instrument is absent from sys.argv."""
        mock_instrumentors = MagicMock()

        with (
            patch("strategies.health.server.constants") as mock_const,
            patch.dict(
                "sys.modules", {"petrosa_otel.instrumentors": mock_instrumentors}
            ),
            patch("sys.argv", ["python", "-m", "strategies.main"]),
        ):
            _setup_mock_constants(mock_const)
            HealthServer(port=8080)

        mock_instrumentors.instrument_fastapi.assert_called_once()

    def test_guard_detects_cli_wrapper_in_any_argv_position(self):
        """HealthServer skips instrument_fastapi() regardless of where opentelemetry-instrument appears in argv."""
        cases = [
            ["opentelemetry-instrument", "python"],
            ["/usr/bin/opentelemetry-instrument", "python"],
            ["python", "opentelemetry-instrument"],
        ]

        for argv in cases:
            mock_instrumentors = MagicMock()
            with (
                patch("strategies.health.server.constants") as mock_const,
                patch.dict(
                    "sys.modules", {"petrosa_otel.instrumentors": mock_instrumentors}
                ),
                patch("sys.argv", argv),
            ):
                _setup_mock_constants(mock_const)
                HealthServer(port=8080)

            (
                mock_instrumentors.instrument_fastapi.assert_not_called(),
                (f"instrument_fastapi was called for argv={argv}"),
            )


class TestLifespanNoDuplicateLoggingHandler:
    """AC2: attach_logging_handler() removed from lifespan to avoid duplicate calls."""

    def test_attach_logging_handler_not_called_during_lifespan(self):
        """FastAPI lifespan startup must not invoke attach_logging_handler.

        A MagicMock is injected into sys.modules["petrosa_otel"] so that any
        local 'from petrosa_otel import attach_logging_handler' call inside the
        lifespan would be tracked. The test fails if the call count is non-zero.
        """
        attach_mock = MagicMock()
        petrosa_otel_mock = MagicMock()
        petrosa_otel_mock.attach_logging_handler = attach_mock

        with (
            patch("strategies.health.server.constants") as mock_const,
            patch.dict(
                "sys.modules",
                {
                    "petrosa_otel": petrosa_otel_mock,
                    "petrosa_otel.instrumentors": MagicMock(),
                },
            ),
            patch("sys.argv", ["opentelemetry-instrument", "python"]),
        ):
            _setup_mock_constants(mock_const)
            server = HealthServer(port=8080)
            with TestClient(server.app):
                pass  # triggers lifespan startup and shutdown

        attach_mock.assert_not_called()

    def test_lifespan_completes_successfully(self):
        """FastAPI lifespan must start and shut down without error."""
        with (
            patch("strategies.health.server.constants") as mock_const,
            patch.dict("sys.modules", {"petrosa_otel.instrumentors": MagicMock()}),
            patch("sys.argv", ["opentelemetry-instrument", "python"]),
        ):
            _setup_mock_constants(mock_const)
            server = HealthServer(port=8080)
            with TestClient(server.app) as client:
                response = client.get("/healthz")
                assert response.status_code in (200, 503)
