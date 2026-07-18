from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, model_validator

from trace_jepa.util import sha256_value
from trace_jepa.workbench.models import FrozenModel


ShockType = Literal[
    "communication_loss",
    "communication_restore",
    "sensor_degradation",
    "levee_breach",
    "road_submergence",
    "wind_shift",
    "group_deterioration",
    "asset_grounded",
    "fuel_limit",
]


class ShockEntry(FrozenModel):
    shock_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
    scheduled_at: float = Field(ge=0.0, le=86_400.0)
    shock_type: ShockType
    severity: float = Field(ge=0.0, le=1.0)
    target: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"
    )


class ShockRegistry(FrozenModel):
    schema_version: Literal["trace-shock-registry-v1"] = "trace-shock-registry-v1"
    regime: Literal["R-A", "R-B", "R-C"]
    seed: int = Field(ge=0)
    entries: tuple[ShockEntry, ...] = ()

    @model_validator(mode="after")
    def validate_order_and_identity(self) -> "ShockRegistry":
        ids = [entry.shock_id for entry in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError("shock_id values must be unique")
        schedule_keys = [
            (entry.scheduled_at, entry.shock_id) for entry in self.entries
        ]
        if schedule_keys != sorted(schedule_keys):
            raise ValueError("shock entries must be sorted by scheduled_at, shock_id")
        return self

    @property
    def registry_hash(self) -> str:
        return sha256_value(self.model_dump(mode="json"))


def load_shock_registry(
    path: str | Path,
    *,
    registry_root: str | Path,
    expected_seed: int | None = None,
    expected_regime: str | None = None,
) -> ShockRegistry:
    """Load one strict YAML registry confined to ``registry_root``."""

    root = Path(registry_root).resolve(strict=True)
    registry_path = Path(path)
    if not registry_path.is_absolute():
        registry_path = root / registry_path
    resolved = registry_path.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("shock registry path escapes the configured root") from exc
    if not resolved.is_file():
        raise ValueError("shock registry must be a regular file")
    if resolved.stat().st_size > 1_000_000:
        raise ValueError("shock registry exceeds the 1 MB safety limit")

    raw = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("shock registry must contain a YAML mapping")
    registry = ShockRegistry.model_validate(raw)
    if expected_seed is not None and registry.seed != expected_seed:
        raise ValueError(
            f"shock registry seed {registry.seed} does not match {expected_seed}"
        )
    if expected_regime is not None and registry.regime != expected_regime:
        raise ValueError(
            f"shock registry regime {registry.regime} does not match {expected_regime}"
        )
    return registry
