"""Private-plan execution and seed-concealing shard receipts for recovery."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable, Mapping
from pathlib import Path

from trace_jepa.support import (
    ArtifactLocator,
    atomic_write_bytes,
    canonical_json_bytes,
    safe_directory,
)
from trace_reference.validation.registration import REFERENCE_VALIDATION_PROTOCOL
from trace_reference.validation.registration_models import (
    ReferenceValidationMissionReceipt,
)

from .bindings import bind_artifact
from .frozen_compatibility import frozen_failure_receipt, run_frozen_mission
from .models import RecoveryProtectedSeedPlan, RecoveryShardReceipt
from .protected_plan import PlanFactory, derive_recovery_plan
from .registration import EXPECTED_SEED_LIST_SHA256, require_recovery_boundary

MAX_RECEIPT_BYTES = 64 * 1024 * 1024
MissionRunner = Callable[..., ReferenceValidationMissionReceipt]


def _remove_generated_tree(root: Path) -> None:
    for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_file() or path.is_symlink():
            path.unlink()
        elif path.is_dir():
            path.rmdir()
    root.rmdir()


def _run_shard_missions(
    repository_root: Path,
    work_root: Path,
    *,
    shard_index: int,
    plan: RecoveryProtectedSeedPlan,
    mission_runner: MissionRunner,
) -> tuple[ReferenceValidationMissionReceipt, ...]:
    missions = []
    for mission_index in range(shard_index * 5, shard_index * 5 + 5):
        mission_root = work_root / f"mission-{mission_index:03d}"
        mission_root.mkdir()
        try:
            try:
                receipt = mission_runner(
                    repository_root,
                    mission_root,
                    mission_index=mission_index,
                    seed=plan.seeds[mission_index],
                )
            except Exception as exc:  # noqa: BLE001 - failures are registered evidence
                receipt = frozen_failure_receipt(
                    mission_index,
                    plan.seeds[mission_index],
                    f"{type(exc).__name__}: {exc}",
                )
            missions.append(receipt)
        finally:
            _remove_generated_tree(mission_root)
    return tuple(missions)


def run_recovery_shard(
    repository_root: Path,
    output_path: Path,
    *,
    shard_index: int,
    environment: Mapping[str, str] | None = None,
    plan_factory: PlanFactory = derive_recovery_plan,
    mission_runner: MissionRunner = run_frozen_mission,
) -> RecoveryShardReceipt:
    """Privately derive, execute, and emit one seed-concealing shard receipt."""

    if output_path.exists():
        raise ValueError("recovery shard output already exists")
    protocol, manifest, identity = require_recovery_boundary(
        repository_root,
        os.environ if environment is None else environment,
    )
    if not 0 <= shard_index < protocol.shard_count:
        raise ValueError("recovery shard index is outside the frozen plan")
    plan = plan_factory(identity)
    if plan.execution != identity or plan.seed_list_sha256 != EXPECTED_SEED_LIST_SHA256:
        raise ValueError("recovery shard plan is not bound to this execution")
    output_root = safe_directory(
        output_path.parent,
        declared_root=output_path.parent,
        label="recovery shard output root",
    )
    work_root = output_root / f"mission-work-{shard_index:02d}"
    work_root.mkdir()
    try:
        missions = _run_shard_missions(
            repository_root,
            work_root,
            shard_index=shard_index,
            plan=plan,
            mission_runner=mission_runner,
        )
    finally:
        if work_root.exists() and not any(work_root.iterdir()):
            work_root.rmdir()
    body = {
        "schema_version": "delta-reference-validation-recovery-shard-receipt-v1",
        "execution": identity.model_dump(mode="json"),
        "failed_original_run_id": 31833291955,
        "shard_index": shard_index,
        "base_protocol_sha256": bind_artifact(
            repository_root, REFERENCE_VALIDATION_PROTOCOL
        ).sha256,
        "base_freeze_digest": protocol.base_freeze_digest,
        "recovery_governance_aggregate_sha256": manifest.recovery_aggregate_sha256,
        "seed_list_sha256": plan.seed_list_sha256,
        "missions": [item.model_dump(mode="json") for item in missions],
    }
    receipt = RecoveryShardReceipt(
        **body,
        shard_digest=hashlib.sha256(canonical_json_bytes(body)).hexdigest(),
    )
    atomic_write_bytes(
        output_path,
        canonical_json_bytes(receipt.model_dump(mode="json")),
        root=output_root,
        label="recovery shard receipt",
    )
    return receipt


def load_present_shards(shard_root: Path) -> tuple[RecoveryShardReceipt, ...]:
    """Load validly named shard receipts without inventing missing evidence."""

    receipts = []
    for shard_index in range(20):
        try:
            path = ArtifactLocator(
                root=shard_root,
                relative_name=Path(f"shard-{shard_index:02d}.json"),
                maximum_bytes=MAX_RECEIPT_BYTES,
                label=f"recovery shard {shard_index}",
            ).resolve()
        except (OSError, ValueError):
            continue
        receipt = RecoveryShardReceipt.model_validate_json(path.read_text("utf-8"))
        if receipt.shard_index != shard_index:
            raise ValueError("recovery shard filename does not match its receipt")
        receipts.append(receipt)
    return tuple(receipts)
