"""Safe deterministic seed namespaces for companion Reference development."""

from __future__ import annotations

import hashlib
from typing import Literal

ReferenceStudyRole = Literal["development"]
_ALLOWED_ROLES = frozenset({"development"})


def derive_study_seed(role: str, index: int) -> int:
    """Derive one unsigned-31-bit seed without exposing a confirmatory namespace."""

    if role not in _ALLOWED_ROLES:
        raise ValueError("only development, selection, and validation seeds are available")
    if index < 0:
        raise ValueError("seed index must be non-negative")
    payload = f"WF-DFLD-01-REFERENCE|{role}-v1|{index}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:4], "big") & 0x7FFFFFFF


def derive_seed_prefix(role: ReferenceStudyRole, count: int) -> tuple[int, ...]:
    """Materialize an explicitly requested spent-development prefix only."""

    if count <= 0:
        raise ValueError("seed count must be positive")
    seeds = tuple(derive_study_seed(role, index) for index in range(count))
    if len(set(seeds)) != count:
        raise ValueError("derived Reference seed prefix contains a collision")
    return seeds
