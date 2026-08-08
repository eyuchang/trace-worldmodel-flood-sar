from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

from trace_jepa.scenario.delta.geography_models import GeographyCatalog
from trace_jepa.scenario.delta.models import (
    CrossingState,
    DeltaScenarioConfig,
    GroundTruthV8,
    IncidentCandidateAudit,
    IncidentTruth,
    LeveeTruth,
    PersonPosition,
    PersonTruth,
    StructureState,
    StructureTruth,
    WeatherSample,
)
from trace_jepa.scenario.delta.randomness import KeyedRandom
from trace_jepa.scenario.delta.truth_v7 import (
    INCIDENT_REQUIREMENTS_V7,
    IncidentCandidate,
    build_truth_inputs_v7,
)

# Placeholder development coefficients. They are replaced only by the committed
# calibration procedure before v8 becomes the default or a holdout is derived.
TYPE_INTERCEPTS_V2 = {
    "C-STR": 0.003802684544028396,
    "C-VEH": 0.010590227133044604,
    "C-LEV": 0.24001430962351156,
    "C-MED": 0.005440831471262897,
    "C-WEL": 0.003542798578404174,
    "C-MIS": 0.00872872306670035,
}


@dataclass(frozen=True)
class EpisodeCandidate:
    candidate: IncidentCandidate
    candidate_digest: str
    draw_digest: str
    episode_key: str
    probability: float
    accepted_draw: bool


def _digest(*parts: object) -> str:
    return hashlib.sha256("\x1f".join(str(part) for part in parts).encode("utf-8")).hexdigest()


def _candidate_identity(candidate: IncidentCandidate) -> tuple[object, ...]:
    return (
        candidate.structure_id,
        candidate.simulation_time_s,
        candidate.incident_type,
        candidate.infrastructure_id or "no-infrastructure",
        ",".join(candidate.person_ids),
    )


def _eligibility_subject(candidate: IncidentCandidate) -> str:
    if candidate.incident_type == "C-LEV":
        return candidate.infrastructure_id or candidate.structure_id
    return ",".join(sorted(candidate.person_ids))


def _episode_base(candidate: IncidentCandidate) -> tuple[str, str, str]:
    anchor = (
        candidate.infrastructure_id
        if candidate.incident_type == "C-LEV" and candidate.infrastructure_id is not None
        else candidate.structure_id
    )
    return candidate.incident_type, anchor, _eligibility_subject(candidate)


def form_episode_candidates_v8(
    candidates: list[IncidentCandidate],
    keyed: KeyedRandom,
    tick_s: int,
    intercepts: dict[str, float] | None = None,
) -> list[EpisodeCandidate]:
    """Assign continuous eligibility episodes without changing keyed draws.

    A new episode begins when the eligibility subject changes or eligibility was
    absent for at least one simulation tick. The candidate draw remains keyed to
    the original structure/tick/type identity, preserving common random numbers.
    """

    coefficients = intercepts or TYPE_INTERCEPTS_V2
    ordered = sorted(
        candidates,
        key=lambda item: (
            item.simulation_time_s,
            item.incident_type,
            item.structure_id,
            item.infrastructure_id or "",
            _digest(*_candidate_identity(item)),
        ),
    )
    last_time_by_base: dict[tuple[str, str, str], int] = {}
    episode_number_by_base: dict[tuple[str, str, str], int] = {}
    result: list[EpisodeCandidate] = []
    for candidate in ordered:
        base = _episode_base(candidate)
        previous_time = last_time_by_base.get(base)
        if previous_time is None or candidate.simulation_time_s != previous_time + tick_s:
            episode_number_by_base[base] = episode_number_by_base.get(base, 0) + 1
        last_time_by_base[base] = candidate.simulation_time_s
        episode_key = _digest("episode-v1", *base, episode_number_by_base[base])
        identity = _candidate_identity(candidate)
        candidate_digest = _digest("candidate-v1", *identity)
        draw_digest = _digest(
            keyed.root_seed,
            keyed.parameter_hash,
            keyed.stage_name,
            "incident-candidate",
            *identity[:-1],
        )
        probability = 1.0 - math.exp(-coefficients[candidate.incident_type] * candidate.factor)
        result.append(
            EpisodeCandidate(
                candidate=candidate,
                candidate_digest=candidate_digest,
                draw_digest=draw_digest,
                episode_key=episode_key,
                probability=probability,
                accepted_draw=keyed.bernoulli(
                    probability,
                    "incident-candidate",
                    candidate.structure_id,
                    candidate.simulation_time_s,
                    candidate.incident_type,
                    candidate.infrastructure_id or "no-infrastructure",
                ),
            )
        )
    return result


def _truth_from_inputs_v8(
    config: DeltaScenarioConfig,
    structures: list[StructureTruth],
    states: list[StructureState],
    people: list[PersonTruth],
    positions: list[PersonPosition],
    levees: list[LeveeTruth],
    episode_candidates: list[EpisodeCandidate],
    keyed: KeyedRandom,
) -> GroundTruthV8:
    incidents: list[IncidentTruth] = []
    audit: list[IncidentCandidateAudit] = []
    accepted_episode_keys: set[str] = set()
    for item in episode_candidates:
        candidate = item.candidate
        if not item.accepted_draw:
            disposition = "rejected_by_keyed_draw"
            suppression_reason = None
        elif item.episode_key in accepted_episode_keys:
            disposition = "suppressed_existing_episode_incident"
            suppression_reason = "one-incident-per-continuous-eligibility-episode"
        else:
            disposition = "accepted_as_truth_incident"
            suppression_reason = None
            accepted_episode_keys.add(item.episode_key)
            capability, service_duration_s = INCIDENT_REQUIREMENTS_V7[candidate.incident_type]
            service_units = (
                2
                if candidate.incident_type in {"C-STR", "C-MED"} and len(candidate.person_ids) >= 3
                else 1
            )
            incident_digest = _digest("incident-v8", item.episode_key, item.candidate_digest)[:12]
            incidents.append(
                IncidentTruth(
                    incident_id=f"INC8-{incident_digest}",
                    structure_id=candidate.structure_id,
                    person_ids=list(candidate.person_ids),
                    incident_type=candidate.incident_type,
                    required_capability=capability,
                    onset_s=candidate.simulation_time_s,
                    service_duration_s=service_duration_s,
                    service_units=service_units,
                    complexity_milli=keyed.randint(
                        0,
                        1_000,
                        "incident-complexity",
                        candidate.structure_id,
                        candidate.simulation_time_s,
                        candidate.incident_type,
                        candidate.infrastructure_id or "no-infrastructure",
                    ),
                    causal_mechanism=candidate.causal_mechanism.replace("-v1", "-episode-v2"),
                    infrastructure_id=candidate.infrastructure_id,
                    causal_factors_milli={
                        "hazard": round(1_000 * candidate.hazard_factor),
                        "occupancy": round(1_000 * candidate.occupancy_factor),
                        "vulnerability": round(1_000 * candidate.vulnerability_factor),
                        "access": round(1_000 * candidate.access_factor),
                        "candidate_probability": round(1_000 * item.probability),
                    },
                )
            )
        audit.append(
            IncidentCandidateAudit(
                candidate_digest=item.candidate_digest,
                draw_digest=item.draw_digest,
                structure_id=candidate.structure_id,
                infrastructure_id=candidate.infrastructure_id,
                incident_type=candidate.incident_type,
                simulation_time_s=candidate.simulation_time_s,
                probability_millionths=round(1_000_000 * item.probability),
                episode_key=item.episode_key,
                disposition=disposition,
                suppression_reason=suppression_reason,
            )
        )
    accepted_episode_list = [
        item.episode_key for item in audit if item.disposition == "accepted_as_truth_incident"
    ]
    if len(accepted_episode_list) != len(set(accepted_episode_list)):
        raise RuntimeError("more than one truth incident was accepted within an episode")
    return GroundTruthV8(
        schema_version="delta-ground-truth-v5",
        cohort_label="synthetic-isleton-teaching-cohort-v4-not-demographic",
        structures=structures,
        structure_states=states,
        people=people,
        person_positions=positions,
        levees=levees,
        incidents=sorted(incidents, key=lambda incident: (incident.onset_s, incident.incident_id)),
        candidate_audit=audit,
    )


def generate_truth_v8(
    config: DeltaScenarioConfig,
    geography: GeographyCatalog,
    weather: list[WeatherSample],
    crossing_states: list[CrossingState],
    keyed: KeyedRandom,
    *,
    intercepts: dict[str, float] | None = None,
) -> GroundTruthV8:
    structures, states, people, positions, levees, candidates = build_truth_inputs_v7(
        config, geography, weather, crossing_states, keyed
    )
    episode_candidates = form_episode_candidates_v8(
        candidates,
        keyed,
        config.timeline.tick_s,
        intercepts,
    )
    return _truth_from_inputs_v8(
        config,
        structures,
        states,
        people,
        positions,
        levees,
        episode_candidates,
        keyed,
    )


def expected_incidents_by_type_v8(
    episode_candidates: list[EpisodeCandidate],
) -> dict[str, float]:
    """Expected count after one-incident episode thinning.

    Candidate acceptances within an episode are independent keyed Bernoulli draws;
    the probability of at least one acceptance is one minus the product of all
    rejection probabilities.
    """

    rejection_by_episode: dict[tuple[str, str], float] = {}
    for item in episode_candidates:
        key = (item.candidate.incident_type, item.episode_key)
        rejection_by_episode[key] = rejection_by_episode.get(key, 1.0) * (1.0 - item.probability)
    result = {incident_type: 0.0 for incident_type in INCIDENT_REQUIREMENTS_V7}
    for (incident_type, _episode_key), rejection_probability in rejection_by_episode.items():
        result[incident_type] += 1.0 - rejection_probability
    return result
