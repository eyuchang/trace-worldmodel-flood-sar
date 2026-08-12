"""Lightweight aggregate references for the generated Reference scenario."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import Field

from trace_jepa.scenario.delta.domain.base import DeltaModel
from trace_reference.geography import ReferenceGeographyCatalog
from trace_reference.models import ReferenceGovernanceRegistry, ReferenceScenarioConfig

from .coordination import ReferenceCoordinationArtifacts
from .exposure import ReferenceExposureScenario
from .observations import ReferenceObservationArtifacts
from .physical import ReferencePhysicalScenario
from .resources import ReferenceResourceArtifacts
from .truth import ReferenceTruthScenario


class ReferencePriorProfile(DeltaModel):
    schema_version: Literal["delta-reference-prior-profile-v1"]
    profile_id: Literal["reference-prior-pi-v1"]
    calibration_version: Literal["toy-calibration-v1"]
    prior_accuracy_milli: int = Field(ge=300, le=1_000)
    pi_micros: int = Field(ge=300_000, le=1_000_000)


@dataclass(frozen=True)
class ReferenceScenarioArtifacts:
    """References existing immutable stages without copying their large collections."""

    config: ReferenceScenarioConfig
    geography: ReferenceGeographyCatalog
    governance: ReferenceGovernanceRegistry
    physical: ReferencePhysicalScenario
    exposure: ReferenceExposureScenario
    truth: ReferenceTruthScenario
    observations: ReferenceObservationArtifacts
    resources: ReferenceResourceArtifacts
    coordination: ReferenceCoordinationArtifacts
    prior: ReferencePriorProfile
