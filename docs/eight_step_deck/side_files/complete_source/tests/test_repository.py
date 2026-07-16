from pathlib import Path

import pytest

from trace_jepa.contracts import Claim, ClaimLayer, TraceRecord, TraceStatus
from trace_jepa.runtime.storage import ImmutableWriteError, TraceRepository


def make_record() -> TraceRecord:
    return TraceRecord(
        policy_version="test-policy",
        claim=Claim(layer=ClaimLayer.PREDICTIVE, text="A route is open."),
        evidence_refs=("evidence-1",),
        final_status=TraceStatus.ACCEPT,
    )


def test_repository_is_append_only_and_chain_verifies(tmp_path: Path):
    repository = TraceRepository(tmp_path / "trace.jsonl")
    record = make_record()
    repository.write(record)
    repository.write(record)
    assert len(repository.all()) == 1
    assert repository.verify_chain()

    changed = record.model_copy(update={"final_status": TraceStatus.REJECT})
    with pytest.raises(ImmutableWriteError):
        repository.write(changed)
