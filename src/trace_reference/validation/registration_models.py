"""Typed contracts for the protected base-Reference validation boundary."""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import Field, model_validator

from trace_jepa.scenario.delta.domain.base import DeltaModel
from trace_jepa.support import canonical_json_bytes

REFERENCE_VALIDATION_MISSION_GATE_IDS = (
    "RV-CHAIN-INTEGRITY",
    "RV-CONSERVATION",
    "RV-EXACT-REPLAY",
    "RV-FAULT-REACHABILITY",
    "RV-HIDDEN-TRUTH",
    "RV-RECOVERY-EQUIVALENCE",
)
REFERENCE_VALIDATION_METRIC_NAMES = (
    "acquisition_request_count",
    "allocation_count",
    "compensation_count",
    "consistency_debt_count",
    "evaluation_report_count",
    "evaluation_truth_incident_count",
    "refusal_count",
    "scarcity_peak_finite_strict_load_ratio",
    "scarcity_strict_unserviceable_window_count",
    "strict_peak_finite_load_ratio",
    "strict_unserviceable_window_count",
)


class ReferenceValidationBinding(DeltaModel):
    """One exact repository file bound by a protocol or freeze record."""

    repository_relative_path: str = Field(min_length=1, max_length=300)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReferenceValidationStudyDeclaration(DeltaModel):
    """A lifecycle declaration that intentionally contains no protected seed."""

    role: Literal[
        "development-v1",
        "selection-v1",
        "validation-v1",
        "selection-v2",
        "validation-v2",
        "future-confirmatory",
    ]
    namespace_template: str = Field(min_length=20, max_length=120)
    mission_count: int | None = Field(default=None, ge=1, le=10_000)
    lifecycle: Literal[
        "spent-development",
        "superseded-before-scientific-use",
        "reserved-not-derived-not-materialized",
        "approved-awaiting-separate-execution-authorization",
        "deferred-requires-separate-powered-protocol",
    ]
    execution_boundary: Literal[
        "local-development-only",
        "never-use",
        "disabled",
        "remote-original-once-only",
    ]
    contains_seed_values: Literal[False] = False


class ReferenceValidationGateDefinition(DeltaModel):
    """One deterministic integration requirement; no fitted threshold is permitted."""

    gate_id: str = Field(pattern=r"^RV-[A-Z0-9-]+$")
    requirement: str = Field(min_length=10, max_length=400)
    scope: Literal["every-mission", "study-aggregate", "canonical-environment"]
    numerical_threshold: Literal[False] = False


class ReferenceValidationEstimandDefinition(DeltaModel):
    """One descriptive mission-seed summary without a superiority claim."""

    estimand_id: str = Field(pattern=r"^reference-[a-z0-9-]+$")
    unit: Literal["mission-seed"]
    method: str = Field(min_length=10, max_length=400)
    interval: Literal["deterministic-10000-resample-mission-cluster-bootstrap"]
    numerical_acceptance_gate: Literal[False] = False


class ReferenceBaseValidationProtocol(DeltaModel):
    """Approved design for an unopened, tag-authorized original study."""

    schema_version: Literal["delta-reference-base-validation-protocol-v2"]
    status: Literal["approved-frozen-input-awaiting-separate-execution-authorization"]
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    scientific_role: Literal["base-non-leap-integration-validation-not-policy-effectiveness"]
    approval_amendment: ReferenceValidationBinding
    canonical_axes: str = Field(min_length=20, max_length=180)
    registered_scarcity_sensitivity: Literal["reference-kappa-0p5-scarcity-v1"]
    study_declarations: tuple[ReferenceValidationStudyDeclaration, ...] = Field(
        min_length=6, max_length=6
    )
    seed_derivation_algorithm: Literal[
        "sha256-utf8-first-u32-big-endian-mask-unsigned31-reject-collision-v1"
    ]
    protected_seed_values: tuple[int, ...] = ()
    mission_count: Literal[100]
    shard_count: Literal[20]
    missions_per_shard: Literal[5]
    exact_gates: tuple[ReferenceValidationGateDefinition, ...] = Field(min_length=8)
    report_only_estimands: tuple[ReferenceValidationEstimandDefinition, ...] = Field(
        min_length=8
    )
    inference_unit: Literal["mission-seed"]
    interval_method: Literal["deterministic-10000-resample-mission-cluster-bootstrap"]
    authorization_tag: Literal["wf-dfld-01-reference-validation-v2-original"]
    workflow_file: Literal["reference-base-validation-v2-original.yml"]
    environment_contract_path: Literal[
        "data/scenario/delta/reference/environment/reference_python311_linux_amd64_v1.json"
    ]
    dependency_lock_path: Literal["requirements-delta-python311.lock"]
    scientific_manifest_path: Literal[
        "data/scenario/delta/reference_protocol/reference_scientific_input_manifest_v2.json"
    ]
    freeze_record_path: Literal[
        "data/scenario/delta/reference_protocol/reference_base_validation_freeze_v2.json"
    ]
    run_attempt: Literal[1]
    concurrency_cancellation: Literal[False] = False
    network_during_scientific_execution: Literal[False] = False
    failure_policy: Literal["publish-without-retuning-seed-replacement-or-result-suppression"]
    leap_behavior_present: Literal[False] = False
    policy_effectiveness_claim_present: Literal[False] = False

    @model_validator(mode="after")
    def validate_protocol(self) -> ReferenceBaseValidationProtocol:
        if self.protected_seed_values:
            raise ValueError("protected Reference protocol must not contain seed values")
        expected_roles = (
            "development-v1",
            "selection-v1",
            "validation-v1",
            "selection-v2",
            "validation-v2",
            "future-confirmatory",
        )
        if tuple(item.role for item in self.study_declarations) != expected_roles:
            raise ValueError("Reference study lifecycle declarations are missing or out of order")
        gates = tuple(item.gate_id for item in self.exact_gates)
        if gates != tuple(sorted(set(gates))):
            raise ValueError("Reference validation gates must be unique and ordered")
        estimands = tuple(item.estimand_id for item in self.report_only_estimands)
        if estimands != tuple(sorted(set(estimands))):
            raise ValueError("Reference validation estimands must be unique and ordered")
        if self.shard_count * self.missions_per_shard != self.mission_count:
            raise ValueError("Reference validation shard plan does not cover all missions")
        return self


class ReferenceBaseValidationFreeze(DeltaModel):
    """Non-self-referential binding of the approved protocol to exact inputs."""

    schema_version: Literal["delta-reference-base-validation-freeze-v2"]
    status: Literal["frozen-awaiting-separate-execution-authorization"]
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    protocol: ReferenceValidationBinding
    scientific_input_manifest: ReferenceValidationBinding
    scientific_input_aggregate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    scientific_input_member_count: int = Field(ge=1)
    workflow: ReferenceValidationBinding
    environment_contract: ReferenceValidationBinding
    dependency_lock: ReferenceValidationBinding
    g3_handoff: ReferenceValidationBinding
    phase6_development_acceptance: ReferenceValidationBinding
    canonical_phase6_execution_receipt: ReferenceValidationBinding
    authorization_tag: Literal["wf-dfld-01-reference-validation-v2-original"]
    source_commit_required: Literal[True] = True
    protected_seed_values: tuple[int, ...] = ()
    freeze_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_freeze(self) -> ReferenceBaseValidationFreeze:
        if self.protected_seed_values:
            raise ValueError("Reference freeze record must not contain protected seeds")
        body = self.model_dump(mode="json", exclude={"freeze_digest"})
        if hashlib.sha256(canonical_json_bytes(body)).hexdigest() != self.freeze_digest:
            raise ValueError("Reference base-validation freeze digest is invalid")
        return self


class ReferenceOriginalExecutionIdentity(DeltaModel):
    """Immutable GitHub identity required before protected derivation is reachable."""

    execution_role: Literal["original-base-reference-validation"]
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    authorization_tag: Literal["wf-dfld-01-reference-validation-v2-original"]
    git_ref: Literal["refs/tags/wf-dfld-01-reference-validation-v2-original"]
    workflow_file: Literal["reference-base-validation-v2-original.yml"]
    workflow_run_id: int = Field(ge=1)
    workflow_run_attempt: Literal[1]
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class ReferenceCanonicalPhase6ExecutionReceipt(DeltaModel):
    """Execution provenance proving the corrected canonical Phase 6 classification."""

    schema_version: Literal["delta-reference-canonical-phase6-execution-receipt-v2"]
    scientific_status: Literal["canonical-development-preflight-not-validation-evidence"]
    execution_role: Literal["canonical-development-preflight"]
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    scientific_input_aggregate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    environment_contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dependency_lock_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    oci_index_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    oci_platform_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    oci_platform: Literal["linux/amd64"]
    derived_reference_image_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    docker_engine_version: str = Field(min_length=3, max_length=100)
    recorded_utc: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:]+Z$")
    raw_core_receipt: ReferenceValidationBinding
    raw_core_receipt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    raw_resource_receipt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    raw_runner_measurement_role: Literal["canonical"]
    raw_runner_canonical_gate_status: Literal["passed"]
    environment_verification_matches: Literal[True]
    registered_resource_ceilings_observed_within_limits: Literal[True]
    exact_replay_byte_identical: Literal[True]
    publication_regeneration_byte_identical: Literal[True]
    leap_behavior_present: Literal[False] = False
    selection_validation_or_confirmatory_authority: Literal[False] = False
    receipt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_receipt(self) -> ReferenceCanonicalPhase6ExecutionReceipt:
        body = self.model_dump(mode="json", exclude={"receipt_digest"})
        if hashlib.sha256(canonical_json_bytes(body)).hexdigest() != self.receipt_digest:
            raise ValueError("Reference canonical Phase 6 receipt digest is invalid")
        return self


class ReferenceProtectedSeedPlan(DeltaModel):
    """Remote-only plan produced once after every authorization guard passes."""

    schema_version: Literal["delta-reference-protected-seed-plan-v2"]
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    execution: ReferenceOriginalExecutionIdentity
    namespace: Literal["WF-DFLD-01-REFERENCE|validation-v2|index"]
    derivation_algorithm: Literal[
        "sha256-utf8-first-u32-big-endian-mask-unsigned31-reject-collision-v1"
    ]
    seeds: tuple[int, ...] = Field(min_length=100, max_length=100)
    seed_list_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_seed_plan(self) -> ReferenceProtectedSeedPlan:
        if len(set(self.seeds)) != 100 or any(not 0 <= item <= 2_147_483_647 for item in self.seeds):
            raise ValueError("Reference protected seed plan is incomplete or contains a collision")
        body = {
            "namespace": self.namespace,
            "derivation_algorithm": self.derivation_algorithm,
            "seeds": self.seeds,
        }
        if hashlib.sha256(canonical_json_bytes(body)).hexdigest() != self.seed_list_sha256:
            raise ValueError("Reference protected seed-list digest is invalid")
        return self


class ReferenceValidationGateResult(DeltaModel):
    """One exact gate result; failures remain valid report content."""

    gate_id: str = Field(pattern=r"^RV-[A-Z0-9-]+$")
    passed: bool
    evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    adverse_finding: str | None = Field(default=None, min_length=4, max_length=500)

    @model_validator(mode="after")
    def validate_finding(self) -> ReferenceValidationGateResult:
        if self.passed == (self.adverse_finding is not None):
            raise ValueError("Reference gate result must explain failures and only failures")
        return self


class ReferenceValidationMissionReceipt(DeltaModel):
    """Seed-concealing result for one original-validation mission index."""

    schema_version: Literal["delta-reference-validation-mission-receipt-v2"]
    mission_index: int = Field(ge=0, le=99)
    mission_seed_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    scenario_input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    nominal_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    fault_report_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    gates: tuple[ReferenceValidationGateResult, ...] = Field(min_length=6)
    metric_micros: dict[str, int] = Field(min_length=8)
    receipt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_receipt(self) -> ReferenceValidationMissionReceipt:
        gate_ids = tuple(item.gate_id for item in self.gates)
        if gate_ids != REFERENCE_VALIDATION_MISSION_GATE_IDS:
            raise ValueError("Reference mission gate results are incomplete or out of order")
        if tuple(self.metric_micros) != REFERENCE_VALIDATION_METRIC_NAMES:
            raise ValueError("Reference mission metrics are incomplete or out of order")
        body = self.model_dump(mode="json", exclude={"receipt_digest"})
        if hashlib.sha256(canonical_json_bytes(body)).hexdigest() != self.receipt_digest:
            raise ValueError("Reference mission receipt digest is invalid")
        return self


class ReferenceValidationShardReceipt(DeltaModel):
    """One isolated five-mission shard bound to the protected original identity."""

    schema_version: Literal["delta-reference-validation-shard-receipt-v2"]
    execution: ReferenceOriginalExecutionIdentity
    shard_index: int = Field(ge=0, le=19)
    protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    freeze_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    missions: tuple[ReferenceValidationMissionReceipt, ...] = Field(min_length=5, max_length=5)
    shard_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_shard(self) -> ReferenceValidationShardReceipt:
        expected = tuple(range(self.shard_index * 5, self.shard_index * 5 + 5))
        if tuple(item.mission_index for item in self.missions) != expected:
            raise ValueError("Reference validation shard has missing or reordered missions")
        body = self.model_dump(mode="json", exclude={"shard_digest"})
        if hashlib.sha256(canonical_json_bytes(body)).hexdigest() != self.shard_digest:
            raise ValueError("Reference validation shard digest is invalid")
        return self


class ReferenceValidationDescriptiveInterval(DeltaModel):
    """One mission-cluster descriptive interval copied into the original report."""

    metric_name: str = Field(pattern=r"^[a-z][a-z0-9_]{2,79}$")
    point_micros: int
    lower_micros: int
    upper_micros: int
    method: Literal["deterministic-cluster-bootstrap-percentile-v1"]
    resample_count: Literal[10_000]
    randomness_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReferenceBaseValidationOriginalReport(DeltaModel):
    """Immutable original result; adverse outcomes are first-class report content."""

    schema_version: Literal["delta-reference-base-validation-original-report-v2"]
    execution_role: Literal["original-base-reference-validation"]
    execution: ReferenceOriginalExecutionIdentity
    protocol: ReferenceValidationBinding
    freeze_record: ReferenceValidationBinding
    freeze_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    scientific_input_aggregate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    environment_contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dependency_lock_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    seed_list_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mission_count: Literal[100]
    shard_digests: tuple[str, ...] = Field(min_length=20, max_length=20)
    exact_gates: tuple[ReferenceValidationGateResult, ...] = Field(min_length=8)
    descriptive_intervals: tuple[ReferenceValidationDescriptiveInterval, ...] = Field(
        min_length=8
    )
    adverse_findings: tuple[str, ...]
    all_exact_gates_pass: bool
    report_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_report(self) -> ReferenceBaseValidationOriginalReport:
        if len(set(self.shard_digests)) != 20:
            raise ValueError("Reference original report has duplicate shard evidence")
        gates = tuple(item.gate_id for item in self.exact_gates)
        if gates != tuple(sorted(set(gates))):
            raise ValueError("Reference original aggregate gates must be unique and ordered")
        intervals = tuple(item.metric_name for item in self.descriptive_intervals)
        if intervals != tuple(sorted(set(intervals))):
            raise ValueError("Reference descriptive intervals must be unique and ordered")
        if self.all_exact_gates_pass != all(item.passed for item in self.exact_gates):
            raise ValueError("Reference aggregate gate status is inconsistent")
        body = self.model_dump(mode="json", exclude={"report_digest"})
        if hashlib.sha256(canonical_json_bytes(body)).hexdigest() != self.report_digest:
            raise ValueError("Reference original validation report digest is invalid")
        return self
