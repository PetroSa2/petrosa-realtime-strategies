"""Realtime-strategies subsystem evaluator (P2.7, petrosa_k8s#697 AC3 / #175).

Adopts the shared `petrosa_otel.evaluators` framework (P2.1) so
realtime-strategies publishes a structured health verdict on
``evaluator.realtime-strategies.verdict``, closing one of the five
"silent service" gaps that keep FR17 / FR23 / FR32 at YELLOW.
"""

from strategies.evaluators.health_evaluator import (
    RealtimeStrategiesHealthEvaluator,
    build_realtime_strategies_health_evaluator,
)

__all__ = [
    "RealtimeStrategiesHealthEvaluator",
    "build_realtime_strategies_health_evaluator",
]
