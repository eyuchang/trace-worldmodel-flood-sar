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
from .truth import (
    ReferenceIncidentCandidateAudit,
    ReferenceIncidentType,
    ReferenceTruthIncident,
    ReferenceTruthScenario,
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
    "ReferenceIncidentCandidateAudit",
    "ReferenceIncidentType",
    "ReferencePhysicalParameters",
    "ReferencePhysicalSample",
    "ReferencePhysicalScenario",
    "ReferenceRuntimeCheckpoint",
    "ReferenceSyntheticPerson",
    "ReferenceSyntheticStructure",
    "ReferenceTrajectoryChangePoint",
    "ReferenceTruthIncident",
    "ReferenceTruthScenario",
    "ReferenceWeatherSample",
]
