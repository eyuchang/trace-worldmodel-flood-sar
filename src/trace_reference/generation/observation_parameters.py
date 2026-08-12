"""Immutable observation parameters and keyed channel primitives."""

from __future__ import annotations

from dataclasses import dataclass

from trace_reference.domain.observations import ReferencePublicTaxonomy
from trace_reference.domain.truth import ReferenceIncidentType

from .randomness import uniform_micros

LEGACY_OBSERVATION_RANDOMNESS_NAMESPACE = "reference-observations-v1"

REFERENCE_PUBLIC_TAXONOMY_BY_INCIDENT: dict[ReferenceIncidentType, ReferencePublicTaxonomy] = {
    ReferenceIncidentType.STRANDED_STRUCTURE: ReferencePublicTaxonomy.C_STR,
    ReferenceIncidentType.VEHICLE_RESCUE: ReferencePublicTaxonomy.C_VEH,
    ReferenceIncidentType.LEVEE_INSPECTION: ReferencePublicTaxonomy.C_LEV,
    ReferenceIncidentType.MEDICAL_ACCESS: ReferencePublicTaxonomy.C_MED,
    ReferenceIncidentType.WELFARE_CHECK: ReferencePublicTaxonomy.C_WEL,
    ReferenceIncidentType.MISSING_PERSON: ReferencePublicTaxonomy.C_MIS,
    ReferenceIncidentType.ANIMAL_RESCUE: ReferencePublicTaxonomy.C_ANI,
    ReferenceIncidentType.INFORMATION_NEED: ReferencePublicTaxonomy.C_INF,
    ReferenceIncidentType.HAZARD_RESPONSE: ReferencePublicTaxonomy.C_HAZ,
}


@dataclass(frozen=True)
class ReferenceObservationGenerationCoefficients:
    """Frozen channel coefficients supplied by the caller-trusted pipeline."""

    coefficient_version: str
    coefficient_digest: str
    randomness_namespace: str
    initial_report_probability_micros: int
    supplemental_witness_slots_per_incident: int
    hourly_witness_probability_micros: tuple[int, ...]

    def __post_init__(self) -> None:
        if not 10_000 <= self.initial_report_probability_micros <= 950_000:
            raise ValueError("Reference initial-report probability is outside safe bounds")
        if self.supplemental_witness_slots_per_incident < 0:
            raise ValueError("Reference witness slot count cannot be negative")
        if len(self.hourly_witness_probability_micros) != 96:
            raise ValueError("Reference witness probability vector must cover 96 hours")
        if any(not 0 <= item <= 1_000_000 for item in self.hourly_witness_probability_micros):
            raise ValueError("Reference witness probability is outside [0,1]")


@dataclass(frozen=True)
class ReferenceObservationFitPotentials:
    """Compact sufficient statistics for analytical report expectations."""

    initial: tuple[int, ...]
    duplicate: tuple[int, ...]
    multi_channel: tuple[int, ...]
    conflict: tuple[int, ...]
    third_party_welfare: tuple[int, ...]
    stranded_revision: tuple[int, ...]
    false_benign_levee: tuple[int, ...]
    witness_opportunities: tuple[int, ...]


@dataclass(frozen=True)
class ReferenceObservationDrawSummary:
    """Selected-coefficient stochastic counts without materializing public models."""

    evaluation_reports: int
    hourly_counts: tuple[int, ...]
    relationship_counts: tuple[tuple[str, int], ...]
    taxonomy_counts: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class ReferenceObservationFitIncident:
    """Minimal truth-side state sufficient to replay report-count draws exactly."""

    truth_incident_id: str
    onset_s: int
    incident_type: ReferenceIncidentType
    vulnerable_affected_person: bool


def legacy_reference_observation_coefficients() -> ReferenceObservationGenerationCoefficients:
    """Return the pre-fit channel for historical characterization only."""

    return ReferenceObservationGenerationCoefficients(
        coefficient_version="delta-reference-observation-development-coefficients-v1",
        coefficient_digest="legacy-development-unfrozen",
        randomness_namespace=LEGACY_OBSERVATION_RANDOMNESS_NAMESPACE,
        initial_report_probability_micros=760_000,
        supplemental_witness_slots_per_incident=0,
        hourly_witness_probability_micros=(0,) * 96,
    )


def observation_probability_micros(
    base_micros: int,
    iota_micros: int,
    *,
    inverse: bool = False,
) -> int:
    """Scale one registered mechanism probability by information quality."""

    quality = iota_micros / 700_000
    scaled = base_micros / quality if inverse else base_micros * quality
    return min(950_000, max(10_000, round(scaled)))


def observation_draw_micros(seed: int, namespace: str, key: str, mechanism: str) -> int:
    """Return one semantic-keyed common-random-number draw."""

    return uniform_micros(seed, namespace, key, mechanism)


def witness_observed_at_s(
    seed: int,
    namespace: str,
    truth_incident_id: str,
    onset_s: int,
    slot: int,
) -> int:
    """Return the fixed keyed observation time for one witness opportunity."""

    key = f"{truth_incident_id}|independent-witness-{slot:02d}"
    return min(
        345_300,
        onset_s + 60 + observation_draw_micros(seed, namespace, key, "observation-offset") % 3_301,
    )
