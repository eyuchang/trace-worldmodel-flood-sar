"""Typed spent-development observation-calibration contracts."""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import Field, model_validator

from trace_jepa.scenario.delta.domain.base import DeltaModel
from trace_jepa.support import canonical_json_bytes

from .models import ReferenceResourceStopBounds


class ReferenceObservationBaseProbabilities(DeltaModel):
    duplicate: Literal[300_000]
    multi_channel: Literal[140_000]
    conflict: Literal[160_000]
    third_party_welfare: Literal[120_000]
    stranded_revision: Literal[400_000]
    false_benign_levee: Literal[90_000]
    callback_failure: Literal[310_000]
    call_drop: Literal[100_000]


class ReferenceObservationFitProtocol(DeltaModel):
    schema_version: Literal["delta-reference-observation-fit-protocol-v1"]
    scientific_status: Literal["spent-development-only-no-validation-authority"]
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    protocol_amendment_sha256: Literal[
        "07b0c901231323d1110ded728c8a1bb67e2a110368ed0644113a25626a7303d5"
    ]
    truth_fit_report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    truth_coefficients_file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    truth_coefficient_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    seed_namespace: Literal["WF-DFLD-01-REFERENCE|development-v1|index"]
    seed_count: Literal[100]
    evaluation_start_s: Literal[0]
    evaluation_end_s: Literal[345_600]
    hour_bin_s: Literal[3_600]
    target_evaluation_reports: Literal[2_900]
    breach_phase_start_s: Literal[187_200]
    breach_phase_end_s: Literal[230_400]
    breach_hourly_target_micros: Literal[95_000_000]
    unscaled_nonbreach_integral_micros: Literal[2_620_000_000]
    nonbreach_scale_numerator: Literal[88]
    nonbreach_scale_denominator: Literal[131]
    scaled_nonbreach_integral_micros: Literal[1_760_000_000]
    supplemental_witness_slots_per_incident: Literal[24]
    initial_report_probability_candidates_micros: tuple[int, ...] = Field(min_length=2)
    maximum_witness_probability_micros: Literal[950_000]
    selection_rule: Literal["largest-feasible-initial-probability"]
    tie_break: Literal["lower-maximum-witness-probability-then-lower-candidate"]
    fixed_base_probabilities_micros: ReferenceObservationBaseProbabilities
    resource_stop_bounds: ReferenceResourceStopBounds
    limitations: tuple[str, ...] = Field(min_length=3)

    @model_validator(mode="after")
    def validate_design(self) -> ReferenceObservationFitProtocol:
        candidates = self.initial_report_probability_candidates_micros
        if candidates != tuple(sorted(set(candidates))):
            raise ValueError("Reference observation candidates must be unique and increasing")
        if candidates[0] < 10_000 or candidates[-1] > 950_000:
            raise ValueError("Reference observation candidate probability is outside bounds")
        target_micros = self.target_evaluation_reports * 1_000_000
        breach_micros = 12 * self.breach_hourly_target_micros
        if breach_micros + self.scaled_nonbreach_integral_micros != target_micros:
            raise ValueError("Reference observation schedule does not integrate to 2,900")
        if (
            self.unscaled_nonbreach_integral_micros * self.nonbreach_scale_numerator
            != self.scaled_nonbreach_integral_micros * self.nonbreach_scale_denominator
        ):
            raise ValueError("Reference non-breach scale is not exact")
        return self


class ReferenceObservationFitBenchmarkReceipt(DeltaModel):
    schema_version: Literal[
        "delta-reference-observation-fit-benchmark-v1",
        "delta-reference-observation-fit-benchmark-v2",
    ]
    scientific_status: Literal["development-resource-gate-not-fit-evidence"]
    measurement_method: Literal[
        "two-pass-wall-and-separate-tracemalloc-v1",
        "single-world-pass-compact-replay-and-separate-tracemalloc-v2",
    ]
    wall_time_margin_micros: Literal[1_100_000]
    protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    seed_indices: tuple[int, ...] = Field(min_length=1)
    elapsed_ms: int = Field(ge=0)
    projected_full_fit_ms: int = Field(ge=0)
    traced_python_peak_bytes: int = Field(ge=0)
    projected_additional_disk_bytes: int = Field(ge=0)
    potential_witness_count: int = Field(ge=0)
    truth_incident_count: int = Field(ge=0)
    within_registered_bounds: bool
    receipt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_digest(self) -> ReferenceObservationFitBenchmarkReceipt:
        body = self.model_dump(mode="json", exclude={"receipt_digest"})
        if hashlib.sha256(canonical_json_bytes(body)).hexdigest() != self.receipt_digest:
            raise ValueError("Reference observation benchmark receipt digest is invalid")
        return self


class ReferenceObservationCandidateEvaluation(DeltaModel):
    initial_report_probability_micros: int = Field(ge=0, le=1_000_000)
    analytical_baseline_evaluation_reports_micros: int = Field(ge=0)
    infeasible_hour_indices: tuple[int, ...]
    minimum_witness_probability_micros: int = Field(ge=0)
    maximum_witness_probability_micros: int = Field(ge=0)
    feasible: bool


class ReferenceObservationHourlyCoefficient(DeltaModel):
    hour_index: int = Field(ge=0, lt=96)
    target_expected_reports_micros: int = Field(ge=0)
    baseline_expected_reports_micros: int = Field(ge=0)
    witness_opportunities: int = Field(ge=0)
    witness_probability_micros: int = Field(ge=0, le=1_000_000)
    fitted_expected_reports_micros: int = Field(ge=0)
    analytical_residual_micros: int


class ReferenceObservationCoefficientSet(DeltaModel):
    schema_version: Literal["delta-reference-observation-coefficients-v2"]
    scientific_status: Literal["frozen-spent-development-fit-not-validation-evidence"]
    coefficient_version: Literal["delta-reference-observation-development-coefficients-v2"]
    randomness_namespace: Literal["reference-observations-v2"]
    fit_protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    truth_coefficient_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    development_seed_list_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    initial_report_probability_micros: int = Field(ge=0, le=1_000_000)
    supplemental_witness_slots_per_incident: Literal[24]
    hourly: tuple[ReferenceObservationHourlyCoefficient, ...] = Field(min_length=96, max_length=96)
    coefficient_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_coefficient_set(self) -> ReferenceObservationCoefficientSet:
        if tuple(item.hour_index for item in self.hourly) != tuple(range(96)):
            raise ValueError("Reference observation hourly coefficients are incomplete")
        body = self.model_dump(mode="json", exclude={"coefficient_digest"})
        if hashlib.sha256(canonical_json_bytes(body)).hexdigest() != self.coefficient_digest:
            raise ValueError("Reference observation coefficient digest is invalid")
        return self


class ReferenceNamedCount(DeltaModel):
    name: str = Field(min_length=1, max_length=80)
    count: int = Field(ge=0)


class ReferenceObservationSeedResult(DeltaModel):
    seed_index: int = Field(ge=0)
    seed: int = Field(ge=0, le=2_147_483_647)
    evaluation_reports: int = Field(ge=0)
    breach_hour_counts: tuple[int, ...] = Field(min_length=12, max_length=12)
    relationship_counts: tuple[ReferenceNamedCount, ...]
    taxonomy_counts: tuple[ReferenceNamedCount, ...]


class ReferenceObservationFitReport(DeltaModel):
    schema_version: Literal["delta-reference-observation-fit-report-v1"]
    scientific_status: Literal["spent-development-calibration-not-validation-evidence"]
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    scientific_input_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    truth_coefficient_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    development_seeds: tuple[int, ...] = Field(min_length=100, max_length=100)
    development_seed_list_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    benchmark_receipt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_evaluations: tuple[ReferenceObservationCandidateEvaluation, ...] = Field(min_length=2)
    selected_initial_report_probability_micros: int = Field(ge=0, le=1_000_000)
    hourly: tuple[ReferenceObservationHourlyCoefficient, ...] = Field(min_length=96, max_length=96)
    seed_results: tuple[ReferenceObservationSeedResult, ...] = Field(min_length=100, max_length=100)
    analytical_expected_evaluation_reports_micros: int = Field(ge=0)
    realized_mean_evaluation_reports_milli: int = Field(ge=0)
    realized_breach_hour_means_milli: tuple[int, ...] = Field(min_length=12, max_length=12)
    aggregate_relationship_counts: tuple[ReferenceNamedCount, ...]
    aggregate_taxonomy_counts: tuple[ReferenceNamedCount, ...]
    elapsed_ms: int = Field(ge=0)
    adverse_findings: tuple[str, ...]
    coefficient_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    report_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_report_digest(self) -> ReferenceObservationFitReport:
        body = self.model_dump(mode="json", exclude={"report_digest"})
        if hashlib.sha256(canonical_json_bytes(body)).hexdigest() != self.report_digest:
            raise ValueError("Reference observation fit report digest is invalid")
        return self
