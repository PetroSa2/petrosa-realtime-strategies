"""Unit tests for RealtimeStrategiesHealthEvaluator (#175, P2.7 AC3)."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from petrosa_otel.evaluators import ConsecutiveSamplesHysteresis
from petrosa_otel.evaluators.publisher import (
    EVALUATOR_SUBJECT_TEMPLATE,
    NatsVerdictPublisher,
)

from strategies.evaluators import (
    RealtimeStrategiesHealthEvaluator,
    build_realtime_strategies_health_evaluator,
)


class FakeClock:
    def __init__(self, start: datetime, step: timedelta) -> None:
        self._t = start
        self._step = step

    def __call__(self) -> datetime:
        now = self._t
        self._t = self._t + self._step
        return now


class MetricsSource:
    def __init__(self) -> None:
        self.snap = {
            "message_count": 0,
            "signal_count": 0,
            "error_count": 0,
            "consumer_connected": True,
            "publisher_connected": True,
        }

    def __call__(self) -> dict:
        return dict(self.snap)


class FakeNats:
    def __init__(self) -> None:
        self.messages: list[tuple[str, bytes]] = []

    async def publish(self, subject: str, payload: bytes) -> None:
        self.messages.append((subject, payload))


def _make(source, clock, *, publisher=None, n: int = 1):
    return RealtimeStrategiesHealthEvaluator(
        metrics_source=source,
        publisher=publisher,
        hysteresis=ConsecutiveSamplesHysteresis(n=n),
        time_source=clock,
    )


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(datetime(2026, 5, 27, 12, 0, 0, tzinfo=UTC), timedelta(seconds=15))


@pytest.mark.asyncio
async def test_first_sample_is_unknown(clock):
    ev = _make(MetricsSource(), clock)
    verdict, reason = await ev.evaluate()
    assert verdict == "unknown"
    assert "baseline" in reason.lower()


@pytest.mark.asyncio
async def test_healthy_when_connected_and_flowing(clock):
    src = MetricsSource()
    ev = _make(src, clock)
    await ev.evaluate()
    src.snap["message_count"] = 1500
    src.snap["signal_count"] = 2
    verdict, reason = await ev.evaluate()
    assert verdict == "healthy"
    assert "msg/s" in reason


@pytest.mark.asyncio
async def test_unhealthy_when_consumer_disconnected(clock):
    src = MetricsSource()
    ev = _make(src, clock)
    await ev.evaluate()
    src.snap["consumer_connected"] = False
    verdict, reason = await ev.evaluate()
    assert verdict == "unhealthy"
    assert "consumer" in reason.lower()


@pytest.mark.asyncio
async def test_unhealthy_when_publisher_disconnected(clock):
    src = MetricsSource()
    ev = _make(src, clock)
    await ev.evaluate()
    src.snap["publisher_connected"] = False
    verdict, reason = await ev.evaluate()
    assert verdict == "unhealthy"
    assert "publisher" in reason.lower()


@pytest.mark.asyncio
async def test_unhealthy_on_error_burst(clock):
    src = MetricsSource()
    ev = _make(src, clock)
    await ev.evaluate()
    src.snap["error_count"] = 6  # >= threshold (5) in one interval
    verdict, reason = await ev.evaluate()
    assert verdict == "unhealthy"
    assert "error" in reason.lower()


@pytest.mark.asyncio
async def test_unhealthy_on_subscribe_lag(clock):
    src = MetricsSource()
    ev = _make(src, clock)
    await ev.evaluate()  # prime
    messages = 0
    for _ in range(4):
        messages += 1500
        src.snap["message_count"] = messages
        verdict, _ = await ev.evaluate()
        assert verdict == "healthy"
    # Inbound messages stall (no new messages) while still connected.
    src.snap["message_count"] = messages
    verdict, reason = await ev.evaluate()
    assert verdict == "unhealthy"
    assert "subscribe lag" in reason


@pytest.mark.asyncio
async def test_unhealthy_on_signal_collapse(clock):
    src = MetricsSource()
    ev = _make(src, clock)
    await ev.evaluate()  # prime
    messages = 0
    signals = 0
    for _ in range(4):
        messages += 1500
        signals += 1  # ~0.067 signals/s baseline
        src.snap["message_count"] = messages
        src.snap["signal_count"] = signals
        verdict, _ = await ev.evaluate()
        assert verdict == "healthy"
    # Messages keep flowing but signals stop entirely.
    messages += 1500
    src.snap["message_count"] = messages  # signal_count unchanged
    verdict, reason = await ev.evaluate()
    assert verdict == "unhealthy"
    assert "signal emission collapsed" in reason


@pytest.mark.asyncio
async def test_counter_reset_returns_unknown(clock):
    src = MetricsSource()
    ev = _make(src, clock)
    src.snap["message_count"] = 9000
    await ev.evaluate()
    src.snap["message_count"] = 5  # pod restart
    verdict, reason = await ev.evaluate()
    assert verdict == "unknown"
    assert "reset" in reason.lower()


@pytest.mark.asyncio
async def test_publishes_on_realtime_strategies_subject(clock):
    src = MetricsSource()
    nats = FakeNats()
    publisher = NatsVerdictPublisher(nats_client=nats)
    ev = _make(src, clock, publisher=publisher, n=1)

    await ev.tick()  # unknown baseline
    src.snap["message_count"] = 1500
    await ev.tick()  # healthy

    assert nats.messages, "evaluator did not publish"
    subject, payload = nats.messages[-1]
    assert subject == "evaluator.realtime-strategies.verdict"
    assert subject == EVALUATOR_SUBJECT_TEMPLATE.format(subsystem="realtime-strategies")
    body = json.loads(payload.decode())
    assert body["subsystem"] == "realtime-strategies"
    assert body["verdict"] == "healthy"


@pytest.mark.asyncio
async def test_hysteresis_suppresses_single_flap(clock):
    src = MetricsSource()
    ev = _make(src, clock, n=3)

    await ev.tick()  # unknown baseline
    messages = 0
    for _ in range(3):
        messages += 1500
        src.snap["message_count"] = messages
        v = await ev.tick()
    assert v.verdict == "healthy"

    # One disconnected sample must NOT flip the committed verdict (n=3).
    src.snap["consumer_connected"] = False
    v = await ev.tick()
    assert v.verdict == "healthy"


def test_build_returns_none_without_nats():
    class _Pub:
        nats_client = None

    class _Con:
        nats_client = None

    assert build_realtime_strategies_health_evaluator(_Con(), _Pub()) is None
