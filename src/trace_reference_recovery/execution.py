"""Remote-only mission execution for the governed validation-v2 recovery."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from trace_jepa.support import (
    ArtifactLocator,
    atomic_write_bytes,
    canonical_json_bytes,
    safe_directory,
    sha256_file,
)
from trace_reference import verify_small_baseline
from trace_reference.validation import original_execution as frozen_execution
from trace_reference.validation.registration import (
    REFERENCE_VALIDATION_FREEZE,
    REFERENCE_VALIDATION_PROTOCOL,
    load_reference_validation_protocol,
    verify_reference_validation_freeze,
)
from trace_reference.validation.registration_models import (
    ReferenceValidationBinding,
    ReferenceValidationDescriptiveInterval,
    ReferenceValidationGateResult,
    ReferenceValidationMissionReceipt,
)
from trace_reference.validation.statistics import (
    ReferenceSeedMetric,
    cluster_bootstrap_mean_interval,
)

from .manifest import RECOVERY_MANIFEST_PATH
from .models import (
    RecoveryContinuationPlan,
    RecoveryExecutionIdentity,
    RecoveryInterruptionRecord,
    RecoveryOriginalReport,
    RecoveryProtectedSeedPlan,
    RecoveryShardReceipt,
)
from .registration import (
    EXPECTED_SEED_LIST_SHA256,
    FAILURE_RECORD_PATH,
    RECOVERY_PROTOCOL_PATH,
    require_recovery_boundary,
)

_VALIDATION_NAMESPACE = "WF-DFLD-01-REFERENCE|validation-v2|index"
_DERIVATION_ALGORITHM = "sha256-utf8-first-u32-big-endian-mask-unsigned31-reject-collision-v1"
_SMALL_REGISTRY = Path("data/scenario/delta/reference_protocol/small_baseline_v1.json")
_MAX_RECEIPT_BYTES = 64 * 1024 * 1024
PlanFactory = Callable[[RecoveryExecutionIdentity], RecoveryProtectedSeedPlan]
MissionRunner = Callable[..., ReferenceValidationMissionReceipt]


@dataclass(frozen=True)
class RecoveryInterruptionRequest:
    """Caller-bound inputs for one seed-free recovery failure record."""

    shard_root: Path
    failure_stage: Literal[
        "incomplete-shards",
        "normalization",
        "aggregation",
        "artifact-preflight",
        "artifact-upload",
    ]
    final_report_written: bool
    raw_plan_written: bool
    environment: Mapping[str, str] | None = None


def authorize_recovery(
    repository_root: Path,
    *,
    environment: Mapping[str, str] | None = None,
) -> RecoveryExecutionIdentity:
    """Verify recovery authority without deriving or materializing any seed."""

    _, _, identity = require_recovery_boundary(
        repository_root,
        os.environ if environment is None else environment,
    )
    return identity


def _protected_seed(index: int) -> int:
    payload = f"{_VALIDATION_NAMESPACE.removesuffix('|index')}|{index}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:4], "big") & 0x7FFFFFFF


def _derive_recovery_plan(identity: RecoveryExecutionIdentity) -> RecoveryProtectedSeedPlan:
    """Derive the original list only inside a verified remote recovery boundary."""

    seeds = tuple(_protected_seed(index) for index in range(100))
    return RecoveryProtectedSeedPlan(
        schema_version="delta-reference-protected-seed-plan-recovery-v1",
        scenario_id="WF-DFLD-01-REFERENCE",
        execution=identity,
        namespace=_VALIDATION_NAMESPACE,
        derivation_algorithm=_DERIVATION_ALGORITHM,
        seeds=seeds,
        seed_list_sha256=EXPECTED_SEED_LIST_SHA256,
    )


def _remove_generated_tree(root: Path) -> None:
    for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_file() or path.is_symlink():
            path.unlink()
        elif path.is_dir():
            path.rmdir()
    root.rmdir()


def _binding(repository_root: Path, relative_path: Path) -> ReferenceValidationBinding:
    return ReferenceValidationBinding(
        repository_relative_path=relative_path.as_posix(),
        sha256=sha256_file(repository_root / relative_path),
    )


def _run_shard_missions(
    repository_root: Path,
    work_root: Path,
    *,
    shard_index: int,
    plan: RecoveryProtectedSeedPlan,
    mission_runner: MissionRunner,
) -> tuple[ReferenceValidationMissionReceipt, ...]:
    missions = []
    for mission_index in range(shard_index * 5, shard_index * 5 + 5):
        mission_root = work_root / f"mission-{mission_index:03d}"
        mission_root.mkdir()
        try:
            try:
                receipt = mission_runner(
                    repository_root,
                    mission_root,
                    mission_index=mission_index,
                    seed=plan.seeds[mission_index],
                )
            except Exception as exc:  # noqa: BLE001 - failures are registered evidence
                receipt = frozen_execution._failed_mission_receipt(
                    mission_index,
                    plan.seeds[mission_index],
                    f"{type(exc).__name__}: {exc}",
                )
            missions.append(receipt)
        finally:
            _remove_generated_tree(mission_root)
    return tuple(missions)


def run_recovery_shard(
    repository_root: Path,
    output_path: Path,
    *,
    shard_index: int,
    environment: Mapping[str, str] | None = None,
    plan_factory: PlanFactory = _derive_recovery_plan,
    mission_runner: MissionRunner = frozen_execution._run_mission,
) -> RecoveryShardReceipt:
    """Privately derive, execute, and emit one seed-concealing shard receipt."""

    if output_path.exists():
        raise ValueError("recovery shard output already exists")
    protocol, manifest, identity = require_recovery_boundary(
        repository_root,
        os.environ if environment is None else environment,
    )
    if not 0 <= shard_index < protocol.shard_count:
        raise ValueError("recovery shard index is outside the frozen plan")
    plan = plan_factory(identity)
    if plan.execution != identity or plan.seed_list_sha256 != EXPECTED_SEED_LIST_SHA256:
        raise ValueError("recovery shard plan is not bound to this execution")
    output_root = safe_directory(
        output_path.parent,
        declared_root=output_path.parent,
        label="recovery shard output root",
    )
    work_root = output_root / f"mission-work-{shard_index:02d}"
    work_root.mkdir()
    try:
        missions = _run_shard_missions(
            repository_root,
            work_root,
            shard_index=shard_index,
            plan=plan,
            mission_runner=mission_runner,
        )
    finally:
        if work_root.exists() and not any(work_root.iterdir()):
            work_root.rmdir()
    body = {
        "schema_version": "delta-reference-validation-recovery-shard-receipt-v1",
        "execution": identity.model_dump(mode="json"),
        "failed_original_run_id": 31833291955,
        "shard_index": shard_index,
        "base_protocol_sha256": sha256_file(repository_root / REFERENCE_VALIDATION_PROTOCOL),
        "base_freeze_digest": protocol.base_freeze_digest,
        "recovery_governance_aggregate_sha256": manifest.recovery_aggregate_sha256,
        "seed_list_sha256": plan.seed_list_sha256,
        "missions": [item.model_dump(mode="json") for item in missions],
    }
    receipt = RecoveryShardReceipt(
        **body,
        shard_digest=hashlib.sha256(canonical_json_bytes(body)).hexdigest(),
    )
    atomic_write_bytes(
        output_path,
        canonical_json_bytes(receipt.model_dump(mode="json")),
        root=output_root,
        label="recovery shard receipt",
    )
    return receipt


def _load_present_shards(shard_root: Path) -> tuple[RecoveryShardReceipt, ...]:
    receipts = []
    for shard_index in range(20):
        try:
            path = ArtifactLocator(
                root=shard_root,
                relative_name=Path(f"shard-{shard_index:02d}.json"),
                maximum_bytes=_MAX_RECEIPT_BYTES,
                label=f"recovery shard {shard_index}",
            ).resolve()
        except (OSError, ValueError):
            continue
        receipt = RecoveryShardReceipt.model_validate_json(path.read_text("utf-8"))
        if receipt.shard_index != shard_index:
            raise ValueError("recovery shard filename does not match its receipt")
        receipts.append(receipt)
    return tuple(receipts)


def build_recovery_continuation_plan(
    repository_root: Path,
    output_path: Path,
    *,
    shard_root: Path,
    environment: Mapping[str, str] | None = None,
) -> RecoveryContinuationPlan:
    """Preserve completed shards and authorize no mission reruns after interruption."""

    if output_path.exists():
        raise ValueError("recovery continuation output already exists")
    _, manifest, identity = require_recovery_boundary(
        repository_root,
        os.environ if environment is None else environment,
    )
    receipts = _load_present_shards(shard_root)
    if any(
        item.execution != identity
        or item.recovery_governance_aggregate_sha256 != manifest.recovery_aggregate_sha256
        or item.seed_list_sha256 != EXPECTED_SEED_LIST_SHA256
        for item in receipts
    ):
        raise ValueError("recovery continuation evidence belongs to another execution")
    completed = tuple(item.shard_index for item in receipts)
    missing = tuple(index for index in range(20) if index not in completed)
    body = {
        "schema_version": "delta-reference-validation-recovery-continuation-plan-v1",
        "interrupted_execution": identity.model_dump(mode="json"),
        "seed_list_sha256": EXPECTED_SEED_LIST_SHA256,
        "completed_shard_indices": completed,
        "missing_shard_indices": missing,
        "completed_mission_indices": [
            mission for shard in completed for mission in range(shard * 5, shard * 5 + 5)
        ],
        "missing_mission_indices": [
            mission for shard in missing for mission in range(shard * 5, shard * 5 + 5)
        ],
        "completed_shards_must_not_rerun": True,
        "continuation_requires_new_versioned_authorization": True,
        "protected_namespace_must_not_change": True,
    }
    plan = RecoveryContinuationPlan(
        **body,
        plan_digest=hashlib.sha256(canonical_json_bytes(body)).hexdigest(),
    )
    output_root = safe_directory(
        output_path.parent,
        declared_root=output_path.parent,
        label="recovery continuation output root",
    )
    atomic_write_bytes(
        output_path,
        canonical_json_bytes(plan.model_dump(mode="json")),
        root=output_root,
        label="recovery continuation plan",
    )
    return plan


def write_recovery_interruption_record(
    repository_root: Path,
    output_path: Path,
    request: RecoveryInterruptionRequest,
) -> RecoveryInterruptionRecord:
    """Record a recovery infrastructure failure without deriving or exposing seeds."""

    if output_path.exists():
        raise ValueError("recovery interruption output already exists")
    _, manifest, identity = require_recovery_boundary(
        repository_root,
        os.environ if request.environment is None else request.environment,
    )
    trusted = safe_directory(
        request.shard_root,
        declared_root=request.shard_root,
        label="recovery interruption shard root",
    )
    candidates = tuple(sorted(trusted.rglob("shard-*.json")))
    valid: list[int] = []
    invalid_count = 0
    for candidate in candidates:
        try:
            path = ArtifactLocator.from_path(
                root=trusted,
                path=candidate,
                maximum_bytes=_MAX_RECEIPT_BYTES,
                label="recovery interruption shard",
            ).resolve()
            receipt = RecoveryShardReceipt.model_validate_json(path.read_text("utf-8"))
            if (
                receipt.execution != identity
                or receipt.recovery_governance_aggregate_sha256
                != manifest.recovery_aggregate_sha256
                or receipt.seed_list_sha256 != EXPECTED_SEED_LIST_SHA256
                or receipt.shard_index in valid
            ):
                raise ValueError("recovery interruption shard binding is invalid")
            valid.append(receipt.shard_index)
        except (OSError, ValueError):
            invalid_count += 1
    body = {
        "schema_version": "delta-reference-validation-recovery-interruption-record-v1",
        "interrupted_execution": identity.model_dump(mode="json"),
        "failure_stage": request.failure_stage,
        "seed_list_sha256": EXPECTED_SEED_LIST_SHA256,
        "discovered_shard_file_count": len(candidates),
        "valid_completed_shard_indices": sorted(valid),
        "invalid_shard_file_count": invalid_count,
        "final_report_written": request.final_report_written,
        "raw_plan_written": request.raw_plan_written,
        "raw_plan_uploaded": False,
        "scientific_result_complete": request.final_report_written,
        "completed_shards_must_not_rerun": True,
        "continuation_requires_new_versioned_authorization": True,
    }
    record = RecoveryInterruptionRecord(
        **body,
        record_digest=hashlib.sha256(canonical_json_bytes(body)).hexdigest(),
    )
    output_root = safe_directory(
        output_path.parent,
        declared_root=output_path.parent,
        label="recovery interruption output root",
    )
    atomic_write_bytes(
        output_path,
        canonical_json_bytes(record.model_dump(mode="json")),
        root=output_root,
        label="recovery interruption record",
    )
    return record


def _validate_complete_shards(
    shards: tuple[RecoveryShardReceipt, ...],
    *,
    identity: RecoveryExecutionIdentity,
    governance_digest: str,
    protocol_sha256: str,
    freeze_digest: str,
    plan: RecoveryProtectedSeedPlan,
) -> tuple[ReferenceValidationMissionReceipt, ...]:
    if tuple(item.shard_index for item in shards) != tuple(range(20)):
        raise ValueError("recovery aggregation requires exactly 20 ordered shards")
    if any(
        item.execution != identity
        or item.recovery_governance_aggregate_sha256 != governance_digest
        or item.base_protocol_sha256 != protocol_sha256
        or item.base_freeze_digest != freeze_digest
        or item.seed_list_sha256 != plan.seed_list_sha256
        for item in shards
    ):
        raise ValueError("recovery shard bindings are inconsistent")
    missions = tuple(mission for shard in shards for mission in shard.missions)
    if tuple(item.mission_index for item in missions) != tuple(range(100)):
        raise ValueError("recovery mission coverage is incomplete")
    if any(
        item.mission_seed_sha256
        != hashlib.sha256(str(plan.seeds[index]).encode("ascii")).hexdigest()
        for index, item in enumerate(missions)
    ):
        raise ValueError("recovery mission receipts do not match the protected list")
    return missions


def _aggregate_fixed_gates(
    missions: tuple[ReferenceValidationMissionReceipt, ...],
    *,
    phase6: dict[str, object],
    canonical: dict[str, object],
    protocol: object,
    freeze_digest: str,
) -> tuple[ReferenceValidationGateResult, ...]:
    from trace_reference.validation.registration_models import ReferenceBaseValidationProtocol

    if not isinstance(protocol, ReferenceBaseValidationProtocol):
        raise TypeError("recovery aggregation requires the frozen base protocol")
    checks = phase6.get("checks")
    if not isinstance(checks, list):
        raise TypeError("base Phase 6 checks are unavailable")
    fixed = {
        "RV-AXIS-ISOLATION": any(
            isinstance(item, dict)
            and item.get("check_id") == "P6-AXIS-ISOLATION"
            and item.get("passed") is True
            for item in checks
        ),
        "RV-CANONICAL-PERFORMANCE": (
            canonical.get("execution_role") == "canonical-development-preflight"
            and canonical.get("environment_verification_matches") is True
            and canonical.get("registered_resource_ceilings_observed_within_limits") is True
            and canonical.get("exact_replay_byte_identical") is True
            and canonical.get("publication_regeneration_byte_identical") is True
        ),
        "RV-SMALL-PRESERVATION": True,
        "RV-SOURCE-SECURITY": phase6.get("all_nonperformance_checks_pass") is True,
    }
    return tuple(
        frozen_execution._aggregate_gate(
            definition.gate_id,
            missions,
            fixed_pass=fixed.get(definition.gate_id),
            fixed_evidence=(freeze_digest if definition.gate_id in fixed else None),
        )
        for definition in protocol.exact_gates
    )


def _descriptive_intervals(
    missions: tuple[ReferenceValidationMissionReceipt, ...],
    *,
    protocol_sha256: str,
) -> tuple[ReferenceValidationDescriptiveInterval, ...]:
    metric_names = tuple(sorted(missions[0].metric_micros))
    if any(tuple(item.metric_micros) != metric_names for item in missions):
        raise ValueError("recovery mission receipts expose inconsistent metric sets")
    intervals = []
    for metric_name in metric_names:
        interval = cluster_bootstrap_mean_interval(
            tuple(
                ReferenceSeedMetric(
                    seed=item.mission_index,
                    value_micros=item.metric_micros[metric_name],
                )
                for item in missions
            ),
            protocol_hash=protocol_sha256,
            metric_name=metric_name,
        )
        intervals.append(
            ReferenceValidationDescriptiveInterval(
                metric_name=metric_name,
                point_micros=interval.point_micros,
                lower_micros=interval.lower_micros,
                upper_micros=interval.upper_micros,
                method="deterministic-cluster-bootstrap-percentile-v1",
                resample_count=10_000,
                randomness_sha256=interval.randomness_sha256 or "",
            )
        )
    return tuple(intervals)


def aggregate_recovery_report(
    repository_root: Path,
    output_path: Path,
    *,
    shard_root: Path,
    disclosed_plan_output_path: Path,
    environment: Mapping[str, str] | None = None,
    plan_factory: PlanFactory = _derive_recovery_plan,
) -> RecoveryOriginalReport:
    """Aggregate complete evidence, then disclose the exact plan beside the report."""

    if output_path.exists() or disclosed_plan_output_path.exists():
        raise ValueError("recovery aggregate output already exists")
    recovery_protocol, manifest, identity = require_recovery_boundary(
        repository_root,
        os.environ if environment is None else environment,
    )
    plan = plan_factory(identity)
    if plan.execution != identity or plan.seed_list_sha256 != EXPECTED_SEED_LIST_SHA256:
        raise ValueError("recovery aggregate plan is not bound to this execution")
    base_protocol = load_reference_validation_protocol(repository_root)
    base_freeze = verify_reference_validation_freeze(repository_root)
    protocol_sha = sha256_file(repository_root / REFERENCE_VALIDATION_PROTOCOL)
    shards = _load_present_shards(shard_root)
    missions = _validate_complete_shards(
        shards,
        identity=identity,
        governance_digest=manifest.recovery_aggregate_sha256,
        protocol_sha256=protocol_sha,
        freeze_digest=base_freeze.freeze_digest,
        plan=plan,
    )
    phase6 = json.loads(
        (
            repository_root / base_freeze.phase6_development_acceptance.repository_relative_path
        ).read_text("utf-8")
    )
    canonical = json.loads(
        (
            repository_root
            / base_freeze.canonical_phase6_execution_receipt.repository_relative_path
        ).read_text("utf-8")
    )
    verify_small_baseline(repository_root, _SMALL_REGISTRY)
    gates = _aggregate_fixed_gates(
        missions,
        phase6=phase6,
        canonical=canonical,
        protocol=base_protocol,
        freeze_digest=base_freeze.freeze_digest,
    )
    intervals = _descriptive_intervals(missions, protocol_sha256=protocol_sha)
    adverse = tuple(
        f"mission-{mission.mission_index:03d}:{gate.gate_id}:{gate.adverse_finding}"
        for mission in missions
        for gate in mission.gates
        if not gate.passed
    )
    body = {
        "schema_version": "delta-reference-base-validation-recovery-report-v1",
        "execution_role": "original-base-reference-validation-recovery",
        "execution": identity.model_dump(mode="json"),
        "failed_original_authorization": _binding(repository_root, FAILURE_RECORD_PATH).model_dump(
            mode="json"
        ),
        "failed_original_run_id": 31833291955,
        "base_protocol": _binding(repository_root, REFERENCE_VALIDATION_PROTOCOL).model_dump(
            mode="json"
        ),
        "base_freeze": _binding(repository_root, REFERENCE_VALIDATION_FREEZE).model_dump(
            mode="json"
        ),
        "recovery_protocol": _binding(repository_root, RECOVERY_PROTOCOL_PATH).model_dump(
            mode="json"
        ),
        "recovery_governance_manifest": _binding(
            repository_root, RECOVERY_MANIFEST_PATH
        ).model_dump(mode="json"),
        "base_freeze_digest": base_freeze.freeze_digest,
        "scientific_input_aggregate_sha256": (
            recovery_protocol.base_scientific_input_aggregate_sha256
        ),
        "seed_list_sha256": plan.seed_list_sha256,
        "mission_count": 100,
        "completed_mission_count": len(missions),
        "mission_execution_status": "complete",
        "shard_indices": [item.shard_index for item in shards],
        "shard_digests": [item.shard_digest for item in shards],
        "exact_gates": [item.model_dump(mode="json") for item in gates],
        "descriptive_intervals": [item.model_dump(mode="json") for item in intervals],
        "adverse_findings": adverse,
        "all_exact_gates_pass": all(item.passed for item in gates),
        "original_authorization_failed_before_evaluation": True,
        "first_mission_executing_evaluation": True,
    }
    report = RecoveryOriginalReport(
        **body,
        report_digest=hashlib.sha256(canonical_json_bytes(body)).hexdigest(),
    )
    report_root = safe_directory(
        output_path.parent,
        declared_root=output_path.parent,
        label="recovery report output root",
    )
    plan_root = safe_directory(
        disclosed_plan_output_path.parent,
        declared_root=disclosed_plan_output_path.parent,
        label="recovery disclosed-plan output root",
    )
    atomic_write_bytes(
        output_path,
        canonical_json_bytes(report.model_dump(mode="json")),
        root=report_root,
        label="recovery original report",
    )
    atomic_write_bytes(
        disclosed_plan_output_path,
        canonical_json_bytes(plan.model_dump(mode="json")),
        root=plan_root,
        label="post-evaluation disclosed recovery seed plan",
    )
    return report
