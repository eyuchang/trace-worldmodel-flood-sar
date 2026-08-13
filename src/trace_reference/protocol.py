"""Immutable companion bindings for the current Reference design draft."""

from __future__ import annotations

from dataclasses import dataclass

from .models import REFERENCE_GENERATION_ORDER


@dataclass(frozen=True)
class ReferenceProtocolRevision:
    """Version identifiers that must advance together at scientific freeze."""

    status: str
    approved_decision_set: str
    protocol_amendment_sha256: str
    geography_amendment_sha256: str
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
    coordination: str
    demand_capacity: str
    faults: str
    recovery: str
    acceptance: str
    validation: str
    replay_manifest: str
    generation_order: tuple[str, ...]


REFERENCE_PROTOCOL = ReferenceProtocolRevision(
    status="approved-decisions-development-only",
    approved_decision_set="reference-scientific-decisions-v4",
    protocol_amendment_sha256=("07b0c901231323d1110ded728c8a1bb67e2a110368ed0644113a25626a7303d5"),
    geography_amendment_sha256=("c4c908436ce18b89dbc5e01486fc7119c7bef5fd4b2b2604ebd9aa2ce70be225"),
    scenario_schema="trace-delta-reference-scenario-v5",
    generator="delta-reference-generator-v3",
    randomness_namespace="delta-reference-randomness-v1",
    geography="delta-reference-geography-v3",
    physical="delta-reference-physical-v1",
    breach="delta-reference-breach-v1",
    truth="delta-reference-ground-truth-v2",
    observations="delta-reference-observations-v2",
    resources="delta-reference-resources-v1",
    governance="delta-reference-governance-v1",
    coordination="delta-reference-coordination-v2",
    demand_capacity="delta-reference-demand-capacity-v1",
    faults="delta-reference-faults-v1",
    recovery="delta-reference-recovery-v1",
    acceptance="delta-reference-acceptance-v1",
    validation="delta-reference-validation-v1",
    replay_manifest="delta-reference-replay-manifest-v2",
    generation_order=REFERENCE_GENERATION_ORDER,
)
