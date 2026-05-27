"""Realtime-strategies health evaluator (P2.7, petrosa_k8s#697 AC3 / #175).

Emits ``evaluator.realtime-strategies.verdict`` via the shared P2.1 framework
(:mod:`petrosa_otel.evaluators`) so the operator dashboard's evaluator strip
counts realtime-strategies among the reporting subsystems (FR17 / FR23 / FR32).

The verdict combines three health signals sampled from the running NATS
consumer + trade-order publisher on each emit tick:

1. **NATS subscribe lag** — inbound market-data message rate. When the consumer
   is connected and a message baseline has been established, a tick with zero
   new messages signals that the subscription has stalled (no market data
   flowing) even though the connection is up.
2. **Signal-emission rate vs baseline** — outbound signal rate (publisher
   ``signal_count``). Once a meaningful emission baseline exists, a collapse to
   a small fraction of it means the strategy pipeline stopped producing signals
   while data kept arriving.
3. **Strategy-error rate** — the increase in combined consumer + publisher
   ``error_count`` over one emit interval. A burst of errors means message
   processing or publishing is failing.

Verdict vocabulary is the framework's locked three-state contract
(``healthy`` / ``unhealthy`` / ``unknown``); there is no separate ``degraded``
state, so any breached signal maps to ``unhealthy`` and the reason string names
which signal tripped (NFR-O5 verbatim render).

Hysteresis / cadence (AC4 / AC7, FR18 per-evaluator ``decision_window``): emits
every ``EMIT_INTERVAL_S`` (15s) and, via ``ConsecutiveSamplesHysteresis(n=3)``,
only flips the published verdict after 3 consecutive matching samples (~45s
decision window). Signals are bursty (market data is continuous but signals are
sporadic), so smoothing avoids flapping while a sustained stall surfaces within
~45s.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any

try:
    from datetime import UTC
except ImportError:  # pragma: no cover - py310 compatibility
    from datetime import timezone

    UTC = timezone.utc  # noqa: UP017

from petrosa_otel.evaluators import (
    ConsecutiveSamplesHysteresis,
    Evaluator,
    NatsVerdictPublisher,
)

if TYPE_CHECKING:
    from petrosa_otel.evaluators.base import HysteresisPolicy
    from petrosa_otel.evaluators.publisher import VerdictPublisher

logger = logging.getLogger(__name__)

SUBSYSTEM = "realtime-strategies"

# Cadence + smoothing (documented per AC4 / AC7).
EMIT_INTERVAL_S = 15.0
HYSTERESIS_SAMPLES = 3

# Strategy-error rate: 5+ new errors inside one emit interval is a sustained
# failure rather than a single transient parse/processing error.
DEFAULT_ERROR_RATE_THRESHOLD = 5
# Signal-emission collapse: once a baseline is established, dropping below 10%
# of the rolling-mean emission rate means the strategy pipeline stalled.
DEFAULT_SIGNAL_COLLAPSE_RATIO = 0.1
# Minimum baseline emission rate (signals/s) before the collapse check may
# trip. Signals are naturally sporadic, so a near-zero baseline never trips.
DEFAULT_MIN_SIGNAL_RATE = 0.02
# Rolling baseline windows (8 samples ≈ 2 min at 15s).
DEFAULT_BASELINE_WINDOW = 8
DEFAULT_MIN_BASELINE_SAMPLES = 4


class RealtimeStrategiesHealthEvaluator(Evaluator):
    """Subsystem evaluator for realtime-strategies consume→signal health."""

    def __init__(
        self,
        *,
        metrics_source: Callable[[], dict[str, Any]],
        publisher: VerdictPublisher | None = None,
        hysteresis: HysteresisPolicy | None = None,
        error_rate_threshold: int = DEFAULT_ERROR_RATE_THRESHOLD,
        signal_collapse_ratio: float = DEFAULT_SIGNAL_COLLAPSE_RATIO,
        min_signal_rate: float = DEFAULT_MIN_SIGNAL_RATE,
        baseline_window: int = DEFAULT_BASELINE_WINDOW,
        min_baseline_samples: int = DEFAULT_MIN_BASELINE_SAMPLES,
        emit_interval_s: float = EMIT_INTERVAL_S,
        time_source: Callable[[], datetime] | None = None,
    ) -> None:
        super().__init__(
            subsystem=SUBSYSTEM,
            publisher=publisher,
            hysteresis=hysteresis or ConsecutiveSamplesHysteresis(n=HYSTERESIS_SAMPLES),
        )
        self._metrics_source = metrics_source
        self._error_rate_threshold = error_rate_threshold
        self._signal_collapse_ratio = signal_collapse_ratio
        self._min_signal_rate = min_signal_rate
        self._min_baseline_samples = max(1, min_baseline_samples)
        self._emit_interval_s = emit_interval_s
        self._time = time_source or (lambda: datetime.now(UTC))

        self._msg_baseline: deque[float] = deque(maxlen=max(1, baseline_window))
        self._signal_baseline: deque[float] = deque(maxlen=max(1, baseline_window))
        self._prev_messages: int | None = None
        self._prev_signals: int = 0
        self._prev_errors: int = 0
        self._prev_sample_at: datetime | None = None

        self._emit_task: asyncio.Task[Any] | None = None

    # ----- lifecycle -----

    async def start(self) -> None:
        """Start the periodic emit loop (idempotent)."""
        if self._emit_task is not None:
            return
        self._emit_task = asyncio.create_task(self._emit_loop())
        logger.info(
            "realtime_strategies_health_evaluator_started",
            extra={"subsystem": SUBSYSTEM, "emit_interval_s": self._emit_interval_s},
        )

    async def stop(self) -> None:
        """Stop the emit loop."""
        if self._emit_task is None:
            return
        self._emit_task.cancel()
        try:
            await self._emit_task
        except asyncio.CancelledError:
            pass
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"realtime_strategies_health_evaluator stop error: {exc}")
        self._emit_task = None

    async def _emit_loop(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception as exc:  # noqa: BLE001 — never crash the loop
                logger.warning(
                    "realtime_strategies_health_evaluator_tick_failed",
                    extra={"error": str(exc)},
                )
            await asyncio.sleep(self._emit_interval_s)

    # ----- framework hook -----

    async def evaluate(self) -> tuple[str, str]:
        """Compute the raw ``(verdict, reason)`` sample for the current state."""
        snapshot = self._metrics_source()
        now = self._time()

        messages = int(snapshot.get("message_count", 0) or 0)
        signals = int(snapshot.get("signal_count", 0) or 0)
        errors = int(snapshot.get("error_count", 0) or 0)
        consumer_connected = bool(snapshot.get("consumer_connected"))
        publisher_connected = bool(snapshot.get("publisher_connected"))

        prev_messages = self._prev_messages
        prev_signals = self._prev_signals
        prev_errors = self._prev_errors
        prev_at = self._prev_sample_at

        self._prev_messages = messages
        self._prev_signals = signals
        self._prev_errors = errors
        self._prev_sample_at = now

        if prev_messages is None or prev_at is None:
            return "unknown", "establishing baseline (first sample)"

        if messages < prev_messages or signals < prev_signals or errors < prev_errors:
            self._msg_baseline.clear()
            self._signal_baseline.clear()
            return "unknown", "counter reset detected; rebaselining"

        # 1) Connectivity is the dominant signal.
        if not consumer_connected:
            return "unhealthy", "NATS consumer disconnected; not receiving market data"
        if not publisher_connected:
            return "unhealthy", "NATS publisher disconnected; cannot emit signals"

        # 2) Strategy-error rate.
        error_delta = errors - prev_errors
        if error_delta >= self._error_rate_threshold:
            return (
                "unhealthy",
                f"strategy errors: {error_delta} in last {int(self._emit_interval_s)}s",
            )

        interval_s = (now - prev_at).total_seconds()
        msg_rate = (messages - prev_messages) / interval_s if interval_s > 0 else 0.0
        signal_rate = (signals - prev_signals) / interval_s if interval_s > 0 else 0.0

        # 3) NATS subscribe lag — inbound messages stalled while connected.
        if len(self._msg_baseline) >= self._min_baseline_samples and self._msg_baseline:
            msg_baseline_mean = sum(self._msg_baseline) / len(self._msg_baseline)
            if msg_baseline_mean > 0 and msg_rate == 0:
                self._msg_baseline.append(msg_rate)
                return (
                    "unhealthy",
                    f"subscribe lag: 0 msg/s vs baseline "
                    f"{msg_baseline_mean:.1f} msg/s — subscription stalled",
                )
        self._msg_baseline.append(msg_rate)

        # 4) Signal-emission rate vs baseline.
        if (
            len(self._signal_baseline) >= self._min_baseline_samples
            and self._signal_baseline
        ):
            sig_baseline_mean = sum(self._signal_baseline) / len(self._signal_baseline)
            if (
                sig_baseline_mean >= self._min_signal_rate
                and signal_rate < self._signal_collapse_ratio * sig_baseline_mean
            ):
                self._signal_baseline.append(signal_rate)
                return (
                    "unhealthy",
                    f"signal emission collapsed: {signal_rate:.2f}/s vs baseline "
                    f"{sig_baseline_mean:.2f}/s",
                )
        self._signal_baseline.append(signal_rate)

        return (
            "healthy",
            f"{msg_rate:.1f} msg/s in, {signal_rate:.2f} signals/s out, "
            f"errors {error_delta}",
        )


def build_realtime_strategies_health_evaluator(
    consumer: Any,
    publisher: Any,
) -> RealtimeStrategiesHealthEvaluator | None:
    """Construct an evaluator sourcing from ``consumer`` + ``publisher``.

    Publishes verdicts on the publisher's NATS connection. Returns ``None`` if
    the publisher has no live NATS client yet. Call after both are started.
    """
    nats_client = getattr(publisher, "nats_client", None)
    if nats_client is None:
        logger.warning(
            "realtime_strategies_health_evaluator not started: no NATS client"
        )
        return None

    def _snapshot() -> dict[str, Any]:
        c_client = getattr(consumer, "nats_client", None)
        p_client = getattr(publisher, "nats_client", None)
        return {
            "consumer_connected": bool(c_client and c_client.is_connected),
            "publisher_connected": bool(p_client and p_client.is_connected),
            "message_count": getattr(consumer, "message_count", 0),
            "signal_count": getattr(publisher, "signal_count", 0),
            "error_count": getattr(consumer, "error_count", 0)
            + getattr(publisher, "error_count", 0),
        }

    publisher_obj = NatsVerdictPublisher(nats_client=nats_client)
    return RealtimeStrategiesHealthEvaluator(
        metrics_source=_snapshot,
        publisher=publisher_obj,
    )
