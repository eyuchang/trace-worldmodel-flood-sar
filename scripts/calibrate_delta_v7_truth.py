from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

from trace_jepa.scenario.delta.generator import _projection_hash
from trace_jepa.scenario.delta.loading import (
    load_acceptance_config,
    load_geography_catalog,
    load_scenario_config,
)
from trace_jepa.scenario.delta.physical import (
    generate_crossing_states,
    generate_gauges,
    generate_geography,
    generate_weather,
)
from trace_jepa.scenario.delta.randomness import KeyedRandom
from trace_jepa.scenario.delta.truth_v7 import (
    INCIDENT_REQUIREMENTS_V7,
    IncidentCandidate,
    build_truth_inputs_v7,
)

TARGET_WEIGHTS = {
    "C-STR": 34,
    "C-VEH": 8,
    "C-LEV": 11,
    "C-MED": 14,
    "C-WEL": 20,
    "C-MIS": 13,
}


def _fit_intercept(candidates_by_seed: list[list[IncidentCandidate]], target: float) -> float:
    lower, upper = 0.0, 1.0

    def mean_expected(intercept: float) -> float:
        return sum(
            sum(1.0 - math.exp(-intercept * item.factor) for item in candidates)
            for candidates in candidates_by_seed
        ) / len(candidates_by_seed)

    while mean_expected(upper) < target:
        upper *= 2.0
    for _ in range(100):
        middle = (lower + upper) / 2.0
        if mean_expected(middle) < target:
            lower = middle
        else:
            upper = middle
    return (lower + upper) / 2.0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fit v7 truth type intercepts using only registered development seeds."
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--geography", type=Path, required=True)
    parser.add_argument("--acceptance", type=Path, required=True)
    arguments = parser.parse_args()
    config = load_scenario_config(arguments.config)
    geography = generate_geography(config, load_geography_catalog(arguments.geography))
    acceptance = load_acceptance_config(arguments.acceptance)
    first_seed = acceptance.development_ensemble.first_seed
    seed_count = acceptance.development_ensemble.seed_count
    candidates_by_type: dict[str, list[list[IncidentCandidate]]] = {
        incident_type: [] for incident_type in INCIDENT_REQUIREMENTS_V7
    }
    for seed in range(first_seed, first_seed + seed_count):
        seeded_config = config.model_copy(update={"seed": seed})
        weather = generate_weather(seeded_config)
        gauges = generate_gauges(seeded_config, geography, weather)
        crossing_states = generate_crossing_states(seeded_config, geography, weather, gauges)
        namespace_hash = _projection_hash(
            {
                "scenario_id": seeded_config.scenario_id,
                "generator_version": seeded_config.randomness_namespace_version,
                "extent": seeded_config.extent.model_dump(mode="json"),
            }
        )
        *_, candidates = build_truth_inputs_v7(
            seeded_config,
            geography,
            weather,
            crossing_states,
            KeyedRandom(seed, namespace_hash, "ground_truth"),
        )
        grouped: dict[str, list[IncidentCandidate]] = defaultdict(list)
        for candidate in candidates:
            grouped[candidate.incident_type].append(candidate)
        for incident_type, values in candidates_by_type.items():
            values.append(grouped[incident_type])
    latent_total = config.call_process.latent_expected_incidents
    intercepts = {
        incident_type: _fit_intercept(
            candidates_by_type[incident_type],
            latent_total * TARGET_WEIGHTS[incident_type] / sum(TARGET_WEIGHTS.values()),
        )
        for incident_type in candidates_by_type
    }
    expected_by_type: dict[str, float] = {}
    expected_by_hour = [0.0] * 6
    for incident_type, seed_candidates in candidates_by_type.items():
        intercept = intercepts[incident_type]
        expected_by_type[incident_type] = (
            sum(
                sum(1.0 - math.exp(-intercept * item.factor) for item in candidates)
                for candidates in seed_candidates
            )
            / seed_count
        )
        for candidates in seed_candidates:
            for item in candidates:
                expected_by_hour[item.simulation_time_s // 3_600] += (
                    1.0 - math.exp(-intercept * item.factor)
                ) / seed_count
    print(
        json.dumps(
            {
                "schema_version": "delta-truth-intercept-calibration-v1",
                "development_seed_first": first_seed,
                "development_seed_count": seed_count,
                "target_latent_total": latent_total,
                "target_weights": TARGET_WEIGHTS,
                "intercepts": intercepts,
                "analytical_expected_by_type": expected_by_type,
                "analytical_expected_by_hour": expected_by_hour,
                "analytical_expected_total": sum(expected_by_type.values()),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
