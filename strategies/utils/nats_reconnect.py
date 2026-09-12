"""
Shared NATS reconnect helpers: bounded jittered backoff.

Both NATSConsumer and TradeOrderPublisher connect to the same NATS
deployment and run with multiple replicas (HPA min 2 / max 5). Without
jitter, a single broker restart causes every replica to retry on the exact
same cadence (nats-py's default reconnect loop sleeps a fixed
``reconnect_time_wait`` between attempts on a single-server pool), producing
a thundering herd against the broker the moment it comes back up.

nats-py (as pinned via ``nats-py>=2.0.0``) has no built-in per-attempt time
jitter for single-server pools -- it only shuffles server *pool order*
(irrelevant when there is one server). This module fills that gap via the
client's ``reconnect_to_server_handler`` hook, which nats-py invokes before
every reconnect attempt and lets the caller override the inter-attempt
delay while leaving the client's own server-selection logic untouched.

See: PetroSa2/petrosa-realtime-strategies#185 (AC1).
"""

from __future__ import annotations

import random
from collections.abc import Callable

DEFAULT_BASE_RECONNECT_WAIT = 2.0
DEFAULT_MAX_RECONNECT_WAIT = 30.0
DEFAULT_JITTER_FRACTION = 0.5  # +/- 50% around the base wait


def jittered_reconnect_delay(
    base_seconds: float = DEFAULT_BASE_RECONNECT_WAIT,
    max_seconds: float = DEFAULT_MAX_RECONNECT_WAIT,
    jitter_fraction: float = DEFAULT_JITTER_FRACTION,
) -> float:
    """Return a bounded, randomized reconnect delay.

    Applies +/- ``jitter_fraction`` randomization around ``base_seconds``,
    then clamps the result to ``[0, max_seconds]`` so a large base value
    (or an unlucky roll) never produces an unbounded wait.

    Args:
        base_seconds: Center point of the delay before jitter.
        max_seconds: Hard upper bound on the returned delay.
        jitter_fraction: Fraction of ``base_seconds`` to randomize by, in
            both directions (e.g. 0.5 == +/-50%).

    Returns:
        A non-negative delay in seconds, never exceeding ``max_seconds``.
    """
    jitter = base_seconds * jitter_fraction
    delay = base_seconds + random.uniform(-jitter, jitter)  # nosec B311
    return max(0.0, min(delay, max_seconds))


def make_reconnect_handler(
    delay_fn: Callable[[], float] = jittered_reconnect_delay,
) -> Callable[[list, object], tuple[None, float]]:
    """Build a nats-py ``reconnect_to_server_handler`` callback.

    nats-py invokes the handler as
    ``handler(server_snapshot, server_info) -> (selected_server, delay_seconds)``
    immediately before each reconnect attempt. Returning ``None`` for the
    selected server keeps nats-py's own default selection (first eligible
    server in the pool) -- this handler exists purely to inject a jittered
    delay in place of the library's fixed ``reconnect_time_wait``.

    Args:
        delay_fn: Zero-arg callable returning the delay in seconds to use
            for this attempt. Defaults to :func:`jittered_reconnect_delay`.

    Returns:
        A callable suitable for the ``reconnect_to_server_handler``
        connect() kwarg.
    """

    def _handler(server_snapshot: list, server_info: object) -> tuple[None, float]:
        return None, delay_fn()

    return _handler
