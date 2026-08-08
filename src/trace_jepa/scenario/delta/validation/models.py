"""Frozen report identities for original and replication evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import Field

from trace_jepa.scenario.delta.domain import DeltaModel
from trace_jepa.scenario.delta.provenance.artifacts import canonical_json_bytes, sha256_file


class OriginalReportIdentity(DeltaModel):
    """Fields that uniquely identify the one authorized original study."""

    schema_version: Literal["delta-statistical-validation-v5"]
    execution_role: Literal["original-confirmatory"]
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    authorization_tag: Literal["wf-dfld-01-small-confirmatory-v8-original"]
    workflow_run_id: str = Field(min_length=1)
    workflow_name: str = Field(min_length=1)
    workflow_file: Literal["delta-confirmatory-v8.yml"]
    protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    scientific_input_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    scientific_input_aggregate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    scientific_input_core_aggregate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    environment_contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dependency_lock_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    scenario_configuration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    geography_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    seed_list: tuple[int, ...] = Field(min_length=100, max_length=100)
    study_ids: tuple[str, ...]
    study_seed_counts: tuple[int, ...]
    baseline_reconciliation_algorithm: str
    selected_reconciliation_algorithm: str

    @classmethod
    def from_report(cls, report: dict[str, object]) -> OriginalReportIdentity:
        studies = report.get("studies")
        paired = report.get("paired_reconciliation")
        if not isinstance(studies, list) or not isinstance(paired, dict):
            raise TypeError("original report omits registered studies or reconciliation")
        return cls(
            **{
                key: report[key]
                for key in (
                    "schema_version",
                    "execution_role",
                    "source_commit",
                    "authorization_tag",
                    "workflow_run_id",
                    "workflow_name",
                    "workflow_file",
                    "protocol_sha256",
                    "scientific_input_manifest_sha256",
                    "scientific_input_aggregate_sha256",
                    "scientific_input_core_aggregate_sha256",
                    "environment_contract_sha256",
                    "dependency_lock_sha256",
                    "scenario_configuration_sha256",
                    "geography_sha256",
                    "policy_sha256",
                    "seed_list",
                )
            },
            study_ids=tuple(str(item["study_id"]) for item in studies),
            study_seed_counts=tuple(int(item["seed_count"]) for item in studies),
            baseline_reconciliation_algorithm=str(paired["baseline_algorithm_id"]),
            selected_reconciliation_algorithm=str(paired["selected_algorithm_id"]),
        )

    @property
    def canonical_sha256(self) -> str:
        import hashlib

        return hashlib.sha256(canonical_json_bytes(self.model_dump(mode="json"))).hexdigest()


class OriginalReportRegistry(DeltaModel):
    schema_version: Literal["delta-original-report-registry-v1"]
    report_path: str
    report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    identity_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def verify_registered_original_report(
    repository_root: Path,
    supplied_report: Path,
    registry_path: Path,
) -> tuple[dict[str, object], OriginalReportIdentity]:
    """Require the supplied original to equal the committed registry byte-for-byte."""

    if not registry_path.is_file() or registry_path.is_symlink():
        raise ValueError("replication is disabled until the original-report registry is committed")
    registry = OriginalReportRegistry.model_validate_json(registry_path.read_text("utf-8"))
    expected = (repository_root / registry.report_path).resolve(strict=True)
    supplied = supplied_report.resolve(strict=True)
    if supplied != expected or supplied.is_symlink() or not supplied.is_file():
        raise ValueError("supplied original report does not match the committed registry path")
    if sha256_file(supplied) != registry.report_sha256:
        raise ValueError("supplied original report does not match the committed registry digest")
    try:
        report = json.loads(supplied.read_text("utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("committed original report is invalid JSON") from exc
    if not isinstance(report, dict):
        raise TypeError("committed original report must be a JSON object")
    identity = OriginalReportIdentity.from_report(report)
    if identity.canonical_sha256 != registry.identity_sha256:
        raise ValueError("original report identity does not match the committed registry")
    return report, identity


class OriginalWorkflowContext(DeltaModel):
    """Immutable GitHub execution identity admitted by the original-study gate."""

    workflow_run_id: str = Field(min_length=1)
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    authorization_tag: Literal["wf-dfld-01-small-confirmatory-v8-original"]
    workflow_name: str = Field(min_length=1)
    workflow_file: Literal["delta-confirmatory-v8.yml"]


class DevelopmentValidationRequest(DeltaModel):
    """All explicit inputs for a safe development-only validation run."""

    config_path: Path
    geography_path: Path
    policy_path: Path
    scientific_manifest_path: Path
    output_path: Path


class RegisteredValidationRequest(DeltaModel):
    """All explicit inputs for an original or registry-bound replication."""

    study: Literal["original-confirmatory", "replication"]
    config_path: Path
    geography_path: Path
    policy_path: Path
    acceptance_path: Path
    scientific_manifest_path: Path
    output_path: Path
    confirmation_token: str | None = None
    original_report_path: Path | None = None


class ReplicationBindingRequest(DeltaModel):
    """Expected immutable identity fields for a registered replication."""

    original_report_path: Path | None
    protocol_hash: str
    manifest_path: Path
    config_path: Path
    geography_path: Path
    policy_path: Path
    confirmatory_seeds: tuple[int, ...]


class StudyBundleRequest(DeltaModel):
    """Inputs shared by development and confirmatory study execution."""

    development_first_seed: int
    development_seed_count: int
    confirmatory_seeds: tuple[int, ...]
    config_path: Path
    geography_path: Path
    policy_path: Path
    protocol_hash: str
