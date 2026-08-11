"""Immutable companion bindings for the current Reference design draft."""

from __future__ import annotations

from dataclasses import dataclass

from .models import REFERENCE_GENERATION_ORDER


@dataclass(frozen=True)
class ReferenceProtocolRevision:
    """Version identifiers that must advance together at scientific freeze."""

    status: str
    scenario_schema: str
    generator: str
    randomness_namespace: str
    geography: str
    physical: str
    breach: str
    truth: str
    observations: str
    resources: str
    governance: str
    faults: str
    recovery: str
    acceptance: str
    validation: str
    replay_manifest: str
    generation_order: tuple[str, ...]


REFERENCE_PROTOCOL = ReferenceProtocolRevision(
    status="design-draft-development-only",
    scenario_schema="trace-delta-reference-scenario-v1",
    generator="delta-reference-generator-v1",
    randomness_namespace="delta-reference-randomness-v1",
    geography="delta-reference-geography-v1",
    physical="delta-reference-physical-v1",
    breach="delta-reference-breach-v1",
    truth="delta-reference-ground-truth-v1",
    observations="delta-reference-observations-v1",
    resources="delta-reference-resources-v1",
    governance="delta-reference-governance-v1",
    faults="delta-reference-faults-v1",
    recovery="delta-reference-recovery-v1",
    acceptance="delta-reference-acceptance-v1",
    validation="delta-reference-validation-v1",
    replay_manifest="delta-reference-replay-manifest-v1",
    generation_order=REFERENCE_GENERATION_ORDER,
)
