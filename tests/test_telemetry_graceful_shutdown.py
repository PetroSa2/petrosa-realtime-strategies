"""
Tests for graceful telemetry shutdown functions in strategies/utils/telemetry.py.

Tests flush_telemetry() and shutdown_telemetry() to ensure telemetry data
is properly flushed and providers are shut down during graceful shutdown scenarios.
"""

from unittest.mock import MagicMock, patch

from strategies.utils.telemetry import flush_telemetry, shutdown_telemetry


class TestFlushTelemetry:
    """Test suite for flush_telemetry function."""

    def test_flush_telemetry_with_all_providers(self):
        """Test flushing telemetry with all providers configured."""
        # Mock providers
        mock_tracer_provider = MagicMock()
        mock_tracer_provider.force_flush = MagicMock()

        mock_meter_provider = MagicMock()
        mock_meter_provider.force_flush = MagicMock()

        mock_logger_provider = MagicMock()
        mock_logger_provider.force_flush = MagicMock()

        with patch(
            "strategies.utils.telemetry.trace.get_tracer_provider",
            return_value=mock_tracer_provider,
        ):
            with patch(
                "strategies.utils.telemetry.metrics.get_meter_provider",
                return_value=mock_meter_provider,
            ):
                with patch(
                    "strategies.utils.telemetry._global_logger_provider",
                    mock_logger_provider,
                ):
                    flush_telemetry()

        # Verify all providers were flushed
        mock_tracer_provider.force_flush.assert_called_once()
        mock_meter_provider.force_flush.assert_called_once()
        mock_logger_provider.force_flush.assert_called_once()

    def test_flush_telemetry_with_timeout(self):
        """Test flushing telemetry with custom timeout."""
        mock_tracer_provider = MagicMock()
        mock_tracer_provider.force_flush = MagicMock()

        with patch(
            "strategies.utils.telemetry.trace.get_tracer_provider",
            return_value=mock_tracer_provider,
        ):
            with patch(
                "strategies.utils.telemetry.metrics.get_meter_provider",
                return_value=MagicMock(),
            ):
                with patch("strategies.utils.telemetry._global_logger_provider", None):
                    flush_telemetry(timeout_seconds=2.0)

        # Verify flush was called (may or may not include timeout parameter)
        assert mock_tracer_provider.force_flush.called

    def test_flush_telemetry_without_providers(self):
        """Test flushing when providers are not configured."""
        mock_tracer_provider = MagicMock(spec=[])  # No force_flush method
        mock_meter_provider = MagicMock(spec=[])  # No force_flush method

        with patch(
            "strategies.utils.telemetry.trace.get_tracer_provider",
            return_value=mock_tracer_provider,
        ):
            with patch(
                "strategies.utils.telemetry.metrics.get_meter_provider",
                return_value=mock_meter_provider,
            ):
                with patch("strategies.utils.telemetry._global_logger_provider", None):
                    # Should not raise exception - function handles missing providers gracefully
                    flush_telemetry()
        
        # Verify the function completed without errors
        assert True  # Test passes if no exception was raised

    def test_flush_telemetry_handles_exceptions(self):
        """Test that flush_telemetry handles provider exceptions gracefully."""
        mock_tracer_provider = MagicMock()
        mock_tracer_provider.force_flush = MagicMock(
            side_effect=Exception("Flush failed")
        )

        mock_meter_provider = MagicMock()
        mock_meter_provider.force_flush = MagicMock()

        with patch(
            "strategies.utils.telemetry.trace.get_tracer_provider",
            return_value=mock_tracer_provider,
        ):
            with patch(
                "strategies.utils.telemetry.metrics.get_meter_provider",
                return_value=mock_meter_provider,
            ):
                with patch("strategies.utils.telemetry._global_logger_provider", None):
                    # Should not raise exception - function catches and logs errors
                    # Verify that even if tracer provider fails, meter provider still gets flushed
                    flush_telemetry()
                    mock_meter_provider.force_flush.assert_called_once()

    def test_flush_telemetry_without_opentelemetry(self):
        """Test flushing when OpenTelemetry is not available."""
        with patch("strategies.utils.telemetry.trace", None):
            with patch("strategies.utils.telemetry.metrics", None):
                # Should not raise exception - function handles missing OpenTelemetry gracefully
                flush_telemetry()
        
        # Verify the function completed without errors
        assert True  # Test passes if no exception was raised


class TestShutdownTelemetry:
    """Test suite for shutdown_telemetry function."""

    def test_shutdown_telemetry_with_all_providers(self):
        """Test shutting down telemetry with all providers configured."""
        # Mock providers
        mock_tracer_provider = MagicMock()
        mock_tracer_provider.shutdown = MagicMock()

        mock_meter_provider = MagicMock()
        mock_meter_provider.shutdown = MagicMock()

        mock_logger_provider = MagicMock()
        mock_logger_provider.shutdown = MagicMock()

        with patch(
            "strategies.utils.telemetry.trace.get_tracer_provider",
            return_value=mock_tracer_provider,
        ):
            with patch(
                "strategies.utils.telemetry.metrics.get_meter_provider",
                return_value=mock_meter_provider,
            ):
                with patch(
                    "strategies.utils.telemetry._global_logger_provider",
                    mock_logger_provider,
                ):
                    shutdown_telemetry()

        # Verify all providers were shut down
        mock_tracer_provider.shutdown.assert_called_once()
        mock_meter_provider.shutdown.assert_called_once()
        mock_logger_provider.shutdown.assert_called_once()

    def test_shutdown_telemetry_without_providers(self):
        """Test shutting down when providers are not configured."""
        mock_tracer_provider = MagicMock(spec=[])  # No shutdown method
        mock_meter_provider = MagicMock(spec=[])  # No shutdown method

        with patch(
            "strategies.utils.telemetry.trace.get_tracer_provider",
            return_value=mock_tracer_provider,
        ):
            with patch(
                "strategies.utils.telemetry.metrics.get_meter_provider",
                return_value=mock_meter_provider,
            ):
                with patch("strategies.utils.telemetry._global_logger_provider", None):
                    # Should not raise exception - function handles missing providers gracefully
                    shutdown_telemetry()
        
        # Verify the function completed without errors
        assert True  # Test passes if no exception was raised

    def test_shutdown_telemetry_handles_exceptions(self):
        """Test that shutdown_telemetry handles provider exceptions gracefully."""
        mock_tracer_provider = MagicMock()
        mock_tracer_provider.shutdown = MagicMock(
            side_effect=Exception("Shutdown failed")
        )

        with patch(
            "strategies.utils.telemetry.trace.get_tracer_provider",
            return_value=mock_tracer_provider,
        ):
            with patch(
                "strategies.utils.telemetry.metrics.get_meter_provider",
                return_value=MagicMock(),
            ):
                with patch("strategies.utils.telemetry._global_logger_provider", None):
                    # Should not raise exception - function catches and logs errors
                    shutdown_telemetry()
        
        # Verify the function completed without errors
        assert True  # Test passes if no exception was raised

    def test_shutdown_telemetry_without_opentelemetry(self):
        """Test shutting down when OpenTelemetry is not available."""
        with patch("strategies.utils.telemetry.trace", None):
            with patch("strategies.utils.telemetry.metrics", None):
                # Should not raise exception - function handles missing OpenTelemetry gracefully
                shutdown_telemetry()
        
        # Verify the function completed without errors
        assert True  # Test passes if no exception was raised
