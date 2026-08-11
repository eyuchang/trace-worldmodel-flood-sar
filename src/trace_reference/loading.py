"""Bounded companion loaders for Reference inputs beneath caller-trusted roots."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from trace_jepa.support import ArtifactLocator

from .models import (
    ReferenceGovernanceRegistry,
    ReferenceScenarioConfig,
    ReferenceSmallBaselineRegistry,
    ReferenceSourceRequirements,
    ReferenceSourceResearchRegistry,
)

MAXIMUM_REFERENCE_INPUT_BYTES = 2_000_000


class ReferenceConfigurationError(ValueError):
    """Raised when a Reference design input violates security or schema constraints."""


def _read_bounded_text(root: Path, relative_name: Path, label: str) -> str:
    try:
        resolved = ArtifactLocator(
            root=root,
            relative_name=relative_name,
            maximum_bytes=MAXIMUM_REFERENCE_INPUT_BYTES,
            label=label,
        ).resolve()
        return resolved.read_text("utf-8")
    except (OSError, UnicodeError, ValueError) as exc:
        raise ReferenceConfigurationError(f"unable to read safe {label}") from exc


def _load_yaml(root: Path, relative_name: Path, label: str) -> object:
    try:
        return yaml.safe_load(_read_bounded_text(root, relative_name, label))
    except yaml.YAMLError as exc:
        raise ReferenceConfigurationError(f"{label} is not valid YAML") from exc


def _load_json(root: Path, relative_name: Path, label: str) -> object:
    try:
        return json.loads(_read_bounded_text(root, relative_name, label))
    except json.JSONDecodeError as exc:
        raise ReferenceConfigurationError(f"{label} is not valid JSON") from exc


def load_reference_config(root: Path, relative_name: Path) -> ReferenceScenarioConfig:
    payload = _load_yaml(root, relative_name, "Reference scenario configuration")
    try:
        return ReferenceScenarioConfig.model_validate(payload)
    except ValueError as exc:
        raise ReferenceConfigurationError("Reference configuration violates its design contract") from exc


def load_reference_governance(root: Path, relative_name: Path) -> ReferenceGovernanceRegistry:
    payload = _load_yaml(root, relative_name, "Reference governance registry")
    try:
        return ReferenceGovernanceRegistry.model_validate(payload)
    except ValueError as exc:
        raise ReferenceConfigurationError("Reference governance registry violates its schema") from exc


def load_reference_source_requirements(
    root: Path, relative_name: Path
) -> ReferenceSourceRequirements:
    payload = _load_yaml(root, relative_name, "Reference source requirements")
    try:
        return ReferenceSourceRequirements.model_validate(payload)
    except ValueError as exc:
        raise ReferenceConfigurationError("Reference source requirements violate their schema") from exc


def load_reference_source_research(
    root: Path, relative_name: Path
) -> ReferenceSourceResearchRegistry:
    payload = _load_yaml(root, relative_name, "Reference source research registry")
    try:
        return ReferenceSourceResearchRegistry.model_validate(payload)
    except ValueError as exc:
        raise ReferenceConfigurationError(
            "Reference source research registry violates its schema"
        ) from exc


def load_small_baseline_registry(
    root: Path, relative_name: Path
) -> ReferenceSmallBaselineRegistry:
    payload = _load_json(root, relative_name, "Reference Small baseline registry")
    try:
        return ReferenceSmallBaselineRegistry.model_validate(payload)
    except ValueError as exc:
        raise ReferenceConfigurationError("Reference Small baseline registry violates its schema") from exc
