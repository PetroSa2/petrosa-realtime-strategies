"""
Telemetry utility functions for graceful shutdown.

This module provides functions to flush and shutdown OpenTelemetry providers
to prevent data loss during pod termination in Kubernetes.
"""

import logging
import time
from typing import Optional

try:
    from opentelemetry import metrics, trace
except ImportError:
    trace = None  # type: ignore
    metrics = None  # type: ignore

logger = logging.getLogger(__name__)

# Global logger provider reference (if available)
_global_logger_provider: Optional[object] = None


def set_logger_provider(provider: object) -> None:
    """
    Set the global logger provider reference.

    Args:
        provider: The OpenTelemetry LoggerProvider instance
    """
    global _global_logger_provider
    _global_logger_provider = provider


def flush_telemetry(timeout_seconds: float = 5.0) -> None:
    """
    Force flush all telemetry data (traces, metrics, logs) to prevent data loss.

    This function should be called on graceful shutdown (e.g., SIGTERM, SIGINT)
    to ensure that the last batch of telemetry data is exported before the
    process terminates.

    **Important Notes:**
    - This function is synchronous and may block for up to `timeout_seconds`
    - The default timeout (5 seconds) is designed to allow batch processors
      time to export pending data
    - For asyncio applications, consider calling this from the shutdown handler
      rather than signal handlers to avoid blocking the event loop
    - OpenTelemetry's force_flush() has its own internal timeout, which this
      function respects

    Args:
        timeout_seconds: Maximum time to wait for flush operations (default: 5.0)

    Returns:
        None
    """
    if trace is None or metrics is None:
        logger.warning("OpenTelemetry not available - skipping telemetry flush")
        return

    start_time = time.time()
    try:
        # Flush traces (with timeout)
        tracer_provider = trace.get_tracer_provider()
        if hasattr(tracer_provider, "force_flush"):
            try:
                # force_flush() accepts a timeout parameter
                tracer_provider.force_flush(timeout_millis=int(timeout_seconds * 1000))
                logger.info("✅ Traces flushed successfully")
            except TypeError:
                # Fallback for providers that don't accept timeout
                tracer_provider.force_flush()
                logger.info("✅ Traces flushed successfully")

        # Flush metrics (with timeout if supported)
        meter_provider = metrics.get_meter_provider()
        if hasattr(meter_provider, "force_flush"):
            try:
                meter_provider.force_flush(timeout_millis=int(timeout_seconds * 1000))
                logger.info("✅ Metrics flushed successfully")
            except TypeError:
                meter_provider.force_flush()
                logger.info("✅ Metrics flushed successfully")

        # Flush logs (with timeout if supported)
        global _global_logger_provider
        if _global_logger_provider is not None and hasattr(
            _global_logger_provider, "force_flush"
        ):
            try:
                _global_logger_provider.force_flush(
                    timeout_millis=int(timeout_seconds * 1000)
                )
                logger.info("✅ Logs flushed successfully")
            except TypeError:
                _global_logger_provider.force_flush()
                logger.info("✅ Logs flushed successfully")

        # Ensure we don't exceed total timeout
        elapsed = time.time() - start_time
        if elapsed < timeout_seconds:
            # Brief wait to allow batch processors to finalize export
            remaining_time = timeout_seconds - elapsed
            time.sleep(min(0.5, remaining_time))

    except Exception as e:
        logger.error(f"⚠️  Error flushing telemetry: {e}")


def shutdown_telemetry() -> None:
    """
    Shutdown all telemetry providers to ensure clean termination.

    This function should be called after flush_telemetry() to properly shut down
    all OpenTelemetry providers and release resources.

    Returns:
        None
    """
    if trace is None or metrics is None:
        logger.warning("OpenTelemetry not available - skipping telemetry shutdown")
        return

    try:
        # Shutdown traces
        tracer_provider = trace.get_tracer_provider()
        if hasattr(tracer_provider, "shutdown"):
            tracer_provider.shutdown()
            logger.info("✅ Trace provider shut down successfully")

        # Shutdown metrics
        meter_provider = metrics.get_meter_provider()
        if hasattr(meter_provider, "shutdown"):
            meter_provider.shutdown()
            logger.info("✅ Metrics provider shut down successfully")

        # Shutdown logs
        global _global_logger_provider
        if _global_logger_provider is not None and hasattr(
            _global_logger_provider, "shutdown"
        ):
            _global_logger_provider.shutdown()
            logger.info("✅ Log provider shut down successfully")

    except Exception as e:
        logger.error(f"⚠️  Error shutting down telemetry: {e}")
