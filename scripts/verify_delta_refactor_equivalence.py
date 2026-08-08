"""Compare canonical v8 behavior with the immutable b8dd299 refactor baseline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import BaseModel

from trace_jepa.predictor import ToyActionPrefixPredictor
from trace_jepa.scenario.delta.domain import DeltaScenarioConfig
from trace_jepa.scenario.delta.domain.loading import load_geography_catalog, load_scenario_config
from trace_jepa.scenario.delta.generator import generate_delta_small_from_models
from trace_jepa.scenario.delta.runtime import run_delta_small
from trace_jepa.support import atomic_write_bytes, canonical_json_bytes, sha256_bytes
from trace_jepa.support.files import safe_regular_file

AXIS_VARIANTS: dict[str, tuple[str, object]] = {
    "sigma": ("sigma", 0.6),
    "kappa": ("kappa", 1.0),
    "mu": ("mu", 1.5),
    "iota": ("iota", 0.6),
    "phi": ("phi", 3),
    "pi": ("pi", 0.6),
    "epsilon": ("exposure_profile", "isleton_high_vulnerability_v1"),
    "delta": ("delta", 0.4),
}


def _json_value(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _hash(value: object) -> str:
    return sha256_bytes(canonical_json_bytes(_json_value(value)))


def _projection(
    config: DeltaScenarioConfig, geography_path: Path, policy_path: Path
) -> dict[str, str]:
    geography = load_geography_catalog(geography_path)
    scenario = generate_delta_small_from_models(config, geography, Path("<equivalence-fixture>"))
    result = run_delta_small(scenario, ToyActionPrefixPredictor(), policy_path)
    return {
        "geography": _hash(scenario.geography),
        "weather": _hash(scenario.weather),
        "gauges": _hash(scenario.gauges),
        "crossings": _hash(scenario.crossing_states),
        "truth": _hash(scenario.truth),
        "observations": _hash(scenario.observations),
        "coordination": _hash(scenario.coordination),
        "resources": _hash(scenario.resources),
        "prior": _hash(scenario.prior_profile),
        "predictor_requests": _hash(result.predictor_requests),
        "evidence": _hash(result.evidence),
        "decisions": _hash(result.decisions),
        "trace_records": _hash(result.trace_records),
        "commitments": _hash(result.commitments),
        "outcomes": _hash(result.outcomes),
        "reconciliation": _hash(result.reconciliation_artifact),
        "evaluation": _hash(result.reconciliation_evaluation),
    }


def _variant(config: DeltaScenarioConfig, axis_name: str, value: object) -> DeltaScenarioConfig:
    return config.model_copy(update={"axes": config.axes.model_copy(update={axis_name: value})})


def build_current_projection(
    config_path: Path,
    geography_path: Path,
    policy_path: Path,
) -> dict[str, object]:
    config = load_scenario_config(config_path)
    development = {
        str(seed): _projection(
            config.model_copy(update={"seed": seed}), geography_path, policy_path
        )
        for seed in range(20260803, 20260903)
    }
    axis_variants = {"book": development[str(config.seed)]}
    for label, (axis_name, value) in AXIS_VARIANTS.items():
        axis_variants[label] = _projection(
            _variant(config, axis_name, value), geography_path, policy_path
        )
    return {
        "source_commit": "current-worktree",
        "development": development,
        "axis_variants": axis_variants,
    }


def compare_projection(expected: dict[str, object], actual: dict[str, object]) -> dict[str, object]:
    mismatches: list[dict[str, str]] = []
    for group in ("development", "axis_variants"):
        expected_group = expected[group]
        actual_group = actual[group]
        for case_id, expected_projection in expected_group.items():
            for artifact, expected_hash in expected_projection.items():
                actual_hash = actual_group[case_id][artifact]
                if actual_hash != expected_hash:
                    mismatches.append(
                        {
                            "group": group,
                            "case_id": case_id,
                            "artifact": artifact,
                            "expected_sha256": expected_hash,
                            "actual_sha256": actual_hash,
                        }
                    )
    return {
        "schema_version": "delta-refactor-equivalence-v1",
        "baseline_commit": expected["source_commit"],
        "development_seed_count": len(expected["development"]),
        "axis_variant_count": len(expected["axis_variants"]),
        "artifact_projection_count": sum(
            len(projection) for projection in actual["development"].values()
        )
        + sum(len(projection) for projection in actual["axis_variants"].values()),
        "byte_equivalent": not mismatches,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--geography", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    baseline = safe_regular_file(
        args.baseline,
        declared_root=args.baseline.parent,
        maximum_bytes=1_000_000,
        label="refactor baseline",
    )
    expected = json.loads(baseline.read_text("utf-8"))
    actual = build_current_projection(args.config, args.geography, args.policy)
    report = compare_projection(expected, actual)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(
        args.output,
        canonical_json_bytes(report),
        root=args.output.parent,
        label="refactor equivalence report",
    )
    if not report["byte_equivalent"]:
        raise SystemExit("Delta refactor changed one or more registered projections")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
