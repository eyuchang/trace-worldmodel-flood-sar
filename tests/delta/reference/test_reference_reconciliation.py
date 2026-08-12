from __future__ import annotations

from trace_reference.domain.observations import (
    ReferencePublicLocation,
    ReferencePublicTaxonomy,
    ReferenceRawReport,
)
from trace_reference.reconciliation import ReferenceEvidenceGraph


def _report(
    index: int,
    *,
    observed_at_s: int = 1_000,
    east_mm: int = 621_000_000,
    callback_token: str | None = None,
    taxonomy: ReferencePublicTaxonomy = ReferencePublicTaxonomy.C_STR,
    occupants: int | None = 2,
    descriptor: str = "water-rising",
    revision_of: str | None = None,
) -> ReferenceRawReport:
    return ReferenceRawReport(
        call_id=f"RC-{index:016x}",
        observed_at_s=observed_at_s,
        channel="911",
        callback_token=callback_token,
        callback_failed=callback_token is None,
        call_dropped=False,
        third_party=False,
        language_access="english",
        location=ReferencePublicLocation(
            easting_mm_epsg26910=east_mm,
            northing_mm_epsg26910=4_222_000_000,
            precision_m=100,
            method="landmark",
            stated_descriptor="near the source-derived island anchor",
        ),
        taxonomy=taxonomy,
        reported_occupants=occupants,
        medical_descriptors=(),
        descriptor_tokens=(descriptor,),
        revision_of_call_id=revision_of,
    )


def test_reference_reconciliation_hard_links_visible_revision_and_callback() -> None:
    graph = ReferenceEvidenceGraph("AUTH-01")
    first = _report(1, callback_token="SYN-CB-0000000000000001")
    graph.process(first, delivered_at_s=1_100)
    duplicate = _report(
        2,
        observed_at_s=1_200,
        callback_token="SYN-CB-0000000000000001",
    )
    linked = graph.process(duplicate, delivered_at_s=1_300)
    assert linked.relationship_status == "confirmed"
    assert linked.visible_evidence_basis == ("exact_shared_callback_token",)

    revision = _report(
        3,
        observed_at_s=1_400,
        taxonomy=ReferencePublicTaxonomy.C_MED,
        occupants=4,
        revision_of=first.call_id,
    )
    revised = graph.process(revision, delivered_at_s=1_500)
    assert revised.relationship_status == "confirmed"
    assert revised.visible_evidence_basis == ("explicit_visible_revision_pointer",)
    assert revised.belief_cluster_id == linked.belief_cluster_id


def test_reference_reconciliation_ambiguous_soft_evidence_remains_suspected() -> None:
    graph = ReferenceEvidenceGraph("AUTH-02")
    graph.process(_report(1, east_mm=621_000_000), delivered_at_s=1_100)
    graph.process(_report(2, east_mm=621_200_000), delivered_at_s=1_100)
    ambiguous = graph.process(
        _report(3, east_mm=621_100_000, observed_at_s=1_100),
        delivered_at_s=1_200,
    )
    assert ambiguous.relationship_status == "suspected"
    assert not ambiguous.repaired_prior_belief
    artifact = graph.artifact()
    assert len(artifact.clusters) == 3
    assert all(link.status == "suspected" for link in artifact.links)


def test_reference_reconciliation_visible_contradiction_rejects_soft_merge() -> None:
    graph = ReferenceEvidenceGraph("AUTH-03")
    graph.process(_report(1), delivered_at_s=1_100)
    contradictory = graph.process(
        _report(2, taxonomy=ReferencePublicTaxonomy.C_MED),
        delivered_at_s=1_200,
    )
    assert contradictory.relationship_status == "suspected"
    artifact = graph.artifact()
    assert len(artifact.clusters) == 2
    assert artifact.links[0].status == "rejected"


def test_reference_reconciliation_is_deterministic_and_public_only() -> None:
    reports = (
        _report(1),
        _report(2, observed_at_s=1_100, descriptor="porch-visible"),
    )
    artifacts = []
    for _ in range(2):
        graph = ReferenceEvidenceGraph("AUTH-04")
        for report in reports:
            graph.process(report, delivered_at_s=report.observed_at_s + 60)
        artifacts.append(graph.artifact())
    assert artifacts[0].model_dump_json() == artifacts[1].model_dump_json()
    public = artifacts[0].model_dump_json()
    for forbidden in ("truth_incident", "truth_person", "hidden_lineage", "RI-", "RP-"):
        assert forbidden not in public
