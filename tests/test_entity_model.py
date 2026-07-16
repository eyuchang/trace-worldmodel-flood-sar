from pathlib import Path

from trace_jepa.demo import run_demo


def test_summary_names_operational_entities_and_structured_dispatch(tmp_path: Path):
    summary = run_demo(tmp_path / "run")
    assert summary["entities"]["environment"] == "FloodEnvironment"
    assert summary["entities"]["mission_controller"] == "mission-controller-v2"
    assert summary["entities"]["fleet"] == ["survey_drone_1", "rescue_boat_1"]
    assert summary["entities"]["offline_scorer_in_control_loop"] is False

    initial = summary["initial_mission_controller_knowledge"]
    assert initial["routes"]["north_channel"]["report"] == "unknown"
    assert initial["north_route_open"] is None

    final_commitment = summary["final_commitment"]
    action = final_commitment["action"]
    assert action["action_type"] == "dispatch_rescue_boat"
    assert action["actor_id"] == "rescue_boat_1"
    assert action["origin"] == "rescue_base"
    assert action["destination"] == "riverside_apartments"
    assert action["route_id"] == "south_detour"
    assert action["parameters"]["people_count"] == 4
    assert action["parameters"]["deadline_s"] == 1200
