"""Causal latent-incident contracts for WF-DFLD-01-REFERENCE."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import Field, model_validator

from trace_jepa.scenario.delta.domain.base import DeltaModel


class ReferenceIncidentType(str, Enum):
    STRANDED_STRUCTURE = "stranded_structure"
    VEHICLE_RESCUE = "vehicle_rescue"
    LEVEE_INSPECTION = "levee_inspection"
    MEDICAL_ACCESS = "medical_access"
    WELFARE_CHECK = "welfare_check"
    MISSING_PERSON = "missing_person"
    ANIMAL_RESCUE = "animal_rescue"
    INFORMATION_NEED = "information_need"
    HAZARD_RESPONSE = "hazard_response"


class ReferenceServiceRequirement(DeltaModel):
    capability: Literal[
        "water-rescue",
        "road-rescue",
        "levee-inspection",
        "medical-transport",
        "welfare-check",
        "missing-person-search",
        "animal-rescue",
        "public-information",
        "hazard-control",
    ]
    service_units: int = Field(ge=1, le=8)
    deterministic_service_duration_s: int = Field(ge=900, le=43_200)


class ReferenceIncidentCandidateAttempt(DeltaModel):
    candidate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    at_s: int = Field(ge=-172_800, le=345_300)
    probability_micros: int = Field(ge=0, le=1_000_000)
    draw_micros: int = Field(ge=0, lt=1_000_000)
    disposition: Literal["draw-rejected", "accepted-new-episode"]


class ReferenceIncidentCandidateAudit(DeltaModel):
    """One eligible causal episode and its bounded keyed candidate history."""

    incident_type: ReferenceIncidentType
    episode_key: str = Field(min_length=12)
    anchor_id: str = Field(min_length=8)
    eligible_start_s: int = Field(ge=-172_800, le=345_300)
    eligible_end_s: int = Field(gt=-172_800, le=345_600)
    subject_count_at_start: int = Field(ge=0)
    attempt_count: int = Field(ge=1)
    rejected_attempt_count: int = Field(ge=0)
    attempt_trace_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    representative_attempt: ReferenceIncidentCandidateAttempt
    accepted_truth_incident_id: str | None = Field(default=None, pattern=r"^RI-[0-9a-f]{16}$")
    suppressed_eligible_ticks: int = Field(ge=0)
    suppression_reason: (
        Literal["eligible state and affected subject set persisted after incident acceptance"]
        | None
    ) = None

    @model_validator(mode="after")
    def validate_disposition(self) -> ReferenceIncidentCandidateAudit:
        if self.eligible_start_s >= self.eligible_end_s:
            raise ValueError("eligible incident episode must be a nonempty half-open interval")
        accepted = self.representative_attempt.disposition == "accepted-new-episode"
        if (self.accepted_truth_incident_id is None) == accepted:
            raise ValueError("accepted episode must bind its exact truth incident")
        expected_attempt_count = self.rejected_attempt_count + int(accepted)
        if self.attempt_count != expected_attempt_count:
            raise ValueError("candidate attempt summary count is inconsistent")
        suppressed = self.suppressed_eligible_ticks > 0
        if suppressed != (self.suppression_reason is not None):
            raise ValueError("suppression summary must match suppressed eligible ticks")
        if suppressed and self.accepted_truth_incident_id is None:
            raise ValueError("a rejected episode cannot suppress later eligible ticks")
        return self


class ReferenceTruthIncident(DeltaModel):
    truth_incident_id: str = Field(pattern=r"^RI-[0-9a-f]{16}$")
    incident_type: ReferenceIncidentType
    episode_key: str = Field(min_length=12)
    onset_s: int = Field(ge=-172_800, le=345_300)
    scheduled_resolution_s: int = Field(gt=-172_800)
    island_id: str = Field(pattern=r"^ISL-0[1-8]$")
    truth_structure_id: str | None = Field(default=None, pattern=r"^RS-[0-9a-f]{16}$")
    infrastructure_id: str | None = None
    affected_truth_person_ids: tuple[str, ...]
    location_easting_mm: int
    location_northing_mm: int
    service_requirement: ReferenceServiceRequirement
    severity_micros: int = Field(ge=1, le=1_000_000)

    @model_validator(mode="after")
    def validate_subject_binding(self) -> ReferenceTruthIncident:
        infrastructure_only = self.incident_type in {
            ReferenceIncidentType.LEVEE_INSPECTION,
            ReferenceIncidentType.ANIMAL_RESCUE,
            ReferenceIncidentType.INFORMATION_NEED,
            ReferenceIncidentType.HAZARD_RESPONSE,
        }
        if not infrastructure_only and not self.affected_truth_person_ids:
            raise ValueError("person-centered Reference incident has no affected person")
        if (
            self.incident_type == ReferenceIncidentType.LEVEE_INSPECTION
            and not self.infrastructure_id
        ):
            raise ValueError("levee inspection requires an infrastructure segment")
        return self


class ReferenceTruthScenario(DeltaModel):
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    schema_version: Literal["delta-reference-ground-truth-v1"]
    coefficient_version: Literal["delta-reference-truth-development-coefficients-v1"]
    scientific_status: Literal["development-coefficients-not-frozen-for-validation"]
    seed: int = Field(ge=0)
    incidents: tuple[ReferenceTruthIncident, ...]
    candidate_audit: tuple[ReferenceIncidentCandidateAudit, ...]
    truth_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_episode_uniqueness(self) -> ReferenceTruthScenario:
        incident_ids = tuple(item.truth_incident_id for item in self.incidents)
        if len(set(incident_ids)) != len(incident_ids):
            raise ValueError("Reference truth incident identifiers must be unique")
        ordered = tuple(
            sorted(self.incidents, key=lambda item: (item.onset_s, item.truth_incident_id))
        )
        if self.incidents != ordered:
            raise ValueError("Reference truth incidents must use canonical onset/ID order")
        episode_keys = tuple(item.episode_key for item in self.candidate_audit)
        if len(set(episode_keys)) != len(episode_keys):
            raise ValueError("Reference candidate episode keys must be unique")
        accepted = {
            item.accepted_truth_incident_id
            for item in self.candidate_audit
            if item.accepted_truth_incident_id is not None
        }
        if accepted != set(incident_ids):
            raise ValueError("Reference accepted candidate audit and incident totals differ")
        return self
