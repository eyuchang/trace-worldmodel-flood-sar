"""Registered Delta validation roles and immutable execution boundaries."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, cast

from trace_jepa.scenario.delta.domain import GeneratedScenario
from trace_jepa.scenario.delta.domain.acceptance import DeltaSmallAcceptanceConfig
from trace_jepa.scenario.delta.domain.loading import load_acceptance_config, load_scenario_config
from trace_jepa.scenario.delta.environment import require_reference_environment
from trace_jepa.scenario.delta.provenance.artifacts import (
    canonical_json_bytes,
    current_git_commit,
    sha256_file,
)
from trace_jepa.scenario.delta.provenance.scientific_inputs import (
    ScientificInputManifest,
    scientific_input_core_aggregate,
    verify_scientific_input_manifest,
)
from trace_jepa.scenario.delta.runtime import DeltaRunResult
from trace_jepa.scenario.delta.validation.gates import (
    book_gates,
    confirmatory_gates,
    reconciliation_claims,
)
from trace_jepa.scenario.delta.validation.models import (
    DevelopmentValidationRequest,
    OriginalReportIdentity,
    OriginalWorkflowContext,
    RegisteredValidationRequest,
    ReplicationBindingRequest,
    StudyBundleRequest,
    verify_registered_original_report,
)
from trace_jepa.scenario.delta.validation.performance import book_and_performance
from trace_jepa.scenario.delta.validation.reconciliation import (
    paired_reconciliation_report,
)
from trace_jepa.scenario.delta.validation_v7 import run_v7_study

ValidationStudy = Literal["development", "original-confirmatory", "replication"]
ORIGINAL_CONFIRMATION_TOKEN = "EXECUTE-CONFIRMATORY-V8-ORIGINAL-ONCE"
ORIGINAL_AUTHORIZATION_TAG = "wf-dfld-01-small-confirmatory-v8-original-r2"
ORIGINAL_WORKFLOW_FILE = "delta-confirmatory-v8.yml"


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[5]


def canonical_v9_paths(repository_root: Path) -> dict[str, Path]:
    """Return the only inputs admitted to a v9 registered execution."""

    return {
        "config": repository_root / "configs/scenarios/wf_dfld_01_small.yaml",
        "geography": repository_root
        / "data/scenario/delta/geography/delta_small_geography_v3.yaml",
        "policy": repository_root / "configs/policies/trace_delta_small_v1.yaml",
        "acceptance": repository_root / "configs/scenarios/wf_dfld_01_small_acceptance_v5.yaml",
        "scientific_manifest": repository_root
        / "data/scenario/delta/provenance/v8_scientific_input_manifest_v2.json",
        "environment": repository_root
        / "data/scenario/delta/environment/python311_linux_amd64_v1.json",
        "lock": repository_root / "requirements-delta-python311.lock",
        "original_registry": repository_root
        / "data/scenario/delta/validation/original_report_registry_v1.json",
    }


# One-release API compatibility; values intentionally point to the current protocol.
canonical_v8_paths = canonical_v9_paths


def _canonical_file(label: str, supplied: Path, expected: Path) -> Path:
    if supplied.is_symlink():
        raise ValueError(f"registered {label} must not be a symlink")
    resolved_supplied = supplied.resolve(strict=True)
    resolved_expected = expected.resolve(strict=True)
    if resolved_supplied != resolved_expected or not resolved_supplied.is_file():
        raise ValueError(f"registered {label} path was substituted")
    return resolved_supplied


def verify_registered_v9_inputs(
    *,
    config_path: Path,
    geography_path: Path,
    policy_path: Path,
    scientific_manifest_path: Path,
    acceptance_path: Path | None = None,
) -> ScientificInputManifest:
    """Reject path substitution and verify every frozen scientific input."""

    root = _repository_root()
    expected = canonical_v9_paths(root)
    _canonical_file("scenario configuration", config_path, expected["config"])
    _canonical_file("geography catalog", geography_path, expected["geography"])
    _canonical_file("policy", policy_path, expected["policy"])
    _canonical_file(
        "scientific-input manifest",
        scientific_manifest_path,
        expected["scientific_manifest"],
    )
    if acceptance_path is not None:
        _canonical_file("acceptance protocol", acceptance_path, expected["acceptance"])
    return verify_scientific_input_manifest(root, scientific_manifest_path)


verify_registered_v8_inputs = verify_registered_v9_inputs


def _write_report(output_path: Path, report: dict[str, object]) -> None:
    if output_path.exists() or output_path.is_symlink():
        raise FileExistsError(f"validation report already exists: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(canonical_json_bytes(report))


def _run_development(request: DevelopmentValidationRequest) -> dict[str, object]:
    """Run only the already-inspected development ensemble."""

    root = _repository_root()
    expected = canonical_v9_paths(root)
    _canonical_file("scenario configuration", request.config_path, expected["config"])
    _canonical_file("geography catalog", request.geography_path, expected["geography"])
    _canonical_file("policy", request.policy_path, expected["policy"])
    manifest: ScientificInputManifest | None = None
    if request.scientific_manifest_path.is_file():
        manifest = verify_registered_v9_inputs(
            config_path=request.config_path,
            geography_path=request.geography_path,
            policy_path=request.policy_path,
            scientific_manifest_path=request.scientific_manifest_path,
        )
        protocol_hash = manifest.aggregate_sha256
        core_hash = manifest.core_aggregate_sha256
        manifest_hash: str | None = sha256_file(request.scientific_manifest_path)
    elif request.scientific_manifest_path == expected["scientific_manifest"]:
        core_hash = scientific_input_core_aggregate(root)
        protocol_hash = core_hash
        manifest_hash = None
    else:
        raise ValueError("development scientific-input path was substituted")
    config = load_scenario_config(request.config_path)
    if config.generator_version != "delta-small-generator-v8":
        raise ValueError("development-v9 requires generator v8")
    seeds = list(range(20260803, 20260903))
    study = run_v7_study(
        study_id="development-v9",
        seeds=seeds,
        config_path=request.config_path,
        geography_path=request.geography_path,
        policy_path=request.policy_path,
        protocol_hash=protocol_hash,
    )
    paired = paired_reconciliation_report(
        seeds=seeds,
        config_path=request.config_path,
        geography_path=request.geography_path,
        protocol_hash=protocol_hash,
        study_id="development-v9",
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
        "scientific_input_manifest_sha256": manifest_hash,
        "scientific_input_aggregate_sha256": (
            None if manifest is None else manifest.aggregate_sha256
        ),
        "scientific_input_core_aggregate_sha256": core_hash,
        "scenario_configuration_sha256": sha256_file(request.config_path),
        "geography_sha256": sha256_file(request.geography_path),
        "policy_sha256": sha256_file(request.policy_path),
        "study": study,
        "paired_reconciliation": paired,
        "claims_limit": [
            "development-data-only",
            "coefficients-and-reconciliation-selected-on-these-seeds",
            "not-confirmatory-evidence",
        ],
    }
    _write_report(request.output_path, report)
    return report


def run_v9_development_validation(**kwargs: object) -> dict[str, object]:
    """Compatibility facade that validates a typed development request."""

    return _run_development(DevelopmentValidationRequest.model_validate(kwargs))


run_v8_development_validation = run_v9_development_validation


def _require_original_remote_context(
    confirmation_token: str | None,
) -> OriginalWorkflowContext:
    if confirmation_token != ORIGINAL_CONFIRMATION_TOKEN:
        raise ValueError(
            "original confirmatory execution requires the explicit authorization token"
        )
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise ValueError("original confirmatory execution is restricted to GitHub Actions")
    if os.environ.get("TRACE_DELTA_EXECUTION_ROLE") != "original-confirmatory":
        raise ValueError("original confirmatory execution requires the dedicated workflow role")
    ref = os.environ.get("GITHUB_REF")
    if ref != f"refs/tags/{ORIGINAL_AUTHORIZATION_TAG}":
        raise ValueError("original execution requires the exact authorization tag")
    if os.environ.get("GITHUB_RUN_ATTEMPT") != "1":
        raise ValueError("original execution is restricted to workflow run attempt one")
    workflow_file = os.environ.get("TRACE_DELTA_WORKFLOW_FILE")
    if workflow_file != ORIGINAL_WORKFLOW_FILE:
        raise ValueError("original execution requires the dedicated workflow file")
    run_id = os.environ.get("GITHUB_RUN_ID")
    source_commit = os.environ.get("GITHUB_SHA")
    workflow_name = os.environ.get("GITHUB_WORKFLOW")
    if not run_id or not source_commit or not workflow_name:
        raise ValueError("original confirmatory workflow provenance is incomplete")
    if current_git_commit(_repository_root()) != source_commit:
        raise ValueError("checked-out source does not match GITHUB_SHA")
    return OriginalWorkflowContext(
        workflow_run_id=run_id,
        source_commit=source_commit,
        authorization_tag=ORIGINAL_AUTHORIZATION_TAG,
        workflow_name=workflow_name,
        workflow_file=ORIGINAL_WORKFLOW_FILE,
    )


def _bound_protocol(
    acceptance_path: Path,
    manifest: ScientificInputManifest,
) -> tuple[DeltaSmallAcceptanceConfig, list[int]]:
    protocol = load_acceptance_config(acceptance_path)
    if protocol.schema_version != "delta-small-acceptance-v9":
        raise ValueError("registered v9 validation requires acceptance v9")
    if protocol.scientific_input_core_aggregate_sha256 != manifest.core_aggregate_sha256:
        raise ValueError("acceptance protocol does not bind the scientific-input core")
    confirmatory = protocol.v8_confirmatory_ensemble
    if confirmatory is None or len(confirmatory.seeds) != 100:
        raise ValueError("acceptance v9 requires exactly 100 confirmatory-v8 seeds")
    return protocol, list(confirmatory.seeds)


def _validate_replication_original(
    request: ReplicationBindingRequest,
    expected_paths: dict[str, Path],
    manifest: ScientificInputManifest,
) -> OriginalReportIdentity:
    if request.original_report_path is None:
        raise ValueError("replication requires --original-report")
    _, identity = verify_registered_original_report(
        _repository_root(),
        request.original_report_path,
        expected_paths["original_registry"],
    )
    expected_values: dict[str, object] = {
        "protocol_sha256": request.protocol_hash,
        "scientific_input_manifest_sha256": sha256_file(request.manifest_path),
        "scientific_input_aggregate_sha256": manifest.aggregate_sha256,
        "scientific_input_core_aggregate_sha256": manifest.core_aggregate_sha256,
        "environment_contract_sha256": sha256_file(expected_paths["environment"]),
        "dependency_lock_sha256": sha256_file(expected_paths["lock"]),
        "scenario_configuration_sha256": sha256_file(request.config_path),
        "geography_sha256": sha256_file(request.geography_path),
        "policy_sha256": sha256_file(request.policy_path),
        "seed_list": request.confirmatory_seeds,
        "study_ids": ("development-v9", "confirmatory-v8-primary"),
        "study_seed_counts": (100, 100),
        "baseline_reconciliation_algorithm": "baseline-v7-heuristic",
        "selected_reconciliation_algorithm": "evidence-graph-q075",
    }
    for field, expected in expected_values.items():
        if getattr(identity, field) != expected:
            raise ValueError(f"original report identity mismatch: {field}")
    return identity


def _study_bundle(
    request: StudyBundleRequest,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    development_seeds = list(
        range(
            request.development_first_seed,
            request.development_first_seed + request.development_seed_count,
        )
    )
    studies = [
        run_v7_study(
            study_id="development-v9",
            seeds=development_seeds,
            config_path=request.config_path,
            geography_path=request.geography_path,
            policy_path=request.policy_path,
            protocol_hash=request.protocol_hash,
        ),
        run_v7_study(
            study_id="confirmatory-v8-primary",
            seeds=list(request.confirmatory_seeds),
            config_path=request.config_path,
            geography_path=request.geography_path,
            policy_path=request.policy_path,
            protocol_hash=request.protocol_hash,
        ),
    ]
    paired = paired_reconciliation_report(
        seeds=list(request.confirmatory_seeds),
        config_path=request.config_path,
        geography_path=request.geography_path,
        protocol_hash=request.protocol_hash,
        study_id="confirmatory-v8-primary",
    )
    return studies, paired


def _book_summary(
    scenario: GeneratedScenario,
    result: DeltaRunResult,
    allocation_share: float,
    gates: dict[str, bool],
    seed: int,
) -> dict[str, object]:
    return {
        "seed": seed,
        "observed_calls": len(scenario.observations.calls),
        "latent_incidents": len(scenario.truth.incidents),
        "allocations": result.allocated,
        "refusals": result.refused,
        "visible_evidence_repairs": result.repaired,
        "allocation_share": allocation_share,
        "peak_finite_strict_concurrent_load_ratio": (
            result.peak_finite_strict_concurrent_load_ratio_milli / 1000.0
        ),
        "peak_finite_uncapped_compatible_load_ratio": (
            result.peak_finite_uncapped_compatible_load_ratio_milli / 1000.0
        ),
        "peak_finite_registered_normalized_coverable_load_index": (
            result.peak_finite_registered_normalized_coverable_load_index_milli / 1000.0
        ),
        "strict_unserviceable_windows": result.strict_unserviceable_windows,
        "uncapped_unserviceable_windows": result.uncapped_unserviceable_windows,
        "historical_capped_unserviceable_windows": (result.historical_capped_unserviceable_windows),
        "peak_finite_residual_strict_pressure_ratio": (
            result.peak_finite_residual_strict_pressure_ratio_milli / 1000.0
        ),
        "residual_strict_unserviceable_windows": (result.residual_strict_unserviceable_windows),
        "registered_gate_evaluation": gates,
    }


def _run_registered(request: RegisteredValidationRequest) -> dict[str, object]:
    """Execute one authorized original, or a registry-bound replication."""

    context = (
        _require_original_remote_context(request.confirmation_token)
        if request.study == "original-confirmatory"
        else None
    )
    manifest = verify_registered_v9_inputs(
        config_path=request.config_path,
        geography_path=request.geography_path,
        policy_path=request.policy_path,
        acceptance_path=request.acceptance_path,
        scientific_manifest_path=request.scientific_manifest_path,
    )
    protocol, confirmatory_seeds = _bound_protocol(request.acceptance_path, manifest)
    expected = canonical_v9_paths(_repository_root())
    protocol_hash = sha256_file(request.acceptance_path)
    if context is not None:
        require_reference_environment(expected["environment"], expected["lock"])
        source_commit = context.source_commit
        original_identity = None
    else:
        original_identity = _validate_replication_original(
            ReplicationBindingRequest(
                original_report_path=request.original_report_path,
                protocol_hash=protocol_hash,
                manifest_path=request.scientific_manifest_path,
                config_path=request.config_path,
                geography_path=request.geography_path,
                policy_path=request.policy_path,
                confirmatory_seeds=tuple(confirmatory_seeds),
            ),
            expected_paths=expected,
            manifest=manifest,
        )
        source_commit = current_git_commit(_repository_root())

    studies, paired = _study_bundle(
        StudyBundleRequest(
            development_first_seed=protocol.development_ensemble.first_seed,
            development_seed_count=protocol.development_ensemble.seed_count,
            confirmatory_seeds=tuple(confirmatory_seeds),
            config_path=request.config_path,
            geography_path=request.geography_path,
            policy_path=request.policy_path,
            protocol_hash=protocol_hash,
        )
    )
    book_scenario, book_result, elapsed = book_and_performance(
        request.config_path, request.geography_path, request.policy_path
    )
    book_gate_values, allocation_share = book_gates(book_scenario, book_result, protocol)
    confirmatory_gate_values, channel_gates = confirmatory_gates(studies[1], protocol, elapsed)
    studies[0]["registered_gate_evaluation"] = {
        "protocol_role": "development-only-no-confirmatory-gates",
        "all_episode_keys_unique": bool(
            cast(dict[str, object], studies[0]["operations"])["all_episode_keys_unique"]
        ),
    }
    studies[1]["registered_gate_evaluation"] = confirmatory_gate_values

    report: dict[str, object] = {
        "schema_version": "delta-statistical-validation-v5",
        "execution_role": request.study,
        "execution_policy": "tag-authorized-original-once-then-registry-bound-replication",
        "source_commit": source_commit,
        "authorization_tag": (
            context.authorization_tag
            if context is not None
            else cast(OriginalReportIdentity, original_identity).authorization_tag
        ),
        "workflow_run_id": context.workflow_run_id if context is not None else None,
        "workflow_name": context.workflow_name if context is not None else None,
        "workflow_file": ORIGINAL_WORKFLOW_FILE,
        "original_identity_sha256": (
            None if original_identity is None else original_identity.canonical_sha256
        ),
        "protocol_sha256": protocol_hash,
        "scientific_input_manifest_sha256": sha256_file(request.scientific_manifest_path),
        "scientific_input_aggregate_sha256": manifest.aggregate_sha256,
        "scientific_input_core_aggregate_sha256": manifest.core_aggregate_sha256,
        "scenario_configuration_sha256": sha256_file(request.config_path),
        "geography_sha256": sha256_file(request.geography_path),
        "policy_sha256": sha256_file(request.policy_path),
        "environment_contract_sha256": sha256_file(expected["environment"]),
        "dependency_lock_sha256": sha256_file(expected["lock"]),
        "seed_list": confirmatory_seeds,
        "studies": studies,
        "paired_reconciliation": paired,
        "paired_reconciliation_claim_evaluation": reconciliation_claims(paired),
        "book_walkthrough": _book_summary(
            book_scenario,
            book_result,
            allocation_share,
            book_gate_values,
            protocol.book_seed,
        ),
        "confirmatory_gate_evaluation": {
            **confirmatory_gate_values,
            "observation_channel_metric_gates": channel_gates,
            "strict_load_numeric_gate": None,
            "all_registered_non_reconciliation_gates_met": (
                all(book_gate_values.values()) and all(confirmatory_gate_values.values())
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
    _write_report(request.output_path, report)
    return report


def run_v9_registered_validation(**kwargs: object) -> dict[str, object]:
    """Compatibility facade that validates a typed registered request."""

    return _run_registered(RegisteredValidationRequest.model_validate(kwargs))


run_v8_registered_validation = run_v9_registered_validation
