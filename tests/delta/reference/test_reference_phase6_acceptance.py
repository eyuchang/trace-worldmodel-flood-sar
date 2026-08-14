from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from trace_jepa.scenario.delta.environment import EnvironmentVerification
from trace_reference.decision.canonical import decision_digest
from trace_reference.generation import generate_reference_scenario
from trace_reference.provenance import ReferenceExecution, ReferenceExecutionInspection
from trace_reference.validation import acceptance as phase6_acceptance
from trace_reference.validation.acceptance_models import (
    REFERENCE_PHASE6_AXIS_IDS,
    REFERENCE_PHASE6_CHECK_IDS,
    ReferencePhase6AcceptanceReport,
    ReferencePhase6AxisResult,
    ReferencePhase6FaultReceipt,
    ReferencePhase6ResourceReceipt,
)
from trace_reference.validation.axis_invariants import build_reference_phase6_axis_results
from trace_reference.validation.models import ReferenceG3IntegrityReport

ROOT = Path(__file__).resolve().parents[3]


def _axis(axis: str) -> ReferencePhase6AxisResult:
    body: dict[str, Any] = {
        "axis": axis,
        "baseline_value": "baseline",
        "variant_value": "variant",
        "unchanged_stage_names": ("geography",),
        "changed_stage_names": ("axis-owned-stage",),
        "mechanism_checks": (("expected-change", True),),
        "observed_digests": (("axis-owned-stage", "9" * 64),),
        "keyed_draw_identity_preserved": True,
        "passed": True,
    }
    return ReferencePhase6AxisResult(**body, evidence_digest=decision_digest(body))


def _resource_receipt(role: str = "local-preflight") -> ReferencePhase6ResourceReceipt:
    body: dict[str, Any] = {
        "schema_version": "delta-reference-phase6-resource-receipt-v2",
        "measurement_role": role,
        "platform": "test-platform",
        "python_version": "3.13.1",
        "environment_contract_sha256": "a" * 64,
        "dependency_lock_sha256": "b" * 64,
        "environment_mismatches": (() if role == "canonical" else ("test environment mismatch",)),
        "elapsed_milliseconds": 1,
        "peak_resident_memory_bytes": 1,
        "transient_output_bytes": 1,
        "wall_time_limit_s": 900,
        "peak_memory_limit_bytes": 2_147_483_648,
        "transient_output_limit_bytes": 1_073_741_824,
        "wall_time_within_limit": True,
        "peak_memory_within_limit": True,
        "transient_output_within_limit": True,
        "canonical_gate_status": (
            "passed" if role == "canonical" else "pending-canonical-environment"
        ),
    }
    return ReferencePhase6ResourceReceipt(**body, receipt_digest=decision_digest(body))


def _g3_report() -> ReferenceG3IntegrityReport:
    families = (
        "authenticated-false-report",
        "completion-after-scenario-censoring",
        "contradictory-outcome-evidence",
        "controller-crash-restart",
        "duplicated-delivery-retry",
        "failed-compensation",
        "identity-dispute-visible-revision",
        "partial-service-outcome",
        "reordered-evidence-delivery",
        "silent-provider-success-after-timeout",
        "stale-acknowledgement-key-rotation",
    )
    body: dict[str, Any] = {
        "schema_version": "delta-reference-g3-runtime-integrity-v2",
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "scenario_seed": 20260812,
        "scientific_input_aggregate_sha256": "1" * 64,
        "scenario_input_digest": "2" * 64,
        "scientific_status": "development-integration-check-not-validation-evidence",
        "fault_profile_id": "reference-faulted-v1",
        "expected_fault_families": families,
        "observed_fault_families": families,
        "faulted_counts": {
            "decisions": 1,
            "allocations": 1,
            "refusals": 0,
            "acquisition_requests": 0,
            "outcomes": 1,
            "reconciliations": 0,
            "compensations": 1,
            "consistency_debts": 1,
        },
        "event_chains_valid": True,
        "trace_chains_valid": True,
        "evidence_chains_valid": True,
        "commitment_chains_valid": True,
        "fault_coverage_complete": True,
        "fault_targets_all_reachable": True,
        "exogenous_inputs_byte_equivalent": True,
        "restart_public_state_equivalent": True,
        "restart_durable_state_equivalent": True,
        "authorization_joins_valid": True,
        "correction_joins_valid": True,
        "public_artifacts_hidden_free": True,
        "all_checks_pass": True,
    }
    return ReferenceG3IntegrityReport(**body, report_digest=decision_digest(body))


def test_phase6_models_require_all_checks_axes_and_noninferential_status() -> None:
    checks = tuple(
        {
            "check_id": check_id,
            "passed": True,
            "evidence_digests": ("1" * 64,),
            "note": "deterministic development check",
        }
        for check_id in REFERENCE_PHASE6_CHECK_IDS
    )
    body: dict[str, Any] = {
        "schema_version": "delta-reference-phase6-development-acceptance-v1",
        "scientific_status": "development-integration-acceptance-not-validation-evidence",
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "seed": 20260812,
        "seed_status": "spent-development-illustrative",
        "protocol": {
            "repository_relative_path": (
                "docs/delta/reference/REFERENCE_PHASE6_DEVELOPMENT_ACCEPTANCE_V1.md"
            ),
            "byte_length": 1,
            "sha256": "2" * 64,
        },
        "scientific_input_manifest_digest": "3" * 64,
        "g3_handoff_manifest_digest": "4" * 64,
        "nominal_replay_manifest_digest": "5" * 64,
        "fault_integrity_report_digest": "6" * 64,
        "publication_manifest_digest": "7" * 64,
        "checks": checks,
        "axis_results": tuple(
            _axis(axis).model_dump(mode="json") for axis in REFERENCE_PHASE6_AXIS_IDS
        ),
        "resource_receipt": _resource_receipt().model_dump(mode="json"),
        "all_nonperformance_checks_pass": True,
        "canonical_performance_status": "pending-canonical-environment",
        "selection_validation_or_confirmatory_authority": False,
        "leap_behavior_present": False,
    }
    report = ReferencePhase6AcceptanceReport(
        **body,
        report_digest=decision_digest(body),
    )

    assert report.all_nonperformance_checks_pass
    assert report.canonical_performance_status == "pending-canonical-environment"
    assert not report.selection_validation_or_confirmatory_authority
    assert not report.leap_behavior_present


def test_phase6_inspection_does_not_expand_the_stable_execution_result() -> None:
    assert tuple(ReferenceExecution.__dataclass_fields__) == ("manifest", "run", "capacity")
    assert tuple(ReferenceExecutionInspection.__dataclass_fields__) == (
        "execution",
        "scenario",
        "runtime_bundle",
    )


def test_phase6_resource_gate_is_enforced_only_in_canonical_environment() -> None:
    local = _resource_receipt()
    canonical = _resource_receipt("canonical")

    assert local.canonical_gate_status == "pending-canonical-environment"
    assert canonical.canonical_gate_status == "passed"

    payload = canonical.model_dump(mode="json")
    payload["environment_mismatches"] = ["forged mismatch"]
    payload["receipt_digest"] = decision_digest(
        {key: value for key, value in payload.items() if key != "receipt_digest"}
    )
    with pytest.raises(ValueError, match="role disagrees"):
        ReferencePhase6ResourceReceipt.model_validate(payload)

    payload = canonical.model_dump(mode="json")
    payload["environment_contract_sha256"] = None
    payload["receipt_digest"] = decision_digest(
        {key: value for key, value in payload.items() if key != "receipt_digest"}
    )
    with pytest.raises(ValueError, match="requires exact environment hashes"):
        ReferencePhase6ResourceReceipt.model_validate(payload)


def test_phase6_runner_derives_canonical_role_from_verified_identity(
    tmp_path: Path,
) -> None:
    verification = EnvironmentVerification(
        contract_id="trace-reference-python311-development-v1",
        contract_sha256="a" * 64,
        lock_sha256="b" * 64,
        interpreter="3.11.14",
        platform_system="Linux",
        platform_machine="x86_64",
        checked_distributions={},
        mismatches=[],
    )

    receipt = phase6_acceptance._resource_receipt(
        time.perf_counter(),
        tmp_path,
        verification,
    )

    assert receipt.measurement_role == "canonical"
    assert receipt.environment_contract_sha256 == "a" * 64
    assert receipt.dependency_lock_sha256 == "b" * 64
    assert receipt.canonical_gate_status == "passed"


def test_phase6_fault_receipt_requires_complete_offline_g3_binding() -> None:
    report = _g3_report()
    body: dict[str, Any] = {
        "schema_version": "delta-reference-phase6-fault-receipt-v1",
        "scientific_status": "development-integration-check-not-validation-evidence",
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "seed": 20260812,
        "offline_execution_guarded": True,
        "integrity_report": report.model_dump(mode="json"),
        "all_checks_pass": True,
    }
    receipt = ReferencePhase6FaultReceipt(
        **body,
        receipt_digest=decision_digest(body),
    )

    assert receipt.integrity_report == report
    with pytest.raises(ValueError, match="fault status"):
        ReferencePhase6FaultReceipt.model_validate(
            {
                **receipt.model_dump(mode="json"),
                "all_checks_pass": False,
                "receipt_digest": decision_digest(
                    {
                        **body,
                        "all_checks_pass": False,
                    }
                ),
            }
        )


def test_phase6_axis_digest_and_stage_partition_fail_closed() -> None:
    result = _axis("sigma")
    payload = result.model_dump(mode="json")
    payload["evidence_digest"] = "0" * 64
    with pytest.raises(ValueError, match="axis result digest"):
        ReferencePhase6AxisResult.model_validate(payload)

    payload = result.model_dump(mode="json")
    payload["changed_stage_names"] = payload["unchanged_stage_names"]
    payload["evidence_digest"] = decision_digest(
        {key: value for key, value in payload.items() if key != "evidence_digest"}
    )
    with pytest.raises(ValueError, match="both changed and unchanged"):
        ReferencePhase6AxisResult.model_validate(payload)


def test_phase6_axis_harness_covers_all_eight_approved_mechanisms() -> None:
    scenario = generate_reference_scenario(ROOT, seed=20260812)

    results = build_reference_phase6_axis_results(ROOT, scenario)

    assert tuple(item.axis for item in results) == REFERENCE_PHASE6_AXIS_IDS
    assert all(item.passed for item in results)
    assert all(item.keyed_draw_identity_preserved for item in results)
    assert all(item.observed_digests for item in results)
