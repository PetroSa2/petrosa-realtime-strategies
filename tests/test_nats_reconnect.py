"""
Unit tests for strategies.utils.nats_reconnect (#185 AC1).

Covers the jittered backoff helper and the reconnect_to_server_handler
factory used by both NATSConsumer and TradeOrderPublisher to avoid a
thundering herd against NATS after a broker restart.
"""

from strategies.utils.nats_reconnect import (
    DEFAULT_BASE_RECONNECT_WAIT,
    DEFAULT_MAX_RECONNECT_WAIT,
    jittered_reconnect_delay,
    make_reconnect_handler,
)


def test_jittered_reconnect_delay_defaults_are_bounded():
    """Repeated calls with default params always stay within the jitter band."""
    base = DEFAULT_BASE_RECONNECT_WAIT
    max_delay = DEFAULT_MAX_RECONNECT_WAIT
    for _ in range(200):
        delay = jittered_reconnect_delay()
        assert 0.0 <= delay <= max_delay
        # Default jitter is +/-50% of base.
        assert base * 0.5 <= delay <= base * 1.5


def test_jittered_reconnect_delay_never_negative():
    """A base near zero must never produce a negative delay."""
    for _ in range(50):
        delay = jittered_reconnect_delay(
            base_seconds=0.1, max_seconds=30.0, jitter_fraction=5.0
        )
        assert delay >= 0.0


def test_jittered_reconnect_delay_respects_max_cap():
    """A large base must be clamped to max_seconds."""
    delay = jittered_reconnect_delay(
        base_seconds=100.0, max_seconds=10.0, jitter_fraction=0.1
    )
    assert delay <= 10.0


def test_jittered_reconnect_delay_is_randomized():
    """Successive calls should not all return the exact same value."""
    delays = {jittered_reconnect_delay() for _ in range(20)}
    assert len(delays) > 1


def test_make_reconnect_handler_uses_injected_delay_fn():
    """The handler should call the provided delay_fn and return (None, delay)."""
    handler = make_reconnect_handler(delay_fn=lambda: 4.2)
    selected, delay = handler([], object())
    assert selected is None
    assert delay == 4.2


def test_make_reconnect_handler_default_delay_fn_is_jittered():
    """Without an override, the handler falls back to a bounded jittered delay."""
    handler = make_reconnect_handler()
    selected, delay = handler([], object())
    assert selected is None
    assert 0.0 <= delay <= DEFAULT_MAX_RECONNECT_WAIT
