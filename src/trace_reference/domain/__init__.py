"""Typed Reference scenario domain contracts."""

from .events import (
    ReferenceEvent,
    ReferenceEventType,
    ReferenceEventVisibility,
    ReferenceRuntimeCheckpoint,
)
from .physical import (
    ReferenceBreachSample,
    ReferenceCrossingStateSample,
    ReferenceGaugeStageSample,
    ReferencePhysicalParameters,
    ReferencePhysicalSample,
    ReferencePhysicalScenario,
    ReferenceWeatherSample,
)

__all__ = [
    "ReferenceBreachSample",
    "ReferenceCrossingStateSample",
    "ReferenceEvent",
    "ReferenceEventType",
    "ReferenceEventVisibility",
    "ReferenceGaugeStageSample",
    "ReferencePhysicalParameters",
    "ReferencePhysicalSample",
    "ReferencePhysicalScenario",
    "ReferenceRuntimeCheckpoint",
    "ReferenceWeatherSample",
]
