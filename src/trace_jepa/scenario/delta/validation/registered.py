from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal, cast

from trace_jepa.scenario.delta.acceptance import DeltaSmallAcceptanceConfig
from trace_jepa.scenario.delta.environment import require_reference_environment
from trace_jepa.scenario.delta.evaluation import evaluate_partitions
from trace_jepa.scenario.delta.generator import generate_delta_small_from_models
from trace_jepa.scenario.delta.loading import (
    load_acceptance_config,
    load_geography_catalog,
    load_scenario_config,
)
from trace_jepa.scenario.delta.provenance.artifacts import (
    canonical_json_bytes,
    current_git_commit,
    sha256_file,
)
from trace_jepa.scenario.delta.provenance.scientific_inputs import (
    ScientificInputManifest,
    verify_scientific_input_manifest,
)
from trace_jepa.scenario.delta.reconciliation_selection import (
    CANONICAL_RECONCILIATION_ALGORITHM,
)
from trace_jepa.scenario.delta.reconciliation_v8 import (
    baseline_v7_clusters,
    evidence_graph_clusters,
)
from trace_jepa.scenario.delta.validation.performance import book_and_performance
from trace_jepa.scenario.delta.validation.statistics import cluster_mean_interval
from trace_jepa.scenario.delta.validation.verification import trace_artifacts_verify
from trace_jepa.scenario.delta.validation_v7 import run_v7_study

ValidationStudy = Literal["development", "original-confirmatory", "replication"]
ORIGINAL_CONFIRMATION_TOKEN = "EXECUTE-CONFIRMATORY-V7-ORIGINAL-ONCE"


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


def canonical_v8_paths(repository_root: Path) -> dict[str, Path]:
    return {
        "config": repository_root / "configs/scenarios/wf_dfld_01_small.yaml",
        "geography": repository_root
        / "data/scenario/delta/geography/delta_small_geography_v3.yaml",
        "policy": repository_root / "configs/policies/trace_delta_small_v1.yaml",
        "acceptance": repository_root / "configs/scenarios/wf_dfld_01_small_acceptance_v4.yaml",
        "scientific_manifest": repository_root
        / "data/scenario/delta/provenance/v8_scientific_input_manifest_v1.json",
        "environment": repository_root
        / "data/scenario/delta/environment/python311_linux_amd64_v1.json",
        "lock": repository_root / "requirements-delta-python311.lock",
    }


def _require_canonical_supplied_path(label: str, supplied: Path, expected: Path) -> Path:
    if supplied.is_symlink():
        raise ValueError(f"registered {label} must not be a symlink")
    resolved_supplied = supplied.resolve(strict=True)
    resolved_expected = expected.resolve(strict=True)
    if resolved_supplied != resolved_expected or not resolved_supplied.is_file():
        raise ValueError(f"registered {label} path was substituted")
    return resolved_supplied


def verify_registered_v8_inputs(
    *,
    config_path: Path,
    geography_path: Path,
    policy_path: Path,
    scientific_manifest_path: Path,
    acceptance_path: Path | None = None,
) -> ScientificInputManifest:
    repository_root = _repository_root()
    expected = canonical_v8_paths(repository_root)
    _require_canonical_supplied_path("scenario configuration", config_path, expected["config"])
    _require_canonical_supplied_path("geography catalog", geography_path, expected["geography"])
    _require_canonical_supplied_path("policy", policy_path, expected["policy"])
    _require_canonical_supplied_path(
        "scientific-input manifest", scientific_manifest_path, expected["scientific_manifest"]
    )
    if acceptance_path is not None:
        _require_canonical_supplied_path(
            "acceptance protocol", acceptance_path, expected["acceptance"]
        )
    return verify_scientific_input_manifest(repository_root, scientific_manifest_path)


def _reference_partition(scenario: Any) -> tuple[dict[str, str], set[str]]:
    reference = {
        item.call_id: (
            item.truth_incident_id
            if item.truth_incident_id is not None
            else f"false-singleton:{item.call_id}"
        )
        for item in scenario.observations.lineage
    }
    false_ids = {
        item.call_id for item in scenario.observations.lineage if item.truth_incident_id is None
    }
    return reference, false_ids


def _paired_reconciliation(
    *,
    seeds: list[int],
    config_path: Path,
    geography_path: Path,
    protocol_hash: str,
    study_id: str,
) -> dict[str, object]:
    config = load_scenario_config(config_path)
    geography = load_geography_catalog(geography_path)
    metric_names = (
        "false_merge_rate",
        "pairwise_precision",
        "pairwise_recall",
        "pairwise_f1",
        "adjusted_rand_index",
        "missed_link_rate",
        "false_report_merge_rate",
    )
    rows: list[dict[str, float | int]] = []
    for seed in seeds:
        scenario = generate_delta_small_from_models(
            config.model_copy(update={"seed": seed}),
            geography,
            config_path.resolve(strict=True),
        )
        calls = sorted(
            scenario.observations.calls, key=lambda item: (item.received_s, item.call_id)
        )
        reference, false_ids = _reference_partition(scenario)
        baseline = evaluate_partitions(reference, baseline_v7_clusters(calls), false_ids)
        selected = evaluate_partitions(
            reference,
            evidence_graph_clusters(calls, CANONICAL_RECONCILIATION_ALGORITHM).cluster_by_call,
            false_ids,
        )
        row: dict[str, float | int] = {"seed": seed}
        for metric in metric_names:
            baseline_value = float(getattr(baseline, metric))
            selected_value = float(getattr(selected, metric))
            row[f"baseline_{metric}"] = baseline_value
            row[f"selected_{metric}"] = selected_value
            row[f"difference_{metric}"] = selected_value - baseline_value
        rows.append(row)

    metrics: dict[str, object] = {}
    for metric in metric_names:
        baseline_values = [float(row[f"baseline_{metric}"]) for row in rows]
        selected_values = [float(row[f"selected_{metric}"]) for row in rows]
        differences = [float(row[f"difference_{metric}"]) for row in rows]
        metrics[metric] = {
            "baseline": cluster_mean_interval(
                baseline_values, protocol_hash, f"{study_id}:baseline:{metric}"
            ),
            "selected": cluster_mean_interval(
                selected_values, protocol_hash, f"{study_id}:selected:{metric}"
            ),
            "paired_difference_selected_minus_baseline": cluster_mean_interval(
                differences, protocol_hash, f"{study_id}:paired-difference:{metric}"
            ),
        }
    return {
        "baseline_algorithm_id": "baseline-v7-heuristic",
        "selected_algorithm_id": "evidence-graph-q075",
        "cluster_unit": "one-complete-seed-run",
        "metrics": metrics,
        "per_seed": rows,
    }


def _write_report(output_path: Path, report: dict[str, object]) -> None:
    if output_path.exists() or output_path.is_symlink():
        raise FileExistsError(f"validation report already exists: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(canonical_json_bytes(report))


def run_v8_development_validation(
    *,
    config_path: Path,
    geography_path: Path,
    policy_path: Path,
    scientific_manifest_path: Path,
    output_path: Path,
) -> dict[str, object]:
    manifest = verify_registered_v8_inputs(
        config_path=config_path,
        geography_path=geography_path,
        policy_path=policy_path,
        scientific_manifest_path=scientific_manifest_path,
    )
    config = load_scenario_config(config_path)
    if config.generator_version != "delta-small-generator-v8":
        raise ValueError("development-v8 requires generator v8")
    seeds = list(range(20260803, 20260903))
    protocol_hash = manifest.aggregate_sha256
    study = run_v7_study(
        study_id="development-v8",
        seeds=seeds,
        config_path=config_path,
        geography_path=geography_path,
        policy_path=policy_path,
        protocol_hash=protocol_hash,
    )
    paired = _paired_reconciliation(
        seeds=seeds,
        config_path=config_path,
        geography_path=geography_path,
        protocol_hash=protocol_hash,
        study_id="development-v8",
    )
    study["registered_gate_evaluation"] = {
        "protocol_role": "development-only-no-confirmatory-gates",
        "all_episode_keys_unique": bool(
            cast(dict[str, object], study["operations"])["all_episode_keys_unique"]
        ),
    }
    report: dict[str, object] = {
        "schema_version": "delta-statistical-validation-v5",
        "execution_role": "development",
        "confirmatory_seeds_accessed": False,
        "scientific_input_manifest_sha256": sha256_file(scientific_manifest_path),
        "scientific_input_aggregate_sha256": manifest.aggregate_sha256,
        "scenario_configuration_sha256": sha256_file(config_path),
        "geography_sha256": sha256_file(geography_path),
        "policy_sha256": sha256_file(policy_path),
        "study": study,
        "paired_reconciliation": paired,
        "claims_limit": [
            "development-data-only",
            "coefficients-and-reconciliation-selected-on-these-seeds",
            "not-confirmatory-evidence",
        ],
    }
    _write_report(output_path, report)
    return report


def _load_original_report(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.resolve(strict=True).is_file():
        raise ValueError("original report must be a safe regular file")
    try:
        report = cast(dict[str, object], json.loads(path.read_text("utf-8")))
    except (OSError, ValueError) as exc:
        raise ValueError("invalid original report") from exc
    if report.get("execution_role") != "original-confirmatory":
        raise ValueError("replication requires a verified original-confirmatory report")
    return report


def _require_original_remote_context(confirmation_token: str | None) -> tuple[str, str]:
    if confirmation_token != ORIGINAL_CONFIRMATION_TOKEN:
        raise ValueError(
            "original confirmatory execution requires the explicit authorization token"
        )
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise ValueError("original confirmatory execution is restricted to GitHub Actions")
    if os.environ.get("TRACE_DELTA_EXECUTION_ROLE") != "original-confirmatory":
        raise ValueError("original confirmatory execution requires the dedicated workflow role")
    run_id = os.environ.get("GITHUB_RUN_ID")
    source_commit = os.environ.get("GITHUB_SHA")
    if not run_id or not source_commit or len(source_commit) != 40:
        raise ValueError("original confirmatory workflow provenance is incomplete")
    if current_git_commit(_repository_root()) != source_commit:
        raise ValueError("checked-out source does not match GITHUB_SHA")
    return run_id, source_commit


def run_v8_registered_validation(
    *,
    study: Literal["original-confirmatory", "replication"],
    config_path: Path,
    geography_path: Path,
    policy_path: Path,
    acceptance_path: Path,
    scientific_manifest_path: Path,
    output_path: Path,
    confirmation_token: str | None = None,
    original_report_path: Path | None = None,
) -> dict[str, object]:
    manifest = verify_registered_v8_inputs(
        config_path=config_path,
        geography_path=geography_path,
        policy_path=policy_path,
        acceptance_path=acceptance_path,
        scientific_manifest_path=scientific_manifest_path,
    )
    protocol: DeltaSmallAcceptanceConfig = load_acceptance_config(acceptance_path)
    if protocol.schema_version != "delta-small-acceptance-v8":
        raise ValueError("v8 registered validation requires acceptance v8")
    if protocol.scientific_input_manifest_sha256 != sha256_file(scientific_manifest_path):
        raise ValueError("acceptance protocol does not bind the supplied scientific manifest")
    confirmatory = protocol.v8_confirmatory_ensemble
    if confirmatory is None or len(confirmatory.seeds) != 100:
        raise ValueError("acceptance v8 requires exactly 100 confirmatory-v7 seeds")
    expected = canonical_v8_paths(_repository_root())
    source_commit: str
    workflow_run_id: str | None
    if study == "original-confirmatory":
        workflow_run_id, source_commit = _require_original_remote_context(confirmation_token)
        require_reference_environment(expected["environment"], expected["lock"])
    else:
        if original_report_path is None:
            raise ValueError("replication requires --original-report")
        original = _load_original_report(original_report_path)
        if original.get("protocol_sha256") != sha256_file(acceptance_path):
            raise ValueError("original report uses another acceptance protocol")
        if original.get("scientific_input_manifest_sha256") != sha256_file(
            scientific_manifest_path
        ):
            raise ValueError("original report uses another scientific input manifest")
        source_commit = current_git_commit(_repository_root())
        workflow_run_id = None

    protocol_hash = sha256_file(acceptance_path)
    development_seeds = list(
        range(
            protocol.development_ensemble.first_seed,
            protocol.development_ensemble.first_seed + protocol.development_ensemble.seed_count,
        )
    )
    studies = [
        run_v7_study(
            study_id="development-v8",
            seeds=development_seeds,
            config_path=config_path,
            geography_path=geography_path,
            policy_path=policy_path,
            protocol_hash=protocol_hash,
        ),
        run_v7_study(
            study_id="confirmatory-v7-primary",
            seeds=confirmatory.seeds,
            config_path=config_path,
            geography_path=geography_path,
            policy_path=policy_path,
            protocol_hash=protocol_hash,
        ),
    ]
    paired = _paired_reconciliation(
        seeds=confirmatory.seeds,
        config_path=config_path,
        geography_path=geography_path,
        protocol_hash=protocol_hash,
        study_id="confirmatory-v7-primary",
    )
    paired_metrics = cast(dict[str, Any], paired["metrics"])
    false_merge_difference = paired_metrics["false_merge_rate"][
        "paired_difference_selected_minus_baseline"
    ]
    recall_difference = paired_metrics["pairwise_recall"][
        "paired_difference_selected_minus_baseline"
    ]
    reconciliation_claim = {
        "false_merge_improvement": float(false_merge_difference["upper_95"]) < 0.0,
        "recall_noninferiority": float(recall_difference["lower_95"]) > -0.05,
    }
    primary = cast(dict[str, Any], studies[1])
    call_count = cast(dict[str, Any], primary["call_count"])
    peak_hour = cast(list[dict[str, Any]], call_count["hourly_mean_95"])[3]
    channel = cast(dict[str, Any], primary["observation_channel"])
    operations = cast(dict[str, Any], primary["operations"])
    channel_gates = {
        name: abs(float(channel[name]["estimate"]) - expected_value)
        <= protocol.observation_channel.point_absolute_tolerances[name]
        for name, expected_value in protocol.observation_channel.expected_point_estimates.items()
    }
    book_scenario, book_result, elapsed = book_and_performance(
        config_path, geography_path, policy_path
    )
    allocation_total = book_result.allocated + book_result.refused
    allocation_share = book_result.allocated / allocation_total if allocation_total else 0.0
    book_gates = {
        "allocation_share_within_registered_band": (
            protocol.demand_capacity.book_allocation_share_minimum
            <= allocation_share
            <= protocol.demand_capacity.book_allocation_share_maximum
        ),
        "has_allocation_refusal_and_visible_evidence_repair": (
            book_result.allocated > 0 and book_result.refused > 0 and book_result.repaired > 0
        ),
        "trace_and_outcome_links_verified": trace_artifacts_verify(book_result),
    }
    confirmatory_gates = {
        "observed_call_mean_within_absolute_tolerance": (
            abs(float(call_count["estimate"]) - protocol.call_process.expected_total_mean)
            <= protocol.call_process.total_mean_absolute_tolerance
        ),
        "configured_peak_inside_hour_four_mean_95_interval": (
            float(peak_hour["lower_95"])
            <= protocol.call_process.configured_peak_intensity_per_hour
            <= float(peak_hour["upper_95"])
        ),
        "observation_channel_points_within_frozen_tolerances": all(channel_gates.values()),
        "nonzero_operational_means": all(
            float(operations[name]["estimate"]) > 0
            for name in ("allocations", "refusals", "repairs")
        ),
        "all_trace_and_outcome_links_verified": bool(operations["all_trace_artifacts_verified"]),
        "no_overlapping_incident_episode_violations": bool(operations["all_episode_keys_unique"]),
        "runtime_below_55_seconds": elapsed <= protocol.performance.maximum_generate_run_replay_s,
    }
    studies[0]["registered_gate_evaluation"] = {
        "protocol_role": "development-only-no-confirmatory-gates",
        "all_episode_keys_unique": bool(
            cast(dict[str, object], studies[0]["operations"])["all_episode_keys_unique"]
        ),
    }
    studies[1]["registered_gate_evaluation"] = confirmatory_gates
    report: dict[str, object] = {
        "schema_version": "delta-statistical-validation-v5",
        "execution_role": study,
        "execution_policy": "original-once-then-explicit-replication",
        "source_commit": source_commit,
        "workflow_run_id": workflow_run_id,
        "protocol_sha256": protocol_hash,
        "scientific_input_manifest_sha256": sha256_file(scientific_manifest_path),
        "scientific_input_aggregate_sha256": manifest.aggregate_sha256,
        "scenario_configuration_sha256": sha256_file(config_path),
        "geography_sha256": sha256_file(geography_path),
        "policy_sha256": sha256_file(policy_path),
        "environment_contract_sha256": sha256_file(expected["environment"]),
        "dependency_lock_sha256": sha256_file(expected["lock"]),
        "seed_list": confirmatory.seeds,
        "studies": studies,
        "paired_reconciliation": paired,
        "paired_reconciliation_claim_evaluation": reconciliation_claim,
        "book_walkthrough": {
            "seed": protocol.book_seed,
            "observed_calls": len(book_scenario.observations.calls),
            "latent_incidents": len(book_scenario.truth.incidents),
            "allocations": book_result.allocated,
            "refusals": book_result.refused,
            "visible_evidence_repairs": book_result.repaired,
            "allocation_share": allocation_share,
            "peak_finite_strict_concurrent_load_ratio": (
                book_result.peak_finite_strict_concurrent_load_ratio_milli / 1000.0
            ),
            "peak_finite_uncapped_compatible_load_ratio": (
                book_result.peak_finite_uncapped_compatible_load_ratio_milli / 1000.0
            ),
            "peak_finite_registered_normalized_coverable_load_index": (
                book_result.peak_finite_registered_normalized_coverable_load_index_milli / 1000.0
            ),
            "strict_unserviceable_windows": book_result.strict_unserviceable_windows,
            "uncapped_unserviceable_windows": book_result.uncapped_unserviceable_windows,
            "historical_capped_unserviceable_windows": (
                book_result.historical_capped_unserviceable_windows
            ),
            "peak_finite_residual_strict_pressure_ratio": (
                book_result.peak_finite_residual_strict_pressure_ratio_milli / 1000.0
            ),
            "residual_strict_unserviceable_windows": (
                book_result.residual_strict_unserviceable_windows
            ),
            "registered_gate_evaluation": book_gates,
        },
        "confirmatory_gate_evaluation": {
            **confirmatory_gates,
            "observation_channel_metric_gates": channel_gates,
            "strict_load_numeric_gate": None,
            "all_registered_non_reconciliation_gates_met": (
                all(book_gates.values()) and all(confirmatory_gates.values())
            ),
        },
        "performance": {
            "generate_run_and_exact_replay_seconds": elapsed,
            "maximum_seconds": protocol.performance.maximum_generate_run_replay_s,
        },
        "claims_limit": [
            "synthetic-process-validation-not-field-effectiveness",
            "strict-load-has-no-numerical-acceptance-gate",
            "automatic-aid-is-a-frozen-teaching-assumption",
            "adverse-results-must-be-published-without-retuning",
        ],
    }
    _write_report(output_path, report)
    return report
