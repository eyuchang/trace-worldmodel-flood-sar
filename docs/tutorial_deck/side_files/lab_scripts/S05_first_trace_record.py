from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from trace_jepa.contracts import (
    Claim,
    ClaimLayer,
    TraceRecord,
    TraceStatus,
    WorldModelEvidence,
)
from trace_jepa.runtime.storage import EvidenceLedger, TraceRepository


def digest(text: str) -> str:
    """Return a stable SHA-256 identifier for a teaching artifact."""
    return sha256(text.encode("utf-8")).hexdigest()


# Fixed timestamp keeps this teaching example idempotent.
STAMP = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

run_dir = Path("artifacts/runs/lab01_first_record")
ledger = EvidenceLedger(run_dir / "evidence")
repository = TraceRepository(run_dir / "records" / "trace.jsonl")

# 1. Record what the world model predicted.
evidence = WorldModelEvidence(
    evidence_id="wm-evidence-lab01-north-route-v1",
    rollout_id="rollout-lab01-north-route-v1",
    encoder_version="mock-encoder-v1",
    fusion_version="flood-fusion-v1",
    predictor_version="toy-predictor-v1",
    semantic_probe_versions=("route-open-probe-v1",),
    training_snapshot="synthetic-flood-training-v1",
    observation_window_hash=digest("unverified north channel observation window"),
    fleet_state_hash=digest("drone available; boat available; north unknown"),
    candidate_plan_id="north-direct",
    action_schema_version="flood-actions-v1",
    rollout_horizon=3,
    predicted_claims=(
        "The North Channel is open for rescue-boat dispatch over the next three steps.",
    ),
    uncertainty=0.08,
    model_support=0.28,
    out_of_distribution_score=0.82,
    rollout_consistency=0.91,
    calibration_version="route-calibration-v1",
    assumptions=(
        "The latest map is current.",
        "The route geometry is represented in the training distribution.",
    ),
    observation_age_s=15.0,
    created_at=STAMP,
)
ledger.put(evidence)

# 2. State the mission claim that the prediction would license.
claim = Claim(
    claim_id="claim-lab01-north-route-open",
    layer=ClaimLayer.PREDICTIVE,
    text="The North Channel is open for rescue-boat dispatch over the next three steps.",
    grounding={
        "route_id": "north_channel",
        "asset_type": "rescue_boat",
        "horizon_steps": 3,
    },
    confidence=0.92,
    confidence_semantics=(
        "Teaching fixture copied from predicted plan success; later stages separate "
        "plan success from calibrated claim probability."
    ),
    created_at=STAMP,
)

# 3. Write the first TRACE record. This hand-authored version intentionally
#    defers the irreversible dispatch because support gates fail.
record = TraceRecord(
    record_id="trace-lab01-north-route-open",
    record_version=1,
    policy_version="trace-flood-v1",
    claim=claim,
    evidence_refs=(evidence.evidence_id,),
    final_status=TraceStatus.DEFER,
    failed_gates=("model_support", "out_of_distribution"),
    missing_items=("A current direct observation of the North Channel.",),
    repair="Send the survey drone to verify the North Channel before dispatching the boat.",
    metadata={"candidate_plan_id": "north-direct", "teaching_example": True},
    created_at=STAMP,
)
repository.write(record)

# 4. Load and verify the stored objects.
loaded_evidence = ledger.get(evidence.evidence_id)
loaded_record = repository.get(record.record_id, record.record_version)

print(f"Evidence stored: {loaded_evidence.evidence_id}")
print(f"Predicted plan success: 0.92")
print(f"Claim confidence: {loaded_record.claim.confidence:.2f}")
print(
    f"Evidence support/OOD: {loaded_evidence.model_support:.2f} / "
    f"{loaded_evidence.out_of_distribution_score:.2f}"
)
print(f"Record stored: {loaded_record.record_id} version {loaded_record.record_version}")
print(f"TRACE status: {loaded_record.final_status.value}")
print(f"Failed gates: {', '.join(loaded_record.failed_gates)}")
print(f"Hash chain valid: {repository.verify_chain()}")
print(f"Records in repository: {len(repository.all())}")
