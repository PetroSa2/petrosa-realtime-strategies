"""
Telemetry utility functions for graceful shutdown.

This module provides functions to flush and shutdown OpenTelemetry providers
to prevent data loss during pod termination in Kubernetes.
"""

import concurrent.futures
import logging
import time
from typing import Optional

try:
    from opentelemetry import metrics, trace
except ImportError:
    trace = None  # type: ignore
    metrics = None  # type: ignore

logger = logging.getLogger(__name__)

# Per #223: default bound for shutdown_telemetry(). See constants.py's
# TELEMETRY_SHUTDOWN_TIMEOUT_SECONDS for the production-configurable value;
# this module-local default keeps the function usable without importing the
# app's `constants` module (tests import this module standalone).
_DEFAULT_SHUTDOWN_TIMEOUT_SECONDS = 3.0


def _run_with_timeout(func, timeout_seconds: float, description: str) -> None:
    """Run a (potentially blocking) zero-arg callable with a hard wall-clock bound.

    Per #223: some OTel SDK provider `.shutdown()` implementations either
    default to a long internal timeout (`MeterProvider.shutdown()` defaults
    to 30_000ms) or have none at all (`TracerProvider.shutdown()` accepts no
    timeout parameter and simply waits on the underlying span processor,
    which itself waits unboundedly on the configured exporter). Calling
    these directly from a SIGTERM path risks consuming the entire pod
    `terminationGracePeriodSeconds`, turning an ordinary restart into a
    forced SIGKILL (exit 137, reason=Error -- easily mistaken for OOMKilled).

    This helper runs `func` on a worker thread and gives up waiting after
    `timeout_seconds`; the worker thread is intentionally NOT force-killed
    (Python cannot safely do that), but the caller no longer blocks on it,
    so the shutdown sequence can proceed and the process can still exit
    promptly (see `SHUTDOWN_WATCHDOG_SECONDS` in `strategies/main.py` for
    the final safety net if a thread never returns).
    """
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(func)
    try:
        future.result(timeout=timeout_seconds)
    except concurrent.futures.TimeoutError:
        logger.warning(
            f"⚠️  {description} did not complete within {timeout_seconds}s "
            "-- continuing shutdown without waiting further"
        )
    except Exception as e:
        logger.error(f"⚠️  Error during {description}: {e}")
    finally:
        # Don't block process exit waiting on a possibly-hung worker thread.
        executor.shutdown(wait=False, cancel_futures=True)


# Global logger provider reference (if available)
_global_logger_provider: object | None = None


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

    # Flush traces (with timeout) - handle failures individually
    try:
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
    except Exception as e:
        logger.error(f"⚠️  Error flushing traces: {e}")

    # Flush metrics (with timeout if supported) - handle failures individually
    try:
        meter_provider = metrics.get_meter_provider()
        if hasattr(meter_provider, "force_flush"):
            try:
                meter_provider.force_flush(timeout_millis=int(timeout_seconds * 1000))
                logger.info("✅ Metrics flushed successfully")
            except TypeError:
                meter_provider.force_flush()
                logger.info("✅ Metrics flushed successfully")
    except Exception as e:
        logger.error(f"⚠️  Error flushing metrics: {e}")

    # Flush logs (with timeout if supported) - handle failures individually
    try:
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
    except Exception as e:
        logger.error(f"⚠️  Error flushing logs: {e}")

    # Ensure we don't exceed total timeout
    elapsed = time.time() - start_time
    if elapsed < timeout_seconds:
        # Brief wait to allow batch processors to finalize export
        remaining_time = timeout_seconds - elapsed
        time.sleep(min(0.5, remaining_time))


def shutdown_telemetry(
    timeout_seconds: float = _DEFAULT_SHUTDOWN_TIMEOUT_SECONDS,
) -> None:
    """
    Shutdown all telemetry providers to ensure clean termination.

    This function should be called after flush_telemetry() to properly shut down
    all OpenTelemetry providers and release resources.

    Per #223: each provider's `.shutdown()` call is individually bounded by
    `timeout_seconds` via `_run_with_timeout`, instead of relying on the SDK's
    own defaults (`MeterProvider.shutdown()` defaults to 30s;
    `TracerProvider.shutdown()` has no bound at all). Without this, a
    slow/unreachable OTLP collector could make pod termination take longer
    than `terminationGracePeriodSeconds`, causing kubelet to SIGKILL the
    process (exit 137, reason=Error) -- a signature easily mistaken for
    OOMKilled even though memory was never the constraint.

    Args:
        timeout_seconds: Maximum time to wait for EACH provider's shutdown
            call (default: 3.0). Total worst-case added latency is therefore
            bounded (roughly 3x this value), not unbounded.

    Returns:
        None
    """
    if trace is None or metrics is None:
        logger.warning("OpenTelemetry not available - skipping telemetry shutdown")
        return

    # Shutdown traces - bounded, handle failures individually
    tracer_provider = trace.get_tracer_provider()
    if hasattr(tracer_provider, "shutdown"):
        _run_with_timeout(
            tracer_provider.shutdown, timeout_seconds, "trace provider shutdown"
        )
        logger.info("✅ Trace provider shutdown attempted")

    # Shutdown metrics - bounded, handle failures individually
    meter_provider = metrics.get_meter_provider()
    if hasattr(meter_provider, "shutdown"):
        # MeterProvider.shutdown() accepts timeout_millis natively (its own
        # default is 30_000ms) -- pass ours explicitly. If a given provider
        # implementation doesn't accept the kwarg, the TypeError is caught
        # (and logged) inside _run_with_timeout itself like any other
        # shutdown failure; the wall-clock bound from the executor still
        # applies regardless.
        _run_with_timeout(
            lambda: meter_provider.shutdown(timeout_millis=int(timeout_seconds * 1000)),
            timeout_seconds,
            "metrics provider shutdown",
        )
        logger.info("✅ Metrics provider shutdown attempted")

    # Shutdown logs - bounded, handle failures individually
    global _global_logger_provider
    if _global_logger_provider is not None and hasattr(
        _global_logger_provider, "shutdown"
    ):
        _run_with_timeout(
            _global_logger_provider.shutdown,
            timeout_seconds,
            "log provider shutdown",
        )
        logger.info("✅ Log provider shutdown attempted")
