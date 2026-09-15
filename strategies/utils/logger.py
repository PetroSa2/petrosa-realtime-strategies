"""
Structured logging setup for the Petrosa Realtime Strategies service.

This module provides structured logging configuration using structlog
with JSON formatting and proper correlation IDs.
"""

import logging
import os
import sys
from typing import Optional

import structlog

import constants

_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

#: Escape hatch (per #221) — explicit opt-in to run DEBUG logging in
#: production even with OTel log export enabled. Must be set intentionally;
#: absence means the safety guard is active.
ALLOW_DEBUG_IN_PROD_ENV = "ALLOW_DEBUG_IN_PROD"


def _resolve_safe_log_level(requested_level: str) -> tuple[str, bool]:
    """Resolve the effective log level, enforcing the production DEBUG guard.

    Per petrosa-realtime-strategies#221: on 2026-09-15, Grafana Cloud Loki
    ingested ~420K `debug`-level log lines from this service in a single
    window — evidence that nothing currently prevents `LOG_LEVEL=DEBUG` from
    reaching a production environment wired to export logs. This guard is
    the code-level backstop (the manifest/config-plane prevention is tracked
    separately per petrosa_k8s#388/#389).

    The guard only engages when ALL of the following hold:
      - the requested level is DEBUG
      - `constants.ENVIRONMENT` is "production"
      - OTel log export is enabled (`ENABLE_OTEL=true` and
        `OTEL_LOGS_EXPORTER` is not "none")

    When engaged and `ALLOW_DEBUG_IN_PROD=1` is NOT set, the effective level
    is downgraded to WARNING (fail-safe: WARNING/ERROR/CRITICAL still flow
    normally, so real incidents are never silenced) and a CRITICAL log is
    emitted so the override is loudly visible. Dev/test tiers, non-OTel
    setups, and the explicit escape hatch are all left untouched — DEBUG
    still works exactly as before there.

    Returns:
        (effective_level, was_overridden)
    """
    requested = (requested_level or "INFO").upper()
    if requested not in _VALID_LOG_LEVELS:
        requested = "INFO"

    if requested != "DEBUG":
        return requested, False

    is_production = constants.ENVIRONMENT.lower() == "production"
    otel_log_export_enabled = (
        getattr(constants, "ENABLE_OTEL", False)
        and getattr(constants, "OTEL_LOGS_EXPORTER", "otlp").lower() != "none"
    )

    if not (is_production and otel_log_export_enabled):
        # Dev/test tiers, or production without OTel log export wired up:
        # DEBUG is safe here, nothing ships to Grafana Cloud.
        return "DEBUG", False

    allow_debug_in_prod = os.getenv(ALLOW_DEBUG_IN_PROD_ENV, "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if allow_debug_in_prod:
        return "DEBUG", False

    return "WARNING", True


def setup_logging(level: str = "INFO") -> structlog.BoundLogger:
    """
    Set up structured logging for the service.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Configured structlog logger
    """
    effective_level, was_overridden = _resolve_safe_log_level(level)

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, effective_level),
        force=True,
    )

    if was_overridden:
        logging.getLogger(constants.SERVICE_NAME).critical(
            "LOG_LEVEL safety guard triggered: refusing to run at DEBUG in "
            "production with OTel log export enabled. Effective level "
            "downgraded to WARNING. Set ALLOW_DEBUG_IN_PROD=1 to explicitly "
            "opt out of this guard (see petrosa-realtime-strategies#221)."
        )

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            (
                structlog.processors.JSONRenderer()
                if constants.LOG_FORMAT == "json"
                else structlog.dev.ConsoleRenderer()
            ),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Create logger with service context
    logger = structlog.get_logger(constants.SERVICE_NAME)

    # Add service metadata
    logger = logger.bind(
        service_name=constants.SERVICE_NAME,
        service_version=constants.SERVICE_VERSION,
        environment=constants.ENVIRONMENT,
    )

    return logger


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    """
    Get a logger instance.

    Args:
        name: Logger name (optional)

    Returns:
        Configured structlog logger
    """
    if name:
        return structlog.get_logger(name)
    else:
        return structlog.get_logger(constants.SERVICE_NAME)


def add_correlation_id(
    logger: structlog.BoundLogger, correlation_id: str
) -> structlog.BoundLogger:
    """
    Add correlation ID to logger context.

    Args:
        logger: Logger instance
        correlation_id: Correlation ID for request tracing

    Returns:
        Logger with correlation ID bound
    """
    return logger.bind(correlation_id=correlation_id)


def add_request_context(
    logger: structlog.BoundLogger, **kwargs
) -> structlog.BoundLogger:
    """
    Add request context to logger.

    Args:
        logger: Logger instance
        **kwargs: Context key-value pairs

    Returns:
        Logger with context bound
    """
    return logger.bind(**kwargs)
