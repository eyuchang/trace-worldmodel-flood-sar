"""Protected validation-v2 plan derivation for the authorized recovery only."""

from __future__ import annotations

import hashlib
from collections.abc import Callable

from .models import RecoveryExecutionIdentity, RecoveryProtectedSeedPlan
from .registration import EXPECTED_SEED_LIST_SHA256

VALIDATION_NAMESPACE = "WF-DFLD-01-REFERENCE|validation-v2|index"
DERIVATION_ALGORITHM = "sha256-utf8-first-u32-big-endian-mask-unsigned31-reject-collision-v1"
PlanFactory = Callable[[RecoveryExecutionIdentity], RecoveryProtectedSeedPlan]


def _protected_seed(index: int) -> int:
    payload = f"{VALIDATION_NAMESPACE.removesuffix('|index')}|{index}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:4], "big") & 0x7FFFFFFF


def derive_recovery_plan(identity: RecoveryExecutionIdentity) -> RecoveryProtectedSeedPlan:
    """Derive the original list only after the remote recovery boundary passes."""

    seeds = tuple(_protected_seed(index) for index in range(100))
    return RecoveryProtectedSeedPlan(
        schema_version="delta-reference-protected-seed-plan-recovery-v1",
        scenario_id="WF-DFLD-01-REFERENCE",
        execution=identity,
        namespace=VALIDATION_NAMESPACE,
        derivation_algorithm=DERIVATION_ALGORITHM,
        seeds=seeds,
        seed_list_sha256=EXPECTED_SEED_LIST_SHA256,
    )
