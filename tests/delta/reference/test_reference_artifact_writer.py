from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from trace_jepa.support import canonical_json_bytes
from trace_reference.domain import ReferenceEvent, ReferenceEventType, ReferenceEventVisibility
from trace_reference.provenance.artifacts import ReferenceArtifactWriter
from trace_reference.provenance.specifications import ReferenceArtifactSpec
from trace_reference.runtime.event_store import create_reference_event


def _events() -> tuple[ReferenceEvent, ...]:
    first = create_reference_event(
        sequence=1,
        at_s=0,
        event_type=ReferenceEventType.CALL_DELIVERED,
        visibility=ReferenceEventVisibility.CONTROLLER_VISIBLE,
        payload={
            "schema_version": "delta-reference-public-event-artifact-v1",
            "artifact_id": "report-1",
            "artifact_schema_version": "test-report-v1",
            "artifact_json": '{"value":1}',
            "artifact_content_sha256": (
                "48208f9428d64634bd8e28ff345bf0eab60d53c18fa2fbdb0b9bc1e84df2b5f6"
            ),
        },
        previous_event_digest="GENESIS",
    )
    second = create_reference_event(
        sequence=2,
        at_s=1,
        event_type=ReferenceEventType.BREACH_ACTIVATED,
        visibility=ReferenceEventVisibility.HIDDEN_EVALUATION_ONLY,
        payload={"active": True},
        previous_event_digest=first.event_digest,
    )
    return first, second


def test_compressed_event_artifact_is_deterministic_canonical_json(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    events = _events()
    spec = ReferenceArtifactSpec(
        name="full_event_chain",
        file_name="full_event_chain.json.gz",
        value=events,
        contains_hidden_truth=True,
        content_encoding="canonical-json-gzip-v1",
    )

    first = ReferenceArtifactWriter(first_root).write(spec)
    second = ReferenceArtifactWriter(second_root).write(spec)
    first_bytes = (first_root / first.file_name).read_bytes()
    second_bytes = (second_root / second.file_name).read_bytes()

    assert first == second
    assert first.content_encoding == "canonical-json-gzip-v1"
    assert first_bytes == second_bytes
    assert gzip.decompress(first_bytes) == canonical_json_bytes(
        [item.model_dump(mode="json") for item in events]
    )


def test_compressed_event_artifact_rejects_non_models_without_output(tmp_path: Path) -> None:
    spec = ReferenceArtifactSpec(
        name="invalid",
        file_name="invalid.json.gz",
        value=({"not": "a model"},),
        content_encoding="canonical-json-gzip-v1",
    )

    with pytest.raises(TypeError, match="non-model"):
        ReferenceArtifactWriter(tmp_path).write(spec)

    assert not (tmp_path / "invalid.json.gz").exists()
    assert not tuple(tmp_path.glob(".invalid.json.gz.*"))
