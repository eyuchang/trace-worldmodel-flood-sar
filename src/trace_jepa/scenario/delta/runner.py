"""Compatibility facade for the modular Delta mission runtime."""

from trace_jepa.scenario.delta.runtime.capacity import evaluate_capacity_windows
from trace_jepa.scenario.delta.runtime.mission import run_delta_small
from trace_jepa.scenario.delta.runtime.models import (
    DeltaDecisionEvent,
    DeltaResourceOutcome,
    DeltaRunResult,
    DemandWindow,
)

__all__ = [
    "DeltaDecisionEvent",
    "DeltaResourceOutcome",
    "DeltaRunResult",
    "DemandWindow",
    "evaluate_capacity_windows",
    "run_delta_small",
]
