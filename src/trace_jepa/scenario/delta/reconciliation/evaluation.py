"""Offline truth-versus-controller evaluation unavailable to runtime policy."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from itertools import combinations
from typing import TYPE_CHECKING

from pydantic import Field

from trace_jepa.scenario.delta.domain import DeltaModel, GeneratedScenario

if TYPE_CHECKING:
    from trace_jepa.scenario.delta.runtime.models import DeltaDecisionEvent


class ReconciliationEvaluation(DeltaModel):
    schema_version: str = "delta-reconciliation-evaluation-v3"
    evaluation_available: bool = True
    unavailable_reason: str | None = None
    call_count: int = Field(ge=0)
    reference_cluster_count: int = Field(ge=0)
    controller_cluster_count: int = Field(ge=0)
    true_positive_pairs: int = Field(ge=0)
    false_positive_pairs: int = Field(ge=0)
    false_negative_pairs: int = Field(ge=0)
    pairwise_precision: float = Field(ge=0.0, le=1.0)
    pairwise_recall: float = Field(ge=0.0, le=1.0)
    pairwise_f1: float = Field(ge=0.0, le=1.0)
    false_merge_rate: float = Field(ge=0.0, le=1.0)
    missed_link_rate: float = Field(ge=0.0, le=1.0)
    false_report_count: int = Field(ge=0)
    false_reports_merged: int = Field(ge=0)
    false_report_merge_rate: float = Field(ge=0.0, le=1.0)
    revision_reference_links: int = Field(ge=0)
    revision_predicted_links: int = Field(ge=0)
    revision_true_positive_links: int = Field(ge=0)
    revision_link_precision: float = Field(ge=0.0, le=1.0)
    revision_link_recall: float = Field(ge=0.0, le=1.0)
    reported_occupant_revisions_scored: int = Field(ge=0)
    reported_occupant_revisions_truth_correct: int = Field(ge=0)
    reported_occupant_revision_truth_accuracy: float = Field(ge=0.0, le=1.0)
    controller_occupant_belief_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    adjusted_rand_index: float = Field(ge=-1.0, le=1.0)

    @property
    def occupant_revision_correctness(self) -> float:
        """Deprecated source-only alias; never serialized as controller performance."""

        return self.reported_occupant_revision_truth_accuracy


def _ratio(numerator: int, denominator: int, *, empty: float) -> float:
    return numerator / denominator if denominator else empty


def _choose_two(count: int) -> int:
    return count * (count - 1) // 2


def _adjusted_rand_index(
    reference_by_call: Mapping[str, str],
    predicted_by_call: Mapping[str, str],
) -> float:
    call_ids = sorted(reference_by_call)
    if len(call_ids) < 2:
        return 1.0
    contingency = Counter(
        (reference_by_call[call_id], predicted_by_call[call_id]) for call_id in call_ids
    )
    reference_sizes = Counter(reference_by_call.values())
    predicted_sizes = Counter(predicted_by_call.values())
    index = sum(_choose_two(count) for count in contingency.values())
    reference_index = sum(_choose_two(count) for count in reference_sizes.values())
    predicted_index = sum(_choose_two(count) for count in predicted_sizes.values())
    total_pairs = _choose_two(len(call_ids))
    expected = reference_index * predicted_index / total_pairs
    maximum = 0.5 * (reference_index + predicted_index)
    denominator = maximum - expected
    if denominator == 0:
        same_partition = all(
            (reference_by_call[left] == reference_by_call[right])
            == (predicted_by_call[left] == predicted_by_call[right])
            for left, right in combinations(call_ids, 2)
        )
        return 1.0 if same_partition else 0.0
    return (index - expected) / denominator


def evaluate_partitions(
    reference_by_call: Mapping[str, str],
    predicted_by_call: Mapping[str, str],
    false_report_call_ids: set[str],
    *,
    revision_links: Sequence[tuple[str, str, bool]] = (),
    occupant_revision_results: Sequence[bool] = (),
) -> ReconciliationEvaluation:
    """Compare complete reference and controller call partitions.

    ``revision_links`` contains ``(revision_call, source_call, reference_is_same)``.
    It deliberately does not encode a public truth label; the boolean is computed
    only inside offline evaluation.
    """
    if set(reference_by_call) != set(predicted_by_call):
        raise ValueError("reference and predicted partitions must contain identical call IDs")
    if not false_report_call_ids <= set(reference_by_call):
        raise ValueError("false-report IDs must be members of the evaluated partition")
    true_positive = 0
    false_positive = 0
    false_negative = 0
    for left, right in combinations(sorted(reference_by_call), 2):
        reference_same = reference_by_call[left] == reference_by_call[right]
        predicted_same = predicted_by_call[left] == predicted_by_call[right]
        true_positive += reference_same and predicted_same
        false_positive += not reference_same and predicted_same
        false_negative += reference_same and not predicted_same
    precision = _ratio(true_positive, true_positive + false_positive, empty=0.0)
    recall = _ratio(true_positive, true_positive + false_negative, empty=1.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    predicted_sizes = Counter(predicted_by_call.values())
    false_reports_merged = sum(
        predicted_sizes[predicted_by_call[call_id]] > 1 for call_id in false_report_call_ids
    )
    revision_reference = sum(reference_same for _call, _source, reference_same in revision_links)
    revision_predicted = sum(
        predicted_by_call[call_id] == predicted_by_call[source_id]
        for call_id, source_id, _reference_same in revision_links
    )
    revision_true_positive = sum(
        reference_same and predicted_by_call[call_id] == predicted_by_call[source_id]
        for call_id, source_id, reference_same in revision_links
    )
    occupant_correct = sum(occupant_revision_results)
    return ReconciliationEvaluation(
        call_count=len(reference_by_call),
        reference_cluster_count=len(set(reference_by_call.values())),
        controller_cluster_count=len(set(predicted_by_call.values())),
        true_positive_pairs=true_positive,
        false_positive_pairs=false_positive,
        false_negative_pairs=false_negative,
        pairwise_precision=precision,
        pairwise_recall=recall,
        pairwise_f1=f1,
        false_merge_rate=_ratio(false_positive, true_positive + false_positive, empty=0.0),
        missed_link_rate=_ratio(false_negative, true_positive + false_negative, empty=0.0),
        false_report_count=len(false_report_call_ids),
        false_reports_merged=false_reports_merged,
        false_report_merge_rate=_ratio(false_reports_merged, len(false_report_call_ids), empty=0.0),
        revision_reference_links=revision_reference,
        revision_predicted_links=revision_predicted,
        revision_true_positive_links=revision_true_positive,
        revision_link_precision=_ratio(revision_true_positive, revision_predicted, empty=0.0),
        revision_link_recall=_ratio(revision_true_positive, revision_reference, empty=1.0),
        reported_occupant_revisions_scored=len(occupant_revision_results),
        reported_occupant_revisions_truth_correct=occupant_correct,
        reported_occupant_revision_truth_accuracy=_ratio(
            occupant_correct, len(occupant_revision_results), empty=1.0
        ),
        adjusted_rand_index=_adjusted_rand_index(reference_by_call, predicted_by_call),
    )


def evaluate_reconciliation(
    scenario: GeneratedScenario,
    decisions: Sequence[DeltaDecisionEvent],
) -> ReconciliationEvaluation:
    """Score controller beliefs against hidden lineage after runtime completion."""
    lineage_by_call = {item.call_id: item for item in scenario.observations.lineage}
    if not lineage_by_call:
        return evaluate_partitions({}, {}, set()).model_copy(
            update={
                "evaluation_available": False,
                "unavailable_reason": "hidden-lineage-artifact-not-provided",
            }
        )
    calls_by_id = {item.call_id: item for item in scenario.observations.calls}
    incidents_by_id = {item.incident_id: item for item in scenario.truth.incidents}
    reference = {
        call_id: (
            lineage.truth_incident_id
            if lineage.truth_incident_id is not None
            else f"false-singleton:{call_id}"
        )
        for call_id, lineage in lineage_by_call.items()
    }
    predicted = {event.call_id: event.belief_cluster_id for event in decisions}
    for call_id in reference:
        predicted.setdefault(call_id, f"unclustered:{call_id}")
    extra = set(predicted) - set(reference)
    if extra:
        raise ValueError(f"controller decisions contain calls absent from lineage: {sorted(extra)}")
    false_ids = {
        call_id for call_id, lineage in lineage_by_call.items() if lineage.truth_incident_id is None
    }
    revision_links: list[tuple[str, str, bool]] = []
    occupant_results: list[bool] = []
    for call_id, call in calls_by_id.items():
        source_id = call.quality.revision_of_call_id
        if source_id is None or source_id not in lineage_by_call:
            continue
        current_truth = lineage_by_call[call_id].truth_incident_id
        source_truth = lineage_by_call[source_id].truth_incident_id
        reference_same = current_truth is not None and current_truth == source_truth
        revision_links.append((call_id, source_id, reference_same))
        if current_truth is not None:
            occupant_results.append(
                call.reported.occupants == len(incidents_by_id[current_truth].person_ids)
            )
    return evaluate_partitions(
        reference,
        predicted,
        false_ids,
        revision_links=revision_links,
        occupant_revision_results=occupant_results,
    )
