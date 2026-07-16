from pathlib import Path

from trace_jepa.emergency_cli import build_parser, run_from_emergency_call
from trace_jepa.intake import EmergencyCallIntake
from trace_jepa.scenario import FloodEnvironment


def test_call_intake_extracts_location_and_people():
    environment = FloodEnvironment.from_yaml(
        "configs/scenarios/riverside_flood_v1.yaml"
    )
    call = EmergencyCallIntake(environment.scenario).parse(
        "Emergency. Four residents are stranded at Riverside Apartments."
    )
    assert call.normalized_location_id == "riverside_apartments"
    assert call.people_count == 4
    assert call.deadline_s == 1200


def test_emergency_call_runs_to_authorized_rescue(tmp_path: Path):
    parser = build_parser()
    args = parser.parse_args(
        [
            "--call",
            "Emergency. Four residents are stranded at Riverside Apartments.",
            "--output",
            str(tmp_path / "call_run"),
            "--quiet",
        ]
    )
    summary = run_from_emergency_call(args)
    assert summary["emergency_call"]["normalized_location_id"] == "riverside_apartments"
    assert summary["first_selected_plan"] == "verify-north"
    assert summary["final_selected_plan"] == "south-detour"
    assert summary["rescued"] is True
    assert summary["timeline"][0]["event_type"] == "call_received"
    assert (tmp_path / "call_run" / "timeline.txt").exists()
    assert (tmp_path / "call_run" / "figures" / "action_timeline.svg").exists()
