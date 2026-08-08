from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from pydantic import Field, model_validator

from trace_jepa.scenario.delta.domain import CallRecord, DeltaModel

EVIDENCE_GRAPH_CANDIDATES = {
    "evidence-graph-q075": 0.75,
    "evidence-graph-q100": 1.00,
    "evidence-graph-q125": 1.25,
}


class ReconciliationLink(DeltaModel):
    link_id: str
    source_call_id: str
    target_call_id: str
    status: str
    evidence_families: tuple[str, ...]
    reason: str
    supersedes_link_id: str | None = None

    @model_validator(mode="after")
    def validate_status(self) -> ReconciliationLink:
        if self.status not in {"confirmed", "suspected", "rejected", "superseded"}:
            raise ValueError("unknown reconciliation link status")
        if self.status == "superseded" and self.supersedes_link_id is None:
            raise ValueError("superseded links must identify the replaced link")
        return self


class ReconciliationNode(DeltaModel):
    call_id: str
    controller_available_s: int = Field(ge=0)
    belief_cluster_id: str


class ReconciliationArtifact(DeltaModel):
    schema_version: str = "delta-reconciliation-v3"
    algorithm_id: str
    hidden_lineage_used: bool = False
    nodes: list[ReconciliationNode]
    links: list[ReconciliationLink]
    cluster_by_call: dict[str, str]


@dataclass(frozen=True)
class ReconciliationStep:
    belief_cluster_id: str
    confirmed_link: ReconciliationLink | None
    emitted_links: tuple[ReconciliationLink, ...]

    @property
    def visible_evidence_basis(self) -> tuple[str, ...]:
        if self.confirmed_link is None:
            return ()
        return (*self.confirmed_link.evidence_families, self.confirmed_link.target_call_id)


def _link_id(
    algorithm_id: str,
    source_call_id: str,
    target_call_id: str,
    status: str,
    evidence_families: Iterable[str],
) -> str:
    payload = "|".join((algorithm_id, source_call_id, target_call_id, status, *evidence_families))
    return "RL-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _distance_m(left: CallRecord, right: CallRecord) -> float:
    return (
        math.hypot(
            left.location.easting_mm - right.location.easting_mm,
            left.location.northing_mm - right.location.northing_mm,
        )
        / 1_000.0
    )


def _callback_is_available(call: CallRecord) -> bool:
    return not call.quality.callback_failed and not call.callback_token.startswith(
        "SYNTH-CB-UNAVAILABLE-"
    )


def _medical_contradiction(left: CallRecord, right: CallRecord) -> bool:
    left_medical = set(left.reported.medical)
    right_medical = set(right.reported.medical)
    return bool(left_medical and right_medical and left_medical != right_medical)


def _visible_contradiction(left: CallRecord, right: CallRecord) -> bool:
    return (
        left.reported.call_type != right.reported.call_type
        or abs(left.reported.occupants - right.reported.occupants) > 1
        or _medical_contradiction(left, right)
    )


def _soft_evidence(
    current: CallRecord,
    previous: CallRecord,
    spatial_multiplier: float,
) -> tuple[bool, tuple[str, ...], bool]:
    temporal = abs(current.received_s - previous.received_s) <= 1_500
    spatial_limit = spatial_multiplier * math.sqrt(
        current.location.precision_m**2 + previous.location.precision_m**2
    )
    spatial = _distance_m(current, previous) <= spatial_limit
    taxonomy = current.reported.call_type == previous.reported.call_type
    descriptor = current.reported.description_token == previous.reported.description_token
    occupant_medical = abs(
        current.reported.occupants - previous.reported.occupants
    ) <= 1 and not _medical_contradiction(current, previous)
    evidence = tuple(
        name
        for name, present in (
            ("temporal_compatibility", temporal),
            ("spatial_uncertainty_compatibility", spatial),
            ("exact_taxonomy_agreement", taxonomy),
            ("shared_nonunique_descriptor", descriptor),
            ("occupant_medical_agreement", occupant_medical),
        )
        if present
    )
    required = temporal and spatial and taxonomy and (descriptor or occupant_medical)
    near_candidate = temporal and spatial
    return required, evidence, near_candidate


class EvidenceGraphReconciler:
    """Deterministic online reconciliation using controller-visible calls only."""

    def __init__(self, algorithm_id: str) -> None:
        try:
            self._spatial_multiplier = EVIDENCE_GRAPH_CANDIDATES[algorithm_id]
        except KeyError as exc:
            raise ValueError(f"unknown evidence-graph algorithm: {algorithm_id}") from exc
        self.algorithm_id = algorithm_id
        self._calls: dict[str, CallRecord] = {}
        self._cluster_by_call: dict[str, str] = {}
        self._members_by_cluster: dict[str, list[str]] = defaultdict(list)
        self._available_s: dict[str, int] = {}
        self._nodes: list[ReconciliationNode] = []
        self._links: list[ReconciliationLink] = []

    def _make_link(
        self,
        current: CallRecord,
        target: CallRecord,
        status: str,
        evidence: tuple[str, ...],
        reason: str,
    ) -> ReconciliationLink:
        return ReconciliationLink(
            link_id=_link_id(
                self.algorithm_id,
                current.call_id,
                target.call_id,
                status,
                evidence,
            ),
            source_call_id=current.call_id,
            target_call_id=target.call_id,
            status=status,
            evidence_families=evidence,
            reason=reason,
        )

    def process(self, call: CallRecord, controller_available_s: int) -> ReconciliationStep:
        if call.call_id in self._calls:
            raise ValueError(f"call already reconciled: {call.call_id}")
        if controller_available_s < call.received_s:
            raise ValueError("controller cannot receive a call before it was reported")

        confirmed: ReconciliationLink | None = None
        emitted: list[ReconciliationLink] = []
        revision_source = call.quality.revision_of_call_id
        if revision_source is not None and revision_source in self._calls:
            target = self._calls[revision_source]
            confirmed = self._make_link(
                call,
                target,
                "confirmed",
                ("explicit_report_revision",),
                "valid explicit revision pointer to an earlier controller-visible call",
            )
        elif _callback_is_available(call):
            callback_matches = sorted(
                (
                    previous
                    for previous in self._calls.values()
                    if _callback_is_available(previous)
                    and previous.callback_token == call.callback_token
                ),
                key=lambda item: (self._available_s[item.call_id], item.call_id),
            )
            if callback_matches:
                confirmed = self._make_link(
                    call,
                    callback_matches[-1],
                    "confirmed",
                    ("exact_shared_available_callback_token",),
                    "exact available callback token is hard controller-visible evidence",
                )

        if confirmed is None:
            eligible_by_cluster: dict[str, list[tuple[CallRecord, tuple[str, ...]]]] = defaultdict(
                list
            )
            near_pairs: list[tuple[CallRecord, tuple[str, ...], bool]] = []
            for previous in sorted(
                self._calls.values(),
                key=lambda item: (self._available_s[item.call_id], item.call_id),
            ):
                compatible, evidence, near_candidate = _soft_evidence(
                    call, previous, self._spatial_multiplier
                )
                cluster_id = self._cluster_by_call[previous.call_id]
                members = [self._calls[item] for item in self._members_by_cluster[cluster_id]]
                resulting_times = [member.received_s for member in members] + [call.received_s]
                span_ok = max(resulting_times) - min(resulting_times) <= 1_800
                contradiction = any(_visible_contradiction(call, member) for member in members)
                if compatible and span_ok and not contradiction:
                    eligible_by_cluster[cluster_id].append((previous, evidence))
                elif near_candidate:
                    near_pairs.append((previous, evidence, contradiction))

            if len(eligible_by_cluster) == 1:
                cluster_id, pairs = next(iter(eligible_by_cluster.items()))
                del cluster_id
                target, evidence = max(
                    pairs,
                    key=lambda item: (self._available_s[item[0].call_id], item[0].call_id),
                )
                confirmed = self._make_link(
                    call,
                    target,
                    "confirmed",
                    evidence,
                    "all conservative soft-evidence and unique-cluster guards passed",
                )
            elif len(eligible_by_cluster) > 1:
                for cluster_id in sorted(eligible_by_cluster):
                    target, evidence = max(
                        eligible_by_cluster[cluster_id],
                        key=lambda item: (
                            self._available_s[item[0].call_id],
                            item[0].call_id,
                        ),
                    )
                    emitted.append(
                        self._make_link(
                            call,
                            target,
                            "suspected",
                            evidence,
                            "multiple eligible destination clusters make the relationship ambiguous",
                        )
                    )
            elif near_pairs:
                target, evidence, contradiction = max(
                    near_pairs,
                    key=lambda item: (
                        len(item[1]),
                        self._available_s[item[0].call_id],
                        item[0].call_id,
                    ),
                )
                emitted.append(
                    self._make_link(
                        call,
                        target,
                        "rejected" if contradiction else "suspected",
                        evidence,
                        (
                            "visible contradiction prevents a soft relationship"
                            if contradiction
                            else "insufficient corroborating visible evidence for confirmation"
                        ),
                    )
                )

        cluster_id = call.call_id
        if confirmed is not None:
            target_cluster = self._cluster_by_call[confirmed.target_call_id]
            cluster_id = target_cluster
            emitted.append(confirmed)
        self._calls[call.call_id] = call
        self._available_s[call.call_id] = controller_available_s
        self._cluster_by_call[call.call_id] = cluster_id
        self._members_by_cluster[cluster_id].append(call.call_id)
        self._nodes.append(
            ReconciliationNode(
                call_id=call.call_id,
                controller_available_s=controller_available_s,
                belief_cluster_id=cluster_id,
            )
        )
        self._links.extend(emitted)
        return ReconciliationStep(
            belief_cluster_id=cluster_id,
            confirmed_link=confirmed,
            emitted_links=tuple(emitted),
        )

    def artifact(self) -> ReconciliationArtifact:
        return ReconciliationArtifact(
            algorithm_id=self.algorithm_id,
            nodes=list(self._nodes),
            links=list(self._links),
            cluster_by_call=dict(sorted(self._cluster_by_call.items())),
        )


def baseline_v7_visible_relationship(
    call: CallRecord,
    earlier_calls: list[CallRecord],
    cluster_by_call: dict[str, str],
) -> tuple[str, tuple[str, ...]]:
    """Immutable v7 online heuristic retained for history and paired evaluation."""

    if call.quality.revision_of_call_id is not None:
        source = call.quality.revision_of_call_id
        return cluster_by_call.get(source, source), ("explicit_report_revision", source)
    for previous in reversed(earlier_calls):
        if call.callback_token == previous.callback_token:
            return cluster_by_call[previous.call_id], (
                "shared_synthetic_callback_token",
                previous.call_id,
            )
    for previous in reversed(earlier_calls):
        if abs(call.received_s - previous.received_s) > 600:
            continue
        if call.reported.call_type != previous.reported.call_type:
            continue
        if _distance_m(call, previous) <= (
            call.location.precision_m + previous.location.precision_m
        ):
            return cluster_by_call[previous.call_id], (
                "spatiotemporal_taxonomy_similarity",
                previous.call_id,
            )
    return call.call_id, ()


def baseline_v7_clusters(calls: list[CallRecord]) -> dict[str, str]:
    """Immutable v7 heuristic for preregistered paired comparison only."""

    earlier: list[CallRecord] = []
    clusters: dict[str, str] = {}
    for call in calls:
        cluster, _basis = baseline_v7_visible_relationship(call, earlier, clusters)
        clusters[call.call_id] = cluster
        earlier.append(call)
    return clusters


def evidence_graph_clusters(calls: list[CallRecord], algorithm_id: str) -> ReconciliationArtifact:
    reconciler = EvidenceGraphReconciler(algorithm_id)
    for call in calls:
        reconciler.process(call, call.received_s)
    return reconciler.artifact()
