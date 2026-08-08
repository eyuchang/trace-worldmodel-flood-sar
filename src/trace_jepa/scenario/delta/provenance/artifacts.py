from __future__ import annotations

import hashlib
import json
import platform
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import Field

from trace_jepa.predictor.protocol import PredictorProvenance
from trace_jepa.scenario.delta.domain import DeltaModel, GeneratedScenario
from trace_jepa.scenario.delta.physical import physical_parameter_table
from trace_jepa.scenario.delta.population import population_parameter_table

if TYPE_CHECKING:
    from trace_jepa.scenario.delta.runner import DeltaRunResult


class ArtifactDescriptor(DeltaModel):
    name: str
    file_name: str
    sha256: str
    byte_length: int = Field(ge=0)
    contains_hidden_truth: bool


class StageSeedRecord(DeltaModel):
    stage_name: str
    seed_sha256: str


class ProvenanceInput(DeltaModel):
    name: str
    identifier: str
    sha256: str


class ReplayManifest(DeltaModel):
    schema_version: str
    scenario_id: str
    generator_version: str
    git_commit: str | None = None
    source_tree_sha256: str
    python_implementation: str | None = None
    python_version: str | None = None
    generation_order: list[str]
    stage_seeds: list[StageSeedRecord]
    inputs: list[ProvenanceInput]
    artifacts: list[ArtifactDescriptor]


class ArtifactMismatchError(RuntimeError):
    pass


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_tree_sha256(package_root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(package_root.rglob("*.py")):
        digest.update(path.relative_to(package_root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _git_commit(repository_root: Path) -> str:
    git_root = repository_root / ".git"
    if not git_root.is_dir():
        return "unavailable"
    head = (git_root / "HEAD").read_text("utf-8").strip()
    if not head.startswith("ref: "):
        return head
    reference = head.removeprefix("ref: ")
    loose = git_root / reference
    if loose.is_file():
        return loose.read_text("utf-8").strip()
    packed = git_root / "packed-refs"
    if packed.is_file():
        for line in packed.read_text("utf-8").splitlines():
            if line and not line.startswith(("#", "^")):
                commit, name = line.split(" ", maxsplit=1)
                if name == reference:
                    return commit
    return "unavailable"


def current_git_commit(repository_root: Path) -> str:
    """Return commit identity for a non-scientific execution receipt."""
    return _git_commit(repository_root)


def _safe_artifact_path(output_root: Path, file_name: str) -> Path:
    relative = Path(file_name)
    if relative.is_absolute() or relative.name != file_name or file_name in {"", ".", ".."}:
        raise ArtifactMismatchError(f"unsafe artifact file name: {file_name!r}")
    path = output_root / relative
    if path.is_symlink():
        raise ArtifactMismatchError(f"artifact path must not be a symlink: {path}")
    if path.parent.resolve(strict=True) != output_root.resolve(strict=True):
        raise ArtifactMismatchError(f"artifact path escapes output root: {path}")
    return path


def _validate_output_root(output_root: Path, *, create: bool) -> Path:
    if output_root.is_symlink():
        raise ArtifactMismatchError(f"artifact root must not be a symlink: {output_root}")
    if output_root.parent.is_symlink():
        raise ArtifactMismatchError(
            f"artifact root parent must not be a symlink: {output_root.parent}"
        )
    if create:
        output_root.mkdir(parents=True, exist_ok=True)
    resolved = output_root.resolve(strict=True)
    if not resolved.is_dir():
        raise ArtifactMismatchError(f"artifact root must be a directory: {resolved}")
    return resolved


def _write_artifact(
    output_root: Path,
    name: str,
    file_name: str,
    value: object,
    contains_hidden_truth: bool,
) -> ArtifactDescriptor:
    payload = canonical_json_bytes(value)
    path = _safe_artifact_path(output_root, file_name)
    path.write_bytes(payload)
    return ArtifactDescriptor(
        name=name,
        file_name=file_name,
        sha256=sha256_bytes(payload),
        byte_length=len(payload),
        contains_hidden_truth=contains_hidden_truth,
    )


def _summary(scenario: GeneratedScenario, run_result: DeltaRunResult) -> dict[str, object]:
    hourly_calls = [
        sum(
            hour * 3600 <= call.received_s < (hour + 1) * 3600
            for call in scenario.observations.calls
        )
        for hour in range(6)
    ]
    return {
        "schema_version": (
            "delta-small-machine-result-summary-v4"
            if scenario.config.generator_version == "delta-small-generator-v8"
            else (
                "delta-small-machine-result-summary-v3"
                if scenario.config.generator_version == "delta-small-generator-v7"
                else "delta-small-machine-result-summary-v2"
            )
        ),
        "scenario_id": scenario.config.scenario_id,
        "seed": scenario.config.seed,
        "seed_role": "descriptive_walkthrough_not_confirmatory",
        "latent_incidents": len(scenario.truth.incidents),
        "observed_calls": len(scenario.observations.calls),
        "realized_hourly_calls": hourly_calls,
        "realized_hourly_maximum": max(hourly_calls),
        "configured_expected_peak_intensity_per_hour": (
            scenario.config.call_process.peak_expected_calls_per_hour
        ),
        "allocations": run_result.allocated,
        "refusals": run_result.refused,
        "visible_evidence_repairs": run_result.repaired,
        "commitments": len(run_result.commitments),
        "completed_within_window": sum(
            item.status == "completed_within_window" for item in run_result.outcomes
        ),
        "active_at_scenario_censoring": sum(
            item.status == "active_at_scenario_censoring" for item in run_result.outcomes
        ),
        "trace_chain_verified": run_result.trace_chain_verified,
        "peak_strict_concurrent_load_ratio_milli": (
            run_result.peak_strict_concurrent_load_ratio_milli
        ),
        "strict_unserviceable_windows": run_result.strict_unserviceable_windows,
        "peak_uncapped_compatible_load_ratio_milli": (
            run_result.peak_uncapped_compatible_load_ratio_milli
        ),
        "uncapped_unserviceable_windows": run_result.uncapped_unserviceable_windows,
        "peak_registered_normalized_coverable_load_index_milli": (
            run_result.peak_registered_normalized_coverable_load_index_milli
        ),
        "historical_capped_unserviceable_windows": (
            run_result.historical_capped_unserviceable_windows
        ),
        "peak_finite_residual_strict_pressure_ratio_milli": (
            run_result.peak_finite_residual_strict_pressure_ratio_milli
        ),
        "residual_strict_unserviceable_windows": (run_result.residual_strict_unserviceable_windows),
        "reconciliation": run_result.reconciliation_evaluation.model_dump(mode="json"),
        "claims_limit": [
            "reduced_order_teaching_hydrology",
            "synthetic_nonrepresentative_cohort",
            "simulation_grade_geography",
            "no_operational_readiness_or_field_generalization_claim",
        ],
    }


def write_scenario_artifacts(
    scenario: GeneratedScenario,
    run_result: DeltaRunResult,
    policy_path: Path,
    predictor_provenance: PredictorProvenance,
    geography_path: Path,
    output_root: Path,
    package_root: Path,
    *,
    recorded_git_commit: str | None = None,
    validation_report_path: Path | None = None,
) -> ReplayManifest:
    _validate_output_root(output_root, create=True)
    repository_root = package_root.parents[1]
    physical_parameters = physical_parameter_table()
    population_parameters = population_parameter_table(scenario.config.generator_version)
    is_v8 = scenario.config.generator_version == "delta-small-generator-v8"
    is_modern = scenario.config.generator_version in {
        "delta-small-generator-v7",
        "delta-small-generator-v8",
    }
    acceptance_path = (
        repository_root
        / "configs/scenarios"
        / (
            "wf_dfld_01_small_acceptance_v4.yaml"
            if is_v8
            else (
                "wf_dfld_01_small_acceptance_v3.yaml"
                if is_modern
                else "wf_dfld_01_small_acceptance_v2.yaml"
            )
        )
    )
    if is_modern and not acceptance_path.is_file():
        # The implementation freeze intentionally precedes the seed-list
        # preregistration commit. Keep that interim state explicitly runnable.
        acceptance_path = (
            repository_root
            / "docs/delta"
            / ("WF_DFLD_01_SMALL_V8_PROTOCOL.md" if is_v8 else "WF_DFLD_01_SMALL_V7_PROTOCOL.md")
        )
    validation_path = validation_report_path
    if validation_path is None and not is_modern:
        legacy_validation = (
            repository_root / "docs/delta/validation/WF_DFLD_01_SMALL_VALIDATION_V2.json"
        )
        validation_path = legacy_validation if legacy_validation.is_file() else None
    if validation_path is not None:
        validation_path = validation_path.resolve(strict=True)
        validation_report = json.loads(validation_path.read_text("utf-8"))
        validation_summary: dict[str, object] = {
            "schema_version": (
                "delta-small-validation-summary-v4"
                if is_v8
                else (
                    "delta-small-validation-summary-v3"
                    if is_modern
                    else "delta-small-validation-summary-v2"
                )
            ),
            "status": (
                "confirmatory-v7-executed"
                if is_v8
                else ("confirmatory-v6-executed" if is_modern else "confirmatory-v5-executed")
            ),
            "source_report_sha256": sha256_file(validation_path),
            "book_walkthrough": validation_report["book_walkthrough"],
            "studies": [
                {
                    "study_id": study["study_id"],
                    "seed_count": study["seed_count"],
                    "call_count": study["call_count"],
                    **(
                        {
                            "peak_strict_concurrent_load_ratio": study[
                                "peak_strict_concurrent_load_ratio"
                            ],
                            "peak_uncapped_compatible_load_ratio": study[
                                "peak_uncapped_compatible_load_ratio"
                            ],
                            "peak_registered_normalized_coverable_load_index": study[
                                "peak_registered_normalized_coverable_load_index"
                            ],
                            "peak_finite_residual_strict_pressure_ratio": study[
                                "peak_finite_residual_strict_pressure_ratio"
                            ],
                            "reconciliation": study["reconciliation"],
                        }
                        if is_modern
                        else {
                            "peak_gross_load_ratio": study["peak_gross_load_ratio"],
                            "peak_finite_residual_pressure_ratio": study[
                                "peak_finite_residual_pressure_ratio"
                            ],
                        }
                    ),
                    "observation_channel": study["observation_channel"],
                    "operations": study["operations"],
                    "registered_gate_evaluation": study["registered_gate_evaluation"],
                }
                for study in validation_report["studies"]
            ],
        }
    else:
        validation_summary = {
            "schema_version": (
                "delta-small-validation-summary-v4"
                if is_v8
                else (
                    "delta-small-validation-summary-v3"
                    if is_modern
                    else "delta-small-validation-summary-v2"
                )
            ),
            "status": (
                "confirmatory-v7-not-yet-derived"
                if is_v8
                else (
                    "confirmatory-v6-preregistered-not-yet-executed"
                    if is_modern
                    else "confirmatory-v5-preregistered-not-yet-executed"
                )
            ),
            "acceptance_protocol_sha256": sha256_file(acceptance_path),
            "studies": [],
        }
    resource_source = (
        repository_root / "data/scenario/delta/resources/rio_vista_fire_source_extract_v1.json"
    )
    resource_provenance = json.loads(resource_source.read_text("utf-8"))
    truth_payload = scenario.truth.model_dump(mode="json")
    candidate_audit_payload = truth_payload.pop("candidate_audit", None)
    artifacts = [
        _write_artifact(
            output_root,
            "configuration",
            "configuration.json",
            scenario.config.model_dump(mode="json"),
            False,
        ),
        _write_artifact(
            output_root,
            "geography",
            "geography.json",
            scenario.geography.model_dump(mode="json"),
            False,
        ),
        _write_artifact(
            output_root,
            "physical_parameters",
            "physical_parameters.json",
            physical_parameters,
            False,
        ),
        _write_artifact(
            output_root,
            "population_parameters",
            "population_parameters.json",
            population_parameters,
            False,
        ),
        _write_artifact(
            output_root,
            "meteorology",
            "meteorology.json",
            [item.model_dump(mode="json") for item in scenario.weather],
            False,
        ),
        _write_artifact(
            output_root,
            "hydrology",
            "hydrology.json",
            [item.model_dump(mode="json") for item in scenario.gauges],
            False,
        ),
        _write_artifact(
            output_root,
            "crossing_states",
            "crossing_states.json",
            [item.model_dump(mode="json") for item in scenario.crossing_states],
            False,
        ),
        _write_artifact(
            output_root,
            "ground_truth",
            "ground_truth.json",
            truth_payload,
            True,
        ),
        _write_artifact(
            output_root,
            "calls",
            "calls.json",
            [item.model_dump(mode="json") for item in scenario.observations.calls],
            False,
        ),
        _write_artifact(
            output_root,
            "call_lineage",
            "call_lineage.json",
            [item.model_dump(mode="json") for item in scenario.observations.lineage],
            True,
        ),
        _write_artifact(
            output_root,
            "resources",
            "resources.json",
            scenario.resources.model_dump(mode="json"),
            False,
        ),
        _write_artifact(
            output_root,
            "resource_provenance",
            "resource_provenance.json",
            resource_provenance,
            False,
        ),
        _write_artifact(
            output_root,
            "predictor_prior",
            "predictor_prior.json",
            scenario.prior_profile.model_dump(mode="json"),
            False,
        ),
        _write_artifact(
            output_root,
            "controller_decisions",
            "controller_decisions.json",
            [item.model_dump(mode="json") for item in run_result.decisions],
            False,
        ),
        _write_artifact(
            output_root,
            "evidence_ledger",
            "evidence_ledger.json",
            [item.model_dump(mode="json") for item in run_result.evidence],
            False,
        ),
        _write_artifact(
            output_root,
            "predictor_requests",
            "predictor_requests.json",
            [item.model_dump(mode="json") for item in run_result.predictor_requests],
            False,
        ),
        _write_artifact(
            output_root,
            "trace_records",
            "trace_records.json",
            [item.model_dump(mode="json") for item in run_result.trace_records],
            False,
        ),
        _write_artifact(
            output_root,
            "commitments",
            "commitments.json",
            [item.model_dump(mode="json") for item in run_result.commitments],
            False,
        ),
        _write_artifact(
            output_root,
            "outcomes",
            "outcomes.json",
            [item.model_dump(mode="json") for item in run_result.outcomes],
            False,
        ),
        _write_artifact(
            output_root,
            "demand_capacity",
            "demand_capacity.json",
            [item.model_dump(mode="json") for item in run_result.demand_windows],
            False,
        ),
        _write_artifact(
            output_root,
            "reconciliation_evaluation",
            "reconciliation_evaluation.json",
            run_result.reconciliation_evaluation.model_dump(mode="json"),
            False,
        ),
        _write_artifact(
            output_root,
            "result_summary",
            "result_summary.json",
            _summary(scenario, run_result),
            False,
        ),
        _write_artifact(
            output_root,
            "validation_summary",
            "validation_summary.json",
            validation_summary,
            False,
        ),
    ]
    if candidate_audit_payload is not None:
        ground_truth_index = next(
            index for index, item in enumerate(artifacts) if item.name == "ground_truth"
        )
        artifacts.insert(
            ground_truth_index + 1,
            _write_artifact(
                output_root,
                "incident_candidate_audit",
                "incident_candidate_audit.json",
                candidate_audit_payload,
                True,
            ),
        )
    if scenario.coordination is not None:
        lineage_index = next(
            index for index, item in enumerate(artifacts) if item.name == "call_lineage"
        )
        artifacts.insert(
            lineage_index + 1,
            _write_artifact(
                output_root,
                "coordination",
                "coordination.json",
                scenario.coordination.model_dump(mode="json"),
                False,
            ),
        )
    if run_result.reconciliation_artifact is not None:
        decisions_index = next(
            index for index, item in enumerate(artifacts) if item.name == "controller_decisions"
        )
        artifacts.insert(
            decisions_index + 1,
            _write_artifact(
                output_root,
                "controller_reconciliation",
                "controller_reconciliation.json",
                run_result.reconciliation_artifact.model_dump(mode="json"),
                False,
            ),
        )
    geography_manifest = geography_path.parent / (
        "build_manifest_v3.json"
        if scenario.config.generator_version
        in {"delta-small-generator-v7", "delta-small-generator-v8"}
        else "build_manifest_v2.json"
    )
    environment_contract = (
        repository_root / "data/scenario/delta/environment/python311_linux_amd64_v1.json"
        if is_modern
        else repository_root / "pyproject.toml"
    )
    dependency_lock = (
        repository_root / "requirements-delta-python311.lock"
        if is_modern
        else repository_root / "requirements-delta-ci.lock"
    )
    inputs = [
        ProvenanceInput(
            name="scenario_configuration",
            identifier=scenario.source_path.name,
            sha256=sha256_file(scenario.source_path),
        ),
        ProvenanceInput(
            name="geography_catalog",
            identifier=geography_path.name,
            sha256=sha256_file(geography_path),
        ),
        ProvenanceInput(
            name="geography_build_manifest",
            identifier=geography_manifest.name,
            sha256=sha256_file(geography_manifest),
        ),
        ProvenanceInput(
            name="physical_parameter_table",
            identifier=str(physical_parameters["schema_version"]),
            sha256=sha256_bytes(canonical_json_bytes(physical_parameters)),
        ),
        ProvenanceInput(
            name="truth_observation_resource_parameters",
            identifier=str(population_parameters["schema_version"]),
            sha256=sha256_bytes(canonical_json_bytes(population_parameters)),
        ),
        ProvenanceInput(
            name="predictor_prior",
            identifier=scenario.prior_profile.profile_id,
            sha256=sha256_bytes(
                canonical_json_bytes(scenario.prior_profile.model_dump(mode="json"))
            ),
        ),
        ProvenanceInput(
            name="policy", identifier=policy_path.name, sha256=sha256_file(policy_path)
        ),
        ProvenanceInput(
            name="predictor_model",
            identifier=predictor_provenance.predictor_version,
            sha256=predictor_provenance.model_hash,
        ),
        ProvenanceInput(
            name="predictor_calibration",
            identifier=predictor_provenance.calibration_version,
            sha256=predictor_provenance.calibration_hash,
        ),
        ProvenanceInput(
            name="environment_contract",
            identifier=environment_contract.name,
            sha256=sha256_file(environment_contract),
        ),
        ProvenanceInput(
            name="dependency_lock",
            identifier=dependency_lock.name,
            sha256=sha256_file(dependency_lock),
        ),
        ProvenanceInput(
            name="registered_acceptance_protocol",
            identifier=acceptance_path.name,
            sha256=sha256_file(acceptance_path),
        ),
        ProvenanceInput(
            name="automatic_aid_source_extract",
            identifier=resource_source.name,
            sha256=sha256_file(resource_source),
        ),
    ]
    if validation_path is not None:
        inputs.append(
            ProvenanceInput(
                name="registered_validation_report",
                identifier=validation_path.name,
                sha256=sha256_file(validation_path),
            )
        )
    if is_modern:
        calibration_record = (
            repository_root
            / "data/scenario/delta/calibration"
            / ("v8_process_coefficients_v1.json" if is_v8 else "v7_process_coefficients_v1.json")
        )
        inputs.append(
            ProvenanceInput(
                name="v8_process_calibration" if is_v8 else "v7_process_calibration",
                identifier=calibration_record.name,
                sha256=sha256_file(calibration_record),
            )
        )
    if predictor_provenance.encoder_checkpoint_hash is not None:
        inputs.append(
            ProvenanceInput(
                name="predictor_encoder",
                identifier=predictor_provenance.encoder_version or "unspecified",
                sha256=predictor_provenance.encoder_checkpoint_hash,
            )
        )
    manifest = ReplayManifest(
        schema_version=(
            "delta-replay-manifest-v5"
            if is_v8
            else ("delta-replay-manifest-v4" if is_modern else "delta-replay-manifest-v3")
        ),
        scenario_id=scenario.config.scenario_id,
        generator_version=scenario.config.generator_version,
        git_commit=(recorded_git_commit or _git_commit(repository_root)) if not is_modern else None,
        source_tree_sha256=source_tree_sha256(package_root),
        python_implementation=None if is_modern else platform.python_implementation(),
        python_version=(
            None if is_modern else f"{sys.version_info.major}.{sys.version_info.minor}"
        ),
        generation_order=scenario.generation_order,
        stage_seeds=[
            StageSeedRecord(stage_name=name, seed_sha256=seed_hash)
            for name, seed_hash in zip(scenario.generation_order, scenario.stage_seeds, strict=True)
        ],
        inputs=inputs,
        artifacts=artifacts,
    )
    _safe_artifact_path(output_root, "manifest.json").write_bytes(
        canonical_json_bytes(manifest.model_dump(mode="json", exclude_none=is_modern))
    )
    return manifest


def verify_scenario_artifacts(output_root: Path) -> ReplayManifest:
    _validate_output_root(output_root, create=False)
    manifest_path = _safe_artifact_path(output_root, "manifest.json")
    try:
        manifest = ReplayManifest.model_validate_json(manifest_path.read_text("utf-8"))
    except (OSError, ValueError) as exc:
        raise ArtifactMismatchError(f"invalid replay manifest: {manifest_path}") from exc
    names: set[str] = set()
    for descriptor in manifest.artifacts:
        if descriptor.file_name in names:
            raise ArtifactMismatchError(f"duplicate artifact file name: {descriptor.file_name}")
        names.add(descriptor.file_name)
        path = _safe_artifact_path(output_root, descriptor.file_name)
        if not path.is_file() or path.is_symlink():
            raise ArtifactMismatchError(f"missing safe generated artifact: {path}")
        payload = path.read_bytes()
        if len(payload) != descriptor.byte_length:
            raise ArtifactMismatchError(f"artifact length mismatch: {path}")
        if sha256_bytes(payload) != descriptor.sha256:
            raise ArtifactMismatchError(f"artifact digest mismatch: {path}")
    return manifest
