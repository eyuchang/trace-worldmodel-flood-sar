"""Stable facade for governed Reference validation-v2 recovery execution."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from .aggregation import aggregate_fixed_gates, aggregate_recovery_report
from .lifecycle import (
    RecoveryInterruptionRequest,
    build_recovery_continuation_plan,
    write_recovery_interruption_record,
)
from .models import RecoveryExecutionIdentity
from .registration import require_recovery_boundary
from .shards import run_recovery_shard


def authorize_recovery(
    repository_root: Path,
    *,
    environment: Mapping[str, str] | None = None,
) -> RecoveryExecutionIdentity:
    """Verify recovery authority without deriving or materializing any seed."""

    _, _, identity = require_recovery_boundary(
        repository_root,
        os.environ if environment is None else environment,
    )
    return identity


__all__ = [
    "RecoveryInterruptionRequest",
    "aggregate_fixed_gates",
    "aggregate_recovery_report",
    "authorize_recovery",
    "build_recovery_continuation_plan",
    "run_recovery_shard",
    "write_recovery_interruption_record",
]
