"""TRACE chain and commitment/outcome integrity checks."""

from __future__ import annotations

from trace_jepa.scenario.delta.runtime import DeltaRunResult


def _record_chain_is_valid(result: DeltaRunResult) -> bool:
    evidence_ids = {item.evidence_id for item in result.evidence}
    records = {(item.record_id, item.record_version): item for item in result.trace_records}
    if any(not set(record.evidence_refs) <= evidence_ids for record in result.trace_records):
        return False
    for record in result.trace_records:
        if record.record_version == 1:
            if (
                record.supersedes_record_id is not None
                or record.supersedes_record_version is not None
            ):
                return False
        elif (
            record.supersedes_record_id != record.record_id
            or record.supersedes_record_version != record.record_version - 1
            or (record.record_id, record.record_version - 1) not in records
        ):
            return False
    return True


def _commitment_links_are_valid(result: DeltaRunResult) -> bool:
    records = {(item.record_id, item.record_version): item for item in result.trace_records}
    commitments = {item.commitment_id: item for item in result.commitments}
    if set(commitments) != {item.authorizing_commitment_id for item in result.outcomes}:
        return False
    if any(
        (
            outcome.authorizing_trace_record_id,
            outcome.authorizing_trace_record_version,
        )
        != (
            commitments[outcome.authorizing_commitment_id].authorizing_record_id,
            commitments[outcome.authorizing_commitment_id].authorizing_record_version,
        )
        for outcome in result.outcomes
    ):
        return False
    for commitment in result.commitments:
        authorizing_record = records.get(
            (commitment.authorizing_record_id, commitment.authorizing_record_version)
        )
        if authorizing_record is None or not authorizing_record.consumer_actions:
            return False
        if authorizing_record.consumer_actions[-1].decision.value != "clear":
            return False
        if not any(
            event.commitment_id == commitment.commitment_id
            and (event.trace_record_id, event.trace_record_version)
            == (commitment.authorizing_record_id, commitment.authorizing_record_version)
            for event in result.decisions
        ):
            return False
    return True


def trace_artifacts_verify(result: DeltaRunResult) -> bool:
    """Verify ledger chain, evidence, commitment, decision, and outcome links."""

    if not result.trace_chain_verified or not _record_chain_is_valid(result):
        return False
    if not _commitment_links_are_valid(result):
        return False
    records = {(item.record_id, item.record_version) for item in result.trace_records}
    return all(
        (event.trace_record_id, event.trace_record_version) in records for event in result.decisions
    )
