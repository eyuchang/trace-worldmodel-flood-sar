"""Separate provenance inventory for recovery orchestration and governance."""

from __future__ import annotations

import hashlib
from pathlib import Path

from trace_jepa.support import (
    ArtifactLocator,
    atomic_write_bytes,
    canonical_json_bytes,
    safe_directory,
    sha256_file,
)
from trace_reference.provenance import (
    ReferenceScientificInputManifest,
    verify_reference_scientific_input_manifest,
)
from trace_reference.validation.registration import verify_reference_validation_freeze
from trace_reference.validation.registration_models import ReferenceValidationBinding

from .models import RecoveryGovernanceManifest, RecoveryManifestMember

RECOVERY_MANIFEST_PATH = Path(
    "data/scenario/delta/reference_recovery/recovery_governance_manifest_v1.json"
)
BASE_SCIENTIFIC_MANIFEST_PATH = Path(
    "data/scenario/delta/reference_protocol/reference_scientific_input_manifest_v2.json"
)
BASE_FREEZE_PATH = Path(
    "data/scenario/delta/reference_protocol/reference_base_validation_freeze_v2.json"
)
RECOVERY_MEMBER_PATHS = (
    ".github/workflows/reference-base-validation-v2-recovery.yml",
    ".github/workflows/reference-validation-recovery-governance.yml",
    "data/scenario/delta/reference_recovery/failed_original_authorization_v1.json",
    "data/scenario/delta/reference_recovery/recovery_protocol_v1.json",
    "docs/delta/reference/recovery/REFERENCE_VALIDATION_V2_RECOVERY_ADR_V1.md",
    "docs/delta/reference/recovery/REFERENCE_VALIDATION_V2_RECOVERY_AMENDMENT_V1.md",
    "recovery_tests/reference/test_recovery_governance.py",
    "recovery_tests/reference/test_recovery_workflow.py",
    "scripts/reference/run_base_validation_recovery_v1.py",
    "src/trace_reference_recovery/__init__.py",
    "src/trace_reference_recovery/execution.py",
    "src/trace_reference_recovery/manifest.py",
    "src/trace_reference_recovery/models.py",
    "src/trace_reference_recovery/registration.py",
)
_MAX_MEMBER_BYTES = 16 * 1024 * 1024


def _binding(repository_root: Path, relative_path: Path) -> ReferenceValidationBinding:
    path = ArtifactLocator(
        root=repository_root,
        relative_name=relative_path,
        maximum_bytes=_MAX_MEMBER_BYTES,
        label=f"recovery binding {relative_path}",
    ).resolve()
    return ReferenceValidationBinding(
        repository_relative_path=relative_path.as_posix(),
        sha256=sha256_file(path),
    )


def _load_base_manifest(repository_root: Path) -> ReferenceScientificInputManifest:
    path = ArtifactLocator(
        root=repository_root,
        relative_name=BASE_SCIENTIFIC_MANIFEST_PATH,
        maximum_bytes=_MAX_MEMBER_BYTES,
        label="frozen base scientific manifest",
    ).resolve()
    return ReferenceScientificInputManifest.model_validate_json(path.read_text("utf-8"))


def build_recovery_governance_manifest(repository_root: Path) -> RecoveryGovernanceManifest:
    """Bind recovery files while proving all frozen scientific members remain exact."""

    root = safe_directory(
        repository_root,
        declared_root=repository_root,
        label="recovery repository root",
    )
    base_manifest = _load_base_manifest(root)
    verify_reference_scientific_input_manifest(root, base_manifest)
    base_freeze = verify_reference_validation_freeze(root)
    members = []
    for relative_name in RECOVERY_MEMBER_PATHS:
        path = ArtifactLocator(
            root=root,
            relative_name=Path(relative_name),
            maximum_bytes=_MAX_MEMBER_BYTES,
            label=f"recovery governance member {relative_name}",
        ).resolve()
        members.append(
            RecoveryManifestMember(
                repository_relative_path=relative_name,
                byte_length=path.stat().st_size,
                sha256=sha256_file(path),
            )
        )
    body = {
        "schema_version": "delta-reference-validation-recovery-governance-manifest-v1",
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "scientific_source_commit": "2cb58539425af467ac068ba7ef7500891e2fbe78",
        "base_scientific_manifest": _binding(root, BASE_SCIENTIFIC_MANIFEST_PATH).model_dump(
            mode="json"
        ),
        "base_scientific_manifest_aggregate_sha256": base_manifest.aggregate_sha256,
        "base_scientific_member_count": len(base_manifest.members),
        "base_freeze": _binding(root, BASE_FREEZE_PATH).model_dump(mode="json"),
        "base_freeze_digest": base_freeze.freeze_digest,
        "base_scientific_members_unchanged": True,
        "protected_seed_values": [],
        "recovery_members": [item.model_dump(mode="json") for item in members],
    }
    return RecoveryGovernanceManifest(
        **body,
        recovery_aggregate_sha256=hashlib.sha256(canonical_json_bytes(body)).hexdigest(),
    )


def write_recovery_governance_manifest(
    repository_root: Path,
    output_path: Path,
) -> RecoveryGovernanceManifest:
    """Write the deterministic, non-self-referential recovery inventory."""

    manifest = build_recovery_governance_manifest(repository_root)
    output_root = safe_directory(
        output_path.parent,
        declared_root=output_path.parent,
        label="recovery governance manifest output root",
    )
    atomic_write_bytes(
        output_path,
        canonical_json_bytes(manifest.model_dump(mode="json")),
        root=output_root,
        label="recovery governance manifest",
    )
    return manifest


def verify_recovery_governance_manifest(
    repository_root: Path,
) -> RecoveryGovernanceManifest:
    """Reject recovery substitution without modifying the immutable base freeze."""

    path = ArtifactLocator(
        root=repository_root,
        relative_name=RECOVERY_MANIFEST_PATH,
        maximum_bytes=_MAX_MEMBER_BYTES,
        label="committed recovery governance manifest",
    ).resolve()
    expected = RecoveryGovernanceManifest.model_validate_json(path.read_text("utf-8"))
    actual = build_recovery_governance_manifest(repository_root)
    if actual != expected:
        raise ValueError("recovery governance manifest is not current")
    return expected
