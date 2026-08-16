"""Scientific and filesystem boundary checks for the lab package."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import lab_runtime
import pytest

HIDDEN_BOOK_FILES = {
    "ground_truth.json",
    "incident_candidate_audit.json",
    "call_lineage.json",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_declared_artifacts_are_manifest_public_and_hash_bound() -> None:
    case_manifest, _ = lab_runtime.load_public_book()
    source = case_manifest["source"]
    book = lab_runtime.REPO_ROOT / source["book_path"]
    canonical_manifest = json.loads((book / "manifest.json").read_text(encoding="utf-8"))
    registered = {item["file_name"]: item for item in canonical_manifest["artifacts"]}

    declared_names = {item["file_name"] for item in case_manifest["public_artifacts"]}
    assert declared_names.isdisjoint(HIDDEN_BOOK_FILES)
    for expected in case_manifest["public_artifacts"]:
        entry = registered[expected["file_name"]]
        assert entry["contains_hidden_truth"] is False
        assert entry["sha256"] == expected["sha256"]
        assert _sha256(book / expected["file_name"]) == expected["sha256"]


def test_loading_cases_never_opens_hidden_truth(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[Path] = []
    original_open = Path.open

    def tracking_open(path: Path, *args: Any, **kwargs: Any) -> Any:
        opened.append(path)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", tracking_open)

    lab_runtime.build_cases()

    assert not ({path.name for path in opened} & HIDDEN_BOOK_FILES)


def test_hash_drift_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = json.loads(lab_runtime.CASE_MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["public_artifacts"][0]["sha256"] = "0" * 64
    changed = tmp_path / "changed-manifest.json"
    changed.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(lab_runtime, "CASE_MANIFEST_PATH", changed)

    with pytest.raises(lab_runtime.LabDataError, match="hash drift"):
        lab_runtime.load_public_book()


def test_runtime_leaves_all_source_artifact_hashes_unchanged(controller_name: str) -> None:
    manifest = json.loads(lab_runtime.CASE_MANIFEST_PATH.read_text(encoding="utf-8"))
    book = lab_runtime.REPO_ROOT / manifest["source"]["book_path"]
    before = {
        item["file_name"]: _sha256(book / item["file_name"])
        for item in manifest["public_artifacts"]
    }

    lab_runtime.run_lab(controller_name, "all")

    after = {
        item["file_name"]: _sha256(book / item["file_name"])
        for item in manifest["public_artifacts"]
    }
    assert after == before


def test_output_inside_registered_reference_is_refused(controller_name: str) -> None:
    report = lab_runtime.run_lab(controller_name, "allocation")
    protected = lab_runtime.PROTECTED_OUTPUT_ROOTS[0] / "forbidden-lab-output.json"

    with pytest.raises(ValueError, match="protected"):
        lab_runtime.write_report(report, protected)
    assert not protected.exists()


def test_reconciliation_explicitly_excludes_hidden_lineage() -> None:
    _, artifacts = lab_runtime.load_public_book()

    assert artifacts["controller_reconciliation.json"]["hidden_lineage_used"] is False
