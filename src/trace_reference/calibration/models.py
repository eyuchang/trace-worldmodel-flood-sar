"""Typed contracts for the spent-development Reference truth fit."""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import Field, model_validator

from trace_jepa.scenario.delta.domain.base import DeltaModel
from trace_jepa.support import canonical_json_bytes
from trace_reference.domain.truth import ReferenceIncidentType


class ReferenceTruthTargetShare(DeltaModel):
    incident_type: ReferenceIncidentType
    share_micros: int = Field(gt=0, le=1_000_000)


class ReferenceTruthFitSolver(DeltaModel):
    objective: Literal["separable-type-absolute-count-residual"]
    tie_break: Literal["lower-intercept"]
    probability_rounding: Literal["integer-half-up"]
    seed_weighting: Literal["equal-mission-weight"]
    per_seed_normalization: Literal["forbidden"]


class ReferenceResourceStopBounds(DeltaModel):
    maximum_additional_disk_bytes: Literal[1_073_741_824]
    maximum_peak_memory_bytes: Literal[2_147_483_648]
    maximum_wall_time_s: Literal[900]


class ReferenceTruthFitProtocol(DeltaModel):
    schema_version: Literal["delta-reference-truth-fit-protocol-v1"]
    scientific_status: Literal["spent-development-only-no-validation-authority"]
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    protocol_amendment_sha256: Literal[
        "9ebe678e38a0360a3ebbef8ad55a9e334e77269c74c0065adbcc83e813d9f6ac"
    ]
    seed_namespace: Literal["WF-DFLD-01-REFERENCE|development-v1|index"]
    seed_count: Literal[100]
    evaluation_start_s: Literal[0]
    evaluation_end_s: Literal[345600]
    target_total_lower: Literal[1800]
    target_total_midpoint: Literal[2000]
    target_total_upper: Literal[2200]
    intercept_lower: int = Field(ge=1)
    intercept_upper: int = Field(gt=1)
    coarse_grid_points: int = Field(ge=17, le=257)
    refinement_grid_points: int = Field(ge=9, le=129)
    target_shares: tuple[ReferenceTruthTargetShare, ...] = Field(min_length=9, max_length=9)
    solver: ReferenceTruthFitSolver
    resource_stop_bounds: ReferenceResourceStopBounds
    limitations: tuple[str, ...] = Field(min_length=3)

    @model_validator(mode="after")
    def validate_fit_design(self) -> ReferenceTruthFitProtocol:
        expected = (
            ReferenceIncidentType.INFORMATION_NEED,
            ReferenceIncidentType.HAZARD_RESPONSE,
            ReferenceIncidentType.WELFARE_CHECK,
            ReferenceIncidentType.LEVEE_INSPECTION,
            ReferenceIncidentType.ANIMAL_RESCUE,
            ReferenceIncidentType.MISSING_PERSON,
            ReferenceIncidentType.STRANDED_STRUCTURE,
            ReferenceIncidentType.VEHICLE_RESCUE,
            ReferenceIncidentType.MEDICAL_ACCESS,
        )
        if tuple(item.incident_type for item in self.target_shares) != expected:
            raise ValueError("Reference truth targets are incomplete or out of order")
        if sum(item.share_micros for item in self.target_shares) != 1_000_000:
            raise ValueError("Reference truth target shares must sum to one")
        if self.intercept_lower >= self.intercept_upper:
            raise ValueError("Reference truth intercept bounds are invalid")
        return self


class ReferenceTruthFitBenchmarkReceipt(DeltaModel):
    schema_version: Literal["delta-reference-truth-fit-benchmark-v1"]
    scientific_status: Literal["development-resource-gate-not-fit-evidence"]
    protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    seed_indices: tuple[int, ...] = Field(min_length=1)
    elapsed_ms: int = Field(ge=0)
    projected_full_fit_ms: int = Field(ge=0)
    traced_python_peak_bytes: int = Field(ge=0)
    projected_additional_disk_bytes: int = Field(ge=0)
    observed_episode_count: int = Field(ge=0)
    observed_interval_count: int = Field(ge=0)
    within_registered_bounds: bool
    receipt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_digest(self) -> ReferenceTruthFitBenchmarkReceipt:
        body = self.model_dump(mode="json", exclude={"receipt_digest"})
        if hashlib.sha256(canonical_json_bytes(body)).hexdigest() != self.receipt_digest:
            raise ValueError("Reference truth benchmark receipt digest is invalid")
        return self


class ReferenceTruthCandidateEvaluation(DeltaModel):
    incident_type: ReferenceIncidentType
    intercept_micros: int = Field(ge=0)
    aggregate_evaluation_incidents: int = Field(ge=0)
    target_aggregate_incidents: int = Field(ge=0)
    absolute_residual: int = Field(ge=0)
    search_stage: Literal["coarse", "refinement"]


class ReferenceTruthSelectedCoefficient(DeltaModel):
    incident_type: ReferenceIncidentType
    intercept_micros: int = Field(ge=0)
    aggregate_evaluation_incidents: int = Field(ge=0)
    mean_evaluation_incidents_milli: int = Field(ge=0)
    target_mean_incidents: int = Field(ge=0)
    absolute_aggregate_residual: int = Field(ge=0)


class ReferenceTruthSeedResult(DeltaModel):
    seed_index: int = Field(ge=0)
    seed: int = Field(ge=0, le=2_147_483_647)
    evaluation_incidents: int = Field(ge=0)
    counts_by_type: tuple[int, ...] = Field(min_length=9, max_length=9)


class ReferenceTruthCoefficientSet(DeltaModel):
    schema_version: Literal["delta-reference-truth-coefficients-v2"]
    scientific_status: Literal["frozen-spent-development-fit-not-validation-evidence"]
    coefficient_version: Literal["delta-reference-truth-development-coefficients-v2"]
    probability_rounding: Literal["integer-half-up"]
    randomness_namespace: Literal["delta-reference-randomness-v1"]
    fit_protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    development_seed_list_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected: tuple[ReferenceTruthSelectedCoefficient, ...] = Field(min_length=9, max_length=9)
    coefficient_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_coefficient_digest(self) -> ReferenceTruthCoefficientSet:
        body = self.model_dump(mode="json", exclude={"coefficient_digest"})
        if hashlib.sha256(canonical_json_bytes(body)).hexdigest() != self.coefficient_digest:
            raise ValueError("Reference truth coefficient digest is invalid")
        if len({item.incident_type for item in self.selected}) != 9:
            raise ValueError("Reference truth coefficients must cover each incident type once")
        return self


class ReferenceTruthFitReport(DeltaModel):
    schema_version: Literal["delta-reference-truth-fit-report-v1"]
    scientific_status: Literal["spent-development-calibration-not-validation-evidence"]
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    scientific_input_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    development_seeds: tuple[int, ...] = Field(min_length=100, max_length=100)
    development_seed_list_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    benchmark_receipt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_evaluations: tuple[ReferenceTruthCandidateEvaluation, ...] = Field(min_length=9)
    selected: tuple[ReferenceTruthSelectedCoefficient, ...] = Field(min_length=9, max_length=9)
    seed_results: tuple[ReferenceTruthSeedResult, ...] = Field(min_length=100, max_length=100)
    aggregate_evaluation_incidents: int = Field(ge=0)
    mean_evaluation_incidents_milli: int = Field(ge=0)
    mean_inside_approved_band: bool
    eligible_episode_count: int = Field(ge=0)
    retained_interval_count: int = Field(ge=0)
    elapsed_ms: int = Field(ge=0)
    adverse_findings: tuple[str, ...]
    coefficient_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    report_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_report_digest(self) -> ReferenceTruthFitReport:
        body = self.model_dump(mode="json", exclude={"report_digest"})
        if hashlib.sha256(canonical_json_bytes(body)).hexdigest() != self.report_digest:
            raise ValueError("Reference truth fit report digest is invalid")
        return self
