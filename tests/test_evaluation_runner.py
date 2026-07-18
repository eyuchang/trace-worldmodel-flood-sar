from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from trace_jepa.evaluation.runner import (
    COMPLETION_SCHEMA_VERSION,
    RUN_SCHEMA_VERSION,
    CompletionMarker,
    RunRequest,
    _artifact_hashes,
    resolve_policy,
    run_one_sync,
    validate_run_directory,
)
from trace_jepa.evaluation.cached_storage import CachedEventStore
from trace_jepa.workbench.models import EventType, SimulationEvent
from trace_jepa.workbench.store import EventStore
from trace_jepa.util import canonical_json, sha256_value


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCENARIO = REPOSITORY_ROOT / "configs/scenarios/riverside_flood_dynamic_v2.yaml"
SHOCK_ROOT = REPOSITORY_ROOT / "configs/shocks"
PROTOCOL = REPOSITORY_ROOT / "tests/fixtures/experiment_protocol_stub.txt"
AMENDED_WORKLOAD = (
    REPOSITORY_ROOT / "configs/workloads/g2_later_horizon_v1.yaml"
)


def _request(
    tmp_path: Path,
    *,
    policy: str = "none",
    seed: int = 1,
    resume: bool = True,
    forcing_noise_std: float = 0.35,
) -> RunRequest:
    return RunRequest(
        regime="R-B",
        policy=policy,
        seed=seed,
        scenario_path=SCENARIO,
        shock_registry_root=SHOCK_ROOT,
        protocol_path=PROTOCOL,
        output_root=tmp_path / "runs",
        duration_s=3.0,
        tick_s=1.0,
        requested_speed=50.0,
        forcing_noise_std=forcing_noise_std,
        resume=resume,
    )


def _amended_request(
    tmp_path: Path,
    *,
    policy: str = "none",
    seed: int = 21,
) -> RunRequest:
    return RunRequest(
        regime="R-B",
        policy=policy,
        seed=seed,
        scenario_path=SCENARIO,
        shock_registry_root=SHOCK_ROOT,
        protocol_path=PROTOCOL,
        output_root=tmp_path / "amended-runs",
        evaluation_workload_path=AMENDED_WORKLOAD,
        protocol_amendment_id="g2-workload-amendment-1",
        duration_s=7800.0,
        tick_s=1.0,
        requested_speed=50.0,
        forcing_noise_std=0.35,
    )


def _rehash_payloads(path: Path, payloads: list[dict]) -> None:
    previous_hash = "GENESIS"
    envelopes = []
    for sequence, payload in enumerate(payloads, start=1):
        body = {
            "sequence": sequence,
            "previous_hash": previous_hash,
            "payload_hash": sha256_value(payload),
            "payload": payload,
        }
        envelope = {**body, "entry_hash": sha256_value(body)}
        envelopes.append(envelope)
        previous_hash = envelope["entry_hash"]
    path.write_text(
        "".join(canonical_json(envelope) + "\n" for envelope in envelopes),
        encoding="utf-8",
    )


def _rewrite_completion(directory: Path) -> None:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    body = {
        "schema_version": COMPLETION_SCHEMA_VERSION,
        "run_schema_version": RUN_SCHEMA_VERSION,
        "run_id": manifest["run_id"],
        "run_fingerprint": manifest["run_fingerprint"],
        "artifact_sha256": _artifact_hashes(directory),
    }
    marker = CompletionMarker(**body, completion_hash=sha256_value(body))
    (directory / "COMPLETED.json").write_text(
        json.dumps(marker.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_runner_publishes_complete_validated_atomic_cell(tmp_path: Path) -> None:
    directory = run_one_sync(_request(tmp_path))
    valid, errors = validate_run_directory(directory)
    assert valid, errors

    required = {
        "COMPLETED.json",
        "commitment_ledger.jsonl",
        "commitment_unit_ledger.jsonl",
        "environment.json",
        "events.jsonl",
        "exogenous.jsonl",
        "manifest.json",
        "metrics.json",
        "refresh_ledger.jsonl",
    }
    assert required <= {path.name for path in directory.iterdir() if path.is_file()}
    assert not list(directory.rglob("*.tmp"))
    assert not list(directory.parent.glob("*.staging-*"))

    metrics = json.loads((directory / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["schema_version"] == "trace-run-metrics-v2"
    assert metrics["completed"] is True
    assert metrics["terminal_simulation_time"] == pytest.approx(3.0)
    assert metrics["commitment"]["proposed"] > 0
    assert metrics["commitment"]["proposal_records"] >= metrics["commitment"][
        "proposed"
    ]
    assert metrics["commitment"]["proposed"] == sum(
        metrics["commitment"][key] for key in ("executed", "held", "escalated")
    )
    exogenous_rows = (directory / "exogenous.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    assert len(exogenous_rows) == 3
    assert metrics["verification_cost"] == {
        "common_baseline_acquisitions": 0,
        "common_baseline_cost": 0.0,
        "discretionary_acquisitions": 0,
        "discretionary_cost": 0.0,
        "total_acquisitions": 0,
        "total_cost": 0.0,
    }


def test_cached_event_store_is_byte_identical_to_frozen_store(
    tmp_path: Path,
) -> None:
    frozen = EventStore(tmp_path / "frozen.jsonl")
    cached = CachedEventStore(tmp_path / "cached.jsonl")
    events = [
        SimulationEvent(
            run_id="run",
            sequence=sequence,
            simulation_time=float(sequence - 1),
            source="test",
            event_type=EventType.TICK,
            payload={"dt": 1.0},
        )
        for sequence in (1, 2)
    ]
    for event in events:
        frozen.append(event)
        cached.append(event)
    assert frozen.path.read_bytes() == cached.path.read_bytes()
    assert frozen.verify_chain()
    assert cached.verify_chain()
    assert cached.all() == events


def test_resume_reuses_only_a_valid_complete_cell(tmp_path: Path) -> None:
    request = _request(tmp_path)
    directory = run_one_sync(request)
    completion_before = (directory / "COMPLETED.json").read_bytes()
    modification_before = (directory / "COMPLETED.json").stat().st_mtime_ns

    resumed = run_one_sync(request)
    assert resumed == directory
    assert (directory / "COMPLETED.json").read_bytes() == completion_before
    assert (directory / "COMPLETED.json").stat().st_mtime_ns == modification_before


def test_tampered_cell_is_quarantined_and_recomputed(tmp_path: Path) -> None:
    request = _request(tmp_path)
    directory = run_one_sync(request)
    with (directory / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("{}\n")
    valid, _ = validate_run_directory(directory)
    assert not valid

    replacement = run_one_sync(request)
    valid, errors = validate_run_directory(replacement)
    assert valid, errors
    quarantines = list(replacement.parent.glob(".1.quarantine-*"))
    assert len(quarantines) == 1
    assert (quarantines[0] / "events.jsonl").read_text(encoding="utf-8").endswith(
        "{}\n"
    )


def test_independent_truth_replay_rejects_self_consistent_false_stale_label(
    tmp_path: Path,
) -> None:
    directory = run_one_sync(_request(tmp_path))
    envelopes = [
        json.loads(line)
        for line in (directory / "events.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    payloads = [envelope["payload"] for envelope in envelopes]
    action = next(payload for payload in payloads if payload["event_type"] == "ACTION_STARTED")
    assert action["payload"]["truth_safe_at_execution"] is True
    action["payload"]["executed_stale"] = True
    _rehash_payloads(directory / "events.jsonl", payloads)
    _rewrite_completion(directory)

    valid, errors = validate_run_directory(directory)
    assert not valid
    assert any("replay oracle" in error for error in errors)


def test_validator_rejects_rehashed_commitment_unit_tampering(
    tmp_path: Path,
) -> None:
    directory = run_one_sync(_request(tmp_path))
    unit_path = directory / "commitment_unit_ledger.jsonl"
    envelopes = [json.loads(line) for line in unit_path.read_text().splitlines()]
    payloads = [envelope["payload"] for envelope in envelopes]
    payloads[0]["proposal_record_count"] += 1
    _rehash_payloads(unit_path, payloads)
    _rewrite_completion(directory)

    valid, errors = validate_run_directory(directory)
    assert not valid
    assert any("commitment-unit ledger" in error for error in errors)


def test_resume_never_reuses_a_different_noise_setting(tmp_path: Path) -> None:
    first = run_one_sync(_request(tmp_path, forcing_noise_std=0.35))
    first_manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
    replacement = run_one_sync(_request(tmp_path, forcing_noise_std=0.70))
    second_manifest = json.loads(
        (replacement / "manifest.json").read_text(encoding="utf-8")
    )
    assert first_manifest["run_fingerprint"] != second_manifest["run_fingerprint"]
    assert (
        second_manifest["scientific_identity"]["request"]["forcing_noise_std"]
        == pytest.approx(0.70)
    )
    assert len(list(replacement.parent.glob(".1.quarantine-*"))) == 1


def test_common_exogenous_stream_is_identical_across_policies(
    tmp_path: Path,
) -> None:
    policies = ("none", "fixed-k:5", "clock:0.5", "adaptive:1")
    projections = []
    for policy in policies:
        directory = run_one_sync(_request(tmp_path, policy=policy))
        projections.append((directory / "exogenous.jsonl").read_bytes())
    assert len(set(projections)) == 1


def test_amended_workload_occurs_exactly_once_and_has_no_time_zero_demand(
    tmp_path: Path,
) -> None:
    directory = run_one_sync(_amended_request(tmp_path))
    valid, errors = validate_run_directory(directory)
    assert valid, errors
    events = EventStore(directory / "events.jsonl").all()

    assert not any(
        event.event_type == EventType.EMERGENCY_CALL
        and event.source == "evaluation_harness"
        for event in events
    )
    common_gauge = [
        event for event in events if event.source == "common_baseline_gauge"
    ]
    assert [event.event_type for event in common_gauge] == [
        EventType.GAUGE_POLL,
        EventType.OBSERVATION,
        EventType.EVIDENCE_ACQUIRED,
    ]
    assert [event.simulation_time for event in common_gauge] == [
        6420.0,
        6425.0,
        6425.0,
    ]
    incidents = [
        event
        for event in events
        if event.source == "registered_workload_scheduler"
    ]
    assert len(incidents) == 1
    assert incidents[0].event_type == EventType.EMERGENCY_CALL
    assert incidents[0].simulation_time == 6443.0
    assert incidents[0].payload["group_id"] == "group_riverside_late_6443"
    assert any(
        event.event_type == EventType.PLAN_PROPOSED
        and event.simulation_time >= 6443.0
        for event in events
    )
    metrics = json.loads((directory / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["common_baseline_evidence"] == {
        "acquisitions": 1,
        "usable_acquisitions": 1,
        "total_cost": 0.2,
    }
    assert metrics["verification_cost"] == {
        "common_baseline_acquisitions": 1,
        "common_baseline_cost": 0.2,
        "discretionary_acquisitions": 0,
        "discretionary_cost": 0.0,
        "total_acquisitions": 1,
        "total_cost": 0.2,
    }


def test_amended_workload_exogenous_projection_is_policy_invariant(
    tmp_path: Path,
) -> None:
    projections = []
    for policy in ("none", "fixed-k:45", "clock:0.55", "adaptive:1"):
        directory = run_one_sync(_amended_request(tmp_path, policy=policy))
        projections.append((directory / "exogenous.jsonl").read_bytes())
    assert len(set(projections)) == 1


def test_validator_rejects_rehashed_mutated_workload_event(tmp_path: Path) -> None:
    directory = run_one_sync(_amended_request(tmp_path))
    envelopes = [
        json.loads(line)
        for line in (directory / "events.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    payloads = [envelope["payload"] for envelope in envelopes]
    incident = next(
        payload
        for payload in payloads
        if payload["source"] == "registered_workload_scheduler"
    )
    incident["payload"]["scheduled_at"] = 6444.0
    _rehash_payloads(directory / "events.jsonl", payloads)
    _rewrite_completion(directory)

    valid, errors = validate_run_directory(directory)
    assert not valid
    assert any("workload incident payload" in error for error in errors)


def test_validator_rejects_rehashed_unregistered_amended_demand(
    tmp_path: Path,
) -> None:
    directory = run_one_sync(_amended_request(tmp_path))
    envelopes = [
        json.loads(line)
        for line in (directory / "events.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    payloads = [envelope["payload"] for envelope in envelopes]
    incident = next(
        payload
        for payload in payloads
        if payload["source"] == "registered_workload_scheduler"
    )
    incident["source"] = "operator_ui"
    _rehash_payloads(directory / "events.jsonl", payloads)
    _rewrite_completion(directory)

    valid, errors = validate_run_directory(directory)
    assert not valid
    assert any("unregistered demand" in error for error in errors)


def test_validator_rejects_rehashed_unregistered_shock(tmp_path: Path) -> None:
    directory = run_one_sync(_request(tmp_path))
    envelopes = [
        json.loads(line)
        for line in (directory / "events.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    payloads = [envelope["payload"] for envelope in envelopes]
    event = next(
        payload for payload in payloads if payload["event_type"] == "RUN_PAUSED"
    )
    event["event_type"] = "INJECT_SHOCK"
    event["source"] = "operator_ui"
    event["scenario_level"] = "S4"
    event["visibility"] = "truth"
    event["payload"] = {
        "shock_id": "unregistered",
        "scheduled_at": event["simulation_time"],
        "shock_type": "wind_shift",
        "severity": 0.5,
        "target": None,
        "registry_hash": "not-registered",
    }
    _rehash_payloads(directory / "events.jsonl", payloads)
    _rewrite_completion(directory)

    valid, errors = validate_run_directory(directory)
    assert not valid
    assert any("unregistered shock source" in error for error in errors)


def test_validator_rejects_rehashed_workload_visibility_change(
    tmp_path: Path,
) -> None:
    directory = run_one_sync(_amended_request(tmp_path))
    envelopes = [
        json.loads(line)
        for line in (directory / "events.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    payloads = [envelope["payload"] for envelope in envelopes]
    request = next(
        payload
        for payload in payloads
        if payload["source"] == "common_baseline_gauge"
        and payload["event_type"] == "GAUGE_POLL"
    )
    request["visibility"] = "both"
    _rehash_payloads(directory / "events.jsonl", payloads)
    _rewrite_completion(directory)

    valid, errors = validate_run_directory(directory)
    assert not valid
    assert any("gauge request has invalid visibility" in error for error in errors)


def test_validator_rejects_rehashed_event_time_reversal(tmp_path: Path) -> None:
    directory = run_one_sync(_request(tmp_path))
    envelopes = [
        json.loads(line)
        for line in (directory / "events.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    payloads = [envelope["payload"] for envelope in envelopes]
    payloads[-1]["simulation_time"] = 0.0
    _rehash_payloads(directory / "events.jsonl", payloads)
    _rewrite_completion(directory)

    valid, errors = validate_run_directory(directory)
    assert not valid
    assert any("not nondecreasing" in error for error in errors)


@pytest.mark.parametrize(
    "spec",
    (
        "../none",
        "fixed-k:../../etc/passwd",
        "fixed-k:nan",
        "clock:1.1",
        "adaptive:7.5",
        "adaptive:inf",
    ),
)
def test_policy_parser_rejects_unsafe_or_out_of_protocol_specs(spec: str) -> None:
    with pytest.raises(ValueError):
        resolve_policy(spec)


def test_day1_runner_blocks_nondevelopment_seeds(tmp_path: Path) -> None:
    assert _amended_request(tmp_path, seed=41).seed == 41
    assert _amended_request(tmp_path, seed=60).seed == 60
    with pytest.raises(ValidationError):
        _request(tmp_path, seed=101)
    with pytest.raises(ValidationError):
        _request(tmp_path, seed=1001)
    with pytest.raises(ValidationError):
        _request(tmp_path, seed=21)
    with pytest.raises(ValidationError):
        _amended_request(tmp_path, seed=20)
    with pytest.raises(ValidationError):
        _amended_request(tmp_path, seed=61)
