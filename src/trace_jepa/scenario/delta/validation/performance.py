"""Canonical book run and exact-replay timing for registered validation."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from trace_jepa.predictor import ToyActionPrefixPredictor
from trace_jepa.scenario.delta.domain import GeneratedScenario
from trace_jepa.scenario.delta.domain.loading import load_geography_catalog, load_scenario_config
from trace_jepa.scenario.delta.generator import generate_delta_small_from_models
from trace_jepa.scenario.delta.pipeline import execute_delta_small, verify_exact_replay
from trace_jepa.scenario.delta.runtime import DeltaRunResult, run_delta_small


def book_and_performance(
    config_path: Path,
    geography_path: Path,
    policy_path: Path,
) -> tuple[GeneratedScenario, DeltaRunResult, float]:
    config = load_scenario_config(config_path)
    geography = load_geography_catalog(geography_path)
    scenario = generate_delta_small_from_models(config, geography, config_path.resolve(strict=True))
    result = run_delta_small(scenario, ToyActionPrefixPredictor(), policy_path)
    with tempfile.TemporaryDirectory(prefix="delta-v8-performance-") as temporary:
        root = Path(temporary)
        started = time.perf_counter()
        execute_delta_small(
            config_path,
            geography_path,
            policy_path,
            root / "reference",
            ToyActionPrefixPredictor(),
        )
        verify_exact_replay(
            config_path,
            geography_path,
            policy_path,
            root / "reference",
            root / "replay",
            ToyActionPrefixPredictor(),
        )
        elapsed = time.perf_counter() - started
    return scenario, result, elapsed
