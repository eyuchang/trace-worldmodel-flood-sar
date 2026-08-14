from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from trace_jepa.support import canonical_json_bytes
from trace_reference.validation.registration import verify_reference_validation_freeze
from trace_reference.validation.registration_models import (
    REFERENCE_VALIDATION_METRIC_NAMES,
    REFERENCE_VALIDATION_MISSION_GATE_IDS,
    ReferenceValidationGateResult,
    ReferenceValidationMissionReceipt,
)
from trace_reference_recovery import execution
from trace_reference_recovery import manifest as recovery_manifest
from trace_reference_recovery.manifest import verify_recovery_governance_manifest
from trace_reference_recovery.models import (
    RecoveryContinuationPlan,
    RecoveryExecutionIdentity,
)
from trace_reference_recovery.registration import (
    EXPECTED_SEED_LIST_SHA256,
    RECOVERY_AUTHORIZATION_TAG,
    load_failed_original_record,
    load_recovery_protocol,
    require_recovery_identity,
    verify_recovery_protocol,
)

ROOT = Path(__file__).resolve().parents[2]


def _identity_environment() -> dict[str, str]:
    return {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REF": f"refs/tags/{RECOVERY_AUTHORIZATION_TAG}",
        "GITHUB_REPOSITORY": "eyuchang/trace-worldmodel-flood-sar",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_RUN_ID": "900001",
        "GITHUB_SHA": "a" * 40,
        "TRACE_REFERENCE_ANNOTATED_TAG_GUARD": "verified-annotated-tag-points-to-sha",
        "TRACE_REFERENCE_AUTHORIZATION_TAG": RECOVERY_AUTHORIZATION_TAG,
        "TRACE_REFERENCE_EXECUTION_ROLE": "original-base-reference-validation-recovery",
        "TRACE_REFERENCE_FAILED_ORIGINAL_GUARD": (
            "verified-run-31833291955-pre-evaluation-failure"
        ),
        "TRACE_REFERENCE_PRIOR_RECOVERY_GUARD": "verified-no-prior-recovery-attempt",
        "TRACE_REFERENCE_WORKFLOW_FILE": "reference-base-validation-v2-recovery.yml",
    }


def _identity() -> RecoveryExecutionIdentity:
    return require_recovery_identity(_identity_environment())


def _gate(gate_id: str) -> ReferenceValidationGateResult:
    evidence = hashlib.sha256(gate_id.encode()).hexdigest()
    return ReferenceValidationGateResult(
        gate_id=gate_id,
        passed=True,
        evidence_sha256=evidence,
        adverse_finding=None,
    )


def _mission() -> ReferenceValidationMissionReceipt:
    body = {
        "schema_version": "delta-reference-validation-mission-receipt-v2",
        "mission_index": 0,
        "mission_seed_sha256": "1" * 64,
        "scenario_input_digest": "2" * 64,
        "nominal_manifest_digest": "3" * 64,
        "fault_report_digest": "4" * 64,
        "gates": [
            _gate(gate_id).model_dump(mode="json")
            for gate_id in REFERENCE_VALIDATION_MISSION_GATE_IDS
        ],
        "metric_micros": dict.fromkeys(REFERENCE_VALIDATION_METRIC_NAMES, 0),
    }
    return ReferenceValidationMissionReceipt(
        **body,
        receipt_digest=hashlib.sha256(canonical_json_bytes(body)).hexdigest(),
    )


def test_failed_original_record_is_pre_evaluation_and_seed_free() -> None:
    record = load_failed_original_record(ROOT)

    assert record.workflow_run_id == 31833291955
    assert record.source_commit == "2cb58539425af467ac068ba7ef7500891e2fbe78"
    assert record.protected_seed_list_sha256 == EXPECTED_SEED_LIST_SHA256
    assert record.protected_list_derivation_succeeded
    assert record.artifact_count == 0
    assert record.shard_job_status == "skipped"
    assert record.aggregate_job_status == "skipped"
    assert not record.mission_execution_started
    assert not record.scientific_outcomes_observed
    assert record.protected_seed_values_recorded == ()


def test_recovery_protocol_preserves_base_science_and_namespace() -> None:
    assert load_recovery_protocol(ROOT) == verify_recovery_protocol(ROOT)
    protocol = verify_recovery_protocol(ROOT)
    freeze = verify_reference_validation_freeze(ROOT)

    assert freeze.freeze_digest == protocol.base_freeze_digest
    assert freeze.scientific_input_member_count == 240
    assert protocol.namespace == "WF-DFLD-01-REFERENCE|validation-v2|index"
    assert protocol.protected_seed_list_sha256 == EXPECTED_SEED_LIST_SHA256
    assert protocol.protected_seed_values == ()
    assert not protocol.scientific_mechanics_changed
    assert not protocol.protected_namespace_changed
    assert not protocol.intermediate_seed_plan_artifact


@pytest.mark.parametrize(
    ("name", "value"),
    (
        ("GITHUB_ACTIONS", "false"),
        ("GITHUB_REF", "refs/tags/wf-dfld-01-reference-validation-v2-original"),
        ("GITHUB_RUN_ATTEMPT", "2"),
        ("TRACE_REFERENCE_FAILED_ORIGINAL_GUARD", ""),
        ("TRACE_REFERENCE_PRIOR_RECOVERY_GUARD", ""),
    ),
)
def test_recovery_identity_fails_closed(name: str, value: str) -> None:
    environment = _identity_environment()
    environment[name] = value
    with pytest.raises(ValueError, match="identity is incomplete"):
        require_recovery_identity(environment)


def test_recovery_boundary_precedes_protected_derivation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    def blocked_boundary(*_args: object, **_kwargs: object) -> object:
        calls.append("boundary")
        raise ValueError("blocked before protected derivation")

    def forbidden_plan(_identity: RecoveryExecutionIdentity) -> object:
        calls.append("plan")
        raise AssertionError("protected derivation must not be reached")

    monkeypatch.setattr(execution, "require_recovery_boundary", blocked_boundary)
    with pytest.raises(ValueError, match="blocked before protected derivation"):
        execution.run_recovery_shard(
            ROOT,
            tmp_path / "shard.json",
            shard_index=0,
            plan_factory=forbidden_plan,  # type: ignore[arg-type]
        )
    assert calls == ["boundary"]


def test_recovery_manifest_is_separate_complete_and_detects_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = verify_recovery_governance_manifest(ROOT)
    paths = {item.repository_relative_path for item in manifest.recovery_members}

    assert manifest.base_scientific_member_count == 240
    assert manifest.base_scientific_members_unchanged
    assert manifest.protected_seed_values == ()
    assert paths == set(recovery_manifest.RECOVERY_MEMBER_PATHS)
    assert recovery_manifest.RECOVERY_MANIFEST_PATH.as_posix() not in paths
    assert "src/trace_reference_recovery/execution.py" in paths
    assert ".github/workflows/reference-base-validation-v2-recovery.yml" in paths
    assert (
        "data/scenario/delta/reference_protocol/reference_scientific_input_manifest_v2.json"
        not in paths
    )

    original = recovery_manifest.sha256_file

    def changed(path: Path, chunk_size: int = 1024 * 1024) -> str:
        if path.name == "recovery_protocol_v1.json":
            return "0" * 64
        return original(path, chunk_size)

    monkeypatch.setattr(recovery_manifest, "sha256_file", changed)
    with pytest.raises(ValueError, match="manifest is not current"):
        verify_recovery_governance_manifest(ROOT)


def test_continuation_plan_partitions_only_missing_missions() -> None:
    completed = (0, 2, 7)
    missing = tuple(index for index in range(20) if index not in completed)
    body = {
        "schema_version": "delta-reference-validation-recovery-continuation-plan-v1",
        "interrupted_execution": _identity().model_dump(mode="json"),
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

    assert set(plan.completed_mission_indices).isdisjoint(plan.missing_mission_indices)
    assert tuple(sorted((*plan.completed_mission_indices, *plan.missing_mission_indices))) == tuple(
        range(100)
    )

    invalid = {**body, "missing_shard_indices": (*missing, completed[0])}
    invalid["plan_digest"] = hashlib.sha256(canonical_json_bytes(invalid)).hexdigest()
    with pytest.raises(ValueError, match="partition all recovery shards"):
        RecoveryContinuationPlan.model_validate(invalid)


def test_source_security_gate_retains_phase6_requirement() -> None:
    from trace_reference.validation.registration import load_reference_validation_protocol

    protocol = load_reference_validation_protocol(ROOT)
    canonical = {
        "execution_role": "canonical-development-preflight",
        "environment_verification_matches": True,
        "registered_resource_ceilings_observed_within_limits": True,
        "exact_replay_byte_identical": True,
        "publication_regeneration_byte_identical": True,
    }
    phase6 = {
        "checks": [{"check_id": "P6-AXIS-ISOLATION", "passed": True}],
        "all_nonperformance_checks_pass": False,
    }

    gates = execution._aggregate_fixed_gates(
        (_mission(),),
        phase6=phase6,
        canonical=canonical,
        protocol=protocol,
        freeze_digest="b401b976fd22c19d6f2f81100e011946b566a48443ccd21a62d525bf9da820b3",
    )

    source_security = next(item for item in gates if item.gate_id == "RV-SOURCE-SECURITY")
    assert not source_security.passed
    assert source_security.adverse_finding is not None
