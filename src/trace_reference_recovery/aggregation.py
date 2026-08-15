"""Complete-shard verification and descriptive aggregation for recovery."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path

from trace_jepa.support import atomic_write_bytes, canonical_json_bytes, safe_directory
from trace_reference import verify_small_baseline
from trace_reference.validation.registration import (
    REFERENCE_VALIDATION_FREEZE,
    REFERENCE_VALIDATION_PROTOCOL,
    load_reference_validation_protocol,
    verify_reference_validation_freeze,
)
from trace_reference.validation.registration_models import (
    ReferenceBaseValidationProtocol,
    ReferenceValidationDescriptiveInterval,
    ReferenceValidationGateResult,
    ReferenceValidationMissionReceipt,
)
from trace_reference.validation.statistics import (
    ReferenceSeedMetric,
    cluster_bootstrap_mean_interval,
)

from .bindings import bind_artifact, read_bound_text
from .manifest import RECOVERY_MANIFEST_PATH
from .models import (
    RecoveryExecutionIdentity,
    RecoveryOriginalReport,
    RecoveryProtectedSeedPlan,
    RecoveryShardReceipt,
)
from .protected_plan import PlanFactory, derive_recovery_plan
from .registration import (
    EXPECTED_SEED_LIST_SHA256,
    FAILED_RECOVERY_RECORD_PATH,
    FAILURE_RECORD_PATH,
    RECOVERY_PROTOCOL_PATH,
    require_recovery_boundary,
)
from .shards import load_present_shards

SMALL_REGISTRY = Path("data/scenario/delta/reference_protocol/small_baseline_v1.json")


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


def _gate(
    gate_id: str,
    passed: bool,
    evidence: object,
) -> ReferenceValidationGateResult:
    return ReferenceValidationGateResult(
        gate_id=gate_id,
        passed=passed,
        evidence_sha256=hashlib.sha256(canonical_json_bytes(evidence)).hexdigest(),
        adverse_finding=None if passed else "one or more mission-level checks failed",
    )


def _aggregate_gate(
    gate_id: str,
    missions: tuple[ReferenceValidationMissionReceipt, ...],
    *,
    fixed_pass: bool | None = None,
    fixed_evidence: object | None = None,
) -> ReferenceValidationGateResult:
    matches = tuple(gate for item in missions for gate in item.gates if gate.gate_id == gate_id)
    passed = all(item.passed for item in matches) if fixed_pass is None else fixed_pass
    evidence = (
        fixed_evidence
        if fixed_evidence is not None
        else tuple(item.evidence_sha256 for item in matches)
    )
    return _gate(gate_id, passed, evidence)


def aggregate_fixed_gates(
    missions: tuple[ReferenceValidationMissionReceipt, ...],
    *,
    phase6: dict[str, object],
    canonical: dict[str, object],
    protocol: ReferenceBaseValidationProtocol,
    freeze_digest: str,
) -> tuple[ReferenceValidationGateResult, ...]:
    """Aggregate frozen gates while retaining exact fixed-evidence conditions."""

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
        _aggregate_gate(
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
    plan_factory: PlanFactory = derive_recovery_plan,
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
    protocol_binding = bind_artifact(repository_root, REFERENCE_VALIDATION_PROTOCOL)
    shards = load_present_shards(shard_root)
    missions = _validate_complete_shards(
        shards,
        identity=identity,
        governance_digest=manifest.recovery_aggregate_sha256,
        protocol_sha256=protocol_binding.sha256,
        freeze_digest=base_freeze.freeze_digest,
        plan=plan,
    )
    phase6 = json.loads(read_bound_text(repository_root, base_freeze.phase6_development_acceptance))
    canonical = json.loads(
        read_bound_text(repository_root, base_freeze.canonical_phase6_execution_receipt)
    )
    verify_small_baseline(repository_root, SMALL_REGISTRY)
    gates = aggregate_fixed_gates(
        missions,
        phase6=phase6,
        canonical=canonical,
        protocol=base_protocol,
        freeze_digest=base_freeze.freeze_digest,
    )
    intervals = _descriptive_intervals(missions, protocol_sha256=protocol_binding.sha256)
    adverse = (
        "lifecycle:original-authorization-failed-before-evaluation",
        "lifecycle:recovery-v1-tag-identity-failed-before-derivation",
        *tuple(
            f"mission-{mission.mission_index:03d}:{gate.gate_id}:{gate.adverse_finding}"
            for mission in missions
            for gate in mission.gates
            if not gate.passed
        ),
    )
    body = {
        "schema_version": "delta-reference-base-validation-recovery-report-v2",
        "execution_role": "original-base-reference-validation-recovery",
        "execution": identity.model_dump(mode="json"),
        "failed_original_authorization": bind_artifact(
            repository_root, FAILURE_RECORD_PATH
        ).model_dump(mode="json"),
        "failed_recovery_v1_authorization": bind_artifact(
            repository_root, FAILED_RECOVERY_RECORD_PATH
        ).model_dump(mode="json"),
        "failed_original_run_id": 31833291955,
        "failed_recovery_v1_run_id": 31856190911,
        "base_protocol": protocol_binding.model_dump(mode="json"),
        "base_freeze": bind_artifact(repository_root, REFERENCE_VALIDATION_FREEZE).model_dump(
            mode="json"
        ),
        "recovery_protocol": bind_artifact(repository_root, RECOVERY_PROTOCOL_PATH).model_dump(
            mode="json"
        ),
        "recovery_governance_manifest": bind_artifact(
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
        "recovery_v1_authorization_failed_before_evaluation": True,
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
