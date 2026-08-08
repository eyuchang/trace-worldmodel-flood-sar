from __future__ import annotations

from pathlib import Path

import yaml

from trace_jepa.scenario.delta.acceptance import DeltaSmallAcceptanceConfig
from trace_jepa.scenario.delta.domain import DeltaScenarioConfig
from trace_jepa.scenario.delta.geography_models import GeographyCatalog

MAXIMUM_INPUT_BYTES = 1_000_000


class DeltaConfigurationError(ValueError):
    pass


def _load_yaml_mapping(path: Path, label: str) -> object:
    if path.is_symlink():
        raise DeltaConfigurationError(f"{label} must not be a symlink: {path}")
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise DeltaConfigurationError(f"{label} must be a regular file: {resolved}")
    if resolved.stat().st_size > MAXIMUM_INPUT_BYTES:
        raise DeltaConfigurationError(f"{label} exceeds the 1 MB input limit: {resolved}")
    try:
        with resolved.open("r", encoding="utf-8") as stream:
            return yaml.safe_load(stream)
    except yaml.YAMLError as exc:
        raise DeltaConfigurationError(f"{label} is not valid YAML: {resolved}") from exc


def load_scenario_config(path: Path) -> DeltaScenarioConfig:
    payload = _load_yaml_mapping(path, "scenario configuration")
    try:
        return DeltaScenarioConfig.model_validate(payload)
    except ValueError as exc:
        raise DeltaConfigurationError(
            f"scenario configuration violates the frozen Small contract: {path}"
        ) from exc


def load_acceptance_config(path: Path) -> DeltaSmallAcceptanceConfig:
    payload = _load_yaml_mapping(path, "acceptance configuration")
    try:
        return DeltaSmallAcceptanceConfig.model_validate(payload)
    except ValueError as exc:
        raise DeltaConfigurationError(
            f"acceptance configuration violates its schema: {path}"
        ) from exc


def load_geography_catalog(path: Path) -> GeographyCatalog:
    payload = _load_yaml_mapping(path, "geography catalog")
    try:
        return GeographyCatalog.model_validate(payload)
    except ValueError as exc:
        raise DeltaConfigurationError(f"geography catalog violates its schema: {path}") from exc
