from __future__ import annotations

import json

import pytest

from trace_reference.domain import ReferenceEventType, ReferenceEventVisibility
from trace_reference.runtime import ReferenceEventLog


def _public_report(report_id: str, *, description: str = "water at doorway") -> dict[str, object]:
    return {
        "schema_version": "delta-reference-public-report-fixture-v1",
        "report_id": report_id,
        "taxonomy": "C-STR",
        "description": description,
    }


def test_public_mission_events_replay_and_restart_exactly() -> None:
    log = ReferenceEventLog()
    log.append_public_artifact(
        at_s=1_000,
        event_type=ReferenceEventType.CALL_DELIVERED,
        artifact_id="RE-0000000000000001",
        artifact_schema_version="delta-reference-public-report-fixture-v1",
        artifact=_public_report("RE-0000000000000001"),
    )
    log.append_public_artifact(
        at_s=1_010,
        event_type=ReferenceEventType.COORDINATION_MESSAGE_DELIVERED,
        artifact_id="CD-0000000000000001",
        artifact_schema_version="delta-reference-coordination-v1",
        artifact={
            "schema_version": "delta-reference-coordination-v1",
            "delivery_id": "CD-0000000000000001",
            "evidence_id": "RE-0000000000000001",
        },
    )
    checkpoint = log.checkpoint(through_sequence=1)
    resumed = log.resume(checkpoint)
    for event in log.events[checkpoint.sequence :]:
        resumed.apply(event)
    replayed = log.replay()
    assert resumed.canonical_value() == replayed.canonical_value()
    report_json = replayed.public_mission_artifacts[ReferenceEventType.CALL_DELIVERED.value][
        "RE-0000000000000001"
    ]
    assert json.loads(report_json)["description"] == "water at doorway"


def test_public_artifact_replay_is_idempotent_but_rejects_identity_conflict() -> None:
    log = ReferenceEventLog()
    for description in ("water at doorway", "water at doorway"):
        log.append_public_artifact(
            at_s=1_000,
            event_type=ReferenceEventType.CALL_DELIVERED,
            artifact_id="RE-0000000000000001",
            artifact_schema_version="delta-reference-public-report-fixture-v1",
            artifact=_public_report("RE-0000000000000001", description=description),
        )
    assert len(log.replay().public_mission_artifacts["call_delivered"]) == 1

    log.append_public_artifact(
        at_s=1_001,
        event_type=ReferenceEventType.CALL_DELIVERED,
        artifact_id="RE-0000000000000001",
        artifact_schema_version="delta-reference-public-report-fixture-v1",
        artifact=_public_report("RE-0000000000000001", description="contradictory content"),
    )
    with pytest.raises(ValueError, match="reused with different content"):
        log.replay()


@pytest.mark.parametrize(
    "hidden_value",
    [
        {"truth_incident_id": "RI-0123456789abcdef"},
        {"nested": {"truth_person_ids": ["RP-0123456789abcdef"]}},
        {"ordinary_key": "RI-0123456789abcdef"},
    ],
)
def test_public_event_envelope_rejects_hidden_truth(hidden_value: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="hidden-truth"):
        ReferenceEventLog().append_public_artifact(
            at_s=1_000,
            event_type=ReferenceEventType.CALL_DELIVERED,
            artifact_id="RE-0000000000000001",
            artifact_schema_version="delta-reference-public-report-fixture-v1",
            artifact={"schema_version": "fixture", **hidden_value},
        )


def test_event_visibility_contract_fails_before_append() -> None:
    with pytest.raises(ValueError, match="hidden visibility"):
        ReferenceEventLog().append(
            at_s=1_000,
            event_type=ReferenceEventType.CALL_DELIVERED,
            visibility=ReferenceEventVisibility.HIDDEN_EVALUATION_ONLY,
            payload={"artifact_id": "not-accepted"},
        )
    with pytest.raises(ValueError, match="controller-visible visibility"):
        ReferenceEventLog().append(
            at_s=1_000,
            event_type=ReferenceEventType.HIDDEN_PHYSICAL_TRUTH,
            visibility=ReferenceEventVisibility.CONTROLLER_VISIBLE,
            payload={"breach": {}},
        )
