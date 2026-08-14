"""Typed records for the validation-v2 recovery lifecycle."""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import Field, model_validator

from trace_jepa.scenario.delta.domain.base import DeltaModel
from trace_jepa.support import canonical_json_bytes
from trace_reference.validation.registration_models import (
    ReferenceValidationBinding,
    ReferenceValidationDescriptiveInterval,
    ReferenceValidationGateResult,
    ReferenceValidationMissionReceipt,
)

_SHA256_PATTERN = r"^[0-9a-f]{64}$"


def _canonical_digest(value: DeltaModel, digest_field: str) -> str:
    body = value.model_dump(mode="json", exclude={digest_field})
    return hashlib.sha256(canonical_json_bytes(body)).hexdigest()


class FailedOriginalAuthorizationRecord(DeltaModel):
    """Immutable evidence that the original run stopped before evaluation."""

    schema_version: Literal["delta-reference-validation-v2-failed-authorization-v1"]
    classification: Literal["pre-evaluation-artifact-permission-infrastructure-failure"]
    repository: Literal["eyuchang/trace-worldmodel-flood-sar"]
    workflow_name: Literal["Reference base validation-v2 original (tag-authorized, once-only)"]
    workflow_file: Literal[".github/workflows/reference-base-validation-v2-original.yml"]
    workflow_id: Literal[334574314]
    workflow_run_id: Literal[31833291955]
    workflow_run_attempt: Literal[1]
    workflow_run_url: Literal[
        "https://github.com/eyuchang/trace-worldmodel-flood-sar/actions/runs/31833291955"
    ]
    created_at_utc: Literal["2026-08-14T19:26:58Z"]
    updated_at_utc: Literal["2026-08-14T19:27:52Z"]
    event: Literal["push"]
    conclusion: Literal["failure"]
    authorization_tag: Literal["wf-dfld-01-reference-validation-v2-original"]
    annotated_tag_object: Literal["c32e0db30510f9165cdb891861cf9680b4a33c4e"]
    source_commit: Literal["2cb58539425af467ac068ba7ef7500891e2fbe78"]
    authorize_job_id: Literal[94873822352]
    authorization_guards_passed: Literal[True]
    protected_list_derivation_succeeded: Literal[True]
    protected_seed_list_sha256: Literal[
        "2be02697a2379a974d709fda7b7285935227ae58a8ebe51fc38c0c48020ffa87"
    ]
    failed_step: Literal["Upload the protected plan for this workflow only"]
    failed_action: Literal["actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"]
    error_code: Literal["EACCES"]
    error_summary: Literal[
        "runner upload action could not read the root-owned mode-0600 atomic output"
    ]
    artifact_count: Literal[0]
    shard_job_status: Literal["skipped"]
    aggregate_job_status: Literal["skipped"]
    mission_execution_started: Literal[False]
    scientific_outcomes_observed: Literal[False]
    protected_seed_values_recorded: tuple[int, ...] = ()
    audit_date_utc: Literal["2026-08-14"]
    record_digest: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_record(self) -> FailedOriginalAuthorizationRecord:
        if self.protected_seed_values_recorded:
            raise ValueError("failed-run evidence must not contain protected seed values")
        if _canonical_digest(self, "record_digest") != self.record_digest:
            raise ValueError("failed original authorization record digest is invalid")
        return self


class RecoveryExecutionIdentity(DeltaModel):
    """Exact identity of the first mission-executing recovery attempt."""

    execution_role: Literal["original-base-reference-validation-recovery"]
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    scientific_source_commit: Literal["2cb58539425af467ac068ba7ef7500891e2fbe78"]
    authorization_tag: Literal["wf-dfld-01-reference-validation-v2-recovery-v1"]
    git_ref: Literal["refs/tags/wf-dfld-01-reference-validation-v2-recovery-v1"]
    workflow_file: Literal["reference-base-validation-v2-recovery.yml"]
    workflow_run_id: int = Field(ge=1)
    workflow_run_attempt: Literal[1]
    repository: Literal["eyuchang/trace-worldmodel-flood-sar"]
    failed_original_run_id: Literal[31833291955]


class RecoveryProtocol(DeltaModel):
    """Frozen governance amendment that changes orchestration, not mechanics."""

    schema_version: Literal["delta-reference-validation-v2-recovery-protocol-v1"]
    status: Literal["frozen-awaiting-distinct-tag-authorization"]
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    scientific_role: Literal["base-non-leap-integration-validation-not-policy-effectiveness"]
    failure_record: ReferenceValidationBinding
    amendment: ReferenceValidationBinding
    architecture_decision_record: ReferenceValidationBinding
    base_freeze: ReferenceValidationBinding
    base_scientific_manifest: ReferenceValidationBinding
    base_freeze_digest: Literal["b401b976fd22c19d6f2f81100e011946b566a48443ccd21a62d525bf9da820b3"]
    base_scientific_input_aggregate_sha256: Literal[
        "f9cf4103d75b28d9c14aa5fdb7721552a099a0a8dfccde852401c62036ee8b86"
    ]
    scientific_source_commit: Literal["2cb58539425af467ac068ba7ef7500891e2fbe78"]
    failed_original_run_id: Literal[31833291955]
    namespace: Literal["WF-DFLD-01-REFERENCE|validation-v2|index"]
    derivation_algorithm: Literal[
        "sha256-utf8-first-u32-big-endian-mask-unsigned31-reject-collision-v1"
    ]
    protected_seed_list_sha256: Literal[
        "2be02697a2379a974d709fda7b7285935227ae58a8ebe51fc38c0c48020ffa87"
    ]
    protected_seed_values: tuple[int, ...] = ()
    mission_count: Literal[100]
    shard_count: Literal[20]
    missions_per_shard: Literal[5]
    execution_role: Literal["original-base-reference-validation-recovery"]
    authorization_tag: Literal["wf-dfld-01-reference-validation-v2-recovery-v1"]
    workflow_file: Literal["reference-base-validation-v2-recovery.yml"]
    run_attempt: Literal[1]
    intermediate_seed_plan_artifact: Literal[False]
    raw_seed_disclosure_before_completed_report: Literal[False]
    rerun_completed_missions_after_interruption: Literal[False]
    scientific_mechanics_changed: Literal[False]
    protected_namespace_changed: Literal[False]
    leap_behavior_present: Literal[False]

    @model_validator(mode="after")
    def validate_protocol(self) -> RecoveryProtocol:
        if self.protected_seed_values:
            raise ValueError("recovery protocol must not contain protected seed values")
        if self.shard_count * self.missions_per_shard != self.mission_count:
            raise ValueError("recovery shard contract does not cover every mission")
        return self


class RecoveryProtectedSeedPlan(DeltaModel):
    """Ephemeral remote-only plan, disclosed only with a completed report."""

    schema_version: Literal["delta-reference-protected-seed-plan-recovery-v1"]
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    execution: RecoveryExecutionIdentity
    namespace: Literal["WF-DFLD-01-REFERENCE|validation-v2|index"]
    derivation_algorithm: Literal[
        "sha256-utf8-first-u32-big-endian-mask-unsigned31-reject-collision-v1"
    ]
    seeds: tuple[int, ...] = Field(min_length=100, max_length=100)
    seed_list_sha256: Literal["2be02697a2379a974d709fda7b7285935227ae58a8ebe51fc38c0c48020ffa87"]

    @model_validator(mode="after")
    def validate_plan(self) -> RecoveryProtectedSeedPlan:
        if len(set(self.seeds)) != 100 or any(
            not 0 <= item <= 2_147_483_647 for item in self.seeds
        ):
            raise ValueError("recovery plan is incomplete or contains a collision")
        body = {
            "namespace": self.namespace,
            "derivation_algorithm": self.derivation_algorithm,
            "seeds": self.seeds,
        }
        if hashlib.sha256(canonical_json_bytes(body)).hexdigest() != self.seed_list_sha256:
            raise ValueError("recovery plan differs from the derived original validation-v2 list")
        return self


class RecoveryShardReceipt(DeltaModel):
    """Five seed-concealing mission receipts from one recovery shard."""

    schema_version: Literal["delta-reference-validation-recovery-shard-receipt-v1"]
    execution: RecoveryExecutionIdentity
    failed_original_run_id: Literal[31833291955]
    shard_index: int = Field(ge=0, le=19)
    base_protocol_sha256: str = Field(pattern=_SHA256_PATTERN)
    base_freeze_digest: Literal["b401b976fd22c19d6f2f81100e011946b566a48443ccd21a62d525bf9da820b3"]
    recovery_governance_aggregate_sha256: str = Field(pattern=_SHA256_PATTERN)
    seed_list_sha256: Literal["2be02697a2379a974d709fda7b7285935227ae58a8ebe51fc38c0c48020ffa87"]
    missions: tuple[ReferenceValidationMissionReceipt, ...] = Field(min_length=5, max_length=5)
    shard_digest: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_shard(self) -> RecoveryShardReceipt:
        expected = tuple(range(self.shard_index * 5, self.shard_index * 5 + 5))
        if tuple(item.mission_index for item in self.missions) != expected:
            raise ValueError("recovery shard has missing or reordered missions")
        if _canonical_digest(self, "shard_digest") != self.shard_digest:
            raise ValueError("recovery shard digest is invalid")
        return self


class RecoveryOriginalReport(DeltaModel):
    """First mission-executing report, linked to the failed authorization run."""

    schema_version: Literal["delta-reference-base-validation-recovery-report-v1"]
    execution_role: Literal["original-base-reference-validation-recovery"]
    execution: RecoveryExecutionIdentity
    failed_original_authorization: ReferenceValidationBinding
    failed_original_run_id: Literal[31833291955]
    base_protocol: ReferenceValidationBinding
    base_freeze: ReferenceValidationBinding
    recovery_protocol: ReferenceValidationBinding
    recovery_governance_manifest: ReferenceValidationBinding
    base_freeze_digest: Literal["b401b976fd22c19d6f2f81100e011946b566a48443ccd21a62d525bf9da820b3"]
    scientific_input_aggregate_sha256: Literal[
        "f9cf4103d75b28d9c14aa5fdb7721552a099a0a8dfccde852401c62036ee8b86"
    ]
    seed_list_sha256: Literal["2be02697a2379a974d709fda7b7285935227ae58a8ebe51fc38c0c48020ffa87"]
    mission_count: Literal[100]
    completed_mission_count: Literal[100]
    mission_execution_status: Literal["complete"]
    shard_indices: tuple[int, ...] = Field(min_length=20, max_length=20)
    shard_digests: tuple[str, ...] = Field(min_length=20, max_length=20)
    exact_gates: tuple[ReferenceValidationGateResult, ...] = Field(min_length=8)
    descriptive_intervals: tuple[ReferenceValidationDescriptiveInterval, ...] = Field(min_length=8)
    adverse_findings: tuple[str, ...]
    all_exact_gates_pass: bool
    original_authorization_failed_before_evaluation: Literal[True]
    first_mission_executing_evaluation: Literal[True]
    report_digest: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_report(self) -> RecoveryOriginalReport:
        if self.shard_indices != tuple(range(20)):
            raise ValueError("recovery report shards are missing or reordered")
        if len(set(self.shard_digests)) != 20:
            raise ValueError("recovery report contains duplicate shard evidence")
        gate_ids = tuple(item.gate_id for item in self.exact_gates)
        if gate_ids != tuple(sorted(set(gate_ids))):
            raise ValueError("recovery aggregate gates must be unique and ordered")
        interval_names = tuple(item.metric_name for item in self.descriptive_intervals)
        if interval_names != tuple(sorted(set(interval_names))):
            raise ValueError("recovery descriptive intervals must be unique and ordered")
        if self.all_exact_gates_pass != all(item.passed for item in self.exact_gates):
            raise ValueError("recovery aggregate gate status is inconsistent")
        if _canonical_digest(self, "report_digest") != self.report_digest:
            raise ValueError("recovery report digest is invalid")
        return self


class RecoveryContinuationPlan(DeltaModel):
    """Seed-free rule permitting only missing shards after infrastructure interruption."""

    schema_version: Literal["delta-reference-validation-recovery-continuation-plan-v1"]
    interrupted_execution: RecoveryExecutionIdentity
    seed_list_sha256: Literal["2be02697a2379a974d709fda7b7285935227ae58a8ebe51fc38c0c48020ffa87"]
    completed_shard_indices: tuple[int, ...]
    missing_shard_indices: tuple[int, ...]
    completed_mission_indices: tuple[int, ...]
    missing_mission_indices: tuple[int, ...]
    completed_shards_must_not_rerun: Literal[True]
    continuation_requires_new_versioned_authorization: Literal[True]
    protected_namespace_must_not_change: Literal[True]
    plan_digest: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_plan(self) -> RecoveryContinuationPlan:
        expected_shards = tuple(range(20))
        combined_shards = tuple(
            sorted((*self.completed_shard_indices, *self.missing_shard_indices))
        )
        if combined_shards != expected_shards:
            raise ValueError("continuation plan must partition all recovery shards")
        if set(self.completed_shard_indices) & set(self.missing_shard_indices):
            raise ValueError("continuation plan repeats a shard")
        expected_completed = tuple(
            mission
            for shard in self.completed_shard_indices
            for mission in range(shard * 5, shard * 5 + 5)
        )
        expected_missing = tuple(
            mission
            for shard in self.missing_shard_indices
            for mission in range(shard * 5, shard * 5 + 5)
        )
        if self.completed_mission_indices != expected_completed:
            raise ValueError("continuation completed missions do not match completed shards")
        if self.missing_mission_indices != expected_missing:
            raise ValueError("continuation missing missions do not match missing shards")
        if _canonical_digest(self, "plan_digest") != self.plan_digest:
            raise ValueError("recovery continuation plan digest is invalid")
        return self


class RecoveryInterruptionRecord(DeltaModel):
    """Seed-free lifecycle evidence for incomplete or failed recovery aggregation."""

    schema_version: Literal["delta-reference-validation-recovery-interruption-record-v1"]
    interrupted_execution: RecoveryExecutionIdentity
    failure_stage: Literal[
        "incomplete-shards",
        "normalization",
        "aggregation",
        "artifact-preflight",
        "artifact-upload",
    ]
    seed_list_sha256: Literal["2be02697a2379a974d709fda7b7285935227ae58a8ebe51fc38c0c48020ffa87"]
    discovered_shard_file_count: int = Field(ge=0)
    valid_completed_shard_indices: tuple[int, ...]
    invalid_shard_file_count: int = Field(ge=0)
    final_report_written: bool
    raw_plan_written: bool
    raw_plan_uploaded: Literal[False]
    scientific_result_complete: bool
    completed_shards_must_not_rerun: Literal[True]
    continuation_requires_new_versioned_authorization: Literal[True]
    record_digest: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_record(self) -> RecoveryInterruptionRecord:
        if self.valid_completed_shard_indices != tuple(
            sorted(set(self.valid_completed_shard_indices))
        ):
            raise ValueError("interruption valid shards must be unique and ordered")
        if any(not 0 <= item < 20 for item in self.valid_completed_shard_indices):
            raise ValueError("interruption record contains an invalid shard index")
        if self.raw_plan_written and not self.final_report_written:
            raise ValueError("raw plan cannot precede the completed report")
        if self.scientific_result_complete != self.final_report_written:
            raise ValueError("interruption result status must match the completed report")
        if _canonical_digest(self, "record_digest") != self.record_digest:
            raise ValueError("recovery interruption record digest is invalid")
        return self


class RecoveryManifestMember(DeltaModel):
    """One immutable recovery-governance file."""

    repository_relative_path: str = Field(min_length=1, max_length=300)
    byte_length: int = Field(ge=1)
    sha256: str = Field(pattern=_SHA256_PATTERN)


class RecoveryGovernanceManifest(DeltaModel):
    """Separate recovery inventory layered over the unchanged scientific freeze."""

    schema_version: Literal["delta-reference-validation-recovery-governance-manifest-v1"]
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    scientific_source_commit: Literal["2cb58539425af467ac068ba7ef7500891e2fbe78"]
    base_scientific_manifest: ReferenceValidationBinding
    base_scientific_manifest_aggregate_sha256: Literal[
        "f9cf4103d75b28d9c14aa5fdb7721552a099a0a8dfccde852401c62036ee8b86"
    ]
    base_scientific_member_count: Literal[240]
    base_freeze: ReferenceValidationBinding
    base_freeze_digest: Literal["b401b976fd22c19d6f2f81100e011946b566a48443ccd21a62d525bf9da820b3"]
    base_scientific_members_unchanged: Literal[True]
    protected_seed_values: tuple[int, ...] = ()
    recovery_members: tuple[RecoveryManifestMember, ...] = Field(min_length=8)
    recovery_aggregate_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_manifest(self) -> RecoveryGovernanceManifest:
        if self.protected_seed_values:
            raise ValueError("recovery governance manifest must not contain protected seeds")
        paths = tuple(item.repository_relative_path for item in self.recovery_members)
        if paths != tuple(sorted(set(paths))):
            raise ValueError("recovery governance members must be unique and ordered")
        body = self.model_dump(mode="json", exclude={"recovery_aggregate_sha256"})
        if hashlib.sha256(canonical_json_bytes(body)).hexdigest() != (
            self.recovery_aggregate_sha256
        ):
            raise ValueError("recovery governance aggregate digest is invalid")
        return self
