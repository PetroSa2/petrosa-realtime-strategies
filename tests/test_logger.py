"""
Tests for strategies/utils/logger.py.
"""

import logging

import pytest

import constants
from strategies.utils.logger import (
    _resolve_safe_log_level,
    get_logger,
    setup_logging,
)


class TestLogLevelProductionGuard:
    """Per #221: DEBUG in production + OTel log export must be guarded.

    ~420K debug-level logs shipped to Grafana Cloud Loki because nothing
    prevented LOG_LEVEL=DEBUG from reaching a production environment wired
    to export logs. These tests cover AC3(a)-(d).
    """

    @pytest.fixture(autouse=True)
    def _reset_env(self, monkeypatch):
        monkeypatch.delenv("ALLOW_DEBUG_IN_PROD", raising=False)
        monkeypatch.setattr(constants, "ENVIRONMENT", "production")
        monkeypatch.setattr(constants, "ENABLE_OTEL", True)
        monkeypatch.setattr(constants, "OTEL_LOGS_EXPORTER", "otlp")
        yield

    def test_ac3a_production_debug_no_escape_hatch_is_guarded(self):
        """production + DEBUG + no escape hatch -> downgraded to WARNING."""
        effective, was_overridden = _resolve_safe_log_level("DEBUG")

        assert effective == "WARNING"
        assert was_overridden is True

    def test_ac3b_production_debug_with_escape_hatch_starts_at_debug(self, monkeypatch):
        """production + DEBUG + ALLOW_DEBUG_IN_PROD=1 -> runs at DEBUG."""
        monkeypatch.setenv("ALLOW_DEBUG_IN_PROD", "1")

        effective, was_overridden = _resolve_safe_log_level("DEBUG")

        assert effective == "DEBUG"
        assert was_overridden is False

    def test_ac3c_dev_tier_debug_starts_normally(self, monkeypatch):
        """dev/test tier + DEBUG -> DEBUG allowed, guard does not engage."""
        monkeypatch.setattr(constants, "ENVIRONMENT", "development")

        effective, was_overridden = _resolve_safe_log_level("DEBUG")

        assert effective == "DEBUG"
        assert was_overridden is False

    def test_ac3d_production_info_and_warning_start_normally(self):
        """INFO/WARNING in production -> unaffected by the guard."""
        for level in ("INFO", "WARNING"):
            effective, was_overridden = _resolve_safe_log_level(level)
            assert effective == level
            assert was_overridden is False

    def test_no_otel_log_export_debug_starts_normally(self, monkeypatch):
        """production + DEBUG but OTel log export disabled -> DEBUG allowed."""
        monkeypatch.setattr(constants, "OTEL_LOGS_EXPORTER", "none")

        effective, was_overridden = _resolve_safe_log_level("DEBUG")

        assert effective == "DEBUG"
        assert was_overridden is False

    def test_setup_logging_downgrades_and_logs_critical(self, mocker):
        """setup_logging() must apply the guard end-to-end and log loudly."""
        critical_spy = mocker.patch.object(logging.Logger, "critical")

        logger = setup_logging(level="DEBUG")

        assert logger is not None
        assert logging.getLogger().level == logging.WARNING
        assert critical_spy.call_count == 1
        assert "LOG_LEVEL safety guard" in critical_spy.call_args.args[0]

    def test_setup_logging_escape_hatch_keeps_debug(self, monkeypatch, mocker):
        """setup_logging() honors ALLOW_DEBUG_IN_PROD=1 without complaint."""
        monkeypatch.setenv("ALLOW_DEBUG_IN_PROD", "1")
        critical_spy = mocker.patch.object(logging.Logger, "critical")

        logger = setup_logging(level="DEBUG")

        assert logger is not None
        assert logging.getLogger().level == logging.DEBUG
        critical_spy.assert_not_called()


class TestLogger:
    """Test logger utility functions."""

    def test_get_logger(self):
        """Test get_logger returns a logger instance."""
        logger = get_logger("test")

        assert logger is not None
        assert hasattr(logger, "info")
        assert hasattr(logger, "error")
        assert hasattr(logger, "warning")
        assert hasattr(logger, "debug")

    def test_get_logger_with_name(self):
        """Test get_logger with custom name."""
        logger = get_logger("my_module")

        assert logger is not None

    def test_setup_logging(self):
        """Test setup_logging configures structlog."""
        # Should not raise exception
        logger = setup_logging(level="DEBUG")
        assert logger is not None

    def test_setup_logging_default_level(self):
        """Test setup_logging with default level."""
        logger = setup_logging()
        assert logger is not None

    def test_multiple_logger_instances(self):
        """Test getting multiple logger instances."""
        logger1 = get_logger("module1")
        logger2 = get_logger("module2")

        assert logger1 is not None
        assert logger2 is not None

    def test_get_logger_without_name(self):
        """Test get_logger without name uses service name."""
        logger = get_logger()

        assert logger is not None

    def test_add_correlation_id(self):
        """Test adding correlation ID to logger."""
        from strategies.utils.logger import add_correlation_id

        logger = get_logger("test")
        logger_with_id = add_correlation_id(logger, "test-correlation-123")

        assert logger_with_id is not None

    def test_add_request_context(self):
        """Test adding request context to logger."""
        from strategies.utils.logger import add_request_context

        logger = get_logger("test")
        logger_with_context = add_request_context(
            logger, request_id="req-123", user_id="user-456"
        )

        assert logger_with_context is not None
