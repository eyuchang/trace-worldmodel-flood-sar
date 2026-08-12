"""Typed Reference scenario domain contracts."""

from .events import (
    ReferenceEvent,
    ReferenceEventType,
    ReferenceEventVisibility,
    ReferenceRuntimeCheckpoint,
)
from .exposure import (
    ReferenceExposureParameters,
    ReferenceExposureScenario,
    ReferenceSyntheticPerson,
    ReferenceSyntheticStructure,
    ReferenceTrajectoryChangePoint,
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
    "ReferenceExposureParameters",
    "ReferenceExposureScenario",
    "ReferenceGaugeStageSample",
    "ReferencePhysicalParameters",
    "ReferencePhysicalSample",
    "ReferencePhysicalScenario",
    "ReferenceRuntimeCheckpoint",
    "ReferenceSyntheticPerson",
    "ReferenceSyntheticStructure",
    "ReferenceTrajectoryChangePoint",
    "ReferenceWeatherSample",
]
