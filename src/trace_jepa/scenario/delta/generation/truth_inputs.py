"""Shared exposure, candidate, and historical v7 truth assembly mechanics."""

from __future__ import annotations

import hashlib
import math

from trace_jepa.scenario.delta.domain import (
    CrossingState,
    DeltaScenarioConfig,
    GroundTruth,
    IncidentTruth,
    LeveeTruth,
    PersonPosition,
    PersonTruth,
    StructureState,
    StructureTruth,
    WeatherSample,
)
from trace_jepa.scenario.delta.generation.exposure import (
    generate_levees,
    generate_people_and_positions,
    generate_structure_states,
    generate_structures,
)
from trace_jepa.scenario.delta.generation.incidents import (
    INCIDENT_REQUIREMENTS_V7,
    CandidateInputs,
    IncidentCandidate,
    incident_candidates,
)
from trace_jepa.scenario.delta.generation.randomness import KeyedRandom
from trace_jepa.scenario.delta.geography.models import GeographyCatalog

# These are updated only by the development-seed calibration procedure. The
# committed calibration record binds the exact values and target taxonomy.
TYPE_INTERCEPTS_V1 = {
    "C-STR": 0.003802684544028396,
    "C-VEH": 0.010590227133044604,
    "C-LEV": 0.24001430962351156,
    "C-MED": 0.005440831471262897,
    "C-WEL": 0.003542798578404174,
    "C-MIS": 0.00872872306670035,
}


def build_truth_inputs_v7(
    config: DeltaScenarioConfig,
    geography: GeographyCatalog,
    weather: list[WeatherSample],
    crossing_states: list[CrossingState],
    keyed: KeyedRandom,
) -> tuple[
    list[StructureTruth],
    list[StructureState],
    list[PersonTruth],
    list[PersonPosition],
    list[LeveeTruth],
    list[IncidentCandidate],
]:
    high_vulnerability = config.axes.exposure_profile != "isleton_small_v1"
    structures = generate_structures(geography, keyed, high_vulnerability)
    people, positions = generate_people_and_positions(config, structures, keyed, high_vulnerability)
    states = generate_structure_states(config, structures, weather, keyed)
    levees = generate_levees(config, weather)
    candidates = incident_candidates(
        CandidateInputs(
            config=config,
            structures=structures,
            states=states,
            people=people,
            positions=positions,
            levees=levees,
            weather=weather,
            crossing_states=crossing_states,
        )
    )
    return structures, states, people, positions, levees, candidates


def expected_incidents_by_type_v7(candidates: list[IncidentCandidate]) -> dict[str, float]:
    result = dict.fromkeys(INCIDENT_REQUIREMENTS_V7, 0.0)
    for candidate in candidates:
        intercept = TYPE_INTERCEPTS_V1[candidate.incident_type]
        result[candidate.incident_type] += 1.0 - math.exp(-intercept * candidate.factor)
    return result


def generate_truth_v7(
    config: DeltaScenarioConfig,
    geography: GeographyCatalog,
    weather: list[WeatherSample],
    crossing_states: list[CrossingState],
    keyed: KeyedRandom,
) -> GroundTruth:
    structures, states, people, positions, levees, candidates = build_truth_inputs_v7(
        config,
        geography,
        weather,
        crossing_states,
        keyed,
    )
    incidents: list[IncidentTruth] = []
    for candidate in candidates:
        intercept = TYPE_INTERCEPTS_V1[candidate.incident_type]
        probability = 1.0 - math.exp(-intercept * candidate.factor)
        candidate_key = (
            candidate.structure_id,
            candidate.simulation_time_s,
            candidate.incident_type,
            candidate.infrastructure_id or "no-infrastructure",
        )
        if not keyed.bernoulli(probability, "incident-candidate", *candidate_key):
            continue
        incident_digest = hashlib.sha256(
            "|".join(str(item) for item in candidate_key).encode("utf-8")
        ).hexdigest()[:12]
        complexity_milli = keyed.randint(0, 1_000, "incident-complexity", *candidate_key)
        capability, service_duration_s = INCIDENT_REQUIREMENTS_V7[candidate.incident_type]
        service_units = (
            2
            if candidate.incident_type in {"C-STR", "C-MED"} and len(candidate.person_ids) >= 3
            else 1
        )
        incidents.append(
            IncidentTruth(
                incident_id=f"INC7-{incident_digest}",
                structure_id=candidate.structure_id,
                person_ids=list(candidate.person_ids),
                incident_type=candidate.incident_type,
                required_capability=capability,
                onset_s=candidate.simulation_time_s,
                service_duration_s=service_duration_s,
                service_units=service_units,
                complexity_milli=complexity_milli,
                causal_mechanism=candidate.causal_mechanism,
                infrastructure_id=candidate.infrastructure_id,
                causal_factors_milli={
                    "hazard": round(1_000 * candidate.hazard_factor),
                    "occupancy": round(1_000 * candidate.occupancy_factor),
                    "vulnerability": round(1_000 * candidate.vulnerability_factor),
                    "access": round(1_000 * candidate.access_factor),
                    "candidate_probability": round(1_000 * probability),
                },
            )
        )
    return GroundTruth(
        schema_version="delta-ground-truth-v4",
        cohort_label="synthetic-isleton-teaching-cohort-v3-not-demographic",
        structures=structures,
        structure_states=states,
        people=people,
        person_positions=positions,
        levees=levees,
        incidents=sorted(incidents, key=lambda item: (item.onset_s, item.incident_id)),
    )
