"""
Tests for strategies/utils/circuit_breaker.py.
"""

import asyncio
import time

import pytest

from strategies.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenException,
    CircuitState,
)


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
        result1 = test_func()
        result2 = test_func()
        assert result1 == "success"  # Should succeed
        assert result2 == "success"  # Should succeed
        try:
            test_func(should_fail=True)
        except ValueError:
            # Expected: test_func raises ValueError when should_fail=True
            assert True  # Exception was raised as expected

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


class TestCircuitBreakerStateTransitions:
    """Test circuit breaker state transitions and edge cases."""

    def test_circuit_opens_on_threshold(self):
        """Test circuit opens when failure threshold is exceeded."""
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=1)

        @cb
        def failing_func():
            raise ValueError("Error")

        # Trigger failures up to threshold
        for i in range(3):
            with pytest.raises(ValueError):
                failing_func()
            assert cb.failure_count == i + 1

        # Circuit should be open after threshold is reached
        # Next call should be blocked
        with pytest.raises(CircuitBreakerOpenException):
            failing_func()

        assert cb.state == CircuitState.OPEN
        assert cb.failure_count == 3

    def test_circuit_blocks_execution_when_open(self):
        """Test circuit blocks execution when open."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1)

        @cb
        def failing_func():
            raise ValueError("Error")

        # Open circuit
        for _ in range(2):
            with pytest.raises(ValueError) as exc_info:
                failing_func()
            assert exc_info.value is not None  # Exception should be raised

        # Circuit should be open now
        with pytest.raises(CircuitBreakerOpenException) as exc_info:
            failing_func()
        assert exc_info.value is not None  # Circuit should be open

        # Even a successful function should be blocked
        @cb
        def successful_func():
            return "success"

        with pytest.raises(CircuitBreakerOpenException):
            successful_func()

    def test_half_open_state_transition(self):
        """Test circuit transitions to half-open after recovery timeout."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)

        @cb
        def failing_func():
            raise ValueError("Error")

        # Open circuit (2 failures opens it)
        for _ in range(2):
            with pytest.raises(ValueError):
                failing_func()

        # Force state update to ensure circuit is open
        cb._update_state()
        assert cb.state == CircuitState.OPEN

        # Wait for recovery timeout
        time.sleep(0.15)

        # Update state (should transition to half-open)
        cb._update_state()
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_success_closes_circuit(self):
        """Test successful call in half-open state closes circuit."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)

        @cb
        def func(should_fail=False):
            if should_fail:
                raise ValueError("Error")
            return "success"

        # Open circuit (2 failures opens it)
        for _ in range(2):
            with pytest.raises(ValueError):
                func(should_fail=True)

        # Verify circuit is open
        cb._update_state()
        assert cb.state == CircuitState.OPEN

        # Wait for recovery timeout
        time.sleep(0.15)

        # Manually transition to half-open state (check recovery timeout)
        cb._update_state()
        assert cb.state == CircuitState.HALF_OPEN

        # Success in half-open should close circuit
        result = func(should_fail=False)
        assert result == "success"
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_half_open_failure_reopens_circuit(self):
        """Test failure in half-open state reopens circuit."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)

        @cb
        def failing_func():
            raise ValueError("Error")

        # Open circuit (2 failures opens it)
        for _ in range(2):
            with pytest.raises(ValueError):
                failing_func()

        # Verify circuit is open
        cb._update_state()
        assert cb.state == CircuitState.OPEN

        # Wait for recovery timeout
        time.sleep(0.15)

        # Manually transition to half-open state
        cb._update_state()
        assert cb.state == CircuitState.HALF_OPEN

        # Failure in half-open should reopen circuit
        with pytest.raises(ValueError):
            failing_func()

        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_async_circuit_opens_on_threshold(self):
        """Test async circuit opens when threshold exceeded."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1)

        @cb
        async def async_failing_func():
            raise ValueError("Error")

        # Open circuit
        for _ in range(2):
            with pytest.raises(ValueError):
                await async_failing_func()

        # Should be blocked now
        with pytest.raises(CircuitBreakerOpenException):
            await async_failing_func()

    def test_reset_method(self):
        """Test reset method closes circuit."""
        cb = CircuitBreaker(failure_threshold=2)

        @cb
        def failing_func():
            raise ValueError("Error")

        # Open circuit (2 failures opens it)
        for _ in range(2):
            with pytest.raises(ValueError):
                failing_func()

        # Verify circuit is open (check after state update)
        cb._update_state()
        assert cb.state == CircuitState.OPEN

        # Reset should close circuit
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb.last_failure_time is None

    def test_force_open(self):
        """Test force_open method."""
        cb = CircuitBreaker()

        assert cb.state == CircuitState.CLOSED

        cb.force_open()
        assert cb.state == CircuitState.OPEN
        assert cb.last_failure_time is not None

    def test_force_close(self):
        """Test force_close method."""
        cb = CircuitBreaker(failure_threshold=2)

        @cb
        def failing_func():
            raise ValueError("Error")

        # Open circuit (2 failures opens it)
        for _ in range(2):
            with pytest.raises(ValueError):
                failing_func()

        # Verify circuit is open (check after state update)
        cb._update_state()
        assert cb.state == CircuitState.OPEN

        # Force close
        cb.force_close()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_is_open_method(self):
        """Test is_open method."""
        cb = CircuitBreaker(failure_threshold=2)

        assert not cb.is_open()

        @cb
        def failing_func():
            raise ValueError("Error")

        # Open circuit
        for _ in range(2):
            with pytest.raises(ValueError):
                failing_func()

        assert cb.is_open()

    def test_is_closed_method(self):
        """Test is_closed method."""
        cb = CircuitBreaker()

        assert cb.is_closed()

        cb.force_open()
        assert not cb.is_closed()

        cb.force_close()
        assert cb.is_closed()

    def test_is_half_open_method(self):
        """Test is_half_open method."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)

        @cb
        def failing_func():
            raise ValueError("Error")

        # Open circuit
        for _ in range(2):
            with pytest.raises(ValueError):
                failing_func()

        assert not cb.is_half_open()

        # Wait for recovery timeout
        time.sleep(0.15)
        assert cb.is_half_open()

    def test_metrics_with_zero_requests(self):
        """Test metrics when no requests have been made."""
        cb = CircuitBreaker()

        metrics = cb.get_metrics()
        assert metrics["total_requests"] == 0
        assert metrics["total_failures"] == 0
        assert metrics["total_successes"] == 0
        assert metrics["success_rate"] == 0

    def test_metrics_success_rate_calculation(self):
        """Test metrics success rate calculation."""
        cb = CircuitBreaker()

        @cb
        def test_func(should_fail=False):
            if should_fail:
                raise ValueError("Error")
            return "success"

        # 3 successes, 1 failure
        result1 = test_func()
        result2 = test_func()
        result3 = test_func()
        assert result1 == "success"  # Should succeed
        assert result2 == "success"  # Should succeed
        assert result3 == "success"  # Should succeed
        try:
            test_func(should_fail=True)
        except ValueError:
            # Expected: test_func raises ValueError when should_fail=True
            assert True  # Exception was raised as expected

        metrics = cb.get_metrics()
        assert metrics is not None  # Metrics should be returned
        assert metrics["total_requests"] == 4
        assert metrics["total_successes"] == 3
        assert metrics["total_failures"] == 1
        assert metrics["success_rate"] == 75.0

    def test_can_execute_when_closed(self):
        """Test _can_execute returns True when closed."""
        cb = CircuitBreaker()

        assert cb._can_execute()

    def test_can_execute_when_open(self):
        """Test _can_execute returns False when open."""
        cb = CircuitBreaker(failure_threshold=2)

        @cb
        def failing_func():
            raise ValueError("Error")

        # Open circuit
        for _ in range(2):
            with pytest.raises(ValueError):
                failing_func()

        assert not cb._can_execute()

    def test_can_execute_when_half_open(self):
        """Test _can_execute returns True when half-open."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)

        @cb
        def failing_func():
            raise ValueError("Error")

        # Open circuit (2 failures opens it)
        for _ in range(2):
            with pytest.raises(ValueError):
                failing_func()

        # Verify circuit is open
        cb._update_state()
        assert cb.state == CircuitState.OPEN

        # Wait for recovery timeout
        time.sleep(0.15)

        # _can_execute updates state automatically and should allow execution in half-open
        can_execute = cb._can_execute()
        assert can_execute
        assert cb.state == CircuitState.HALF_OPEN


