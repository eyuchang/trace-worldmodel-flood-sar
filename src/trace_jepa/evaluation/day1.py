from __future__ import annotations

import concurrent.futures
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trace_jepa.evaluation.runner import (
    RunRequest,
    run_one_sync,
    validate_run_directory,
)
from trace_jepa.util import sha256_file, sha256_value


ORIGINAL_G2_SEEDS = tuple(range(1, 21))
AMENDED_G2_SEEDS = tuple(range(41, 61))
ORIGINAL_SMOKE_SEEDS = (1, 2, 3)
AMENDED_SMOKE_SEEDS = (41, 42, 43)
SMOKE_POLICIES = ("fixed-k:45", "clock:0.55", "adaptive:1")
G2_TARGET = (0.10, 0.40)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _noise_slug(value: float) -> str:
    return format(value, ".12g").replace("-", "m").replace(".", "p")


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


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
    # Threads avoid macOS/Python semaphore limits observed on the reference
    # machine. Every simulation, cache, RNG namespace, and output path remains
    # run-local; no mutable simulator state is shared between cells.
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(_execute_cell, requests))
    return sorted(results, key=lambda item: (item["policy"], item["seed"]))


def _read_cell(directory: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    metrics = json.loads((directory / "metrics.json").read_text(encoding="utf-8"))
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    return metrics, manifest


def _cell_provenance(identity: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_tree_hash": identity["code"]["source_tree_hash"],
        "environment_hash": identity["environment_hash"],
        "scenario": identity["scenario"],
        "protocol": identity["protocol"],
        "effective_gate_policy": identity["effective_gate_policy"],
        "rng": identity["rng"],
        "evaluation_workload": identity["evaluation_workload"],
        "protocol_amendment_id": identity["request"][
            "protocol_amendment_id"
        ],
        "duration_s": identity["request"]["duration_s"],
        "tick_s": identity["request"]["tick_s"],
    }


def _cell_phase_provenance(identity: dict[str, Any]) -> dict[str, Any]:
    return {
        **_cell_provenance(identity),
        "partition": identity["partition"],
        "regime": identity["request"]["regime"],
        "forcing_noise_std": identity["request"]["forcing_noise_std"],
        "requested_speed": identity["request"]["requested_speed"],
    }


def run_g2_setting(
    *,
    noise: float,
    output_root: Path,
    repository_root: Path,
    protocol_path: Path,
    duration_s: float,
    workers: int,
    resume: bool,
    evaluation_workload_path: Path | None = None,
    protocol_amendment_id: str | None = None,
) -> dict[str, Any]:
    setting_root = output_root / f"noise-{_noise_slug(noise)}"
    run_root = setting_root / "runs"
    expected_seeds = (
        AMENDED_G2_SEEDS
        if evaluation_workload_path is not None
        else ORIGINAL_G2_SEEDS
    )
    requests = [
        RunRequest(
            regime="R-B",
            policy="none",
            seed=seed,
            scenario_path=(
                repository_root
                / "configs/scenarios/riverside_flood_dynamic_v2.yaml"
            ),
            shock_registry_root=repository_root / "configs/shocks",
            protocol_path=protocol_path,
            output_root=run_root,
            evaluation_workload_path=evaluation_workload_path,
            protocol_amendment_id=protocol_amendment_id,
            forcing_noise_std=noise,
            duration_s=duration_s,
            tick_s=1.0,
            requested_speed=50.0,
            resume=resume,
        )
        for seed in expected_seeds
    ]
    attempts = _run_cells(requests, workers)
    per_seed: list[dict[str, Any]] = []
    fingerprints: list[str] = []
    source_hashes: set[str] = set()
    provenance_by_hash: dict[str, dict[str, Any]] = {}
    phase_provenance_by_hash: dict[str, dict[str, Any]] = {}
    for result in attempts:
        if result["status"] != "complete":
            continue
        directory = Path(result["directory"])
        metrics, manifest = _read_cell(directory)
        commitment = metrics["commitment"]
        per_seed.append(
            {
                "seed": metrics["seed"],
                "proposal_records": commitment["proposal_records"],
                "proposed": commitment["proposed"],
                "executed": commitment["executed"],
                "held": commitment["held"],
                "escalated": commitment["escalated"],
                "executed_stale": commitment["executed_stale"],
                "coverage": commitment["coverage"],
                "stale_execution_rate": commitment["stale_execution_rate"],
                "run_fingerprint": manifest["run_fingerprint"],
            }
        )
        fingerprints.append(manifest["run_fingerprint"])
        identity = manifest["scientific_identity"]
        source_hashes.add(identity["code"]["source_tree_hash"])
        provenance = _cell_provenance(identity)
        provenance_by_hash[sha256_value(provenance)] = provenance
        phase_provenance = _cell_phase_provenance(identity)
        phase_provenance_by_hash[sha256_value(phase_provenance)] = (
            phase_provenance
        )

    valid_seeds = {row["seed"] for row in per_seed}
    all_complete = (
        len(attempts) == len(expected_seeds)
        and all(result["status"] == "complete" for result in attempts)
        and valid_seeds == set(expected_seeds)
    )
    all_have_proposals = all(row["proposed"] > 0 for row in per_seed)
    executed = sum(row["executed"] for row in per_seed)
    executed_stale = sum(row["executed_stale"] for row in per_seed)
    proposal_records = sum(row["proposal_records"] for row in per_seed)
    proposed = sum(row["proposed"] for row in per_seed)
    pooled_rate = executed_stale / executed if executed else None
    pooled_coverage = executed / proposed if proposed else 0.0
    eligible_for_gate = (
        all_complete
        and all_have_proposals
        and executed > 0
        and len(source_hashes) == 1
        and len(provenance_by_hash) == 1
        and len(phase_provenance_by_hash) == 1
    )
    in_target = (
        pooled_rate is not None
        and G2_TARGET[0] <= pooled_rate <= G2_TARGET[1]
    )
    passed = eligible_for_gate and in_target and noise > 0.0
    summary = {
        "schema_version": "trace-g2-setting-v3",
        "created_at_utc": _utc_now(),
        "partition": "development",
        "regime": "R-B",
        "policy": "none",
        "noise": noise,
        "duration_s": duration_s,
        "executor": {"backend": "thread_pool", "workers": workers},
        "expected_seeds": list(expected_seeds),
        "protocol_amendment_id": protocol_amendment_id,
        "attempts": attempts,
        "per_seed": sorted(per_seed, key=lambda row: row["seed"]),
        "aggregate": {
            "proposal_records": proposal_records,
            "proposed": proposed,
            "executed": executed,
            "executed_stale": executed_stale,
            "coverage": pooled_coverage,
            "stale_execution_rate": pooled_rate,
        },
        "checks": {
            "exactly_20_complete_valid_cells": all_complete,
            "every_seed_has_proposal": all_have_proposals,
            "nonzero_executed_denominator": executed > 0,
            "single_source_tree_hash": len(source_hashes) == 1,
            "single_scientific_provenance": len(provenance_by_hash) == 1,
            "single_phase_provenance": len(phase_provenance_by_hash) == 1,
            "positive_noise": noise > 0.0,
            "rate_in_target_interval": in_target,
        },
        "gate_passed": passed,
        "scientific_provenance": (
            next(iter(provenance_by_hash.values()))
            if len(provenance_by_hash) == 1
            else None
        ),
        "phase_provenance": (
            next(iter(phase_provenance_by_hash.values()))
            if len(phase_provenance_by_hash) == 1
            else None
        ),
        "cell_fingerprints": sorted(fingerprints),
    }
    summary["summary_hash"] = sha256_value(summary)
    _atomic_json(setting_root / "g2-setting.json", summary)
    return summary


def _next_g2_noise(history: list[dict[str, Any]]) -> float | None:
    latest = history[-1]
    rate = latest["aggregate"]["stale_execution_rate"]
    if rate is None or not latest["checks"]["exactly_20_complete_valid_cells"]:
        return None
    if len(history) == 1:
        if rate < G2_TARGET[0]:
            return 0.70
        if rate > G2_TARGET[1]:
            return 0.00
        return None
    if len(history) >= 3:
        return None

    first, second = history
    first_rate = first["aggregate"]["stale_execution_rate"]
    second_rate = second["aggregate"]["stale_execution_rate"]
    assert first_rate is not None and second_rate is not None
    expected_non_decreasing = second["noise"] > first["noise"]
    observed_non_decreasing = second_rate >= first_rate
    if expected_non_decreasing != observed_non_decreasing and not math.isclose(
        first_rate, second_rate, abs_tol=1e-12
    ):
        return None
    lower_rate, upper_rate = sorted((first_rate, second_rate))
    if lower_rate <= G2_TARGET[1] and upper_rate >= G2_TARGET[0]:
        return 0.5 * (first["noise"] + second["noise"])
    return None


def run_g2(
    *,
    output_root: Path,
    repository_root: Path,
    protocol_path: Path,
    duration_s: float = 7200.0,
    workers: int = 4,
    resume: bool = True,
    evaluation_workload_path: Path | None = None,
    protocol_amendment_id: str | None = None,
    fixed_noise_settings: tuple[float, ...] | None = None,
) -> dict[str, Any]:
    if not 1 <= workers <= 16:
        raise ValueError("workers must lie in [1, 16]")
    if fixed_noise_settings is not None and not fixed_noise_settings:
        raise ValueError("fixed_noise_settings cannot be empty")
    history: list[dict[str, Any]] = []
    noise_queue = list(fixed_noise_settings or (0.35,))
    noise: float | None = noise_queue.pop(0)
    max_settings = len(fixed_noise_settings) if fixed_noise_settings else 3
    while noise is not None and len(history) < max_settings:
        setting = run_g2_setting(
            noise=noise,
            output_root=output_root,
            repository_root=repository_root,
            protocol_path=protocol_path,
            duration_s=duration_s,
            workers=workers,
            resume=resume,
            evaluation_workload_path=evaluation_workload_path,
            protocol_amendment_id=protocol_amendment_id,
        )
        history.append(setting)
        if setting["gate_passed"]:
            break
        if fixed_noise_settings is not None:
            noise = noise_queue.pop(0) if noise_queue else None
        else:
            noise = _next_g2_noise(history)

    provenance_hashes = {
        sha256_value(setting["scientific_provenance"])
        for setting in history
        if setting["scientific_provenance"] is not None
    }
    cross_setting_provenance = (
        len(provenance_hashes) == 1
        and all(setting["scientific_provenance"] is not None for setting in history)
    )
    passed_setting = next(
        (
            setting
            for setting in history
            if setting["gate_passed"] and cross_setting_provenance
        ),
        None,
    )
    result = {
        "schema_version": "trace-g2-development-gate-v3",
        "created_at_utc": _utc_now(),
        "protocol_sha256": sha256_file(protocol_path),
        "predeclared_target_interval": list(G2_TARGET),
        "max_settings": max_settings,
        "tuning_rule": (
            "fixed_predeclared_settings"
            if fixed_noise_settings is not None
            else "bounded_original_day1_rule"
        ),
        "protocol_amendment_id": protocol_amendment_id,
        "history": [
            {
                "noise": setting["noise"],
                "aggregate": setting["aggregate"],
                "checks": setting["checks"],
                "gate_passed": setting["gate_passed"],
                "summary_hash": setting["summary_hash"],
                "phase_provenance": setting["phase_provenance"],
            }
            for setting in history
        ],
        "status": "passed" if passed_setting is not None else "failed",
        "selected_positive_noise": (
            passed_setting["noise"] if passed_setting is not None else None
        ),
        "inferential_use": False,
        "cross_setting_scientific_provenance_consistent": (
            cross_setting_provenance
        ),
        "scientific_provenance": (
            history[0]["scientific_provenance"]
            if cross_setting_provenance
            else None
        ),
        "selected_phase_provenance": (
            passed_setting["phase_provenance"]
            if passed_setting is not None
            else None
        ),
    }
    result["result_hash"] = sha256_value(result)
    _atomic_json(output_root / "G2_RESULT.json", result)
    return result


def run_smoke(
    *,
    noise: float,
    output_root: Path,
    repository_root: Path,
    protocol_path: Path,
    duration_s: float = 7200.0,
    workers: int = 4,
    resume: bool = True,
    evaluation_workload_path: Path | None = None,
    protocol_amendment_id: str | None = None,
    expected_g2_provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    smoke_seeds = (
        AMENDED_SMOKE_SEEDS
        if evaluation_workload_path is not None
        else ORIGINAL_SMOKE_SEEDS
    )
    requests = [
        RunRequest(
            regime="R-B",
            policy=policy,
            seed=seed,
            scenario_path=(
                repository_root
                / "configs/scenarios/riverside_flood_dynamic_v2.yaml"
            ),
            shock_registry_root=repository_root / "configs/shocks",
            protocol_path=protocol_path,
            output_root=output_root / "runs",
            evaluation_workload_path=evaluation_workload_path,
            protocol_amendment_id=protocol_amendment_id,
            forcing_noise_std=noise,
            duration_s=duration_s,
            tick_s=1.0,
            requested_speed=50.0,
            resume=resume,
        )
        for policy in SMOKE_POLICIES
        for seed in smoke_seeds
    ]
    attempts = _run_cells(requests, workers)
    exogenous_by_seed: dict[int, set[str]] = {seed: set() for seed in smoke_seeds}
    cell_fingerprints: list[str] = []
    provenance_hashes: set[str] = set()
    cell_diagnostics: list[dict[str, Any]] = []
    for attempt in attempts:
        if attempt["status"] != "complete":
            continue
        directory = Path(attempt["directory"])
        exogenous_by_seed[attempt["seed"]].add(
            sha256_file(directory / "exogenous.jsonl")
        )
        metrics, manifest = _read_cell(directory)
        cell_diagnostics.append(
            {
                "policy": attempt["policy"],
                "seed": attempt["seed"],
                "commitment": metrics["commitment"],
                "refresh": metrics["refresh"],
                "common_baseline_evidence": metrics["common_baseline_evidence"],
                "verification_cost": metrics["verification_cost"],
            }
        )
        cell_fingerprints.append(manifest["run_fingerprint"])
        provenance_hashes.add(
            sha256_value(
                _cell_phase_provenance(manifest["scientific_identity"])
            )
        )
    all_complete = len(attempts) == 9 and all(
        attempt["status"] == "complete" for attempt in attempts
    )
    crn_equal = all(len(hashes) == 1 for hashes in exogenous_by_seed.values())
    expected_provenance_hash = (
        sha256_value(expected_g2_provenance)
        if expected_g2_provenance is not None
        else None
    )
    provenance_matches_g2 = (
        len(provenance_hashes) == 1
        and (
            expected_provenance_hash is None
            or next(iter(provenance_hashes)) == expected_provenance_hash
        )
    )
    result = {
        "schema_version": "trace-day1-smoke-v3",
        "created_at_utc": _utc_now(),
        "noise": noise,
        "duration_s": duration_s,
        "executor": {"backend": "thread_pool", "workers": workers},
        "policies": list(SMOKE_POLICIES),
        "seeds": list(smoke_seeds),
        "protocol_amendment_id": protocol_amendment_id,
        "attempts": attempts,
        "cell_diagnostics": sorted(
            cell_diagnostics,
            key=lambda item: (item["policy"], item["seed"]),
        ),
        "checks": {
            "exactly_nine_complete_valid_cells": all_complete,
            "per_seed_exogenous_hashes_identical": crn_equal,
            "scientific_provenance_matches_g2": provenance_matches_g2,
        },
        "exogenous_sha256_by_seed": {
            str(seed): sorted(hashes)
            for seed, hashes in exogenous_by_seed.items()
        },
        "cell_fingerprints": sorted(cell_fingerprints),
        "status": (
            "passed"
            if all_complete and crn_equal and provenance_matches_g2
            else "failed"
        ),
        "inferential_use": False,
    }
    result["result_hash"] = sha256_value(result)
    _atomic_json(output_root / "SMOKE_RESULT.json", result)
    return result
