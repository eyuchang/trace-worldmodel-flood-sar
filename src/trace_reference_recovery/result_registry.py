"""Byte-exact registry for the completed Reference validation-v2 recovery."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from trace_jepa.scenario.delta.domain.base import DeltaModel
from trace_jepa.support import ArtifactLocator, atomic_write_bytes, canonical_json_bytes
from trace_reference.validation.registration_models import ReferenceValidationBinding

from .bindings import MAX_RECOVERY_ARTIFACT_BYTES, bind_artifact, read_bound_text
from .models import RecoveryOriginalReport, RecoveryProtectedSeedPlan, RecoveryShardReceipt

RESULT_ROOT = Path("data/scenario/delta/reference_validation/v2_recovery_original")
REPORT_PATH = RESULT_ROOT / "reference_base_validation_recovery_report_v1.json"
SEED_PLAN_PATH = RESULT_ROOT / "reference_validation_v2_seed_plan.json"
SHARD_ROOT = RESULT_ROOT / "shards"
REGISTRY_PATH = RESULT_ROOT / "reference_base_validation_recovery_registry_v1.json"

_EXPECTED_GATE_IDS = (
    "RV-AXIS-ISOLATION",
    "RV-CANONICAL-PERFORMANCE",
    "RV-CHAIN-INTEGRITY",
    "RV-CONSERVATION",
    "RV-EXACT-REPLAY",
    "RV-FAULT-REACHABILITY",
    "RV-HIDDEN-TRUTH",
    "RV-RECOVERY-EQUIVALENCE",
    "RV-SMALL-PRESERVATION",
    "RV-SOURCE-SECURITY",
)
_EXPECTED_METRIC_NAMES = (
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


def _canonical_digest(value: DeltaModel, digest_field: str) -> str:
    body = value.model_dump(mode="json", exclude={digest_field})
    return hashlib.sha256(canonical_json_bytes(body)).hexdigest()


class RecoveryOriginalResultRegistry(DeltaModel):
    """Committed identity of the first mission-executing Reference validation."""

    schema_version: Literal["delta-reference-validation-recovery-original-registry-v1"]
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    execution_role: Literal["original-base-reference-validation-recovery"]
    result_status: Literal["complete-all-exact-gates-pass"]
    source_commit: Literal["7aae9ef84b0db69fd95d10d3b63aa8110555cd59"]
    scientific_source_commit: Literal["2cb58539425af467ac068ba7ef7500891e2fbe78"]
    authorization_tag: Literal["wf-dfld-01-reference-validation-v2-recovery-v2"]
    workflow_run_id: Literal[31858415326]
    workflow_run_attempt: Literal[1]
    workflow_run_url: Literal[
        "https://github.com/eyuchang/trace-worldmodel-flood-sar/actions/runs/31858415326"
    ]
    mission_count: Literal[100]
    report: ReferenceValidationBinding
    seed_plan: ReferenceValidationBinding
    shard_receipts: tuple[ReferenceValidationBinding, ...] = Field(
        min_length=20,
        max_length=20,
    )
    report_digest: Literal["605967175ae0adbce88699eb1b6b19b212af26cae0a7e56b3fc17bed4d533c27"]
    seed_list_sha256: Literal["2be02697a2379a974d709fda7b7285935227ae58a8ebe51fc38c0c48020ffa87"]
    scientific_input_aggregate_sha256: Literal[
        "f9cf4103d75b28d9c14aa5fdb7721552a099a0a8dfccde852401c62036ee8b86"
    ]
    base_freeze_digest: Literal["b401b976fd22c19d6f2f81100e011946b566a48443ccd21a62d525bf9da820b3"]
    recovery_governance_aggregate_sha256: Literal[
        "23c5417c5d3e90b09f790247482daf661211236ec3dd75f26ffa662cf0c6a3f3"
    ]
    exact_gate_ids: tuple[str, ...] = Field(min_length=10, max_length=10)
    descriptive_metric_names: tuple[str, ...] = Field(min_length=11, max_length=11)
    adverse_findings: tuple[str, ...]
    registry_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_registry(self) -> RecoveryOriginalResultRegistry:
        if self.report.repository_relative_path != REPORT_PATH.as_posix():
            raise ValueError("Reference recovery registry names another report")
        if self.seed_plan.repository_relative_path != SEED_PLAN_PATH.as_posix():
            raise ValueError("Reference recovery registry names another seed plan")
        expected_shards = tuple(
            (SHARD_ROOT / f"shard-{index:02d}.json").as_posix() for index in range(20)
        )
        if tuple(item.repository_relative_path for item in self.shard_receipts) != expected_shards:
            raise ValueError("Reference recovery registry shards are missing or reordered")
        if self.exact_gate_ids != _EXPECTED_GATE_IDS:
            raise ValueError("Reference recovery registry gate set changed")
        if self.descriptive_metric_names != _EXPECTED_METRIC_NAMES:
            raise ValueError("Reference recovery registry metric set changed")
        if _canonical_digest(self, "registry_digest") != self.registry_digest:
            raise ValueError("Reference recovery registry digest is invalid")
        return self


def _load_report(
    repository_root: Path,
    binding: ReferenceValidationBinding,
) -> RecoveryOriginalReport:
    return RecoveryOriginalReport.model_validate_json(read_bound_text(repository_root, binding))


def _load_seed_plan(
    repository_root: Path,
    binding: ReferenceValidationBinding,
) -> RecoveryProtectedSeedPlan:
    return RecoveryProtectedSeedPlan.model_validate_json(read_bound_text(repository_root, binding))


def _load_shards(
    repository_root: Path,
    bindings: tuple[ReferenceValidationBinding, ...],
) -> tuple[RecoveryShardReceipt, ...]:
    return tuple(
        RecoveryShardReceipt.model_validate_json(read_bound_text(repository_root, binding))
        for binding in bindings
    )


def _verify_cross_artifact_identity(
    report: RecoveryOriginalReport,
    seed_plan: RecoveryProtectedSeedPlan,
    shards: tuple[RecoveryShardReceipt, ...],
) -> None:
    if seed_plan.execution != report.execution:
        raise ValueError("Reference recovery seed plan belongs to another execution")
    if tuple(item.shard_index for item in shards) != tuple(range(20)):
        raise ValueError("Reference recovery receipt indices are incomplete")
    if any(item.execution != report.execution for item in shards):
        raise ValueError("Reference recovery shard belongs to another execution")
    if tuple(item.shard_digest for item in shards) != report.shard_digests:
        raise ValueError("Reference recovery report does not bind the committed shards")
    missions = tuple(mission for shard in shards for mission in shard.missions)
    if tuple(item.mission_index for item in missions) != tuple(range(100)):
        raise ValueError("Reference recovery mission coverage is incomplete")
    expected_seed_hashes = tuple(
        hashlib.sha256(str(seed).encode("ascii")).hexdigest() for seed in seed_plan.seeds
    )
    if tuple(item.mission_seed_sha256 for item in missions) != expected_seed_hashes:
        raise ValueError("Reference recovery missions do not match the disclosed seed plan")
    if not report.all_exact_gates_pass or any(not item.passed for item in report.exact_gates):
        raise ValueError("Reference recovery registry cannot mark failed exact gates as passing")


def build_original_result_registry(repository_root: Path) -> RecoveryOriginalResultRegistry:
    """Build the registry from exact downloaded artifacts under one trusted root."""

    report_binding = bind_artifact(repository_root, REPORT_PATH)
    seed_plan_binding = bind_artifact(repository_root, SEED_PLAN_PATH)
    shard_bindings = tuple(
        bind_artifact(repository_root, SHARD_ROOT / f"shard-{index:02d}.json")
        for index in range(20)
    )
    report = _load_report(repository_root, report_binding)
    seed_plan = _load_seed_plan(repository_root, seed_plan_binding)
    shards = _load_shards(repository_root, shard_bindings)
    _verify_cross_artifact_identity(report, seed_plan, shards)
    body = {
        "schema_version": "delta-reference-validation-recovery-original-registry-v1",
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "execution_role": report.execution_role,
        "result_status": "complete-all-exact-gates-pass",
        "source_commit": report.execution.source_commit,
        "scientific_source_commit": report.execution.scientific_source_commit,
        "authorization_tag": report.execution.authorization_tag,
        "workflow_run_id": report.execution.workflow_run_id,
        "workflow_run_attempt": report.execution.workflow_run_attempt,
        "workflow_run_url": (
            "https://github.com/eyuchang/trace-worldmodel-flood-sar/actions/runs/31858415326"
        ),
        "mission_count": report.completed_mission_count,
        "report": report_binding.model_dump(mode="json"),
        "seed_plan": seed_plan_binding.model_dump(mode="json"),
        "shard_receipts": [item.model_dump(mode="json") for item in shard_bindings],
        "report_digest": report.report_digest,
        "seed_list_sha256": report.seed_list_sha256,
        "scientific_input_aggregate_sha256": report.scientific_input_aggregate_sha256,
        "base_freeze_digest": report.base_freeze_digest,
        "recovery_governance_aggregate_sha256": shards[0].recovery_governance_aggregate_sha256,
        "exact_gate_ids": [item.gate_id for item in report.exact_gates],
        "descriptive_metric_names": [item.metric_name for item in report.descriptive_intervals],
        "adverse_findings": list(report.adverse_findings),
    }
    return RecoveryOriginalResultRegistry(
        **body,
        registry_digest=hashlib.sha256(canonical_json_bytes(body)).hexdigest(),
    )


def write_original_result_registry(repository_root: Path) -> RecoveryOriginalResultRegistry:
    """Write the deterministic registry once, after every downloaded artifact verifies."""

    output_path = repository_root / REGISTRY_PATH
    if output_path.exists():
        raise ValueError("Reference recovery result registry already exists")
    registry = build_original_result_registry(repository_root)
    atomic_write_bytes(
        output_path,
        canonical_json_bytes(registry.model_dump(mode="json")),
        root=output_path.parent,
        label="Reference recovery original-result registry",
    )
    return registry


def verify_original_result_registry(repository_root: Path) -> RecoveryOriginalResultRegistry:
    """Verify every retained byte and every cross-artifact identity in the registry."""

    registry_path = ArtifactLocator(
        root=repository_root,
        relative_name=REGISTRY_PATH,
        maximum_bytes=MAX_RECOVERY_ARTIFACT_BYTES,
        label="Reference recovery original-result registry",
    ).resolve()
    expected = RecoveryOriginalResultRegistry.model_validate_json(registry_path.read_text("utf-8"))
    actual = build_original_result_registry(repository_root)
    if actual != expected:
        raise ValueError("Reference recovery original-result registry is not current")
    return expected
