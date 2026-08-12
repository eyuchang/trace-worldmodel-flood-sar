"""Compact exact replay kernel used only for Reference observation fitting."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Literal

from trace_reference.domain.exposure import ReferenceExposureScenario
from trace_reference.domain.observations import ReferencePublicTaxonomy
from trace_reference.domain.truth import ReferenceIncidentType, ReferenceTruthScenario

from .observation_parameters import (
    REFERENCE_PUBLIC_TAXONOMY_BY_INCIDENT,
    ReferenceObservationDrawSummary,
    ReferenceObservationFitIncident,
    ReferenceObservationFitPotentials,
    ReferenceObservationGenerationCoefficients,
    observation_draw_micros,
    observation_probability_micros,
    witness_observed_at_s,
)


@dataclass(frozen=True)
class _OptionalFitReport:
    relationship: Literal["duplicate", "multi-channel", "conflict"]
    base_probability_micros: int
    onset_offset_s: int


@dataclass
class _ObservationCountAccumulator:
    hourly: list[int]
    relationships: Counter[str]
    taxonomies: Counter[str]

    @classmethod
    def empty(cls) -> _ObservationCountAccumulator:
        return cls([0] * 96, Counter(), Counter())

    def add(
        self,
        observed_at_s: int,
        relationship: str,
        taxonomy: ReferencePublicTaxonomy,
    ) -> None:
        if 0 <= observed_at_s < 345_600:
            self.hourly[observed_at_s // 3_600] += 1
            self.relationships[relationship] += 1
            self.taxonomies[taxonomy.value] += 1


def _increment_hour(values: list[int], observed_at_s: int) -> None:
    if 0 <= observed_at_s < 345_600:
        values[observed_at_s // 3_600] += 1


def build_reference_observation_fit_potentials(
    truth: ReferenceTruthScenario,
    exposure: ReferenceExposureScenario,
    *,
    seed: int,
    witness_slots: int,
    randomness_namespace: str = "reference-observations-v2",
) -> ReferenceObservationFitPotentials:
    """Count every truth-linked opportunity needed for analytical fitting."""

    if witness_slots < 1:
        raise ValueError("Reference observation fit requires positive witness slots")
    people_by_id = {item.truth_person_id: item for item in exposure.people}
    counts = {
        name: [0] * 96
        for name in (
            "initial",
            "duplicate",
            "multi_channel",
            "conflict",
            "third_party_welfare",
            "stranded_revision",
            "false_benign_levee",
            "witness_opportunities",
        )
    }
    for incident in truth.incidents:
        if incident.onset_s < 0:
            continue
        _increment_hour(counts["initial"], min(345_300, incident.onset_s + 60))
        _increment_hour(counts["duplicate"], min(345_300, incident.onset_s + 120))
        _increment_hour(counts["multi_channel"], min(345_300, incident.onset_s + 300))
        _increment_hour(counts["conflict"], min(345_300, incident.onset_s + 480))
        affected = tuple(people_by_id[item] for item in incident.affected_truth_person_ids)
        if any(
            person.mobility != "standard" or person.medical_dependency != "none"
            for person in affected
        ):
            _increment_hour(counts["third_party_welfare"], min(345_300, incident.onset_s + 900))
        if incident.incident_type == ReferenceIncidentType.STRANDED_STRUCTURE:
            _increment_hour(counts["stranded_revision"], min(345_300, incident.onset_s + 1_800))
        for slot in range(witness_slots):
            _increment_hour(
                counts["witness_opportunities"],
                witness_observed_at_s(
                    seed,
                    randomness_namespace,
                    incident.truth_incident_id,
                    incident.onset_s,
                    slot,
                ),
            )
    for hour_index in range(96):
        counts["false_benign_levee"][hour_index] = 1
    return ReferenceObservationFitPotentials(
        initial=tuple(counts["initial"]),
        duplicate=tuple(counts["duplicate"]),
        multi_channel=tuple(counts["multi_channel"]),
        conflict=tuple(counts["conflict"]),
        third_party_welfare=tuple(counts["third_party_welfare"]),
        stranded_revision=tuple(counts["stranded_revision"]),
        false_benign_levee=tuple(counts["false_benign_levee"]),
        witness_opportunities=tuple(counts["witness_opportunities"]),
    )


def build_reference_observation_fit_incidents(
    truth: ReferenceTruthScenario,
    exposure: ReferenceExposureScenario,
) -> tuple[ReferenceObservationFitIncident, ...]:
    """Reduce a full truth world to count-preserving observation fit records."""

    people_by_id = {item.truth_person_id: item for item in exposure.people}
    records = []
    for incident in truth.incidents:
        if incident.onset_s < 0:
            continue
        affected = tuple(people_by_id[item] for item in incident.affected_truth_person_ids)
        records.append(
            ReferenceObservationFitIncident(
                truth_incident_id=incident.truth_incident_id,
                onset_s=incident.onset_s,
                incident_type=incident.incident_type,
                vulnerable_affected_person=any(
                    person.mobility != "standard" or person.medical_dependency != "none"
                    for person in affected
                ),
            )
        )
    return tuple(records)


def _replay_initial_report_family(
    incident: ReferenceObservationFitIncident,
    accumulator: _ObservationCountAccumulator,
    *,
    seed: int,
    namespace: str,
    iota_micros: int,
) -> None:
    key = incident.truth_incident_id
    taxonomy = REFERENCE_PUBLIC_TAXONOMY_BY_INCIDENT[incident.incident_type]
    accumulator.add(min(345_300, incident.onset_s + 60), "initial", taxonomy)
    optional_reports = (
        _OptionalFitReport("duplicate", 300_000, 120),
        _OptionalFitReport("multi-channel", 140_000, 300),
        _OptionalFitReport("conflict", 160_000, 480),
    )
    for optional in optional_reports:
        if observation_draw_micros(seed, namespace, key, optional.relationship) >= (
            observation_probability_micros(
                optional.base_probability_micros,
                iota_micros,
                inverse=True,
            )
        ):
            continue
        optional_taxonomy = (
            ReferencePublicTaxonomy.C_WEL
            if optional.relationship == "conflict"
            and incident.incident_type != ReferenceIncidentType.WELFARE_CHECK
            else taxonomy
        )
        accumulator.add(
            min(345_300, incident.onset_s + optional.onset_offset_s),
            optional.relationship,
            optional_taxonomy,
        )
    if incident.vulnerable_affected_person and observation_draw_micros(
        seed, namespace, key, "third-party-welfare"
    ) < observation_probability_micros(120_000, iota_micros, inverse=True):
        accumulator.add(
            min(345_300, incident.onset_s + 900),
            "third-party-welfare",
            ReferencePublicTaxonomy.C_WEL,
        )
    if incident.incident_type == ReferenceIncidentType.STRANDED_STRUCTURE and (
        observation_draw_micros(seed, namespace, key, "revision")
        < observation_probability_micros(400_000, iota_micros, inverse=True)
    ):
        accumulator.add(min(345_300, incident.onset_s + 1_800), "revision", taxonomy)


def _replay_witness_family(
    incident: ReferenceObservationFitIncident,
    accumulator: _ObservationCountAccumulator,
    *,
    seed: int,
    coefficients: ReferenceObservationGenerationCoefficients,
) -> None:
    namespace = coefficients.randomness_namespace
    for slot in range(coefficients.supplemental_witness_slots_per_incident):
        observed_at_s = witness_observed_at_s(
            seed,
            namespace,
            incident.truth_incident_id,
            incident.onset_s,
            slot,
        )
        probability = coefficients.hourly_witness_probability_micros[observed_at_s // 3_600]
        witness_key = f"{incident.truth_incident_id}|independent-witness-{slot:02d}"
        if observation_draw_micros(seed, namespace, witness_key, "report") < probability:
            accumulator.add(
                observed_at_s,
                "independent-witness",
                REFERENCE_PUBLIC_TAXONOMY_BY_INCIDENT[incident.incident_type],
            )


def summarize_reference_observation_fit_incidents(
    records: tuple[ReferenceObservationFitIncident, ...],
    *,
    seed: int,
    coefficients: ReferenceObservationGenerationCoefficients,
    iota: float = 0.7,
) -> ReferenceObservationDrawSummary:
    """Replay the exact report-count draws from compact incident records."""

    iota_micros = round(iota * 1_000_000)
    if not 300_000 <= iota_micros <= 1_000_000:
        raise ValueError("Reference iota must remain within the registered axis range")
    namespace = coefficients.randomness_namespace
    accumulator = _ObservationCountAccumulator.empty()

    for incident in records:
        key = incident.truth_incident_id
        initial_reported = observation_draw_micros(seed, namespace, key, "report") < (
            observation_probability_micros(
                coefficients.initial_report_probability_micros,
                iota_micros,
            )
        )
        if initial_reported:
            _replay_initial_report_family(
                incident,
                accumulator,
                seed=seed,
                namespace=namespace,
                iota_micros=iota_micros,
            )
        _replay_witness_family(
            incident,
            accumulator,
            seed=seed,
            coefficients=coefficients,
        )
    for hour_start in range(0, 345_600, 3_600):
        key = f"false-benign-levee|{hour_start}"
        if observation_draw_micros(seed, namespace, key, "report") < (
            observation_probability_micros(90_000, iota_micros, inverse=True)
        ):
            accumulator.add(
                hour_start + 900,
                "false-benign-levee",
                ReferencePublicTaxonomy.C_LEV,
            )
    return ReferenceObservationDrawSummary(
        evaluation_reports=sum(accumulator.hourly),
        hourly_counts=tuple(accumulator.hourly),
        relationship_counts=tuple(sorted(accumulator.relationships.items())),
        taxonomy_counts=tuple(sorted(accumulator.taxonomies.items())),
    )
