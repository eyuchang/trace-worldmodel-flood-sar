"""Deterministic state transitions for the visible-evidence graph."""

from __future__ import annotations

from collections import defaultdict

from trace_jepa.scenario.delta.domain import CallRecord

from .evidence import (
    callback_is_available,
    link_id,
    soft_evidence,
    visible_contradiction,
)
from .models import (
    ReconciliationArtifact,
    ReconciliationLink,
    ReconciliationNode,
    ReconciliationStep,
)

EVIDENCE_GRAPH_CANDIDATES = {
    "evidence-graph-q075": 0.75,
    "evidence-graph-q100": 1.00,
    "evidence-graph-q125": 1.25,
}


class EvidenceGraphReconciler:
    """Reconcile reports using only evidence visible to the controller."""

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
            link_id=link_id(self.algorithm_id, current.call_id, target.call_id, status, evidence),
            source_call_id=current.call_id,
            target_call_id=target.call_id,
            status=status,
            evidence_families=evidence,
            reason=reason,
        )

    def _hard_link(self, call: CallRecord) -> ReconciliationLink | None:
        revision_source = call.quality.revision_of_call_id
        if revision_source is not None and revision_source in self._calls:
            return self._make_link(
                call,
                self._calls[revision_source],
                "confirmed",
                ("explicit_report_revision",),
                "valid explicit revision pointer to an earlier controller-visible call",
            )
        if not callback_is_available(call):
            return None
        matches = sorted(
            (
                previous
                for previous in self._calls.values()
                if callback_is_available(previous)
                and previous.callback_token == call.callback_token
            ),
            key=lambda item: (self._available_s[item.call_id], item.call_id),
        )
        if not matches:
            return None
        return self._make_link(
            call,
            matches[-1],
            "confirmed",
            ("exact_shared_available_callback_token",),
            "exact available callback token is hard controller-visible evidence",
        )

    def _soft_candidates(
        self, call: CallRecord
    ) -> tuple[
        dict[str, list[tuple[CallRecord, tuple[str, ...]]]],
        list[tuple[CallRecord, tuple[str, ...], bool]],
    ]:
        eligible: dict[str, list[tuple[CallRecord, tuple[str, ...]]]] = defaultdict(list)
        near: list[tuple[CallRecord, tuple[str, ...], bool]] = []
        for previous in sorted(
            self._calls.values(),
            key=lambda item: (self._available_s[item.call_id], item.call_id),
        ):
            compatible, evidence, near_candidate = soft_evidence(
                call, previous, self._spatial_multiplier
            )
            cluster_id = self._cluster_by_call[previous.call_id]
            members = [self._calls[item] for item in self._members_by_cluster[cluster_id]]
            times = [member.received_s for member in members] + [call.received_s]
            span_ok = max(times) - min(times) <= 1_800
            contradiction = any(visible_contradiction(call, member) for member in members)
            if compatible and span_ok and not contradiction:
                eligible[cluster_id].append((previous, evidence))
            elif near_candidate:
                near.append((previous, evidence, contradiction))
        return eligible, near

    def _soft_links(
        self, call: CallRecord
    ) -> tuple[ReconciliationLink | None, list[ReconciliationLink]]:
        eligible, near = self._soft_candidates(call)
        if len(eligible) == 1:
            pairs = next(iter(eligible.values()))
            target, evidence = max(
                pairs,
                key=lambda item: (self._available_s[item[0].call_id], item[0].call_id),
            )
            return self._make_link(
                call,
                target,
                "confirmed",
                evidence,
                "all conservative soft-evidence and unique-cluster guards passed",
            ), []
        if len(eligible) > 1:
            links = []
            for cluster_id in sorted(eligible):
                target, evidence = max(
                    eligible[cluster_id],
                    key=lambda item: (
                        self._available_s[item[0].call_id],
                        item[0].call_id,
                    ),
                )
                links.append(
                    self._make_link(
                        call,
                        target,
                        "suspected",
                        evidence,
                        "multiple eligible destination clusters make the relationship ambiguous",
                    )
                )
            return None, links
        if not near:
            return None, []
        target, evidence, contradiction = max(
            near,
            key=lambda item: (
                len(item[1]),
                self._available_s[item[0].call_id],
                item[0].call_id,
            ),
        )
        return None, [
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
        ]

    def process(self, call: CallRecord, controller_available_s: int) -> ReconciliationStep:
        if call.call_id in self._calls:
            raise ValueError(f"call already reconciled: {call.call_id}")
        if controller_available_s < call.received_s:
            raise ValueError("controller cannot receive a call before it was reported")
        confirmed = self._hard_link(call)
        emitted: list[ReconciliationLink] = []
        if confirmed is None:
            confirmed, emitted = self._soft_links(call)
        cluster_id = call.call_id
        if confirmed is not None:
            cluster_id = self._cluster_by_call[confirmed.target_call_id]
            emitted.append(confirmed)
        self._insert(call, controller_available_s, cluster_id, emitted)
        return ReconciliationStep(
            belief_cluster_id=cluster_id,
            confirmed_link=confirmed,
            emitted_links=tuple(emitted),
        )

    def _insert(
        self,
        call: CallRecord,
        controller_available_s: int,
        cluster_id: str,
        links: list[ReconciliationLink],
    ) -> None:
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
        self._links.extend(links)

    def artifact(self) -> ReconciliationArtifact:
        return ReconciliationArtifact(
            algorithm_id=self.algorithm_id,
            nodes=list(self._nodes),
            links=list(self._links),
            cluster_by_call=dict(sorted(self._cluster_by_call.items())),
        )


def evidence_graph_clusters(calls: list[CallRecord], algorithm_id: str) -> ReconciliationArtifact:
    reconciler = EvidenceGraphReconciler(algorithm_id)
    for call in calls:
        reconciler.process(call, call.received_s)
    return reconciler.artifact()
