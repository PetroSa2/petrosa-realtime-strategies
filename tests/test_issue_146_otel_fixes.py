"""
Tests for issue #146 fixes:
  - AC1: No 'Attempting to instrument' warning when FastAPI app is already auto-instrumented
  - AC2: attach_logging_handler() not called from lifespan (single call via main.py)
"""

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
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
    """AC1: instrument_fastapi() skipped when app is already auto-instrumented by OTel SDK."""

    def test_instrument_fastapi_not_called_when_app_already_instrumented(self):
        """HealthServer.__init__ must skip instrument_fastapi() when the FastAPI app already
        has _is_instrumented_by_opentelemetry=True (set by opentelemetry-instrument CLI)."""
        mock_instrumentors = MagicMock()

        with (
            patch("strategies.health.server.constants") as mock_const,
            patch.dict(
                "sys.modules", {"petrosa_otel.instrumentors": mock_instrumentors}
            ),
            patch("strategies.health.server.FastAPI") as MockFastAPI,
        ):
            _setup_mock_constants(mock_const)
            # Simulate _InstrumentedFastAPI: auto-instrumentation sets the attribute on init
            mock_app = MagicMock(spec=FastAPI)
            mock_app._is_instrumented_by_opentelemetry = True
            MockFastAPI.return_value = mock_app
            HealthServer(port=8080)

        mock_instrumentors.instrument_fastapi.assert_not_called()

    def test_instrument_fastapi_called_when_app_not_yet_instrumented(self):
        """HealthServer.__init__ must call instrument_fastapi() when the FastAPI app has
        not yet been instrumented (no opentelemetry-instrument CLI in the command)."""
        mock_instrumentors = MagicMock()

        with (
            patch("strategies.health.server.constants") as mock_const,
            patch.dict(
                "sys.modules", {"petrosa_otel.instrumentors": mock_instrumentors}
            ),
            patch("strategies.health.server.FastAPI") as MockFastAPI,
        ):
            _setup_mock_constants(mock_const)
            # Simulate plain FastAPI (no auto-instrumentation): attribute absent.
            # spec=FastAPI excludes _is_instrumented_by_opentelemetry (not on the real
            # class), so getattr(app, ..., False) returns the default False — no del needed.
            mock_app = MagicMock(spec=FastAPI)
            MockFastAPI.return_value = mock_app
            HealthServer(port=8080)

        mock_instrumentors.instrument_fastapi.assert_called_once()

    def test_instrument_fastapi_called_when_attribute_explicitly_false(self):
        """Guard falls through to manual instrumentation when _is_instrumented_by_opentelemetry=False."""
        mock_instrumentors = MagicMock()

        with (
            patch("strategies.health.server.constants") as mock_const,
            patch.dict(
                "sys.modules", {"petrosa_otel.instrumentors": mock_instrumentors}
            ),
            patch("strategies.health.server.FastAPI") as MockFastAPI,
        ):
            _setup_mock_constants(mock_const)
            mock_app = MagicMock(spec=FastAPI)
            mock_app._is_instrumented_by_opentelemetry = False
            MockFastAPI.return_value = mock_app
            HealthServer(port=8080)

        mock_instrumentors.instrument_fastapi.assert_called_once()


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
        ):
            _setup_mock_constants(mock_const)
            server = HealthServer(port=8080)
            with TestClient(server.app) as client:
                response = client.get("/healthz")
                assert response.status_code in (200, 503)
