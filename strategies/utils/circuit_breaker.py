"""
Circuit breaker implementation for fault tolerance.

This module provides a circuit breaker pattern implementation to handle
failures gracefully and prevent cascading failures.
"""

import asyncio
import time
from collections.abc import Callable
from enum import Enum
from typing import Any, Optional

import structlog


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "CLOSED"  # Normal operation
    OPEN = "OPEN"  # Circuit is open, requests fail fast
    HALF_OPEN = "HALF_OPEN"  # Testing if service is recovered


class CircuitBreaker:
    """Circuit breaker implementation for fault tolerance."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: type[Exception] = Exception,
        logger: Optional[structlog.BoundLogger] = None,
    ):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Time in seconds to wait before half-opening
            expected_exception: Exception type to count as failures
            logger: Logger instance
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.logger = logger or structlog.get_logger()

        # Circuit state
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        self.last_success_time = None

        # Metrics
        self.total_requests = 0
        self.total_failures = 0
        self.total_successes = 0

    def __call__(self, func: Callable) -> Callable:
        """
        Decorator to wrap functions with circuit breaker.

        Args:
            func: Function to wrap

        Returns:
            Wrapped function
        """
        if asyncio.iscoroutinefunction(func):
            return self._async_wrapper(func)
        else:
            return self._sync_wrapper(func)

    def _sync_wrapper(self, func: Callable) -> Callable:
        """Wrap synchronous function."""

        def wrapper(*args, **kwargs):
            return self._execute(func, *args, **kwargs)

        return wrapper

    def _async_wrapper(self, func: Callable) -> Callable:
        """Wrap asynchronous function."""

        async def wrapper(*args, **kwargs):
            return await self._execute_async(func, *args, **kwargs)

        return wrapper

    def _execute(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker logic."""
        if not self._can_execute():
            raise self._get_circuit_open_exception()

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise e

    async def _execute_async(self, func: Callable, *args, **kwargs) -> Any:
        """Execute async function with circuit breaker logic."""
        if not self._can_execute():
            raise self._get_circuit_open_exception()

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise e

    def _can_execute(self) -> bool:
        """Check if execution is allowed based on circuit state."""
        self._update_state()

        if self.state == CircuitState.CLOSED:
            return True
        elif self.state == CircuitState.OPEN:
            return False
        elif self.state == CircuitState.HALF_OPEN:
            # Allow one request to test recovery
            return True

        return False

    def _update_state(self) -> None:
        """Update circuit state based on current conditions."""
        current_time = time.time()

        if self.state == CircuitState.OPEN:
            # Check if recovery timeout has passed
            if (
                self.last_failure_time
                and current_time - self.last_failure_time >= self.recovery_timeout
            ):
                self.state = CircuitState.HALF_OPEN
                self.logger.info(
                    "Circuit breaker transitioning to HALF_OPEN",
                    failure_count=self.failure_count,
                    recovery_timeout=self.recovery_timeout,
                )

        elif self.state == CircuitState.HALF_OPEN:
            # Stay in half-open until success or failure
            pass

        elif self.state == CircuitState.CLOSED:
            # Check if failure threshold exceeded
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                self.last_failure_time = current_time
                self.logger.warning(
                    "Circuit breaker opened",
                    failure_count=self.failure_count,
                    failure_threshold=self.failure_threshold,
                )

    def _on_success(self) -> None:
        """Handle successful execution."""
        self.total_requests += 1
        self.total_successes += 1
        self.last_success_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            # Success in half-open state, close circuit
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.logger.info("Circuit breaker closed after successful recovery")

        elif self.state == CircuitState.CLOSED:
            # Reset failure count on success
            self.failure_count = 0

    def _on_failure(self) -> None:
        """Handle failed execution."""
        self.total_requests += 1
        self.total_failures += 1
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            # Failure in half-open state, open circuit again
            self.state = CircuitState.OPEN
            self.logger.warning("Circuit breaker reopened after recovery failure")

        self.logger.debug(
            "Circuit breaker failure recorded",
            failure_count=self.failure_count,
            failure_threshold=self.failure_threshold,
        )

    def _get_circuit_open_exception(self) -> Exception:
        """Get exception to raise when circuit is open."""
        return CircuitBreakerOpenException(
            f"Circuit breaker is {self.state.value}. "
            f"Last failure: {self.last_failure_time}"
        )

    def get_metrics(self) -> dict:
        """Get circuit breaker metrics."""
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
            "total_requests": self.total_requests,
            "total_failures": self.total_failures,
            "total_successes": self.total_successes,
            "success_rate": (
                (self.total_successes / self.total_requests * 100)
                if self.total_requests > 0
                else 0
            ),
            "last_failure_time": self.last_failure_time,
            "last_success_time": self.last_success_time,
        }

    def reset(self) -> None:
        """Reset circuit breaker to closed state."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        self.logger.info("Circuit breaker reset to CLOSED state")

    def force_open(self) -> None:
        """Force circuit breaker to open state."""
        self.state = CircuitState.OPEN
        self.last_failure_time = time.time()
        self.logger.warning("Circuit breaker forced to OPEN state")

    def force_close(self) -> None:
        """Force circuit breaker to closed state."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.logger.info("Circuit breaker forced to CLOSED state")

    def is_open(self) -> bool:
        """Check if circuit breaker is open."""
        self._update_state()
        return self.state == CircuitState.OPEN

    def is_closed(self) -> bool:
        """Check if circuit breaker is closed."""
        self._update_state()
        return self.state == CircuitState.CLOSED

    def is_half_open(self) -> bool:
        """Check if circuit breaker is half-open."""
        self._update_state()
        return self.state == CircuitState.HALF_OPEN


class CircuitBreakerOpenException(Exception):
    """Exception raised when circuit breaker is open."""

    pass
