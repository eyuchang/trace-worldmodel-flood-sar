"""Scientific and filesystem boundary checks for the standalone student package."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest
from _support import runtime

LAB_ROOT = Path(__file__).resolve().parents[1]
STUDENT_ROOT = LAB_ROOT / "student"
FIXTURE = STUDENT_ROOT / "_support" / "teaching_fixture.json"
HIDDEN_NAMES = {
    "ground_truth.json",
    "incident_candidate_audit.json",
    "call_lineage.json",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_fixture_builder() -> ModuleType:
    path = LAB_ROOT / "tools" / "build_teaching_fixture.py"
    spec = importlib.util.spec_from_file_location("teaching_fixture_builder", path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fixture_is_regenerated_from_declared_public_inputs_without_drift(tmp_path: Path) -> None:
    builder = _load_fixture_builder()
    regenerated = tmp_path / "teaching_fixture.json"

    builder.write_fixture(regenerated, overwrite=False)

    assert regenerated.read_bytes() == FIXTURE.read_bytes()
    assert _sha256(regenerated) == _sha256(FIXTURE)


def test_student_fixture_has_only_minimal_controller_visible_content() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))

    assert set(payload) == {
        "schema_version",
        "scenario_summary",
        "scenario_artifacts",
        "cases",
    }
    assert payload["scenario_summary"] == {"allocated": 1, "refused": 2, "repaired": 1}
    assert set(payload["scenario_artifacts"]) == set(runtime.SCENARIO_FILES)
    serialized = json.dumps(payload, sort_keys=True).lower()
    assert not any(name in serialized for name in HIDDEN_NAMES)
    assert "trace_jepa" not in serialized


def test_student_runtime_has_no_research_runtime_or_network_dependency() -> None:
    sources = {
        path.relative_to(STUDENT_ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in STUDENT_ROOT.rglob("*.py")
        if not {".venv", "__pycache__"}.intersection(path.relative_to(STUDENT_ROOT).parts)
    }
    combined = "\n".join(sources.values())

    for forbidden in (
        "import trace_jepa",
        "from trace_jepa",
        "requests",
        "urllib",
        "http.client",
        "subprocess.run([\"pip\"",
    ):
        assert forbidden not in combined


def test_runtime_rejects_a_fixture_that_names_hidden_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    changed = json.loads(FIXTURE.read_text(encoding="utf-8"))
    changed["scenario_artifacts"]["ground_truth.json"] = []
    altered = tmp_path / "teaching_fixture.json"
    altered.write_text(json.dumps(changed), encoding="utf-8")
    monkeypatch.setattr(runtime, "FIXTURE_PATH", altered)

    with pytest.raises(runtime.LabDataError, match="unexpected scenario file"):
        runtime.build_cases()


def test_runtime_does_not_mutate_the_frozen_fixture() -> None:
    before = _sha256(FIXTURE)

    runtime.run_lab("solution", "all")
    runtime.scenario_payloads()

    assert _sha256(FIXTURE) == before
