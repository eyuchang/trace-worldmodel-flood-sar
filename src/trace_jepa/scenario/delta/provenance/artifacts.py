from __future__ import annotations

import hashlib
import json
import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import Field

from trace_jepa.predictor.protocol import PredictorProvenance
from trace_jepa.scenario.delta.domain import DeltaModel, GeneratedScenario
from trace_jepa.scenario.delta.generation.parameters import population_parameter_table
from trace_jepa.scenario.delta.generation.physical import physical_parameter_table
from trace_jepa.support import atomic_write_bytes, canonical_json_bytes, sha256_file

__all__ = [
    "ArtifactMismatchError",
    "ArtifactWriteRequest",
    "ReplayManifest",
    "ReplayManifestBuilder",
    "canonical_json_bytes",
    "sha256_bytes",
    "sha256_file",
    "verify_scenario_artifacts",
    "write_scenario_artifacts",
]

if TYPE_CHECKING:
    from trace_jepa.scenario.delta.runtime.models import DeltaRunResult


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


@dataclass(frozen=True)
class ArtifactWriteRequest:
    """All scientific and execution inputs to one artifact-bundle write."""

    scenario: GeneratedScenario
    run_result: DeltaRunResult
    policy_path: Path
    predictor_provenance: PredictorProvenance
    geography_path: Path
    output_root: Path
    package_root: Path
    recorded_git_commit: str | None = None
    validation_report_path: Path | None = None


@dataclass(frozen=True)
class ArtifactSpec:
    """Declarative name, file, payload, and visibility for one artifact."""

    name: str
    file_name: str
    value: object
    contains_hidden_truth: bool = False


class ArtifactWriter:
    """Write canonical artifacts beneath one validated output root."""

    def __init__(self, output_root: Path) -> None:
        self.output_root = _validate_output_root(output_root, create=True)

    def write(self, spec: ArtifactSpec) -> ArtifactDescriptor:
        payload = canonical_json_bytes(spec.value)
        path = _safe_artifact_path(self.output_root, spec.file_name)
        atomic_write_bytes(path, payload, root=self.output_root, label=spec.name)
        return ArtifactDescriptor(
            name=spec.name,
            file_name=spec.file_name,
            sha256=sha256_bytes(payload),
            byte_length=len(payload),
            contains_hidden_truth=spec.contains_hidden_truth,
        )

    def write_all(self, specs: list[ArtifactSpec]) -> list[ArtifactDescriptor]:
        return [self.write(spec) for spec in specs]


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


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
            "delta-small-machine-result-summary-v5"
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
        "peak_finite_strict_concurrent_load_ratio_milli": (
            run_result.peak_finite_strict_concurrent_load_ratio_milli
        ),
        "strict_unserviceable_windows": run_result.strict_unserviceable_windows,
        "peak_finite_uncapped_compatible_load_ratio_milli": (
            run_result.peak_finite_uncapped_compatible_load_ratio_milli
        ),
        "uncapped_unserviceable_windows": run_result.uncapped_unserviceable_windows,
        "peak_finite_registered_normalized_coverable_load_index_milli": (
            run_result.peak_finite_registered_normalized_coverable_load_index_milli
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


@dataclass(frozen=True)
class ValidationSummary:
    payload: dict[str, object]
    acceptance_path: Path
    validation_path: Path | None


class ValidationSummaryBuilder:
    """Build the compact replay-bound view of a validation report."""

    def __init__(self, request: ArtifactWriteRequest) -> None:
        self.request = request
        self.repository_root = request.package_root.parents[1]
        version = request.scenario.config.generator_version
        self.is_v8 = version == "delta-small-generator-v8"
        self.is_modern = version in {
            "delta-small-generator-v7",
            "delta-small-generator-v8",
        }

    def _schema(self) -> str:
        if self.is_v8:
            return "delta-small-validation-summary-v5"
        return (
            "delta-small-validation-summary-v3"
            if self.is_modern
            else "delta-small-validation-summary-v2"
        )

    def _acceptance_path(self) -> Path:
        name = (
            "wf_dfld_01_small_acceptance_v5.yaml"
            if self.is_v8
            else (
                "wf_dfld_01_small_acceptance_v3.yaml"
                if self.is_modern
                else "wf_dfld_01_small_acceptance_v2.yaml"
            )
        )
        path = self.repository_root / "configs/scenarios" / name
        if self.is_modern and not path.is_file():
            protocol = (
                "WF_DFLD_01_SMALL_V8_PROTOCOL.md"
                if self.is_v8
                else "WF_DFLD_01_SMALL_V7_PROTOCOL.md"
            )
            return self.repository_root / "docs/delta" / protocol
        return path

    def _validation_path(self) -> Path | None:
        if self.request.validation_report_path is not None:
            return self.request.validation_report_path.resolve(strict=True)
        if self.is_modern:
            return None
        legacy = self.repository_root / "docs/delta/validation/WF_DFLD_01_SMALL_VALIDATION_V2.json"
        return legacy if legacy.is_file() else None

    def _study(self, study: dict[str, object]) -> dict[str, object]:
        common = {
            "study_id": study["study_id"],
            "seed_count": study["seed_count"],
            "call_count": study["call_count"],
            "observation_channel": study["observation_channel"],
            "operations": study["operations"],
            "registered_gate_evaluation": study["registered_gate_evaluation"],
        }
        metrics = (
            {
                name: study[name]
                for name in (
                    "peak_finite_strict_concurrent_load_ratio",
                    "peak_finite_uncapped_compatible_load_ratio",
                    "peak_finite_registered_normalized_coverable_load_index",
                    "peak_finite_residual_strict_pressure_ratio",
                    "reconciliation",
                )
            }
            if self.is_modern
            else {
                "peak_gross_load_ratio": study["peak_gross_load_ratio"],
                "peak_finite_residual_pressure_ratio": study["peak_finite_residual_pressure_ratio"],
            }
        )
        return {**common, **metrics}

    def build(self) -> ValidationSummary:
        acceptance_path = self._acceptance_path()
        validation_path = self._validation_path()
        if validation_path is not None:
            report = json.loads(validation_path.read_text("utf-8"))
            payload = {
                "schema_version": self._schema(),
                "status": (
                    "confirmatory-v8-original-executed"
                    if self.is_v8
                    else (
                        "confirmatory-v6-executed" if self.is_modern else "confirmatory-v5-executed"
                    )
                ),
                "source_report_sha256": sha256_file(validation_path),
                "book_walkthrough": report["book_walkthrough"],
                "studies": [self._study(study) for study in report["studies"]],
            }
        else:
            status = (
                (
                    "confirmatory-v8-preregistered-not-yet-executed"
                    if acceptance_path.suffix == ".yaml"
                    else "confirmatory-v8-not-yet-derived"
                )
                if self.is_v8
                else (
                    "confirmatory-v6-preregistered-not-yet-executed"
                    if self.is_modern
                    else "confirmatory-v5-preregistered-not-yet-executed"
                )
            )
            payload = {
                "schema_version": self._schema(),
                "status": status,
                "acceptance_protocol_sha256": sha256_file(acceptance_path),
                "studies": [],
            }
        return ValidationSummary(payload, acceptance_path, validation_path)


@dataclass(frozen=True)
class ReplayManifestBuildRequest:
    """Inputs needed after artifacts have been deterministically materialized."""

    write_request: ArtifactWriteRequest
    artifacts: list[ArtifactDescriptor]
    validation: ValidationSummary
    physical_parameters: dict[str, object]
    population_parameters: dict[str, object]


class ReplayManifestBuilder:
    """Bind generated artifacts to every replay-relevant scientific input."""

    def __init__(self, request: ReplayManifestBuildRequest) -> None:
        self.request = request
        self.write = request.write_request
        self.scenario = self.write.scenario
        self.repository_root = self.write.package_root.parents[1]
        version = self.scenario.config.generator_version
        self.is_v8 = version == "delta-small-generator-v8"
        self.is_modern = version in {
            "delta-small-generator-v7",
            "delta-small-generator-v8",
        }

    def _input_paths(self) -> dict[str, Path]:
        geography_manifest = self.write.geography_path.parent / (
            "build_manifest_v3.json" if self.is_modern else "build_manifest_v2.json"
        )
        environment = (
            self.repository_root / "data/scenario/delta/environment/python311_linux_amd64_v1.json"
            if self.is_modern
            else self.repository_root / "pyproject.toml"
        )
        lock = (
            self.repository_root / "requirements-delta-python311.lock"
            if self.is_modern
            else self.repository_root / "requirements-delta-ci.lock"
        )
        return {
            "geography_manifest": geography_manifest,
            "environment": environment,
            "lock": lock,
            "resource_source": (
                self.repository_root
                / "data/scenario/delta/resources/rio_vista_fire_source_extract_v1.json"
            ),
        }

    def _base_inputs(self, paths: dict[str, Path]) -> list[ProvenanceInput]:
        provenance = self.write.predictor_provenance
        physical = self.request.physical_parameters
        population = self.request.population_parameters
        return [
            ProvenanceInput(
                name="scenario_configuration",
                identifier=self.scenario.source_path.name,
                sha256=sha256_file(self.scenario.source_path),
            ),
            ProvenanceInput(
                name="geography_catalog",
                identifier=self.write.geography_path.name,
                sha256=sha256_file(self.write.geography_path),
            ),
            ProvenanceInput(
                name="geography_build_manifest",
                identifier=paths["geography_manifest"].name,
                sha256=sha256_file(paths["geography_manifest"]),
            ),
            ProvenanceInput(
                name="physical_parameter_table",
                identifier=str(physical["schema_version"]),
                sha256=sha256_bytes(canonical_json_bytes(physical)),
            ),
            ProvenanceInput(
                name="truth_observation_resource_parameters",
                identifier=str(population["schema_version"]),
                sha256=sha256_bytes(canonical_json_bytes(population)),
            ),
            ProvenanceInput(
                name="predictor_prior",
                identifier=self.scenario.prior_profile.profile_id,
                sha256=sha256_bytes(
                    canonical_json_bytes(self.scenario.prior_profile.model_dump(mode="json"))
                ),
            ),
            ProvenanceInput(
                name="policy",
                identifier=self.write.policy_path.name,
                sha256=sha256_file(self.write.policy_path),
            ),
            ProvenanceInput(
                name="predictor_model",
                identifier=provenance.predictor_version,
                sha256=provenance.model_hash,
            ),
            ProvenanceInput(
                name="predictor_calibration",
                identifier=provenance.calibration_version,
                sha256=provenance.calibration_hash,
            ),
            ProvenanceInput(
                name="environment_contract",
                identifier=paths["environment"].name,
                sha256=sha256_file(paths["environment"]),
            ),
            ProvenanceInput(
                name="dependency_lock",
                identifier=paths["lock"].name,
                sha256=sha256_file(paths["lock"]),
            ),
            ProvenanceInput(
                name="registered_acceptance_protocol",
                identifier=self.request.validation.acceptance_path.name,
                sha256=sha256_file(self.request.validation.acceptance_path),
            ),
            ProvenanceInput(
                name="automatic_aid_source_extract",
                identifier=paths["resource_source"].name,
                sha256=sha256_file(paths["resource_source"]),
            ),
        ]

    def _optional_inputs(self) -> list[ProvenanceInput]:
        inputs: list[ProvenanceInput] = []
        validation_path = self.request.validation.validation_path
        if validation_path is not None:
            inputs.append(
                ProvenanceInput(
                    name="registered_validation_report",
                    identifier=validation_path.name,
                    sha256=sha256_file(validation_path),
                )
            )
        if self.is_modern:
            calibration = (
                self.repository_root
                / "data/scenario/delta/calibration"
                / (
                    "v8_process_coefficients_v1.json"
                    if self.is_v8
                    else "v7_process_coefficients_v1.json"
                )
            )
            inputs.append(
                ProvenanceInput(
                    name="v8_process_calibration" if self.is_v8 else "v7_process_calibration",
                    identifier=calibration.name,
                    sha256=sha256_file(calibration),
                )
            )
        provenance = self.write.predictor_provenance
        if provenance.encoder_checkpoint_hash is not None:
            inputs.append(
                ProvenanceInput(
                    name="predictor_encoder",
                    identifier=provenance.encoder_version or "unspecified",
                    sha256=provenance.encoder_checkpoint_hash,
                )
            )
        return inputs

    def build(self) -> ReplayManifest:
        paths = self._input_paths()
        return ReplayManifest(
            schema_version=(
                "delta-replay-manifest-v6"
                if self.is_v8
                else ("delta-replay-manifest-v4" if self.is_modern else "delta-replay-manifest-v3")
            ),
            scenario_id=self.scenario.config.scenario_id,
            generator_version=self.scenario.config.generator_version,
            git_commit=(self.write.recorded_git_commit or _git_commit(self.repository_root))
            if not self.is_modern
            else None,
            source_tree_sha256=source_tree_sha256(self.write.package_root),
            python_implementation=(None if self.is_modern else platform.python_implementation()),
            python_version=(
                None if self.is_modern else f"{sys.version_info.major}.{sys.version_info.minor}"
            ),
            generation_order=self.scenario.generation_order,
            stage_seeds=[
                StageSeedRecord(stage_name=name, seed_sha256=seed_hash)
                for name, seed_hash in zip(
                    self.scenario.generation_order, self.scenario.stage_seeds, strict=True
                )
            ],
            inputs=[*self._base_inputs(paths), *self._optional_inputs()],
            artifacts=self.request.artifacts,
        )


def write_scenario_artifacts(request: ArtifactWriteRequest) -> ReplayManifest:
    scenario = request.scenario
    run_result = request.run_result
    output_root = request.output_root
    package_root = request.package_root
    _validate_output_root(output_root, create=True)
    repository_root = package_root.parents[1]
    physical_parameters = physical_parameter_table()
    population_parameters = population_parameter_table(scenario.config.generator_version)
    is_modern = scenario.config.generator_version in {
        "delta-small-generator-v7",
        "delta-small-generator-v8",
    }
    validation = ValidationSummaryBuilder(request).build()
    validation_summary = validation.payload
    resource_source = (
        repository_root / "data/scenario/delta/resources/rio_vista_fire_source_extract_v1.json"
    )
    resource_provenance = json.loads(resource_source.read_text("utf-8"))
    truth_payload = scenario.truth.model_dump(mode="json")
    candidate_audit_payload = truth_payload.pop("candidate_audit", None)
    specs = [
        ArtifactSpec(
            "configuration", "configuration.json", scenario.config.model_dump(mode="json")
        ),
        ArtifactSpec("geography", "geography.json", scenario.geography.model_dump(mode="json")),
        ArtifactSpec("physical_parameters", "physical_parameters.json", physical_parameters),
        ArtifactSpec("population_parameters", "population_parameters.json", population_parameters),
        ArtifactSpec(
            "meteorology",
            "meteorology.json",
            [item.model_dump(mode="json") for item in scenario.weather],
        ),
        ArtifactSpec(
            "hydrology",
            "hydrology.json",
            [item.model_dump(mode="json") for item in scenario.gauges],
        ),
        ArtifactSpec(
            "crossing_states",
            "crossing_states.json",
            [item.model_dump(mode="json") for item in scenario.crossing_states],
        ),
        ArtifactSpec("ground_truth", "ground_truth.json", truth_payload, True),
    ]
    if candidate_audit_payload is not None:
        specs.append(
            ArtifactSpec(
                "incident_candidate_audit",
                "incident_candidate_audit.json",
                candidate_audit_payload,
                True,
            )
        )
    specs.extend(
        [
            ArtifactSpec(
                "calls",
                "calls.json",
                [item.model_dump(mode="json") for item in scenario.observations.calls],
            ),
            ArtifactSpec(
                "call_lineage",
                "call_lineage.json",
                [item.model_dump(mode="json") for item in scenario.observations.lineage],
                True,
            ),
        ]
    )
    if scenario.coordination is not None:
        specs.append(
            ArtifactSpec(
                "coordination",
                "coordination.json",
                scenario.coordination.model_dump(mode="json"),
            )
        )
    specs.extend(
        [
            ArtifactSpec("resources", "resources.json", scenario.resources.model_dump(mode="json")),
            ArtifactSpec("resource_provenance", "resource_provenance.json", resource_provenance),
            ArtifactSpec(
                "predictor_prior",
                "predictor_prior.json",
                scenario.prior_profile.model_dump(mode="json"),
            ),
            ArtifactSpec(
                "controller_decisions",
                "controller_decisions.json",
                [item.model_dump(mode="json") for item in run_result.decisions],
            ),
        ]
    )
    if run_result.reconciliation_artifact is not None:
        specs.append(
            ArtifactSpec(
                "controller_reconciliation",
                "controller_reconciliation.json",
                run_result.reconciliation_artifact.model_dump(mode="json"),
            )
        )
    specs.extend(
        [
            ArtifactSpec(
                "evidence_ledger",
                "evidence_ledger.json",
                [item.model_dump(mode="json") for item in run_result.evidence],
            ),
            ArtifactSpec(
                "predictor_requests",
                "predictor_requests.json",
                [item.model_dump(mode="json") for item in run_result.predictor_requests],
            ),
            ArtifactSpec(
                "trace_records",
                "trace_records.json",
                [item.model_dump(mode="json") for item in run_result.trace_records],
            ),
            ArtifactSpec(
                "commitments",
                "commitments.json",
                [item.model_dump(mode="json") for item in run_result.commitments],
            ),
            ArtifactSpec(
                "outcomes",
                "outcomes.json",
                [item.model_dump(mode="json") for item in run_result.outcomes],
            ),
            ArtifactSpec(
                "demand_capacity",
                "demand_capacity.json",
                [item.model_dump(mode="json") for item in run_result.demand_windows],
            ),
            ArtifactSpec(
                "reconciliation_evaluation",
                "reconciliation_evaluation.json",
                run_result.reconciliation_evaluation.model_dump(mode="json"),
            ),
            ArtifactSpec("result_summary", "result_summary.json", _summary(scenario, run_result)),
            ArtifactSpec("validation_summary", "validation_summary.json", validation_summary),
        ]
    )
    artifacts = ArtifactWriter(output_root).write_all(specs)
    manifest = ReplayManifestBuilder(
        ReplayManifestBuildRequest(
            write_request=request,
            artifacts=artifacts,
            validation=validation,
            physical_parameters=physical_parameters,
            population_parameters=population_parameters,
        )
    ).build()
    atomic_write_bytes(
        _safe_artifact_path(output_root, "manifest.json"),
        canonical_json_bytes(manifest.model_dump(mode="json", exclude_none=is_modern)),
        root=output_root,
        label="replay manifest",
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
