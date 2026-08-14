"""Narrow compatibility seam to the immutable validation-v2 mission mechanics.

The failed original execution froze the mission receipt contract and the exact
mission implementation at scientific source commit ``2cb5853``. Recovery must
reuse those mechanics byte-for-byte while keeping private frozen helpers out of
the rest of the recovery package. This module is the only allowed import seam.
"""

from __future__ import annotations

from pathlib import Path

from trace_reference.validation import original_execution as frozen_execution
from trace_reference.validation.registration_models import (
    ReferenceValidationMissionReceipt,
)


def run_frozen_mission(
    repository_root: Path,
    mission_root: Path,
    *,
    mission_index: int,
    seed: int,
) -> ReferenceValidationMissionReceipt:
    """Execute one mission using the exact frozen validation-v2 implementation."""

    return frozen_execution._run_mission(
        repository_root,
        mission_root,
        mission_index=mission_index,
        seed=seed,
    )


def frozen_failure_receipt(
    mission_index: int,
    seed: int,
    finding: str,
) -> ReferenceValidationMissionReceipt:
    """Encode a mission failure using the exact frozen validation-v2 schema."""

    return frozen_execution._failed_mission_receipt(
        mission_index,
        seed,
        finding,
    )
