from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from trace_jepa.contracts import ActionInstance, Claim, ClaimLayer, WorldModelEvidence
from trace_jepa.runtime import PolicyConfig, PolicyEngine, TraceRuntime
from trace_reference.runtime import (
    ReferenceCommitmentLog,
    ReferenceEvidenceLedger,
    ReferenceTraceRepository,
)

NOW = datetime(2026, 1, 15, 12, tzinfo=UTC)


def _evidence(evidence_id: str = "reference-evidence-001") -> WorldModelEvidence:
    return WorldModelEvidence(
        evidence_id=evidence_id,
        rollout_id="reference-rollout-001",
        encoder_version="reference-fixture-encoder-v1",
        fusion_version="reference-fixture-fusion-v1",
        predictor_version="reference-fixture-predictor-v1",
        semantic_probe_versions=(),
        training_snapshot="reference-development-fixture-v1",
        observation_window_hash="1" * 64,
        fleet_state_hash="2" * 64,
        candidate_plan_id="reference-plan-001",
        action_schema_version="delta-reference-actions-v1",
        rollout_horizon=2,
        predicted_claims=("route is reachable",),
        uncertainty=0.1,
        model_support=0.95,
        out_of_distribution_score=0.05,
        rollout_consistency=0.95,
        reachability_evidence={"route_id": "route-reference-001", "state": "open"},
        calibration_version="reference-fixture-calibration-v1",
        assumptions=("route_report_is_fresh",),
        observation_age_s=60,
        created_at=NOW,
    )


def _runtime(root: Path) -> TraceRuntime:
    policy = PolicyEngine(
        PolicyConfig(
            policy_version="trace-reference-storage-test-v1",
            min_model_support=0.8,
            max_ood_score=0.2,
            max_uncertainty=0.2,
            max_rollout_horizon=8,
            max_observation_age_s=300,
        )
    )
    return TraceRuntime(
        repository=ReferenceTraceRepository(root),
        ledger=ReferenceEvidenceLedger(root),
        commitments=ReferenceCommitmentLog(root),
        policy=policy,
    )


def test_reference_trace_storage_round_trips_full_closure(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    claim = Claim(
        claim_id="reference-claim-001",
        layer=ClaimLayer.PREDICTIVE,
        text="The registered route remains reachable.",
        grounding={"route_id": "route-reference-001"},
        confidence=0.95,
        confidence_semantics="development fixture",
        created_at=NOW,
    )
    record, evaluation = runtime.assess(
        claim=claim,
        evidence=_evidence(),
        action_name="inspect_levee",
        reversible=False,
        authority_present=True,
        lineage_key="reference-storage-test-lineage",
        created_at=NOW,
    )
    consumed = runtime.consume(
        record,
        evaluation,
        consumer="reference-mission-controller",
        consumer_action_id="reference-consumer-action-001",
        created_at=NOW,
    )
    commitment = runtime.commit(
        record=consumed,
        action=ActionInstance(
            action_id="reference-action-001",
            action_type="inspect_levee",
            actor_id="RR-0123456789abcdef",
            destination="public-incident-cluster-001",
            route_id="route-reference-001",
        ),
        commitment_id="reference-commitment-001",
        created_at=NOW,
    )

    repository = ReferenceTraceRepository(tmp_path)
    commitments = ReferenceCommitmentLog(tmp_path)
    evidence = ReferenceEvidenceLedger(tmp_path)
    assert repository.verify_chain()
    assert commitments.verify_chain()
    assert repository.get(consumed.record_id).record_version == consumed.record_version
    assert commitments.all() == [commitment]
    assert evidence.get("reference-evidence-001") == _evidence()
    assert repository.prefix_digest != "GENESIS"
    assert commitments.prefix_digest != "GENESIS"
    assert evidence.prefix_digest != "GENESIS"


def test_reference_trace_storage_is_idempotent_and_detects_tampering(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    claim = Claim(
        claim_id="reference-claim-001",
        layer=ClaimLayer.PREDICTIVE,
        text="The registered route remains reachable.",
        created_at=NOW,
    )
    record, _ = runtime.assess(
        claim=claim,
        evidence=_evidence(),
        action_name="inspect_levee",
        reversible=False,
        authority_present=True,
        lineage_key="reference-storage-test-lineage",
        created_at=NOW,
    )
    assert runtime.repository.write(record) == record

    trace_path = tmp_path / "trace_records.jsonl"
    original = trace_path.read_text("utf-8")
    tampered = original.replace(
        "The registered route remains reachable.",
        "The tampered route remains reachable.",
    )
    assert tampered != original
    trace_path.write_text(tampered)
    with pytest.raises(ValueError, match="chain is invalid"):
        ReferenceTraceRepository(tmp_path)


def test_reference_trace_storage_rejects_unsafe_ids_and_symlink_roots(tmp_path: Path) -> None:
    ledger = ReferenceEvidenceLedger(tmp_path)
    with pytest.raises(ValueError, match="ID is unsafe"):
        ledger.put(_evidence("../escape"))

    target = tmp_path / "target"
    target.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="root must not be a symlink"):
        ReferenceTraceRepository(alias)


def test_reference_evidence_index_detects_content_tampering_and_orphans(tmp_path: Path) -> None:
    ledger = ReferenceEvidenceLedger(tmp_path)
    ledger.put(_evidence())
    original_prefix = ledger.prefix_digest
    assert ReferenceEvidenceLedger(tmp_path).prefix_digest == original_prefix

    evidence_path = tmp_path / "evidence/reference-evidence-001.json"
    evidence_path.write_text(evidence_path.read_text("utf-8").replace("route", "r0ute"))
    with pytest.raises(ValueError, match="index chain is invalid"):
        ReferenceEvidenceLedger(tmp_path)

    clean = tmp_path / "clean"
    clean.mkdir()
    ReferenceEvidenceLedger(clean)
    (clean / "evidence/orphan.json").write_text("{}")
    with pytest.raises(ValueError, match="index chain is invalid"):
        ReferenceEvidenceLedger(clean)
