from __future__ import annotations

from pathlib import Path

import yaml

from trace_jepa.scenario.delta.acceptance import DeltaSmallAcceptanceConfig
from trace_jepa.scenario.delta.geography_models import GeographyCatalog
from trace_jepa.scenario.delta.models import DeltaScenarioConfig

MAXIMUM_INPUT_BYTES = 1_000_000


class DeltaConfigurationError(ValueError):
    pass


def _load_yaml_mapping(path: Path, label: str) -> object:
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
    try:
        return DeltaScenarioConfig.model_validate(
            _load_yaml_mapping(path, "scenario configuration")
        )
    except ValueError as exc:
        raise DeltaConfigurationError(
            f"scenario configuration violates the frozen Small contract: {path}"
        ) from exc


def load_acceptance_config(path: Path) -> DeltaSmallAcceptanceConfig:
    try:
        return DeltaSmallAcceptanceConfig.model_validate(
            _load_yaml_mapping(path, "acceptance configuration")
        )
    except ValueError as exc:
        raise DeltaConfigurationError(
            f"acceptance configuration violates its schema: {path}"
        ) from exc


def load_geography_catalog(path: Path) -> GeographyCatalog:
    try:
        return GeographyCatalog.model_validate(_load_yaml_mapping(path, "geography catalog"))
    except ValueError as exc:
        raise DeltaConfigurationError(f"geography catalog violates its schema: {path}") from exc
