from __future__ import annotations

import hashlib
from pathlib import Path

from trace_jepa.scenario.delta.artifacts import canonical_json_bytes, sha256_bytes
from trace_jepa.scenario.delta.coordination import generate_coordination
from trace_jepa.scenario.delta.domain import DeltaScenarioConfig, GeneratedScenario
from trace_jepa.scenario.delta.generation import generate_prior_profile, generate_resources
from trace_jepa.scenario.delta.generation.observation_channel import (
    generate_observations_v8,
)
from trace_jepa.scenario.delta.geography_models import GeographyCatalog
from trace_jepa.scenario.delta.loading import load_geography_catalog, load_scenario_config
from trace_jepa.scenario.delta.observations_v7 import generate_observations_v7
from trace_jepa.scenario.delta.physical import (
    generate_crossing_states,
    generate_gauges,
    generate_geography,
    generate_weather,
)
from trace_jepa.scenario.delta.population import (
    generate_observations,
    generate_truth,
)
from trace_jepa.scenario.delta.randomness import KeyedRandom, derive_stage_seed, seeded_random
from trace_jepa.scenario.delta.truth_v7 import generate_truth_v7
from trace_jepa.scenario.delta.truth_v8 import generate_truth_v8

GENERATION_ORDER = [
    "geography",
    "meteorology",
    "hydrology",
    "road_crossing_state",
    "ground_truth",
    "observations",
    "resources",
    "predictor_prior",
]
GENERATION_ORDER_V7 = [
    "geography",
    "meteorology",
    "hydrology",
    "road_crossing_state",
    "ground_truth",
    "observations",
    "coordination",
    "resources",
    "predictor_prior",
]


def _projection_hash(value: object) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def generate_delta_small(config_path: Path, geography_path: Path) -> GeneratedScenario:
    config = load_scenario_config(config_path)
    catalog = load_geography_catalog(geography_path)
    return generate_delta_small_from_models(config, catalog, config_path.resolve(strict=True))


def generate_delta_small_from_models(
    config: DeltaScenarioConfig,
    catalog: GeographyCatalog,
    source_path: Path,
) -> GeneratedScenario:
    """Generate from validated frozen models, enabling registered ensemble execution."""
    geography = generate_geography(config, catalog)
    weather = generate_weather(config)
    gauges = generate_gauges(config, geography, weather)
    crossing_states = generate_crossing_states(config, geography, weather, gauges)
    # v6 is a resource/metric protocol amendment. It deliberately reuses the
    # v5 random namespace so the physical state, cohort, truth, and calls are
    # counterfactually identical for every fixed seed.
    randomness_namespace = config.randomness_namespace_version or config.generator_version
    seed_namespace_hash = _projection_hash(
        {
            "scenario_id": config.scenario_id,
            "generator_version": randomness_namespace,
            "extent": config.extent.model_dump(mode="json"),
        }
    )
    if config.generator_version in {"delta-small-generator-v7", "delta-small-generator-v8"}:
        truth_generator = (
            generate_truth_v8
            if config.generator_version == "delta-small-generator-v8"
            else generate_truth_v7
        )
        truth = truth_generator(
            config,
            geography,
            weather,
            crossing_states,
            KeyedRandom(config.seed, seed_namespace_hash, "ground_truth"),
        )
        observation_generator = (
            generate_observations_v8
            if config.generator_version == "delta-small-generator-v8"
            else generate_observations_v7
        )
        observations = observation_generator(
            config,
            truth,
            KeyedRandom(config.seed, seed_namespace_hash, "observations"),
        )
        coordination = generate_coordination(
            config,
            observations,
            KeyedRandom(config.seed, seed_namespace_hash, "coordination"),
        )
        generation_order = GENERATION_ORDER_V7
    else:
        truth = generate_truth(
            config,
            geography,
            weather,
            crossing_states,
            seeded_random(config.seed, seed_namespace_hash, "ground_truth"),
        )
        observations = generate_observations(
            config,
            truth,
            weather,
            crossing_states,
            seeded_random(config.seed, seed_namespace_hash, "observations"),
        )
        coordination = None
        generation_order = GENERATION_ORDER
    resources = generate_resources(config)
    prior_profile = generate_prior_profile(config)
    return GeneratedScenario(
        config=config,
        geography=geography,
        weather=weather,
        gauges=gauges,
        crossing_states=crossing_states,
        truth=truth,
        observations=observations,
        coordination=coordination,
        resources=resources,
        prior_profile=prior_profile,
        stage_seeds=[
            hashlib.sha256(
                str(derive_stage_seed(config.seed, seed_namespace_hash, name)).encode("utf-8")
            ).hexdigest()
            for name in generation_order
        ],
        generation_order=generation_order,
        source_path=source_path,
    )
