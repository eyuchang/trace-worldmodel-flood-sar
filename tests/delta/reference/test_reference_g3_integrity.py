from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from trace_reference import load_reference_fault_schedule
from trace_reference.generation import generate_reference_scenario
from trace_reference.runtime import build_reference_runtime
from trace_reference.runtime.mission_state import reference_scenario_input_digest
from trace_reference.validation import (
    ReferenceG3IntegrityInput,
    ReferenceG3IntegrityReport,
    build_reference_g3_integrity_report,
)

ROOT = Path(__file__).resolve().parents[3]
FAULT_SCHEDULE = Path("data/scenario/delta/reference_protocol/reference_fault_schedule_v1.json")
CRASH_AT_S = 187_200


@pytest.fixture(scope="module")
def integrity_fixture(tmp_path_factory: pytest.TempPathFactory):
    scenario = generate_reference_scenario(ROOT, seed=20260812)
    schedule = load_reference_fault_schedule(ROOT, FAULT_SCHEDULE)

    uninterrupted_root = tmp_path_factory.mktemp("reference-g3-uninterrupted")
    faulted_bundle = build_reference_runtime(
        scenario,
        uninterrupted_root,
        fault_schedule=schedule,
    )
    faulted_run = faulted_bundle.runtime.run()

    restarted_root = tmp_path_factory.mktemp("reference-g3-restarted")
    before_crash = build_reference_runtime(
        scenario,
        restarted_root,
        fault_schedule=schedule,
    )
    before_crash.runtime.run(through_s=CRASH_AT_S)
    checkpoint = before_crash.runtime.checkpoint(register_crash=True)
    restarted_bundle = build_reference_runtime(
        scenario,
        restarted_root,
        events=before_crash.event_log.events,
        fault_schedule=schedule,
        restart_checkpoint=checkpoint,
    )
    restarted_run = restarted_bundle.runtime.run()
    values = ReferenceG3IntegrityInput(
        scenario_seed=20260812,
        scientific_input_aggregate_sha256="1" * 64,
        faulted_scenario_input_digest=reference_scenario_input_digest(scenario),
        restart_checkpoint_scenario_input_digest=checkpoint.scenario_input_digest,
        schedule=schedule,
        faulted_run=faulted_run,
        faulted_bundle=faulted_bundle,
        restarted_run=restarted_run,
        restarted_bundle=restarted_bundle,
    )
    return values


def test_g3_integrity_report_verifies_registered_fault_restart(integrity_fixture) -> None:
    report = build_reference_g3_integrity_report(integrity_fixture)

    assert report.all_checks_pass
    assert report.scientific_input_aggregate_sha256 == "1" * 64
    assert report.scenario_input_digest == integrity_fixture.faulted_scenario_input_digest
    assert report.fault_coverage_complete
    assert len(report.expected_fault_families) == 11
    assert report.faulted_counts.allocations > 0
    assert report.faulted_counts.refusals > 0
    assert report.faulted_counts.acquisition_requests > 0
    assert report.faulted_counts.compensations == 1
    assert report.faulted_counts.consistency_debts == 1
    assert ReferenceG3IntegrityReport.model_validate_json(report.model_dump_json()) == report


def test_g3_integrity_report_exposes_exogenous_digest_disagreement(integrity_fixture) -> None:
    mismatched = replace(
        integrity_fixture,
        restart_checkpoint_scenario_input_digest="0" * 64,
    )

    report = build_reference_g3_integrity_report(mismatched)

    assert not report.exogenous_inputs_byte_equivalent
    assert not report.all_checks_pass


def test_g3_integrity_report_digest_fails_closed(integrity_fixture) -> None:
    report = build_reference_g3_integrity_report(integrity_fixture)

    with pytest.raises(ValueError, match="report digest"):
        ReferenceG3IntegrityReport.model_validate(
            {**report.model_dump(mode="json"), "report_digest": "0" * 64}
        )
