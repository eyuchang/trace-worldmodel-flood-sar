"""Seed-free interruption and continuation lifecycle for validation recovery."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from trace_jepa.support import (
    ArtifactLocator,
    atomic_write_bytes,
    canonical_json_bytes,
    safe_directory,
)

from .models import (
    RecoveryContinuationPlan,
    RecoveryInterruptionRecord,
    RecoveryShardReceipt,
)
from .registration import EXPECTED_SEED_LIST_SHA256, require_recovery_boundary
from .shards import MAX_RECEIPT_BYTES, load_present_shards


@dataclass(frozen=True)
class RecoveryInterruptionRequest:
    """Caller-bound inputs for one seed-free recovery failure record."""

    shard_root: Path
    failure_stage: Literal[
        "incomplete-shards",
        "normalization",
        "aggregation",
        "artifact-preflight",
        "artifact-upload",
    ]
    final_report_written: bool
    raw_plan_written: bool
    environment: Mapping[str, str] | None = None


def build_recovery_continuation_plan(
    repository_root: Path,
    output_path: Path,
    *,
    shard_root: Path,
    environment: Mapping[str, str] | None = None,
) -> RecoveryContinuationPlan:
    """Preserve completed shards and authorize no mission reruns after interruption."""

    if output_path.exists():
        raise ValueError("recovery continuation output already exists")
    _, manifest, identity = require_recovery_boundary(
        repository_root,
        os.environ if environment is None else environment,
    )
    receipts = load_present_shards(shard_root)
    if any(
        item.execution != identity
        or item.recovery_governance_aggregate_sha256 != manifest.recovery_aggregate_sha256
        or item.seed_list_sha256 != EXPECTED_SEED_LIST_SHA256
        for item in receipts
    ):
        raise ValueError("recovery continuation evidence belongs to another execution")
    completed = tuple(item.shard_index for item in receipts)
    missing = tuple(index for index in range(20) if index not in completed)
    body = {
        "schema_version": "delta-reference-validation-recovery-continuation-plan-v1",
        "interrupted_execution": identity.model_dump(mode="json"),
        "seed_list_sha256": EXPECTED_SEED_LIST_SHA256,
        "completed_shard_indices": completed,
        "missing_shard_indices": missing,
        "completed_mission_indices": [
            mission for shard in completed for mission in range(shard * 5, shard * 5 + 5)
        ],
        "missing_mission_indices": [
            mission for shard in missing for mission in range(shard * 5, shard * 5 + 5)
        ],
        "completed_shards_must_not_rerun": True,
        "continuation_requires_new_versioned_authorization": True,
        "protected_namespace_must_not_change": True,
    }
    plan = RecoveryContinuationPlan(
        **body,
        plan_digest=hashlib.sha256(canonical_json_bytes(body)).hexdigest(),
    )
    output_root = safe_directory(
        output_path.parent,
        declared_root=output_path.parent,
        label="recovery continuation output root",
    )
    atomic_write_bytes(
        output_path,
        canonical_json_bytes(plan.model_dump(mode="json")),
        root=output_root,
        label="recovery continuation plan",
    )
    return plan


def write_recovery_interruption_record(
    repository_root: Path,
    output_path: Path,
    request: RecoveryInterruptionRequest,
) -> RecoveryInterruptionRecord:
    """Record a recovery infrastructure failure without deriving or exposing seeds."""

    if output_path.exists():
        raise ValueError("recovery interruption output already exists")
    _, manifest, identity = require_recovery_boundary(
        repository_root,
        os.environ if request.environment is None else request.environment,
    )
    trusted = safe_directory(
        request.shard_root,
        declared_root=request.shard_root,
        label="recovery interruption shard root",
    )
    candidates = tuple(sorted(trusted.rglob("shard-*.json")))
    valid: list[int] = []
    invalid_count = 0
    for candidate in candidates:
        try:
            path = ArtifactLocator.from_path(
                root=trusted,
                path=candidate,
                maximum_bytes=MAX_RECEIPT_BYTES,
                label="recovery interruption shard",
            ).resolve()
            receipt = RecoveryShardReceipt.model_validate_json(path.read_text("utf-8"))
            if (
                receipt.execution != identity
                or receipt.recovery_governance_aggregate_sha256
                != manifest.recovery_aggregate_sha256
                or receipt.seed_list_sha256 != EXPECTED_SEED_LIST_SHA256
                or receipt.shard_index in valid
            ):
                raise ValueError("recovery interruption shard binding is invalid")
            valid.append(receipt.shard_index)
        except (OSError, ValueError):
            invalid_count += 1
    body = {
        "schema_version": "delta-reference-validation-recovery-interruption-record-v1",
        "interrupted_execution": identity.model_dump(mode="json"),
        "failure_stage": request.failure_stage,
        "seed_list_sha256": EXPECTED_SEED_LIST_SHA256,
        "discovered_shard_file_count": len(candidates),
        "valid_completed_shard_indices": sorted(valid),
        "invalid_shard_file_count": invalid_count,
        "final_report_written": request.final_report_written,
        "raw_plan_written": request.raw_plan_written,
        "raw_plan_uploaded": False,
        "scientific_result_complete": request.final_report_written,
        "completed_shards_must_not_rerun": True,
        "continuation_requires_new_versioned_authorization": True,
    }
    record = RecoveryInterruptionRecord(
        **body,
        record_digest=hashlib.sha256(canonical_json_bytes(body)).hexdigest(),
    )
    output_root = safe_directory(
        output_path.parent,
        declared_root=output_path.parent,
        label="recovery interruption output root",
    )
    atomic_write_bytes(
        output_path,
        canonical_json_bytes(record.model_dump(mode="json")),
        root=output_root,
        label="recovery interruption record",
    )
    return record
