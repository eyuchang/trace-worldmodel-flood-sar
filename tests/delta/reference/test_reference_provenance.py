from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from trace_reference.provenance import (
    ReferenceArtifactMismatchError,
    ReferenceExecution,
    ReferenceReplayManifest,
    execute_reference_scenario,
    verify_exact_reference_replay,
    verify_reference_artifacts,
    verify_reference_input_inventory,
)

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def reference_execution(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, Path, ReferenceExecution]:
    parent = tmp_path_factory.mktemp("reference-replay-source")
    bundle = parent / "bundle"
    bundle.mkdir()
    execution = execute_reference_scenario(ROOT, bundle, seed=20260812)
    return parent, bundle, execution


def test_reference_bundle_is_bounded_verified_and_input_bound(
    reference_execution: tuple[Path, Path, ReferenceExecution],
) -> None:
    parent, _bundle, execution = reference_execution
    verified = verify_reference_artifacts(
        trusted_root=parent,
        bundle_relative_path=Path("bundle"),
    )

    assert verified == execution.manifest
    assert verified.scientific_status == "development-only-not-validation-evidence"
    assert verified.generator_version == "delta-reference-generator-v2"
    assert sum(item.byte_length for item in verified.artifacts) < 512 * 1024 * 1024
    assert {item.name for item in verified.artifacts} >= {
        "full_event_chain",
        "trace_chain",
        "evidence_chain",
        "commitment_chain",
        "capacity_evaluation",
        "result_summary",
    }
    verify_reference_input_inventory(ROOT, verified)


def test_public_reference_artifacts_do_not_expose_hidden_entity_ids(
    reference_execution: tuple[Path, Path, ReferenceExecution],
) -> None:
    _parent, bundle, execution = reference_execution
    for descriptor in execution.manifest.artifacts:
        if descriptor.contains_hidden_truth:
            continue
        payload = (bundle / descriptor.file_name).read_text(encoding="utf-8")
        for forbidden in ('"truth_incident_id"', '"truth_person_id"', "RI-", "RP-"):
            assert forbidden not in payload, (descriptor.file_name, forbidden)


def test_reference_manifest_and_artifacts_detect_tampering(
    reference_execution: tuple[Path, Path, ReferenceExecution],
    tmp_path: Path,
) -> None:
    _parent, bundle, _execution = reference_execution
    copied = tmp_path / "copied"
    shutil.copytree(bundle, copied)
    summary = copied / "result_summary.json"
    value = json.loads(summary.read_text(encoding="utf-8"))
    value["report_count"] += 1
    summary.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ReferenceArtifactMismatchError, match=r"digest|length"):
        verify_reference_artifacts(
            trusted_root=tmp_path,
            bundle_relative_path=Path("copied"),
        )


def test_reference_manifest_model_detects_internal_tampering(
    reference_execution: tuple[Path, Path, ReferenceExecution],
) -> None:
    _parent, bundle, _execution = reference_execution
    payload = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    payload["seed"] += 1
    with pytest.raises(ValueError, match="manifest digest"):
        ReferenceReplayManifest.model_validate(payload)


def test_reference_bundle_rejects_symlink_boundary(
    reference_execution: tuple[Path, Path, ReferenceExecution],
    tmp_path: Path,
) -> None:
    _parent, bundle, _execution = reference_execution
    link = tmp_path / "linked"
    link.symlink_to(bundle, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        verify_reference_artifacts(
            trusted_root=tmp_path,
            bundle_relative_path=Path("linked"),
        )


def test_reference_exact_replay_is_byte_identical(
    reference_execution: tuple[Path, Path, ReferenceExecution],
    tmp_path: Path,
) -> None:
    parent, _bundle, _execution = reference_execution
    replay = tmp_path / "replay"
    replay.mkdir()

    verify_exact_reference_replay(
        ROOT,
        trusted_reference_root=parent,
        reference_relative_path=Path("bundle"),
        replay_output_root=replay,
    )
