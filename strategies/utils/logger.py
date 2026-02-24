"""
Structured logging setup for the Petrosa Realtime Strategies service.

This module provides structured logging configuration using structlog
with JSON formatting and proper correlation IDs.
"""

import logging
import sys
from typing import Optional

import structlog

import constants


def setup_logging(level: str = "INFO") -> structlog.BoundLogger:
    """
    Set up structured logging for the service.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Configured structlog logger
    """
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper()),
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
