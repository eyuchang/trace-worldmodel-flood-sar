from __future__ import annotations

import json
from pathlib import Path

import pytest

from trace_jepa.scenario.delta.scientific_manifest import (
    ScientificInputError,
    build_scientific_input_manifest,
    import_closure,
    scientific_input_core_aggregate,
    scientific_input_paths,
    verify_scientific_input_manifest,
    write_scientific_input_manifest,
)

ROOT = Path(__file__).resolve().parents[3]


def test_manifest_covers_runtime_predictor_trace_data_and_geography_sources() -> None:
    acceptance = ROOT / "configs/scenarios/wf_dfld_01_small_acceptance_v6.yaml"
    if not acceptance.is_file():
        paths = {
            path.relative_to(ROOT).as_posix()
            for path in scientific_input_paths(ROOT, include_acceptance=False)
        }
        assert len(scientific_input_core_aggregate(ROOT)) == 64
        assert "src/trace_jepa/scenario/delta/validation/registered.py" in paths
        return
    manifest = build_scientific_input_manifest(ROOT)
    paths = {member.path for member in manifest.members}
    assert "src/trace_jepa/scenario/delta/runner.py" in paths
    assert "src/trace_jepa/scenario/delta/reconciliation_v8.py" in paths
    assert "src/trace_jepa/predictor/toy_qualification_v1.json" in paths
    assert "src/trace_jepa/experimental/revalidation.py" in paths
    assert "data/scenario/delta/geography/build_manifest_v3.json" in paths
    assert ".github/workflows/delta-artifact-reconstruction-v8.yml" in paths
    assert "data/scenario/delta/validation/recovery_execution_failure_v1.json" in paths
    assert any(path.startswith("data/scenario/delta/geography/sources/") for path in paths)
    assert not any(
        path.startswith(("data/scenario/delta/reference/", "docs/delta/validation/"))
        for path in paths
    )

    output = ROOT / "data/scenario/delta/provenance/test_scientific_manifest.json"
    try:
        write_scientific_input_manifest(ROOT, output)
        assert verify_scientific_input_manifest(ROOT, output) == build_scientific_input_manifest(
            ROOT
        )
    finally:
        output.unlink(missing_ok=True)


def test_manifest_rejects_member_substitution() -> None:
    if not (ROOT / "configs/scenarios/wf_dfld_01_small_acceptance_v6.yaml").is_file():
        pytest.skip("complete manifest is created only by the preregistration commit")
    output = ROOT / "data/scenario/delta/provenance/test_tampered_manifest.json"
    try:
        write_scientific_input_manifest(ROOT, output)
        payload = json.loads(output.read_text("utf-8"))
        payload["members"][0]["sha256"] = "0" * 64
        output.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(ScientificInputError, match="changed after freeze"):
            verify_scientific_input_manifest(ROOT, output)
    finally:
        output.unlink(missing_ok=True)


def test_manifest_rejects_symlinked_member() -> None:
    target = ROOT / "data/scenario/delta/provenance/test_symlink_target.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("{}", encoding="utf-8")
    link = ROOT / "data/scenario/delta/provenance/test_symlink_manifest.json"
    try:
        link.symlink_to(target)
        with pytest.raises(ScientificInputError, match="must not be a symlink"):
            write_scientific_input_manifest(ROOT, link)
    finally:
        link.unlink(missing_ok=True)
        target.unlink(missing_ok=True)


def test_complete_source_inventory_contains_registered_import_closure() -> None:
    inventory = {
        path.resolve(strict=True) for path in scientific_input_paths(ROOT, include_acceptance=False)
    }
    closure = import_closure(
        ROOT,
        (
            "trace_jepa.scenario.delta.cli",
            "trace_jepa.scenario.delta.generator",
            "trace_jepa.scenario.delta.runtime",
            "trace_jepa.predictor",
            "trace_jepa.scenario.delta.validation.registered",
            "trace_jepa.scenario.delta.publication",
        ),
    )
    assert closure
    assert closure <= inventory
