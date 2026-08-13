from __future__ import annotations

import json
from pathlib import Path

import pytest

from trace_reference.provenance import (
    ReferenceScientificInputManifest,
    build_reference_scientific_input_manifest,
    verify_reference_scientific_input_manifest,
)
from trace_reference.provenance.source_closure import (
    ReferenceSourceClosureError,
    reference_source_paths,
)

ROOT = Path(__file__).resolve().parents[3]


def test_reference_scientific_manifest_covers_all_python_and_direct_inputs() -> None:
    manifest = build_reference_scientific_input_manifest(ROOT)
    paths = {item.repository_relative_path for item in manifest.members}
    expected_source = {item.relative_to(ROOT).as_posix() for item in reference_source_paths(ROOT)}

    assert expected_source <= paths
    assert "src/trace_reference/decision/counterfactual.py" in expected_source
    assert "src/trace_reference/delivery_history.py" in expected_source
    assert "src/trace_jepa/workbench/d05_server.py" not in expected_source
    assert "pyproject.toml" in paths
    assert "requirements-delta-python311.lock" in paths
    assert (
        "data/scenario/delta/reference/environment/reference_python311_linux_amd64_v1.json" in paths
    )
    assert "docs/delta/reference/WF_DFLD_01_REFERENCE_PROTOCOL_DRAFT.md" in paths
    assert (
        "data/scenario/delta/reference/calibration/reference_observation_coefficients_v2.json"
        in paths
    )
    assert not any(
        path.endswith(
            (
                "reference_observation_fit_benchmark_failed_v1.json",
                "reference_observation_fit_benchmark_v2.json",
                "reference_observation_fit_report_v1.json",
            )
        )
        for path in paths
    )
    assert not any(
        part in path
        for path in paths
        for part in ("reference_bundle", "execution_receipt", "validation_report", "figures/")
    )
    verify_reference_scientific_input_manifest(ROOT, manifest)


def test_reference_scientific_manifest_detects_member_and_aggregate_tampering() -> None:
    manifest = build_reference_scientific_input_manifest(ROOT)
    payload = json.loads(manifest.model_dump_json())
    payload["members"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="aggregate digest"):
        ReferenceScientificInputManifest.model_validate(payload)

    payload = json.loads(manifest.model_dump_json())
    payload["members"].pop()
    with pytest.raises(ValueError, match="aggregate digest"):
        ReferenceScientificInputManifest.model_validate(payload)


def test_reference_source_closure_excludes_unimported_future_extension(tmp_path: Path) -> None:
    package = tmp_path / "src" / "trace_reference"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "entry.py").write_text("from . import support\n", encoding="utf-8")
    (package / "support.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "future_leap.py").write_text("VALUE = 2\n", encoding="utf-8")

    paths = {
        item.relative_to(tmp_path).as_posix()
        for item in reference_source_paths(tmp_path, ("trace_reference.entry",))
    }

    assert paths == {
        "src/trace_reference/__init__.py",
        "src/trace_reference/entry.py",
        "src/trace_reference/support.py",
    }


def test_reference_source_closure_rejects_symlink_and_malformed_module(tmp_path: Path) -> None:
    package = tmp_path / "src" / "trace_reference"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "entry.py").write_text("from . import support\n", encoding="utf-8")
    outside = tmp_path / "outside.py"
    outside.write_text("VALUE = 1\n", encoding="utf-8")
    (package / "support.py").symlink_to(outside)
    with pytest.raises(ValueError, match="symlink"):
        reference_source_paths(tmp_path, ("trace_reference.entry",))

    (package / "support.py").unlink()
    (package / "support.py").write_text("def broken(:\n", encoding="utf-8")
    with pytest.raises(ReferenceSourceClosureError, match="cannot parse"):
        reference_source_paths(tmp_path, ("trace_reference.entry",))
