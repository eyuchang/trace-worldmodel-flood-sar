"""Canonical digest helpers for Reference decision handoff artifacts."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from trace_jepa.support import canonical_json_bytes


def decision_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def model_digest(model: BaseModel, *, digest_field: str) -> str:
    return decision_digest(model.model_dump(mode="json", exclude={digest_field}))


def verify_model_digest(model: BaseModel, *, digest_field: str) -> bool:
    expected = getattr(model, digest_field)
    return isinstance(expected, str) and model_digest(model, digest_field=digest_field) == expected
