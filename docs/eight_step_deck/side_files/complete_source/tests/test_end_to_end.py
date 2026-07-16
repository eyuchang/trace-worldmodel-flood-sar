from pathlib import Path

from trace_jepa.demo import run_demo


def test_flood_demo_holds_unsupported_route_and_repairs_locally(tmp_path: Path):
    summary = run_demo(tmp_path / "run")
    initial = {item["plan_id"]: item for item in summary["initial_assessments"]}

    north = initial["north-direct"]
    assert north["predicted_plan_success_probability"] == 0.92
    assert north["claim_confidence"] == 0.92
    assert "Teaching proxy" in north["claim_confidence_semantics"]
    assert north["model_support"] == 0.28
    assert north["out_of_distribution_score"] == 0.82
    assert north["decision"] == "hold"
    assert north["repair"] == (
        "Send survey_drone_1 to verify north_channel before "
        "dispatching rescue_boat_1."
    )

    assert summary["first_selected_plan"] == "verify-north"
    assert summary["first_action"]["actor_id"] == "survey_drone_1"
    assert summary["first_action"]["route_id"] == "north_channel"
    assert summary["first_outcome"]["observations"]["route_status"] == "blocked"
    assert summary["revisions"][0]["status"] == "reject"

    assert summary["final_selected_plan"] == "south-detour"
    assert summary["final_action"]["actor_id"] == "rescue_boat_1"
    assert summary["final_action"]["destination"] == "riverside_apartments"
    assert summary["final_action"]["route_id"] == "south_detour"
    assert summary["final_action"]["parameters"]["people_count"] == 4
    assert summary["rescued"] is True
    assert summary["record_chain_valid"] is True


def test_controller_never_receives_unverified_hidden_route_truth(tmp_path: Path):
    summary = run_demo(tmp_path / "run")
    initial = summary["initial_mission_controller_knowledge"]
    truth = summary["simulation_ground_truth_after_run"]

    assert initial["routes"]["north_channel"]["report"] == "unknown"
    assert initial["north_route_open"] is None
    assert truth["route_status"]["north_channel"] == "blocked"
