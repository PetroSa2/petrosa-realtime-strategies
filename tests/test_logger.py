"""
Tests for strategies/utils/logger.py.
"""

from strategies.utils.logger import get_logger, setup_logging


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

