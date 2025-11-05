"""
Tests for strategies/utils/circuit_breaker.py.
"""

import asyncio
import time

import pytest

from strategies.utils.circuit_breaker import CircuitBreaker, CircuitState


class TestCircuitBreakerBasics:
    """Test circuit breaker basic functionality."""

    def test_init(self):
        """Test circuit breaker initialization."""
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30)

        assert cb.failure_threshold == 3
        assert cb.recovery_timeout == 30
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb.total_requests == 0

    def test_successful_call(self):
        """Test successful function call."""
        cb = CircuitBreaker()

        @cb
        def successful_func():
            return "success"

        result = successful_func()

        assert result == "success"
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb.total_successes == 1

    def test_single_failure(self):
        """Test single function failure."""
        cb = CircuitBreaker(failure_threshold=5)

        @cb
        def failing_func():
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            failing_func()

        assert cb.state == CircuitState.CLOSED  # Still closed
        assert cb.failure_count == 1
        assert cb.total_failures == 1

    def test_failure_count_tracking(self):
        """Test failure count increments."""
        cb = CircuitBreaker(failure_threshold=5)

        @cb
        def failing_func():
            raise ValueError("Test error")

        # Trigger failures
        for i in range(3):
            with pytest.raises(ValueError):
                failing_func()
            assert cb.failure_count == i + 1

        assert cb.total_failures == 3

    def test_reset_on_success(self):
        """Test circuit resets failure count on success."""
        cb = CircuitBreaker(failure_threshold=5)

        @cb
        def sometimes_failing_func(should_fail=False):
            if should_fail:
                raise ValueError("Error")
            return "success"

        # Some failures
        with pytest.raises(ValueError):
            sometimes_failing_func(should_fail=True)

        assert cb.failure_count == 1

        # Success resets
        result = sometimes_failing_func(should_fail=False)

        assert result == "success"
        assert cb.failure_count == 0

    @pytest.mark.asyncio
    async def test_async_successful_call(self):
        """Test successful async function call."""
        cb = CircuitBreaker()

        @cb
        async def async_successful_func():
            await asyncio.sleep(0.01)
            return "async success"

        result = await async_successful_func()

        assert result == "async success"
        assert cb.state == CircuitState.CLOSED
        assert cb.total_successes == 1

    @pytest.mark.asyncio
    async def test_async_failure(self):
        """Test async function failure."""
        cb = CircuitBreaker(failure_threshold=5)

        @cb
        async def async_failing_func():
            await asyncio.sleep(0.01)
            raise ValueError("Async error")

        with pytest.raises(ValueError):
            await async_failing_func()

        assert cb.failure_count == 1
        assert cb.total_failures == 1

    @pytest.mark.asyncio
    async def test_async_failure_tracking(self):
        """Test async failure tracking."""
        cb = CircuitBreaker(failure_threshold=5)

        @cb
        async def async_failing_func():
            raise ValueError("Error")

        # Trigger failures
        for i in range(3):
            with pytest.raises(ValueError):
                await async_failing_func()
            assert cb.failure_count == i + 1

        assert cb.total_failures == 3

    def test_metrics(self):
        """Test circuit breaker metrics."""
        cb = CircuitBreaker()

        @cb
        def test_func(should_fail=False):
            if should_fail:
                raise ValueError("Error")
            return "success"

        # Mixed operations
        test_func()
        test_func()
        try:
            test_func(should_fail=True)
        except ValueError:
            pass

        assert cb.total_requests == 3
        assert cb.total_successes == 2
        assert cb.total_failures == 1


class TestCircuitBreakerEdgeCases:
    """Test circuit breaker edge cases."""

    def test_different_exception_types(self):
        """Test circuit breaker with different exception types."""
        cb = CircuitBreaker(expected_exception=ValueError, failure_threshold=3)

        @cb
        def func_with_different_errors(error_type=None):
            if error_type == "value":
                raise ValueError("Value error")
            elif error_type == "type":
                raise TypeError("Type error")
            return "success"

        # ValueError should count
        with pytest.raises(ValueError):
            func_with_different_errors(error_type="value")

        assert cb.failure_count == 1

        # TypeError should propagate but might not count
        with pytest.raises(TypeError):
            func_with_different_errors(error_type="type")

    def test_multiple_failures_and_recovery(self):
        """Test multiple failures followed by recovery."""
        cb = CircuitBreaker(failure_threshold=10)

        @cb
        def func(should_fail=False):
            if should_fail:
                raise ValueError("Error")
            return "success"

        # Multiple failures
        for _ in range(3):
            with pytest.raises(ValueError):
                func(should_fail=True)

        assert cb.failure_count == 3
        
        # Success resets
        result = func(should_fail=False)
        assert result == "success"
        assert cb.failure_count == 0

