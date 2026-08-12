"""Deterministic conservative graph transitions using controller-visible fields only."""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from typing import Literal, TypeAlias

from trace_reference.decision.canonical import decision_digest
from trace_reference.domain.observations import ReferenceAuthorityId, ReferenceRawReport

from .models import (
    ReferenceBeliefCluster,
    ReferenceReconciliationArtifact,
    ReferenceReconciliationLink,
    ReferenceReconciliationStep,
)

_ALGORITHM_ID = "reference-visible-evidence-graph-q075-v1"
_SPATIAL_MULTIPLIER = 0.75
_MAX_LINK_TIME_S = 1_500
_MAX_CLUSTER_SPAN_S = 1_800
_TIME_BUCKET_S = 300
_LinkStatus: TypeAlias = Literal["confirmed", "suspected", "rejected"]
_StepStatus: TypeAlias = Literal["new", "confirmed", "suspected"]


def _id(prefix: str, *parts: object) -> str:
    digest = hashlib.sha256("|".join(str(item) for item in parts).encode()).hexdigest()
    return f"{prefix}-{digest[:16]}"


def _distance_m(left: ReferenceRawReport, right: ReferenceRawReport) -> float:
    return (
        math.hypot(
            left.location.easting_mm_epsg26910 - right.location.easting_mm_epsg26910,
            left.location.northing_mm_epsg26910 - right.location.northing_mm_epsg26910,
        )
        / 1_000
    )


def _callback_available(report: ReferenceRawReport) -> bool:
    return report.callback_token is not None and not report.callback_failed


def _visible_contradiction(left: ReferenceRawReport, right: ReferenceRawReport) -> bool:
    medical = bool(
        left.medical_descriptors
        and right.medical_descriptors
        and left.medical_descriptors != right.medical_descriptors
    )
    occupants = (
        left.reported_occupants is not None
        and right.reported_occupants is not None
        and abs(left.reported_occupants - right.reported_occupants) > 1
    )
    return left.taxonomy != right.taxonomy or medical or occupants


def _soft_evidence(
    current: ReferenceRawReport,
    previous: ReferenceRawReport,
) -> tuple[bool, tuple[str, ...], bool]:
    temporal = abs(current.observed_at_s - previous.observed_at_s) <= _MAX_LINK_TIME_S
    spatial_limit = _SPATIAL_MULTIPLIER * math.sqrt(
        current.location.precision_m**2 + previous.location.precision_m**2
    )
    spatial = _distance_m(current, previous) <= spatial_limit
    taxonomy = current.taxonomy == previous.taxonomy
    descriptor = bool(set(current.descriptor_tokens) & set(previous.descriptor_tokens))
    occupant_medical = not _visible_contradiction(current, previous)
    families = tuple(
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
    return (
        temporal and spatial and taxonomy and (descriptor or occupant_medical),
        families,
        (temporal and spatial),
    )


class ReferenceEvidenceGraph:
    """One logical authority's reversible public-report belief graph."""

    def __init__(self, controller_authority_id: ReferenceAuthorityId) -> None:
        self.controller_authority_id = controller_authority_id
        self._reports: dict[str, ReferenceRawReport] = {}
        self._cluster_by_call: dict[str, str] = {}
        self._members_by_cluster: dict[str, list[str]] = defaultdict(list)
        self._links: list[ReferenceReconciliationLink] = []
        self._time_buckets: dict[int, list[str]] = defaultdict(list)
        self._callback_index: dict[str, list[str]] = defaultdict(list)
        self._processing_order: dict[str, int] = {}

    def process(
        self,
        report: ReferenceRawReport,
        *,
        delivered_at_s: int,
    ) -> ReferenceReconciliationStep:
        if report.call_id in self._reports:
            raise ValueError("Reference report was already processed by this authority")
        hard = self._hard_target(report)
        if hard is not None:
            target, families = hard
            cluster_id = self._cluster_by_call[target.call_id]
            link = self._link(report, target, "confirmed", families, delivered_at_s)
            self._insert(report, cluster_id)
            self._links.append(link)
            return self._step(report, cluster_id, "confirmed", families, (link.link_id,), True)

        candidates = self._soft_candidates(report)
        eligible_clusters = {self._cluster_by_call[item[0].call_id] for item in candidates}
        if len(eligible_clusters) == 1:
            cluster_id = next(iter(eligible_clusters))
            target, families = min(candidates, key=lambda item: item[0].call_id)
            if self._cluster_accepts(cluster_id, report):
                link = self._link(report, target, "confirmed", families, delivered_at_s)
                self._insert(report, cluster_id)
                self._links.append(link)
                return self._step(report, cluster_id, "confirmed", families, (link.link_id,), True)

        suspected = self._suspected_links(report, delivered_at_s)
        cluster_id = _id("RBC", self.controller_authority_id, report.call_id)
        self._insert(report, cluster_id)
        self._links.extend(suspected)
        status: _StepStatus = "suspected" if suspected else "new"
        basis = tuple(sorted({family for link in suspected for family in link.evidence_families}))
        return self._step(
            report,
            cluster_id,
            status,
            basis,
            tuple(item.link_id for item in suspected),
            False,
        )

    def artifact(self) -> ReferenceReconciliationArtifact:
        clusters = []
        for cluster_id, call_ids in self._members_by_cluster.items():
            observations = [self._reports[call_id].observed_at_s for call_id in call_ids]
            clusters.append(
                ReferenceBeliefCluster(
                    cluster_id=cluster_id,
                    call_ids=tuple(sorted(call_ids)),
                    earliest_observed_at_s=min(observations),
                    latest_observed_at_s=max(observations),
                )
            )
        clusters.sort(key=lambda item: item.cluster_id)
        links = tuple(sorted(self._links, key=lambda item: item.link_id))
        body = {
            "schema_version": "delta-reference-reconciliation-v1",
            "algorithm_id": _ALGORITHM_ID,
            "controller_authority_id": self.controller_authority_id,
            "clusters": [item.model_dump(mode="json") for item in clusters],
            "links": [item.model_dump(mode="json") for item in links],
        }
        return ReferenceReconciliationArtifact(
            **body,
            artifact_digest=decision_digest(body),
        )

    def _hard_target(
        self,
        report: ReferenceRawReport,
    ) -> tuple[ReferenceRawReport, tuple[str, ...]] | None:
        revision = report.revision_of_call_id
        if revision is not None and revision in self._reports:
            return self._reports[revision], ("explicit_visible_revision_pointer",)
        if _callback_available(report):
            matches = [
                self._reports[call_id]
                for call_id in self._callback_index.get(report.callback_token or "", ())
            ]
            if len({self._cluster_by_call[item.call_id] for item in matches}) == 1 and matches:
                return min(matches, key=lambda item: item.call_id), ("exact_shared_callback_token",)
        return None

    def _soft_candidates(
        self,
        report: ReferenceRawReport,
    ) -> list[tuple[ReferenceRawReport, tuple[str, ...]]]:
        candidates = []
        for previous in self._temporal_candidates(report):
            accepted, families, _ = _soft_evidence(report, previous)
            if accepted and not _visible_contradiction(report, previous):
                candidates.append((previous, families))
        return candidates

    def _cluster_accepts(self, cluster_id: str, report: ReferenceRawReport) -> bool:
        members = [self._reports[item] for item in self._members_by_cluster[cluster_id]]
        observations = [item.observed_at_s for item in members]
        if (
            max((*observations, report.observed_at_s)) - min((*observations, report.observed_at_s))
            > _MAX_CLUSTER_SPAN_S
        ):
            return False
        return not any(_visible_contradiction(report, item) for item in members)

    def _suspected_links(
        self,
        report: ReferenceRawReport,
        delivered_at_s: int,
    ) -> tuple[ReferenceReconciliationLink, ...]:
        links = []
        for previous in self._temporal_candidates(report):
            _accepted, families, plausible = _soft_evidence(report, previous)
            if plausible:
                status: _LinkStatus = (
                    "rejected" if _visible_contradiction(report, previous) else "suspected"
                )
                links.append(self._link(report, previous, status, families, delivered_at_s))
        return tuple(sorted(links, key=lambda item: item.link_id))

    def _link(
        self,
        current: ReferenceRawReport,
        target: ReferenceRawReport,
        status: _LinkStatus,
        families: tuple[str, ...],
        at_s: int,
    ) -> ReferenceReconciliationLink:
        body = {
            "schema_version": "delta-reference-reconciliation-link-v1",
            "link_id": _id("RRL", self.controller_authority_id, current.call_id, target.call_id),
            "source_call_id": current.call_id,
            "target_call_id": target.call_id,
            "status": status,
            "evidence_families": families or ("visible_contradiction",),
            "decided_at_s": at_s,
        }
        return ReferenceReconciliationLink(**body, link_digest=decision_digest(body))

    def _insert(self, report: ReferenceRawReport, cluster_id: str) -> None:
        self._processing_order[report.call_id] = len(self._processing_order)
        self._reports[report.call_id] = report
        self._cluster_by_call[report.call_id] = cluster_id
        self._members_by_cluster[cluster_id].append(report.call_id)
        self._time_buckets[report.observed_at_s // _TIME_BUCKET_S].append(report.call_id)
        if _callback_available(report):
            self._callback_index[report.callback_token or ""].append(report.call_id)

    def _temporal_candidates(self, report: ReferenceRawReport) -> tuple[ReferenceRawReport, ...]:
        """Return exactly the prior reports inside the hard temporal window."""

        lower = (report.observed_at_s - _MAX_LINK_TIME_S) // _TIME_BUCKET_S
        upper = (report.observed_at_s + _MAX_LINK_TIME_S) // _TIME_BUCKET_S
        call_ids = {
            call_id
            for bucket in range(lower, upper + 1)
            for call_id in self._time_buckets.get(bucket, ())
            if abs(self._reports[call_id].observed_at_s - report.observed_at_s) <= _MAX_LINK_TIME_S
        }
        return tuple(
            self._reports[call_id]
            for call_id in sorted(call_ids, key=self._processing_order.__getitem__)
        )

    def _step(
        self,
        report: ReferenceRawReport,
        cluster_id: str,
        status: _StepStatus,
        basis: tuple[str, ...],
        links: tuple[str, ...],
        repaired: bool,
    ) -> ReferenceReconciliationStep:
        body = {
            "call_id": report.call_id,
            "controller_authority_id": self.controller_authority_id,
            "belief_cluster_id": cluster_id,
            "relationship_status": status,
            "visible_evidence_basis": basis,
            "created_link_ids": links,
            "repaired_prior_belief": repaired,
        }
        return ReferenceReconciliationStep(**body, step_digest=decision_digest(body))
