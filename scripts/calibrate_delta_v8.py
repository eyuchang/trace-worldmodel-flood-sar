from __future__ import annotations

import argparse
import hashlib
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, cast

from trace_jepa.scenario.delta.artifacts import canonical_json_bytes, sha256_file
from trace_jepa.scenario.delta.generator import _projection_hash
from trace_jepa.scenario.delta.loading import (
    load_acceptance_config,
    load_geography_catalog,
    load_scenario_config,
)
from trace_jepa.scenario.delta.models import CrossingState, WeatherSample
from trace_jepa.scenario.delta.observations_v8 import (
    channel_probabilities_v8,
    generate_observations_v8,
)
from trace_jepa.scenario.delta.physical import (
    generate_crossing_states,
    generate_gauges,
    generate_geography,
    generate_weather,
)
from trace_jepa.scenario.delta.randomness import KeyedRandom
from trace_jepa.scenario.delta.truth_v7 import INCIDENT_REQUIREMENTS_V7, build_truth_inputs_v7
from trace_jepa.scenario.delta.truth_v8 import (
    EpisodeCandidate,
    form_episode_candidates_v8,
    generate_truth_v8,
)

TARGET_WEIGHTS = {
    "C-STR": 34,
    "C-VEH": 8,
    "C-LEV": 11,
    "C-MED": 14,
    "C-WEL": 20,
    "C-MIS": 13,
}
LOG10_LOWER = -8.0
LOG10_UPPER = 2.0
SOLVER_ITERATIONS = 80


def _mean_episode_expectation(
    episodes_by_seed: list[list[EpisodeCandidate]],
    incident_type: str,
    coefficient: float,
) -> float:
    total = 0.0
    for episodes in episodes_by_seed:
        factor_by_episode: dict[str, float] = defaultdict(float)
        for item in episodes:
            if item.candidate.incident_type == incident_type:
                factor_by_episode[item.episode_key] += item.candidate.factor
        total += sum(1.0 - math.exp(-coefficient * factor) for factor in factor_by_episode.values())
    return total / len(episodes_by_seed)


def _fit_type_intercept(
    episodes_by_seed: list[list[EpisodeCandidate]],
    incident_type: str,
    target: float,
) -> tuple[float, list[dict[str, float | int | str]]]:
    lower = LOG10_LOWER
    upper = LOG10_UPPER
    trace: list[dict[str, float | int | str]] = []
    for iteration in range(SOLVER_ITERATIONS):
        middle = (lower + upper) / 2.0
        coefficient = 10.0**middle
        expected = _mean_episode_expectation(episodes_by_seed, incident_type, coefficient)
        trace.append(
            {
                "incident_type": incident_type,
                "iteration": iteration,
                "log10_coefficient": middle,
                "coefficient": coefficient,
                "mean_expected_incidents": expected,
                "target_incidents": target,
                "squared_error": (expected - target) ** 2,
            }
        )
        if expected < target:
            lower = middle
        else:
            upper = middle
    return 10.0 ** ((lower + upper) / 2.0), trace


def _namespace_hash(config: Any) -> str:
    return _projection_hash(
        {
            "scenario_id": config.scenario_id,
            "generator_version": "delta-small-generator-v8",
            "extent": config.extent.model_dump(mode="json"),
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fit v8 episode-aware truth and observation coefficients on development seeds."
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--geography", type=Path, required=True)
    parser.add_argument("--acceptance", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()

    config = load_scenario_config(arguments.config)
    catalog = load_geography_catalog(arguments.geography)
    geography = generate_geography(config, catalog)
    acceptance = load_acceptance_config(arguments.acceptance)
    seeds = list(
        range(
            acceptance.development_ensemble.first_seed,
            acceptance.development_ensemble.first_seed + acceptance.development_ensemble.seed_count,
        )
    )
    namespace_hash = _namespace_hash(config)
    physical_by_seed: dict[int, tuple[list[WeatherSample], list[CrossingState]]] = {}
    episodes_by_seed: list[list[EpisodeCandidate]] = []
    all_one = dict.fromkeys(INCIDENT_REQUIREMENTS_V7, 1.0)
    for seed in seeds:
        seeded = config.model_copy(update={"seed": seed})
        weather = generate_weather(seeded)
        gauges = generate_gauges(seeded, geography, weather)
        crossings = generate_crossing_states(seeded, geography, weather, gauges)
        physical_by_seed[seed] = (weather, crossings)
        *_, candidates = build_truth_inputs_v7(
            seeded,
            geography,
            weather,
            crossings,
            KeyedRandom(seed, namespace_hash, "ground_truth"),
        )
        episodes_by_seed.append(
            form_episode_candidates_v8(
                candidates,
                KeyedRandom(seed, namespace_hash, "ground_truth"),
                seeded.timeline.tick_s,
                all_one,
            )
        )

    weight_total = sum(TARGET_WEIGHTS.values())
    intercepts: dict[str, float] = {}
    solver_trace: list[dict[str, float | int | str]] = []
    expected_by_type: dict[str, float] = {}
    for incident_type in INCIDENT_REQUIREMENTS_V7:
        target = (
            config.call_process.latent_expected_incidents
            * TARGET_WEIGHTS[incident_type]
            / weight_total
        )
        coefficient, trace = _fit_type_intercept(episodes_by_seed, incident_type, target)
        intercepts[incident_type] = coefficient
        solver_trace.extend(trace)
        expected_by_type[incident_type] = _mean_episode_expectation(
            episodes_by_seed, incident_type, coefficient
        )

    truths = []
    realized_by_hour: list[list[int]] = []
    realized_taxonomy: Counter[str] = Counter()
    for seed in seeds:
        seeded = config.model_copy(update={"seed": seed})
        weather, crossings = physical_by_seed[seed]
        truth = generate_truth_v8(
            seeded,
            geography,
            weather,
            crossings,
            KeyedRandom(seed, namespace_hash, "ground_truth"),
            intercepts=intercepts,
        )
        truths.append(truth)
        realized_taxonomy.update(item.incident_type for item in truth.incidents)
        realized_by_hour.append(
            [
                sum(hour * 3_600 <= item.onset_s < (hour + 1) * 3_600 for item in truth.incidents)
                for hour in range(6)
            ]
        )

    probabilities = channel_probabilities_v8(config.axes.iota)
    report_multiplier = 1.0 + sum(
        probabilities[name] for name in ("duplicate", "multi_channel", "conflict", "revision")
    )
    mean_latent_by_hour = [
        statistics.fmean(row[hour] for row in realized_by_hour) for hour in range(6)
    ]
    minimum_false_by_hour = [
        max(0.0, target - latent * report_multiplier * 0.995)
        for target, latent in zip(
            config.call_process.hourly_intensity, mean_latent_by_hour, strict=True
        )
    ]
    minimum_false_total = sum(minimum_false_by_hour)
    if minimum_false_total > probabilities["false_report_mean"]:
        raise RuntimeError("the frozen false-report mean cannot satisfy the hourly call targets")
    residual_false = probabilities["false_report_mean"] - minimum_false_total
    target_total = sum(config.call_process.hourly_intensity)
    false_report_hour_weights = cast(
        tuple[float, float, float, float, float, float],
        tuple(
            (minimum + residual_false * target / target_total) / probabilities["false_report_mean"]
            for minimum, target in zip(
                minimum_false_by_hour, config.call_process.hourly_intensity, strict=True
            )
        ),
    )
    reporting_by_hour = cast(
        tuple[float, float, float, float, float, float],
        tuple(
            min(
                0.995,
                max(
                    0.35,
                    (target - probabilities["false_report_mean"] * false_report_hour_weights[hour])
                    / max(1e-12, latent * report_multiplier),
                ),
            )
            for hour, (target, latent) in enumerate(
                zip(config.call_process.hourly_intensity, mean_latent_by_hour, strict=True)
            )
        ),
    )

    observed_totals: list[int] = []
    observed_by_hour: list[list[int]] = []
    relationship_counts: Counter[str] = Counter()
    method_counts: Counter[str] = Counter()
    callback_failures = 0
    dropped_calls = 0
    for seed, truth in zip(seeds, truths, strict=True):
        seeded = config.model_copy(update={"seed": seed})
        observations = generate_observations_v8(
            seeded,
            truth,
            KeyedRandom(seed, namespace_hash, "observations"),
            reporting_by_hour=reporting_by_hour,
            false_report_hour_weights=false_report_hour_weights,
        )
        observed_totals.append(len(observations.calls))
        observed_by_hour.append(
            [
                sum(
                    hour * 3_600 <= call.received_s < (hour + 1) * 3_600
                    for call in observations.calls
                )
                for hour in range(6)
            ]
        )
        relationship_counts.update(item.relationship for item in observations.lineage)
        method_counts.update(item.location.method for item in observations.calls)
        callback_failures += sum(item.quality.callback_failed for item in observations.calls)
        dropped_calls += sum(item.quality.call_dropped for item in observations.calls)

    call_denominator = sum(observed_totals)
    candidate_trace_hash = hashlib.sha256(canonical_json_bytes(solver_trace)).hexdigest()
    record = {
        "schema_version": "delta-v8-process-coefficient-calibration-v1",
        "protocol_role": "development-only-fitting-before-confirmatory-v7-derivation",
        "development_seeds": {
            "first_seed": seeds[0],
            "seed_count": len(seeds),
            "last_seed": seeds[-1],
        },
        "inputs": {
            "scenario_configuration_sha256": sha256_file(arguments.config),
            "acceptance_with_development_seed_definition_sha256": sha256_file(arguments.acceptance),
            "geography_catalog_sha256": sha256_file(arguments.geography),
            "calibration_script_sha256": sha256_file(Path(__file__)),
            "truth_implementation_sha256": sha256_file(
                Path(__file__).resolve().parents[1] / "src/trace_jepa/scenario/delta/truth_v8.py"
            ),
            "observation_implementation_sha256": sha256_file(
                Path(__file__).resolve().parents[1]
                / "src/trace_jepa/scenario/delta/observations_v8.py"
            ),
        },
        "solver": {
            "method": "independent-bounded-log10-bisection-v1",
            "lower_log10": LOG10_LOWER,
            "upper_log10": LOG10_UPPER,
            "iterations_per_type": SOLVER_ITERATIONS,
            "candidate_trace_sha256": candidate_trace_hash,
            "candidate_trace": solver_trace,
            "converged": True,
            "final_objective": sum(
                (
                    expected_by_type[incident_type]
                    - config.call_process.latent_expected_incidents
                    * TARGET_WEIGHTS[incident_type]
                    / weight_total
                )
                ** 2
                for incident_type in expected_by_type
            ),
        },
        "truth": {
            "coefficients_version": "delta-truth-intercepts-v2",
            "target_expected_latent_total": config.call_process.latent_expected_incidents,
            "target_taxonomy_weights": TARGET_WEIGHTS,
            "type_intercepts": intercepts,
            "analytical_expected_by_type": expected_by_type,
            "analytical_expected_total": sum(expected_by_type.values()),
            "realized_development_mean": statistics.fmean(len(item.incidents) for item in truths),
            "realized_development_range": [
                min(len(item.incidents) for item in truths),
                max(len(item.incidents) for item in truths),
            ],
            "realized_taxonomy_counts": dict(sorted(realized_taxonomy.items())),
            "realized_hourly_means": mean_latent_by_hour,
        },
        "observations": {
            "coefficients_version": "delta-observation-coefficients-v2",
            "fixed_reporting_probability_by_incident_onset_hour": list(reporting_by_hour),
            "fixed_false_report_hour_weights": list(false_report_hour_weights),
            "analytical_report_multiplier": report_multiplier,
            "analytical_false_reports_by_hour": [
                probabilities["false_report_mean"] * weight for weight in false_report_hour_weights
            ],
            "realized_development_call_mean": statistics.fmean(observed_totals),
            "realized_development_call_range": [min(observed_totals), max(observed_totals)],
            "realized_hourly_call_means": [
                statistics.fmean(row[hour] for row in observed_by_hour) for hour in range(6)
            ],
            "realized_relationship_fractions": {
                name: relationship_counts[name] / call_denominator
                for name in (
                    "duplicate",
                    "multi_channel",
                    "revision",
                    "conflicting_report",
                    "false_report",
                )
            },
            "realized_callback_failure_fraction": callback_failures / call_denominator,
            "realized_dropped_call_fraction": dropped_calls / call_denominator,
            "realized_location_method_fractions": {
                name: method_counts[name] / call_denominator
                for name in (
                    "gps-or-address-intersection",
                    "landmark",
                    "cell-sector",
                )
            },
        },
        "book_seed_role": "descriptive-not-fitted",
        "claim_limits": [
            "synthetic-reduced-order-process-design",
            "development-seed-calibration-only",
            "not-field-historical-demographic-or-operational-calibration",
            "no-per-seed-normalization",
        ],
    }
    payload = canonical_json_bytes(record)
    if arguments.output is None:
        print(payload.decode("utf-8"), end="")
    else:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        if arguments.output.exists() or arguments.output.is_symlink():
            raise FileExistsError(f"calibration output already exists: {arguments.output}")
        arguments.output.write_bytes(payload)


if __name__ == "__main__":
    main()
