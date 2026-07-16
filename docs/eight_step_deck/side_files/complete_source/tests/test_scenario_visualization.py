from pathlib import Path

from trace_jepa.scenario.visualize import load_scenario, render_scenario


SCENARIO = Path("configs/scenarios/riverside_flood_v1.yaml")


def test_scenario_defines_distinct_knowledge_and_truth():
    scenario = load_scenario(SCENARIO)
    north = scenario["routes"]["north_channel"]
    assert north["initial_report"] == "unknown"
    assert north["hidden_status"] == "blocked"


def test_renderer_writes_operational_cast_and_two_vector_views(tmp_path: Path):
    paths = render_scenario(SCENARIO, tmp_path)
    assert set(paths) == {
        "operational_cast",
        "mission_controller_knowledge",
        "simulation_ground_truth",
    }
    for path in paths.values():
        assert path.exists()
        assert path.suffix == ".svg"
        assert path.read_text(encoding="utf-8").startswith("<?xml")

    knowledge = paths["mission_controller_knowledge"].read_text(encoding="utf-8")
    truth = paths["simulation_ground_truth"].read_text(encoding="utf-8")
    cast = paths["operational_cast"].read_text(encoding="utf-8")

    assert "North Channel: UNKNOWN" in knowledge
    assert "debris obstruction" not in knowledge
    assert "North Channel: BLOCKED" in truth
    assert "debris obstruction" in truth
    assert "Mission Controller" in cast
    assert "TRACE Gate" in cast
    assert "Offline Evaluation" in cast
