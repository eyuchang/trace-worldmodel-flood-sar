from pathlib import Path

import pytest

from trace_jepa.contracts import (
    ActionInstance,
    Claim,
    ClaimLayer,
    Commitment,
    TraceRecord,
    TraceStatus,
)
from trace_jepa.runtime.storage import CommitmentLog


def test_commitment_without_consumer_action_is_blocked(tmp_path: Path):
    log = CommitmentLog(tmp_path / "commitments.jsonl")
    record = TraceRecord(
        policy_version="test-policy",
        claim=Claim(layer=ClaimLayer.PREDICTIVE, text="A route is open."),
        evidence_refs=("evidence-1",),
        final_status=TraceStatus.ACCEPT,
    )
    commitment = Commitment(
        action=ActionInstance(
            action_type="dispatch_rescue_boat",
            actor_id="rescue_boat_1",
            origin="rescue_base",
            destination="riverside_apartments",
            route_id="south_detour",
            parameters={"people_count": 4},
        ),
        authorizing_record_id=record.record_id,
        authorizing_record_version=record.record_version,
        consumer_policy_version="test-policy",
    )
    with pytest.raises(ValueError, match="closure violation"):
        log.append(commitment, record)
