"""Typed draft contracts for the unopened base-Reference validation boundary."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from trace_jepa.scenario.delta.domain.base import DeltaModel


class ReferenceDraftBinding(DeltaModel):
    """One exact repository or execution input considered by the draft."""

    name: str = Field(min_length=1, max_length=100)
    repository_relative_path: str = Field(min_length=1, max_length=300)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReferenceDraftStudyRole(DeltaModel):
    """A study namespace declaration that intentionally contains no seeds."""

    role: Literal[
        "development",
        "selection-v1-exposed",
        "validation-v1-exposed",
        "selection-v2-proposed",
        "validation-v2-proposed",
        "future-confirmatory",
    ]
    namespace_template: str = Field(min_length=20, max_length=120)
    planned_mission_count: int | None = Field(default=None, ge=1, le=10_000)
    status: Literal[
        "spent-development",
        "superseded-before-scientific-use",
        "proposed-not-derived-not-materialized",
        "deferred-pending-separate-powered-protocol",
    ]
    execution_boundary: Literal[
        "local-development-only",
        "never-use",
        "remote-original-once-only-after-approval",
        "disabled",
    ]
    contains_seed_values: Literal[False] = False
    rationale: str = Field(min_length=20, max_length=500)


class ReferenceDraftExactGate(DeltaModel):
    """One deterministic integration gate approved by Decision D7."""

    gate_id: str = Field(pattern=r"^RV-[A-Z0-9-]+$")
    requirement: str = Field(min_length=10, max_length=300)
    scope: Literal["every-mission", "study-aggregate", "canonical-environment"]


class ReferenceDraftReportEstimand(DeltaModel):
    """One descriptive mission-cluster estimand without an efficacy claim."""

    estimand_id: str = Field(pattern=r"^reference-[a-z0-9-]+$")
    unit: str = Field(min_length=3, max_length=80)
    method: str = Field(min_length=10, max_length=300)
    numerical_acceptance_gate: Literal[False] = False


class ReferenceDraftPrecisionRationale(DeltaModel):
    """Sample-size rationale calculated only from spent development summaries."""

    proposed_validation_missions: Literal[100]
    development_missions: Literal[100]
    observed_report_total_sd: float = Field(gt=0)
    projected_report_mean_95_half_width: float = Field(gt=0)
    observed_seed_breach_hour_mean_sd: float = Field(gt=0)
    projected_breach_hour_mean_95_half_width: float = Field(gt=0)
    zero_failure_one_sided_95_upper_bound: float = Field(gt=0, lt=1)
    interpretation: str = Field(min_length=40, max_length=700)


class ReferenceDraftRemoteOriginal(DeltaModel):
    """Proposed once-only remote validation design, inactive in this draft."""

    execution_role: Literal["original-base-reference-validation"]
    authorization: Literal["disabled-awaiting-owner-approval"]
    source_identity: Literal["immutable-annotated-tag-and-checked-out-sha"]
    run_attempt: Literal[1]
    prior_success_guard: Literal["workflow-tag-source-commit-registry"]
    concurrency_cancellation: Literal[False] = False
    environment_verification: Literal["exact-contract-lock-oci-index-and-platform-manifest"]
    network_during_scientific_execution: Literal[False] = False
    failure_policy: Literal["publish-without-retuning-or-seed-replacement"]
    output_identity_fields: tuple[str, ...] = Field(min_length=8)


class ReferenceBaseValidationPreregistrationDraft(DeltaModel):
    """Approval-ready design that cannot authorize or reveal untouched seeds."""

    schema_version: Literal["delta-reference-base-validation-preregistration-draft-v1"]
    status: Literal["awaiting-owner-approval-no-untouched-seed-access"]
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    scientific_role: Literal["base-non-leap-integration-validation-not-policy-effectiveness"]
    current_development_source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    scientific_input_aggregate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_scenario_axes: str = Field(min_length=20, max_length=180)
    registered_scarcity_sensitivity: Literal["reference-kappa-0p5-scarcity-v1"]
    bindings: tuple[ReferenceDraftBinding, ...] = Field(min_length=5)
    study_roles: tuple[ReferenceDraftStudyRole, ...] = Field(min_length=6, max_length=6)
    seed_derivation_procedure: str = Field(min_length=40, max_length=400)
    exact_gates: tuple[ReferenceDraftExactGate, ...] = Field(min_length=8)
    report_only_estimands: tuple[ReferenceDraftReportEstimand, ...] = Field(min_length=8)
    inference_unit: Literal["mission-seed"]
    interval_method: Literal["deterministic-10000-resample-mission-cluster-bootstrap"]
    precision_rationale: ReferenceDraftPrecisionRationale
    remote_original: ReferenceDraftRemoteOriginal
    open_approval_decisions: tuple[str, ...] = Field(min_length=3)
    selection_validation_confirmatory_seed_values: tuple[int, ...] = ()
    leap_behavior_present: Literal[False] = False
    policy_effectiveness_claim_present: Literal[False] = False

    @model_validator(mode="after")
    def validate_boundary(self) -> ReferenceBaseValidationPreregistrationDraft:
        if self.selection_validation_confirmatory_seed_values:
            raise ValueError("draft must not contain untouched seed values")
        roles = tuple(item.role for item in self.study_roles)
        expected = (
            "development",
            "selection-v1-exposed",
            "validation-v1-exposed",
            "selection-v2-proposed",
            "validation-v2-proposed",
            "future-confirmatory",
        )
        if roles != expected:
            raise ValueError("draft study roles are missing or out of order")
        paths = tuple(item.repository_relative_path for item in self.bindings)
        if paths != tuple(sorted(paths)) or len(set(paths)) != len(paths):
            raise ValueError("draft bindings must be unique and ordered")
        gate_ids = tuple(item.gate_id for item in self.exact_gates)
        if gate_ids != tuple(sorted(set(gate_ids))):
            raise ValueError("draft exact gates must be unique and ordered")
        estimand_ids = tuple(item.estimand_id for item in self.report_only_estimands)
        if estimand_ids != tuple(sorted(set(estimand_ids))):
            raise ValueError("draft estimands must be unique and ordered")
        return self
