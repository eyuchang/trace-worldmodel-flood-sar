from __future__ import annotations

import json
import xml.etree.ElementTree as element_tree
from pathlib import Path

import pytest

from trace_reference.provenance import execute_reference_scenario
from trace_reference.publication import (
    ReferencePublicationResultTable,
    publish_reference_bundle,
    verify_reference_publication,
)

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def published_bundle(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, Path, Path]:
    parent = tmp_path_factory.mktemp("reference-publication-source")
    source = parent / "source"
    source.mkdir()
    execute_reference_scenario(ROOT, source, seed=20260812)
    output = parent / "publication"
    output.mkdir()
    publish_reference_bundle(
        trusted_reference_root=parent,
        reference_relative_path=Path("source"),
        output_root=output,
    )
    return parent, source, output


def test_reference_publication_is_verified_and_explicitly_development_only(
    published_bundle: tuple[Path, Path, Path],
) -> None:
    parent, _source, output = published_bundle
    manifest = verify_reference_publication(
        trusted_root=parent,
        publication_relative_path=Path("publication"),
    )

    assert manifest.scientific_status == "development-descriptive-not-validation-evidence"
    assert len(manifest.artifacts) == 5
    for descriptor in manifest.artifacts:
        payload = (output / descriptor.file_name).read_text(encoding="utf-8")
        assert "<metadata" not in payload
        assert "2026-" not in payload
        if descriptor.media_type == "image/svg+xml":
            assert element_tree.fromstring(payload).tag.endswith("svg")
    assert "no numerical load gate" in (output / "capacity_sensitivity.svg").read_text(
        encoding="utf-8"
    )
    assert "hidden lineage is excluded" in (output / "trace_flow.svg").read_text(encoding="utf-8")


def test_reference_publication_result_table_is_machine_verified(
    published_bundle: tuple[Path, Path, Path],
) -> None:
    _parent, _source, output = published_bundle
    table = ReferencePublicationResultTable.model_validate_json(
        (output / "result_table.json").read_text(encoding="utf-8")
    )

    assert table.seed == 20260812
    assert table.report_count >= table.evaluation_report_count
    assert table.decision_count == (
        table.allocation_count + table.refusal_count + table.acquisition_request_count
    )
    assert table.peak_finite_strict_concurrent_load_ratio_milli == 4_000


def test_reference_publication_regeneration_is_byte_identical(
    published_bundle: tuple[Path, Path, Path],
    tmp_path: Path,
) -> None:
    parent, _source, first = published_bundle
    second = tmp_path / "second"
    second.mkdir()
    manifest = publish_reference_bundle(
        trusted_reference_root=parent,
        reference_relative_path=Path("source"),
        output_root=second,
    )

    files = [item.file_name for item in manifest.artifacts] + ["publication_manifest.json"]
    for file_name in files:
        assert (first / file_name).read_bytes() == (second / file_name).read_bytes()


def test_reference_publication_detects_tampering(
    published_bundle: tuple[Path, Path, Path],
) -> None:
    parent, _source, output = published_bundle
    path = output / "result_table.json"
    original = path.read_text(encoding="utf-8")
    payload = json.loads(original)
    payload["report_count"] += 1
    path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        with pytest.raises(ValueError, match="artifact differs"):
            verify_reference_publication(
                trusted_root=parent,
                publication_relative_path=Path("publication"),
            )
    finally:
        path.write_text(original, encoding="utf-8")
