"""Fail-closed authorization for the distinct validation-v2 recovery."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from trace_jepa.scenario.delta.environment import (
    inspect_reference_environment,
    require_reference_environment,
)
from trace_jepa.support import ArtifactLocator, sha256_file
from trace_reference.validation.registration import (
    load_reference_validation_protocol,
    verify_reference_validation_freeze,
)

from .manifest import verify_recovery_governance_manifest
from .models import (
    FailedOriginalAuthorizationRecord,
    RecoveryExecutionIdentity,
    RecoveryGovernanceManifest,
    RecoveryProtocol,
)

RECOVERY_AUTHORIZATION_TAG = "wf-dfld-01-reference-validation-v2-recovery-v1"
RECOVERY_EXECUTION_ROLE = "original-base-reference-validation-recovery"
RECOVERY_WORKFLOW_FILE = "reference-base-validation-v2-recovery.yml"
FAILED_ORIGINAL_RUN_ID = 31833291955
EXPECTED_SEED_LIST_SHA256 = "2be02697a2379a974d709fda7b7285935227ae58a8ebe51fc38c0c48020ffa87"
FAILURE_RECORD_PATH = Path(
    "data/scenario/delta/reference_recovery/failed_original_authorization_v1.json"
)
RECOVERY_PROTOCOL_PATH = Path("data/scenario/delta/reference_recovery/recovery_protocol_v1.json")
_MAX_JSON_BYTES = 16 * 1024 * 1024


def _resolve(repository_root: Path, relative_path: Path, label: str) -> Path:
    return ArtifactLocator(
        root=repository_root,
        relative_name=relative_path,
        maximum_bytes=_MAX_JSON_BYTES,
        label=label,
    ).resolve()


def load_failed_original_record(repository_root: Path) -> FailedOriginalAuthorizationRecord:
    """Load the immutable pre-evaluation failure evidence."""

    path = _resolve(repository_root, FAILURE_RECORD_PATH, "failed original authorization")
    return FailedOriginalAuthorizationRecord.model_validate_json(path.read_text("utf-8"))


def load_recovery_protocol(repository_root: Path) -> RecoveryProtocol:
    """Load recovery governance without deriving the protected plan."""

    path = _resolve(repository_root, RECOVERY_PROTOCOL_PATH, "recovery protocol")
    return RecoveryProtocol.model_validate_json(path.read_text("utf-8"))


def _verify_protocol_bindings(repository_root: Path, protocol: RecoveryProtocol) -> None:
    for binding in (
        protocol.failure_record,
        protocol.amendment,
        protocol.architecture_decision_record,
        protocol.base_freeze,
        protocol.base_scientific_manifest,
    ):
        path = _resolve(
            repository_root,
            Path(binding.repository_relative_path),
            f"recovery protocol binding {binding.repository_relative_path}",
        )
        if sha256_file(path) != binding.sha256:
            raise ValueError(
                f"recovery protocol binding changed: {binding.repository_relative_path}"
            )


def verify_recovery_protocol(repository_root: Path) -> RecoveryProtocol:
    """Validate the protocol and every exact file binding without seed derivation."""

    protocol = load_recovery_protocol(repository_root)
    _verify_protocol_bindings(repository_root, protocol)
    return protocol


def require_recovery_identity(environment: Mapping[str, str]) -> RecoveryExecutionIdentity:
    """Accept only the separately tagged first recovery attempt."""

    expected = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REF": f"refs/tags/{RECOVERY_AUTHORIZATION_TAG}",
        "GITHUB_REPOSITORY": "eyuchang/trace-worldmodel-flood-sar",
        "GITHUB_RUN_ATTEMPT": "1",
        "TRACE_REFERENCE_ANNOTATED_TAG_GUARD": "verified-annotated-tag-points-to-sha",
        "TRACE_REFERENCE_AUTHORIZATION_TAG": RECOVERY_AUTHORIZATION_TAG,
        "TRACE_REFERENCE_EXECUTION_ROLE": RECOVERY_EXECUTION_ROLE,
        "TRACE_REFERENCE_FAILED_ORIGINAL_GUARD": (
            "verified-run-31833291955-pre-evaluation-failure"
        ),
        "TRACE_REFERENCE_PRIOR_RECOVERY_GUARD": "verified-no-prior-recovery-attempt",
        "TRACE_REFERENCE_WORKFLOW_FILE": RECOVERY_WORKFLOW_FILE,
    }
    mismatches = tuple(
        name for name, expected_value in expected.items() if environment.get(name) != expected_value
    )
    if mismatches:
        raise ValueError("Reference recovery identity is incomplete: " + ", ".join(mismatches))
    sha = environment.get("GITHUB_SHA", "")
    if len(sha) != 40 or any(character not in "0123456789abcdef" for character in sha):
        raise ValueError("Reference recovery source commit is invalid")
    try:
        run_id = int(environment.get("GITHUB_RUN_ID", ""))
    except ValueError as exc:
        raise ValueError("Reference recovery workflow run ID is invalid") from exc
    return RecoveryExecutionIdentity(
        execution_role=RECOVERY_EXECUTION_ROLE,
        source_commit=sha,
        scientific_source_commit="2cb58539425af467ac068ba7ef7500891e2fbe78",
        authorization_tag=RECOVERY_AUTHORIZATION_TAG,
        git_ref=f"refs/tags/{RECOVERY_AUTHORIZATION_TAG}",
        workflow_file=RECOVERY_WORKFLOW_FILE,
        workflow_run_id=run_id,
        workflow_run_attempt=1,
        repository="eyuchang/trace-worldmodel-flood-sar",
        failed_original_run_id=FAILED_ORIGINAL_RUN_ID,
    )


def require_recovery_boundary(
    repository_root: Path,
    environment: Mapping[str, str],
) -> tuple[RecoveryProtocol, RecoveryGovernanceManifest, RecoveryExecutionIdentity]:
    """Verify unchanged base science and every recovery guard before derivation."""

    protocol = verify_recovery_protocol(repository_root)
    failure = load_failed_original_record(repository_root)
    if failure.workflow_run_id != FAILED_ORIGINAL_RUN_ID or failure.mission_execution_started:
        raise ValueError("recovery predecessor is not the registered pre-evaluation failure")
    base_protocol = load_reference_validation_protocol(repository_root)
    base_freeze = verify_reference_validation_freeze(repository_root)
    if base_freeze.freeze_digest != protocol.base_freeze_digest:
        raise ValueError("recovery changed the base scientific freeze")
    manifest = verify_recovery_governance_manifest(repository_root)
    identity = require_recovery_identity(environment)
    contract = _resolve(
        repository_root,
        Path(base_protocol.environment_contract_path),
        "recovery environment contract",
    )
    lock = _resolve(
        repository_root,
        Path(base_protocol.dependency_lock_path),
        "recovery dependency lock",
    )
    require_reference_environment(contract, lock)
    if not inspect_reference_environment(contract, lock).matches:
        raise ValueError("recovery environment identity does not match the frozen environment")
    if sha256_file(contract) != base_freeze.environment_contract.sha256:
        raise ValueError("recovery environment contract differs from the base freeze")
    if sha256_file(lock) != base_freeze.dependency_lock.sha256:
        raise ValueError("recovery dependency lock differs from the base freeze")
    return protocol, manifest, identity
