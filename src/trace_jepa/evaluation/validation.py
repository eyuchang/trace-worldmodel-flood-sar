from __future__ import annotations

import json
import math
import statistics
import concurrent.futures
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import Field, model_validator

from trace_jepa.evaluation.runner import (
    RunRequest,
    _atomic_write_json,
    _atomic_write_text,
    run_one_sync,
    scientific_source_tree_hash,
    validate_run_directory,
)
from trace_jepa.util import sha256_file, sha256_value
from trace_jepa.workbench.models import FrozenModel


VALIDATION_SCHEMA_VERSION = "trace-validation-sweep-v1"
VALIDATION_RESULT_SCHEMA_VERSION = "trace-validation-sweep-result-v1"
G3_MANIFEST_SCHEMA_VERSION = "trace-g3-manifest-v1"
VALIDATION_SEEDS = tuple(range(101, 126))
TEST_SEED_START = 1001


class ValidationSweepConfig(FrozenModel):
    schema_version: Literal["trace-validation-sweep-v1"] = VALIDATION_SCHEMA_VERSION
    partition: Literal["validation"] = "validation"
    regime: Literal["R-B"] = "R-B"
    seed_start: int
    seed_end: int
    forcing_noise_std: float = Field(gt=0.0, le=2.0)
    duration_s: float = Field(gt=0.0, le=86_400.0)
    tick_s: float = Field(gt=0.0, le=1.0)
    requested_speed: float = Field(gt=0.0, le=50.0)
    scenario: Path
    shock_root: Path
    workload: Path
    protocol_amendment_id: str
    gate_policy: Path
    policies: dict[str, tuple[str, ...]]
    expected_configurations: int = Field(gt=0)
    expected_cells: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_frozen_grid(self) -> "ValidationSweepConfig":
        if tuple(range(self.seed_start, self.seed_end + 1)) != VALIDATION_SEEDS:
            raise ValueError("validation seeds must be exactly 101--125")
        expected_families = {"no_refresh", "fixed_k", "validity_clock", "adaptive"}
        if set(self.policies) != expected_families:
            raise ValueError("validation policy families do not match the protocol")
        flattened = self.policy_specs
        if len(flattened) != len(set(flattened)):
            raise ValueError("validation policy specifications must be unique")
        if len(flattened) != self.expected_configurations:
            raise ValueError("expected_configurations disagrees with the policy grid")
        if self.expected_cells != len(VALIDATION_SEEDS) * len(flattened):
            raise ValueError("expected_cells disagrees with seeds and policies")
        if not math.isclose(self.tick_s, 1.0, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("E6 requires a one-second tick")
        if not math.isclose(self.duration_s, 7800.0, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("the amended two-hour workload requires a 7,800 s horizon")
        if not math.isclose(
            self.forcing_noise_std, 0.35, rel_tol=0.0, abs_tol=1e-12
        ):
            raise ValueError("G2 froze forcing_noise_std at 0.35")
        return self

    @property
    def policy_specs(self) -> tuple[str, ...]:
        return tuple(
            policy
            for family in ("no_refresh", "fixed_k", "validity_clock", "adaptive")
            for policy in self.policies[family]
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _confined_path(repository_root: Path, relative: Path, *, directory: bool) -> Path:
    if relative.is_absolute():
        raise ValueError("experiment configuration paths must be repository-relative")
    resolved = (repository_root / relative).resolve(strict=True)
    try:
        resolved.relative_to(repository_root.resolve(strict=True))
    except ValueError as exc:
        raise ValueError("experiment configuration path escapes the repository") from exc
    if directory and not resolved.is_dir():
        raise ValueError("experiment configuration path is not a directory")
    if not directory and not resolved.is_file():
        raise ValueError("experiment configuration path is not a file")
    return resolved


def load_validation_config(
    path: str | Path, *, repository_root: str | Path
) -> tuple[ValidationSweepConfig, Path]:
    root = Path(repository_root).resolve(strict=True)
    config_root = root / "configs" / "experiments"
    candidate = Path(path)
    resolved = (
        candidate.resolve(strict=True)
        if candidate.is_absolute()
        else (config_root / candidate).resolve(strict=True)
    )
    try:
        resolved.relative_to(config_root.resolve(strict=True))
    except ValueError as exc:
        raise ValueError("validation config escapes configs/experiments") from exc
    if not resolved.is_file() or resolved.stat().st_size > 1_000_000:
        raise ValueError("validation config must be a regular file under 1 MB")
    payload = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("validation config must contain a YAML mapping")
    return ValidationSweepConfig.model_validate(payload), resolved


def _relative_attempt(result: dict[str, Any], output_root: Path) -> dict[str, Any]:
    compact = {key: value for key, value in result.items() if key != "directory"}
    if "directory" in result:
        compact["run_directory"] = Path(result["directory"]).resolve().relative_to(
            output_root.resolve()
        ).as_posix()
    return compact


def _execute_cell(request: RunRequest) -> dict[str, Any]:
    try:
        directory = run_one_sync(request)
        valid, errors = validate_run_directory(directory)
        return {
            "seed": request.seed,
            "policy": request.policy,
            "status": "complete" if valid else "invalid",
            "directory": str(directory),
            "validation_errors": list(errors),
        }
    except BaseException as exc:
        return {
            "seed": request.seed,
            "policy": request.policy,
            "status": "failed",
            "exception_type": type(exc).__name__,
            "exception_message": str(exc)[:2000],
        }


def _run_cells(requests: list[RunRequest], workers: int) -> list[dict[str, Any]]:
    if workers == 1:
        return [_execute_cell(request) for request in requests]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(_execute_cell, requests))
    return sorted(results, key=lambda item: (item["policy"], item["seed"]))


def run_validation_sweep(
    *,
    config_path: str | Path,
    output_root: str | Path,
    repository_root: str | Path,
    protocol_path: str | Path,
    workers: int,
    resume: bool = True,
) -> dict[str, Any]:
    """Execute exactly the registered 19 x 25 validation grid."""

    if not 1 <= workers <= 32:
        raise ValueError("workers must lie in [1, 32]")
    root = Path(repository_root).resolve(strict=True)
    output = Path(output_root).resolve()
    output.mkdir(parents=True, exist_ok=True)
    config, resolved_config = load_validation_config(
        config_path, repository_root=root
    )
    scenario = _confined_path(root, config.scenario, directory=False)
    shock_root = _confined_path(root, config.shock_root, directory=True)
    workload = _confined_path(root, config.workload, directory=False)
    gate_policy = _confined_path(root, config.gate_policy, directory=False)
    protocol = Path(protocol_path).resolve(strict=True)

    requests = [
        RunRequest(
            regime=config.regime,
            partition="validation",
            policy=policy,
            seed=seed,
            scenario_path=scenario,
            shock_registry_root=shock_root,
            protocol_path=protocol,
            output_root=output / "runs",
            gate_policy_path=gate_policy,
            evaluation_workload_path=workload,
            protocol_amendment_id=config.protocol_amendment_id,
            forcing_noise_std=config.forcing_noise_std,
            duration_s=config.duration_s,
            tick_s=config.tick_s,
            requested_speed=config.requested_speed,
            resume=resume,
        )
        for policy in config.policy_specs
        for seed in VALIDATION_SEEDS
    ]
    attempts = _run_cells(requests, workers)

    rows: list[dict[str, Any]] = []
    source_hashes: set[str] = set()
    environment_hashes: set[str] = set()
    exogenous_by_seed: dict[int, set[str]] = {seed: set() for seed in VALIDATION_SEEDS}
    partitions: set[str] = set()
    gate_hashes: set[str] = set()
    for attempt in attempts:
        if attempt["status"] != "complete":
            continue
        directory = Path(attempt["directory"])
        metrics = json.loads((directory / "metrics.json").read_text(encoding="utf-8"))
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        identity = manifest["scientific_identity"]
        commitment = metrics["commitment"]
        refresh = metrics["refresh"]
        verification = metrics["verification_cost"]
        rows.append(
            {
                "seed": metrics["seed"],
                "policy": metrics["policy"],
                "run_fingerprint": manifest["run_fingerprint"],
                "proposal_records": commitment["proposal_records"],
                "proposed": commitment["proposed"],
                "executed": commitment["executed"],
                "held": commitment["held"],
                "escalated": commitment["escalated"],
                "executed_stale": commitment["executed_stale"],
                "coverage": commitment["coverage"],
                "stale_execution_rate": commitment["stale_execution_rate"],
                "verification_cost": verification["total_cost"],
                "discretionary_verification_cost": verification[
                    "discretionary_cost"
                ],
                "common_baseline_cost": verification["common_baseline_cost"],
                "refresh_acquisitions": refresh["evidence_acquisitions"],
                "mission": metrics["mission"],
                "run_directory": directory.resolve().relative_to(output).as_posix(),
            }
        )
        source_hashes.add(identity["code"]["source_tree_hash"])
        environment_hashes.add(identity["environment_hash"])
        partitions.add(identity["partition"])
        gate_hashes.add(identity["effective_gate_policy"]["sha256"])
        exogenous_by_seed[int(metrics["seed"])].add(
            sha256_file(directory / "exogenous.jsonl")
        )

    expected_pairs = {
        (seed, policy) for seed in VALIDATION_SEEDS for policy in config.policy_specs
    }
    observed_pairs = {(int(row["seed"]), str(row["policy"])) for row in rows}
    checks = {
        "exactly_475_complete_valid_cells": (
            len(attempts) == config.expected_cells
            and all(attempt["status"] == "complete" for attempt in attempts)
            and len(rows) == config.expected_cells
            and observed_pairs == expected_pairs
        ),
        "validation_seed_partition_exact": {row["seed"] for row in rows}
        == set(VALIDATION_SEEDS),
        "no_test_seed_access": all(int(row["seed"]) < TEST_SEED_START for row in rows),
        "single_source_tree_hash": len(source_hashes) == 1,
        "single_environment_hash": len(environment_hashes) == 1,
        "partition_labels_are_validation": partitions == {"validation"},
        "single_provisional_e11_gate": (
            gate_hashes == {sha256_file(gate_policy)}
        ),
        "common_random_numbers_match_all_policies": all(
            len(hashes) == 1 for hashes in exogenous_by_seed.values()
        ),
    }
    status = "passed" if all(checks.values()) else "failed"
    summary = {
        "schema_version": VALIDATION_RESULT_SCHEMA_VERSION,
        "created_at_utc": _utc_now(),
        "status": status,
        "inferential_use": False,
        "partition": "validation",
        "regime": config.regime,
        "config": {
            "path": resolved_config.relative_to(root).as_posix(),
            "sha256": sha256_file(resolved_config),
            "resolved": config.model_dump(mode="json"),
        },
        "protocol": {
            "path": protocol.relative_to(root.parent).as_posix(),
            "sha256": sha256_file(protocol),
        },
        "executor": {"backend": "thread_pool", "workers": workers},
        "attempts": [_relative_attempt(attempt, output) for attempt in attempts],
        "cells": sorted(rows, key=lambda row: (row["policy"], row["seed"])),
        "checks": checks,
        "scientific_identity": {
            "source_tree_hash": next(iter(source_hashes)) if len(source_hashes) == 1 else None,
            "environment_hash": (
                next(iter(environment_hashes)) if len(environment_hashes) == 1 else None
            ),
            "gate_policy_sha256": (
                next(iter(gate_hashes)) if len(gate_hashes) == 1 else None
            ),
            "workload_sha256": sha256_file(workload),
            "crn_projection_sha256_by_seed": {
                str(seed): next(iter(hashes)) if len(hashes) == 1 else sorted(hashes)
                for seed, hashes in exogenous_by_seed.items()
            },
        },
    }
    summary["result_hash"] = sha256_value(summary)
    _atomic_write_json(output / "VALIDATION_SWEEP_RESULT.json", summary)
    return summary


def _quantile_type7(values: list[float], probability: float) -> float:
    if not values:
        raise ValueError("cannot compute a quantile of an empty sample")
    ordered = sorted(values)
    index = (len(ordered) - 1) * probability
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (index - lower) * (ordered[upper] - ordered[lower])


def _family(policy: str) -> str:
    if policy == "none":
        return "no_refresh"
    if policy.startswith("fixed-k:"):
        return "fixed_k"
    if policy.startswith("clock:"):
        return "validity_clock"
    if policy.startswith("adaptive:"):
        return "adaptive"
    raise ValueError(f"unknown policy specification: {policy}")


def summarize_configurations(cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in cells:
        grouped.setdefault(str(row["policy"]), []).append(row)
    summaries: list[dict[str, Any]] = []
    for policy, rows in sorted(grouped.items()):
        if {int(row["seed"]) for row in rows} != set(VALIDATION_SEEDS):
            raise ValueError(f"policy {policy} does not contain all validation seeds")
        executed = sum(int(row["executed"]) for row in rows)
        stale = sum(int(row["executed_stale"]) for row in rows)
        proposed = sum(int(row["proposed"]) for row in rows)
        summaries.append(
            {
                "policy": policy,
                "family": _family(policy),
                "mean_verification_cost": statistics.fmean(
                    float(row["verification_cost"]) for row in rows
                ),
                "pooled_executed": executed,
                "pooled_executed_stale": stale,
                "pooled_stale_execution_rate": stale / executed if executed else None,
                "pooled_proposed": proposed,
                "pooled_coverage": executed / proposed if proposed else 0.0,
                "mission_seed_count": len(rows),
            }
        )
    return summaries


def select_operating_points(
    summaries: list[dict[str, Any]], budgets: dict[str, float]
) -> dict[str, dict[str, dict[str, Any] | None]]:
    families = ("no_refresh", "fixed_k", "validity_clock", "adaptive")
    result: dict[str, dict[str, dict[str, Any] | None]] = {}
    for budget_name, budget in budgets.items():
        result[budget_name] = {}
        for family in families:
            feasible = [
                row
                for row in summaries
                if row["family"] == family
                and row["mean_verification_cost"] <= budget + 1e-12
                and row["pooled_stale_execution_rate"] is not None
            ]
            if not feasible:
                result[budget_name][family] = None
                continue
            selected = min(
                feasible,
                key=lambda row: (
                    row["pooled_stale_execution_rate"],
                    row["mean_verification_cost"],
                    row["policy"],
                ),
            )
            result[budget_name][family] = {
                **selected,
                "budget": budget,
                "selection_rule": (
                    "minimum pooled stale-execution rate subject to mean cost <= budget; "
                    "ties: lower mean cost, then lexical policy spec"
                ),
            }
    return result


def _pilot_sample_size(g2_setting_path: Path) -> dict[str, Any]:
    payload = json.loads(g2_setting_path.read_text(encoding="utf-8"))
    rates = [
        float(row["stale_execution_rate"])
        for row in payload["per_seed"]
        if row["stale_execution_rate"] is not None
    ]
    if len(rates) < 2:
        raise ValueError("development pilot has insufficient nonempty seed rates")
    s_pilot = statistics.stdev(rates)
    unbounded = math.ceil((1.96 * s_pilot / 0.025) ** 2)
    return {
        "estimator": (
            "sample SD of per-seed stale-execution fractions among development "
            "seeds with at least one execution"
        ),
        "development_seeds_total": len(payload["per_seed"]),
        "development_seeds_with_execution": len(rates),
        "s_pilot": s_pilot,
        "target_half_width": 0.025,
        "normal_multiplier": 1.96,
        "unbounded_n": unbounded,
        "cap": 120,
        "n_test": min(unbounded, 120),
        "stopping_rule": "run exactly n_test paired seeds; no additions after inspection",
        "review_note": (
            "The cap binds. Confirm the estimator wording at G3 because the protocol "
            "does not define how zero-execution pilot seeds enter s_pilot."
        ),
    }


def prepare_g3_manifest(
    *,
    validation_result_path: str | Path,
    g2_setting_path: str | Path,
    repository_root: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    """Prepare an unsigned review manifest; never commit, tag, or authorize test runs."""

    root = Path(repository_root).resolve(strict=True)
    validation_path = Path(validation_result_path).resolve(strict=True)
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    if validation.get("status") != "passed" or not all(
        validation.get("checks", {}).values()
    ):
        raise ValueError("G3 manifest requires a fully passed validation sweep")
    cells = validation["cells"]
    costs = [float(row["verification_cost"]) for row in cells]
    budgets = {
        "B1": _quantile_type7(costs, 0.25),
        "B2": _quantile_type7(costs, 0.50),
        "B3": _quantile_type7(costs, 0.75),
        "B4": _quantile_type7(costs, 1.00),
    }
    summaries = summarize_configurations(cells)
    operating_points = select_operating_points(summaries, budgets)
    unique_frozen = sorted(
        {
            selected["policy"]
            for by_family in operating_points.values()
            for selected in by_family.values()
            if selected is not None
        }
    )
    g2_path = Path(g2_setting_path).resolve(strict=True)
    source_hash = scientific_source_tree_hash(root)
    validation_source_hash = validation["scientific_identity"]["source_tree_hash"]
    if source_hash != validation_source_hash:
        raise ValueError("source tree changed after validation; rerun before G3 review")

    manifest: dict[str, Any] = {
        "schema_version": G3_MANIFEST_SCHEMA_VERSION,
        "status": "review_draft_unsigned",
        "g3": {
            "professor_signoff": None,
            "signed_at_utc": None,
            "freeze_commit": None,
            "freeze_tag": "exp-freeze-v1",
            "test_execution_authorized": False,
            "instruction": (
                "After professor signoff, commit this exact manifest and source tree, "
                "create exp-freeze-v1, and only then enable the separately reviewed test runner."
            ),
        },
        "protocol": {
            "canonical_sha256": validation["protocol"]["sha256"],
            "measurement_amendment": "day1-measurement-amendment-2",
            "e_values_status": "provisional_pending_professor_g3_signoff",
        },
        "e_decisions": {
            "E1_loss_table": {
                "swamped_boat": 100.0,
                "reroute": 15.0,
                "missed_rescue": 200.0,
                "false_hold_per_hour": 10.0,
                "escalation": 3.0,
            },
            "E2_epsilon_c_grid": [0.25, 0.5, 1.0, 2.0, 4.0, 7.0],
            "E3_channels": {
                "gauge_poll": {"cost": 0.2, "latency_s": 5.0},
                "drone_survey": {
                    "cost": "5.0 + flight_duration_s * 0.0009",
                    "latency_s": "flight_duration_s",
                },
            },
            "E4_gamma_c": {"irreversible": 0.8, "probe": 0.5},
            "E5_budget_rule": "type-7 quartiles of all 475 validation-cell total costs",
            "E6_tick_s": 1.0,
            "E7_regimes": {
                "primary": "R-B drift plus diffusion",
                "stress": "R-C separately, with S4 registry shocks",
            },
            "E8_mission_horizon_s": 7800.0,
            "E9_test_power": _pilot_sample_size(g2_path),
            "E10_forcing_noise_std": 0.35,
            "E11_gate_policy": {
                "path": "configs/policies/trace_exp_v1.yaml",
                "sha256": sha256_file(root / "configs/policies/trace_exp_v1.yaml"),
                "status": "provisional",
            },
            "E12_channel_menu": ["gauge_poll", "drone_survey"],
        },
        "grids": validation["config"]["resolved"]["policies"],
        "partitions": {
            "development": {
                "original": [1, 20],
                "amendment_qa": [21, 40],
                "amended_g2": [41, 60],
            },
            "validation": [101, 125],
            "test": {
                "seed_start": TEST_SEED_START,
                "n_test": _pilot_sample_size(g2_path)["n_test"],
                "executed": False,
            },
        },
        "validation": {
            "result_path": validation_path.relative_to(root.parent).as_posix(),
            "result_sha256": sha256_file(validation_path),
            "result_hash": validation["result_hash"],
            "cell_count": len(cells),
            "budgets": budgets,
            "quantile_method": "Hyndman-Fan type 7 (linear interpolation)",
            "configuration_summaries": summaries,
            "operating_points": operating_points,
            "unique_frozen_configurations": unique_frozen,
        },
        "observables": {
            "stale_execution": {
                "definition": "claim truth is false at ACTION_STARTED",
                "implementation": "trace_jepa.evaluation.adjudication.adjudicate_execution_truth",
            },
            "coverage": {
                "definition": "executed stable commitment units / proposed stable commitment units",
                "raw_revision_count_retained_as": "proposal_records",
                "implementation": "trace_jepa.evaluation.metrics.compute_commitment_unit_metrics",
            },
            "verification_cost": {
                "definition": "common baseline cost plus discretionary refresh cost",
                "implementation": "trace_jepa.evaluation.runner._verification_cost_metrics",
            },
        },
        "statistics": {
            "resampling_unit": "mission seed",
            "paired_bootstrap_resamples": 10_000,
            "simultaneous_band": "max-t across B1--B4",
            "dominance": (
                "no worse at every predeclared budget and strictly better at one or more"
            ),
            "operating_point_ties": "lower cost, then lexical policy specification",
            "undefined_staleness": "zero-execution configurations are ineligible, not set to zero",
        },
        "ablation_list": [
            "adaptive_full",
            "adaptive_minus_predicted",
            "adaptive_minus_observed",
            "adaptive_minus_structural",
            "adaptive_minus_normative",
            "routing_cheapest_regardless_of_adequacy",
            "routing_cheapest_adequate",
        ],
        "rq3": {
            "primary": "raw loss and resource components",
            "secondary": "weighted composite with sensitivity analysis",
            "provisional_weights": {
                "stale_execution": 100.0,
                "reroute": 15.0,
                "missed_rescue": 200.0,
                "false_hold_per_hour": 10.0,
                "escalation": 3.0,
            },
        },
        "integrity": {
            "git_commit_before_freeze": None,
            "git_tree_dirty_for_review": True,
            "scientific_source_tree_hash": source_hash,
            "validation_environment_hash": validation["scientific_identity"][
                "environment_hash"
            ],
            "validation_gate_policy_sha256": validation["scientific_identity"][
                "gate_policy_sha256"
            ],
            "validation_workload_sha256": validation["scientific_identity"][
                "workload_sha256"
            ],
        },
        "review_required": [
            "Confirm E1--E12 provisional values and trace_exp_v1.yaml.",
            "Confirm budget/type-7 quantile and deterministic operating-point tie rules.",
            "Confirm s_pilot estimator wording; the 120-seed cap binds.",
            "Confirm the seven-entry ablation inventory.",
            "Sign before any test seed is enabled or executed.",
        ],
    }
    manifest["manifest_hash"] = sha256_value(manifest)
    destination = Path(output_path)
    rendered = yaml.safe_dump(manifest, sort_keys=False, allow_unicode=False)
    _atomic_write_text(destination, rendered)
    return manifest
