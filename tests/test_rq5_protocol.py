"""RQ5 protocol registration and freeze-discipline contract tests."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from trace_jepa.experimental import (
    HeldOutGateError,
    ProtocolRegistry,
    load_rq5_protocol,
    require_protocol_before_held_out,
)
from trace_jepa.experimental.protocols import RQ5Protocol, default_rq5_protocol


def test_rq5_protocol_declares_required_scenarios_arms_measures_and_invariant():
    protocol = load_rq5_protocol(Path("configs/protocols/rq5_revalidation_guard.yaml"))
    assert protocol.protocol_id == "RQ5"
    scenario_ids = {item.scenario_id for item in protocol.scenarios}
    assert scenario_ids == {"control", "mid_mission_replacement"}
    arms = {item.arm_id: item.revalidation_guard_enabled for item in protocol.arms}
    assert arms == {"gate_without_guard": False, "gate_with_guard": True}
    measure_ids = {item.measure_id for item in protocol.measures}
    assert "high_consequence_clear_on_bad_version" in measure_ids
    assert "held_or_escalated_pending_revalidation" in measure_ids
    assert "time_replacement_to_restored_operation" in measure_ids
    assert "additional_verification_cost" in measure_ids
    assert "mission_completion" in measure_ids
    assert "rescued_people" in measure_ids
    assert "exact_replayability" in measure_ids
    assert protocol.invariant.invariant_id == "no_clear_on_superseded_or_unqualified"
    assert protocol.freeze.requires_registration_before_held_out is True
    assert protocol.freeze.shared_with == ("RQ1", "RQ2", "RQ3", "RQ4")
    assert protocol.content_hash is not None


def test_default_rq5_protocol_matches_yaml_shape():
    default = default_rq5_protocol()
    loaded = load_rq5_protocol(Path("configs/protocols/rq5_revalidation_guard.yaml"))
    assert default.protocol_id == loaded.protocol_id
    assert {s.scenario_id for s in default.scenarios} == {
        s.scenario_id for s in loaded.scenarios
    }


def test_protocol_must_be_registered_before_held_out_run(tmp_path: Path):
    registry = ProtocolRegistry(store_path=tmp_path)
    protocol = load_rq5_protocol(Path("configs/protocols/rq5_revalidation_guard.yaml"))

    with pytest.raises(HeldOutGateError):
        require_protocol_before_held_out(registry, "RQ5", held_out=True)

    digest = registry.register(protocol)
    assert registry.is_registered("RQ5")
    assert digest == protocol.content_hash
    require_protocol_before_held_out(registry, "RQ5", held_out=True)

    # Non-held-out exploratory runs remain allowed without registration.
    empty = ProtocolRegistry()
    require_protocol_before_held_out(empty, "RQ5", held_out=False)


def test_rq5_campaign_witnesses_guard_invariant(tmp_path: Path):
    from trace_jepa.experimental.campaign_rq5 import run_rq5_campaign

    report = run_rq5_campaign(held_out=True, store=tmp_path)
    assert report["invariant_holds"] is True
    guarded_replacement = report["results"][
        "mid_mission_replacement::gate_with_guard"
    ]
    unguarded_replacement = report["results"][
        "mid_mission_replacement::gate_without_guard"
    ]
    assert guarded_replacement["high_consequence_clear_on_bad_version"] == 0
    assert guarded_replacement["held_or_escalated_pending_revalidation"] >= 1
    assert unguarded_replacement["high_consequence_clear_on_bad_version"] >= 1
    # Control bounds overhead when no replacement occurs.
    guarded_control = report["results"]["control::gate_with_guard"]
    assert guarded_control["held_or_escalated_pending_revalidation"] == 0
    assert guarded_control["additional_verification_cost"] == 0.0


def test_rq5_rejects_protocol_missing_guard_arm_pair():
    protocol = default_rq5_protocol()
    payload = protocol.model_dump(mode="json")
    payload["arms"] = [
        {
            "arm_id": "only_unguarded",
            "description": "missing guarded arm",
            "revalidation_guard_enabled": False,
        }
    ]
    with pytest.raises(ValidationError):
        RQ5Protocol.model_validate(payload)

