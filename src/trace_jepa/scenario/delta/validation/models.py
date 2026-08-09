"""Frozen report identities for original and replication evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from trace_jepa.scenario.delta.domain import DeltaModel
from trace_jepa.scenario.delta.provenance.artifacts import canonical_json_bytes, sha256_file
from trace_jepa.support import ArtifactLocator

_EXPECTED_REGISTERED_IDENTITIES: dict[
    str,
    tuple[str, str, str | None, str | None],
] = {
    "original-confirmatory": (
        "wf-dfld-01-small-confirmatory-v8-original-r2",
        "delta-confirmatory-v8.yml",
        None,
        None,
    ),
    "recovery-replication": (
        "wf-dfld-01-small-confirmatory-v8-recovery-replication-v1",
        "delta-confirmatory-v8.yml",
        "31286349320",
        None,
    ),
    "artifact-reconstruction-replication": (
        "wf-dfld-01-small-confirmatory-v8-artifact-reconstruction-replication-v1",
        "delta-artifact-reconstruction-v8.yml",
        "31286349320",
        "31289293944",
    ),
}


class RegisteredEvidenceIdentity(DeltaModel):
    """Fields that identify retained registered evidence without upgrading its role."""

    schema_version: Literal["delta-statistical-validation-v5", "delta-statistical-validation-v6"]
    execution_role: Literal[
        "original-confirmatory",
        "recovery-replication",
        "artifact-reconstruction-replication",
    ]
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    authorization_tag: Literal[
        "wf-dfld-01-small-confirmatory-v8-original-r2",
        "wf-dfld-01-small-confirmatory-v8-recovery-replication-v1",
        "wf-dfld-01-small-confirmatory-v8-artifact-reconstruction-replication-v1",
    ]
    failed_original_workflow_run_id: str | None = None
    failed_recovery_workflow_run_id: str | None = None
    workflow_run_id: str = Field(min_length=1)
    workflow_name: str = Field(min_length=1)
    workflow_file: Literal[
        "delta-confirmatory-v8.yml",
        "delta-artifact-reconstruction-v8.yml",
    ]
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

    @model_validator(mode="after")
    def validate_execution_identity(self) -> RegisteredEvidenceIdentity:
        expected = _EXPECTED_REGISTERED_IDENTITIES[self.execution_role]
        checks = (
            (self.authorization_tag, expected[0], "authorization tag"),
            (self.workflow_file, expected[1], "workflow file"),
            (self.failed_original_workflow_run_id, expected[2], "failed original run"),
            (self.failed_recovery_workflow_run_id, expected[3], "failed recovery run"),
        )
        for actual, registered, label in checks:
            if actual != registered:
                raise ValueError(f"registered evidence names the wrong {label}")
        return self

    @classmethod
    def from_report(cls, report: dict[str, object]) -> RegisteredEvidenceIdentity:
        studies = report.get("studies")
        paired = report.get("paired_reconciliation")
        if not isinstance(studies, list) or not isinstance(paired, dict):
            raise TypeError("registered evidence report omits registered studies or reconciliation")
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
            failed_original_workflow_run_id=report.get("failed_original_workflow_run_id"),
            failed_recovery_workflow_run_id=report.get("failed_recovery_workflow_run_id"),
            study_ids=tuple(str(item["study_id"]) for item in studies),
            study_seed_counts=tuple(int(item["seed_count"]) for item in studies),
            baseline_reconciliation_algorithm=str(paired["baseline_algorithm_id"]),
            selected_reconciliation_algorithm=str(paired["selected_algorithm_id"]),
        )

    @property
    def canonical_sha256(self) -> str:
        import hashlib

        return hashlib.sha256(canonical_json_bytes(self.model_dump(mode="json"))).hexdigest()


class RegisteredEvidenceRegistry(DeltaModel):
    """Byte-level registry for evidence admitted as a replication reference."""

    schema_version: Literal["delta-registered-evidence-registry-v1"]
    report_path: str
    report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    identity_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def verify_registered_evidence_report(
    repository_root: Path,
    supplied_report: Path,
    registry_path: Path,
) -> tuple[dict[str, object], RegisteredEvidenceIdentity]:
    """Require supplied registered evidence to equal the committed registry."""

    try:
        safe_registry = ArtifactLocator.from_path(
            root=repository_root,
            path=registry_path,
            maximum_bytes=1_000_000,
            label="registered-evidence registry",
        ).resolve()
    except ValueError as exc:
        raise ValueError(
            "replication is disabled until the registered-evidence registry is committed"
        ) from exc
    registry = RegisteredEvidenceRegistry.model_validate_json(safe_registry.read_text("utf-8"))
    expected = ArtifactLocator(
        root=repository_root,
        relative_name=Path(registry.report_path),
        maximum_bytes=100_000_000,
        label="registered evidence report",
    ).resolve()
    supplied = ArtifactLocator.from_path(
        root=repository_root,
        path=supplied_report,
        maximum_bytes=100_000_000,
        label="supplied evidence report",
    ).resolve()
    if supplied != expected:
        raise ValueError("supplied evidence report does not match the committed registry path")
    if sha256_file(supplied) != registry.report_sha256:
        raise ValueError("supplied evidence report does not match the committed registry digest")
    try:
        report = json.loads(supplied.read_text("utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("committed evidence report is invalid JSON") from exc
    if not isinstance(report, dict):
        raise TypeError("committed evidence report must be a JSON object")
    identity = RegisteredEvidenceIdentity.from_report(report)
    if identity.canonical_sha256 != registry.identity_sha256:
        raise ValueError("evidence report identity does not match the committed registry")
    return report, identity


# One-release compatibility aliases for prerecovery callers. New code and
# documentation use the scientifically neutral registered-evidence names.
OriginalReportIdentity = RegisteredEvidenceIdentity
OriginalReportRegistry = RegisteredEvidenceRegistry
verify_registered_original_report = verify_registered_evidence_report


class OriginalWorkflowContext(DeltaModel):
    """Immutable GitHub execution identity admitted by the original-study gate."""

    workflow_run_id: str = Field(min_length=1)
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    authorization_tag: Literal["wf-dfld-01-small-confirmatory-v8-original-r2"]
    workflow_name: str = Field(min_length=1)
    workflow_file: Literal["delta-confirmatory-v8.yml"]


class RecoveryWorkflowContext(DeltaModel):
    """Immutable GitHub identity admitted by the recovery-replication gate."""

    workflow_run_id: str = Field(min_length=1)
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    authorization_tag: Literal["wf-dfld-01-small-confirmatory-v8-recovery-replication-v1"]
    workflow_name: str = Field(min_length=1)
    workflow_file: Literal["delta-confirmatory-v8.yml"]
    failed_original_workflow_run_id: Literal["31286349320"]


class ReconstructionWorkflowContext(DeltaModel):
    """Immutable GitHub identity admitted by the artifact-reconstruction gate."""

    workflow_run_id: str = Field(min_length=1)
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    authorization_tag: Literal[
        "wf-dfld-01-small-confirmatory-v8-artifact-reconstruction-replication-v1"
    ]
    workflow_name: str = Field(min_length=1)
    workflow_file: Literal["delta-artifact-reconstruction-v8.yml"]
    failed_original_workflow_run_id: Literal["31286349320"]
    failed_recovery_workflow_run_id: Literal["31289293944"]


class DevelopmentValidationRequest(DeltaModel):
    """All explicit inputs for a safe development-only validation run."""

    config_path: Path
    geography_path: Path
    policy_path: Path
    scientific_manifest_path: Path
    output_path: Path


class RegisteredValidationRequest(DeltaModel):
    """All explicit inputs for a remote registered run or registry-bound replication."""

    study: Literal[
        "original-confirmatory",
        "recovery-replication",
        "artifact-reconstruction-replication",
        "replication",
    ]
    config_path: Path
    geography_path: Path
    policy_path: Path
    acceptance_path: Path
    scientific_manifest_path: Path
    output_path: Path
    confirmation_token: str | None = None
    registered_evidence_report_path: Path | None = None


class ReplicationBindingRequest(DeltaModel):
    """Expected immutable identity fields for a registered replication."""

    registered_evidence_report_path: Path | None
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
