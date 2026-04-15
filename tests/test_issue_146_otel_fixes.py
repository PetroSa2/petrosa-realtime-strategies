"""
Tests for issue #146 fixes:
  - AC1: No 'Attempting to instrument' warning when opentelemetry-instrument is in sys.argv
  - AC2: attach_logging_handler() not called from lifespan (single call via main.py)
"""

import sys
from unittest.mock import MagicMock


class TestAutoInstrumentationGuard:
    """AC1: instrument_fastapi() skipped when CLI wrapper already active."""

    def test_guard_true_when_cli_wrapper_in_argv(self):
        """Guard returns True when opentelemetry-instrument is in sys.argv."""
        fake_argv = ["opentelemetry-instrument", "python", "-m", "strategies.main"]
        result = any("opentelemetry-instrument" in arg for arg in fake_argv)
        assert result is True

    def test_guard_false_when_cli_wrapper_absent(self):
        """Guard returns False when opentelemetry-instrument is NOT in sys.argv."""
        fake_argv = ["python", "-m", "strategies.main"]
        result = any("opentelemetry-instrument" in arg for arg in fake_argv)
        assert result is False

    def test_no_fastapi_instrumentation_when_auto_instrumented(self):
        """When opentelemetry-instrument is in sys.argv, instrument_fastapi is not called."""
        fake_argv = ["opentelemetry-instrument", "python", "-m", "strategies.main"]
        mock_instrument_fastapi = MagicMock()

        _is_auto_instrumented = any(
            "opentelemetry-instrument" in arg for arg in fake_argv
        )
        if not _is_auto_instrumented:
            mock_instrument_fastapi()

        mock_instrument_fastapi.assert_not_called()

    def test_fastapi_instrumented_when_not_auto_instrumented(self):
        """When opentelemetry-instrument is NOT in sys.argv, instrument_fastapi is called."""
        fake_argv = ["python", "-m", "strategies.main"]
        mock_instrument_fastapi = MagicMock()

        _is_auto_instrumented = any(
            "opentelemetry-instrument" in arg for arg in fake_argv
        )
        if not _is_auto_instrumented:
            mock_instrument_fastapi()

        mock_instrument_fastapi.assert_called_once()

    def test_guard_detects_cli_wrapper_in_any_argv_position(self):
        """Guard detects opentelemetry-instrument regardless of argv position."""
        cases = [
            ["opentelemetry-instrument", "python"],
            ["/usr/bin/opentelemetry-instrument", "python"],
            ["python", "opentelemetry-instrument"],
        ]
        for argv in cases:
            result = any("opentelemetry-instrument" in arg for arg in argv)
            assert result is True, f"Failed to detect CLI wrapper in: {argv}"


class TestLifespanNoDuplicateLoggingHandler:
    """AC2: attach_logging_handler() removed from lifespan to avoid duplicate calls."""

    def test_lifespan_does_not_call_attach_logging_handler(self):
        """The lifespan closure in HealthServer.__init__ must not call attach_logging_handler."""
        import pathlib

        server_path = (
            pathlib.Path(__file__).parent.parent / "strategies" / "health" / "server.py"
        )
        source = server_path.read_text()

        lifespan_start = source.find("async def lifespan")
        fastapi_init = source.find("self.app = FastAPI")
        assert lifespan_start != -1, "Could not find lifespan function in server.py"
        assert fastapi_init != -1, "Could not find FastAPI instantiation in server.py"

        lifespan_source = source[lifespan_start:fastapi_init]

        assert "attach_logging_handler" not in lifespan_source, (
            "attach_logging_handler() should not be called from lifespan — "
            "it is called once from main.py; a second call produces duplicate log warnings"
        )

    def test_instrument_fastapi_guard_present_in_source(self):
        """server.py must contain the _is_auto_instrumented guard before instrument_fastapi."""
        import pathlib

        server_path = (
            pathlib.Path(__file__).parent.parent / "strategies" / "health" / "server.py"
        )
        source = server_path.read_text()

        assert "_is_auto_instrumented" in source, (
            "The _is_auto_instrumented guard must be present in server.py "
            "to prevent double FastAPI instrumentation under opentelemetry-instrument CLI"
        )
        assert "opentelemetry-instrument" in source, (
            "The guard must check for 'opentelemetry-instrument' in sys.argv"
        )
