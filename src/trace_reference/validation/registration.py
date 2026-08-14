"""Fail-closed loading and authorization for Reference validation-v2."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

from trace_jepa.scenario.delta.environment import (
    inspect_reference_environment,
    require_reference_environment,
)
from trace_jepa.support import ArtifactLocator, canonical_json_bytes, sha256_file
from trace_reference.provenance.scientific_inputs import (
    ReferenceScientificInputManifest,
    build_reference_scientific_input_manifest,
)

from .registration_models import (
    ReferenceBaseValidationFreeze,
    ReferenceBaseValidationProtocol,
    ReferenceOriginalExecutionIdentity,
    ReferenceValidationBinding,
)

REFERENCE_VALIDATION_PROTOCOL = Path(
    "data/scenario/delta/reference_protocol/reference_base_validation_protocol_v2.json"
)
REFERENCE_VALIDATION_FREEZE = Path(
    "data/scenario/delta/reference_protocol/reference_base_validation_freeze_v2.json"
)
REFERENCE_SCIENTIFIC_MANIFEST = Path(
    "data/scenario/delta/reference_protocol/reference_scientific_input_manifest_v2.json"
)
REFERENCE_VALIDATION_WORKFLOW = Path(".github/workflows/reference-base-validation-v2-original.yml")
REFERENCE_G3_HANDOFF = Path("data/scenario/delta/reference/g3_handoff_v1/g3_handoff_manifest.json")
REFERENCE_PHASE6_ACCEPTANCE = Path(
    "data/scenario/delta/reference/phase6_acceptance_v1/phase6_development_acceptance_report.json"
)
REFERENCE_CANONICAL_PHASE6_RECEIPT = Path(
    "data/scenario/delta/reference/phase6_canonical_v1/canonical_execution_receipt.json"
)
REFERENCE_VALIDATION_TAG = "wf-dfld-01-reference-validation-v2-original"
_MAX_JSON_BYTES = 64 * 1024 * 1024


def _resolve(repository_root: Path, relative_path: Path, label: str) -> Path:
    return ArtifactLocator(
        root=repository_root,
        relative_name=relative_path,
        maximum_bytes=_MAX_JSON_BYTES,
        label=label,
    ).resolve()


def _binding(
    repository_root: Path,
    relative_path: Path,
    *,
    label: str,
) -> ReferenceValidationBinding:
    path = _resolve(repository_root, relative_path, label)
    return ReferenceValidationBinding(
        repository_relative_path=relative_path.as_posix(),
        sha256=sha256_file(path),
    )


def load_reference_validation_protocol(
    repository_root: Path,
) -> ReferenceBaseValidationProtocol:
    """Load the approved protocol through the caller-trusted repository root."""

    path = _resolve(
        repository_root,
        REFERENCE_VALIDATION_PROTOCOL,
        "Reference base-validation protocol",
    )
    return ReferenceBaseValidationProtocol.model_validate_json(path.read_text("utf-8"))


def load_reference_validation_freeze(
    repository_root: Path,
) -> ReferenceBaseValidationFreeze:
    """Load the derived freeze record without trusting ambient paths."""

    path = _resolve(
        repository_root,
        REFERENCE_VALIDATION_FREEZE,
        "Reference base-validation freeze record",
    )
    return ReferenceBaseValidationFreeze.model_validate_json(path.read_text("utf-8"))


def load_reference_scientific_manifest(
    repository_root: Path,
) -> ReferenceScientificInputManifest:
    """Load the committed complete scientific input inventory."""

    path = _resolve(
        repository_root,
        REFERENCE_SCIENTIFIC_MANIFEST,
        "Reference validation scientific-input manifest",
    )
    return ReferenceScientificInputManifest.model_validate_json(path.read_text("utf-8"))


def build_reference_validation_freeze(
    repository_root: Path,
) -> ReferenceBaseValidationFreeze:
    """Bind protocol, complete inputs, workflow, environment, and lock exactly."""

    protocol = load_reference_validation_protocol(repository_root)
    scientific = load_reference_scientific_manifest(repository_root)
    current = build_reference_scientific_input_manifest(repository_root)
    if scientific != current:
        raise ValueError("Reference committed scientific manifest is not current")
    g3_payload = json.loads(
        _resolve(repository_root, REFERENCE_G3_HANDOFF, "Reference current G3 handoff").read_text(
            "utf-8"
        )
    )
    phase6_payload = json.loads(
        _resolve(
            repository_root,
            REFERENCE_PHASE6_ACCEPTANCE,
            "Reference current Phase 6 acceptance",
        ).read_text("utf-8")
    )
    canonical_payload = json.loads(
        _resolve(
            repository_root,
            REFERENCE_CANONICAL_PHASE6_RECEIPT,
            "Reference current canonical Phase 6 receipt",
        ).read_text("utf-8")
    )
    if not g3_payload.get("g3_ready") or (
        g3_payload.get("scientific_input_aggregate_sha256") != current.aggregate_sha256
    ):
        raise ValueError("Reference G3 handoff does not bind the current scientific inputs")
    phase6_resource = phase6_payload.get("resource_receipt", {})
    if (
        phase6_payload.get("scientific_input_manifest_digest") != current.aggregate_sha256
        or not phase6_payload.get("all_nonperformance_checks_pass")
        or phase6_resource.get("schema_version") != "delta-reference-phase6-resource-receipt-v2"
        or phase6_resource.get("measurement_role") != "canonical"
        or phase6_resource.get("canonical_gate_status") != "passed"
    ):
        raise ValueError("Reference Phase 6 acceptance is not current canonical evidence")
    if (
        canonical_payload.get("scientific_input_aggregate_sha256") != current.aggregate_sha256
        or canonical_payload.get("execution_role") != "canonical-development-preflight"
        or canonical_payload.get("raw_runner_measurement_role") != "canonical"
        or canonical_payload.get("raw_runner_canonical_gate_status") != "passed"
        or not canonical_payload.get("environment_verification_matches")
        or not canonical_payload.get("registered_resource_ceilings_observed_within_limits")
        or not canonical_payload.get("exact_replay_byte_identical")
        or not canonical_payload.get("publication_regeneration_byte_identical")
    ):
        raise ValueError("Reference canonical Phase 6 receipt is stale or incomplete")
    environment_path = Path(protocol.environment_contract_path)
    lock_path = Path(protocol.dependency_lock_path)
    body = {
        "schema_version": "delta-reference-base-validation-freeze-v2",
        "status": "frozen-awaiting-separate-execution-authorization",
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "protocol": _binding(
            repository_root,
            REFERENCE_VALIDATION_PROTOCOL,
            label="Reference frozen validation protocol",
        ).model_dump(mode="json"),
        "scientific_input_manifest": _binding(
            repository_root,
            REFERENCE_SCIENTIFIC_MANIFEST,
            label="Reference frozen scientific manifest",
        ).model_dump(mode="json"),
        "scientific_input_aggregate_sha256": scientific.aggregate_sha256,
        "scientific_input_member_count": len(scientific.members),
        "workflow": _binding(
            repository_root,
            REFERENCE_VALIDATION_WORKFLOW,
            label="Reference frozen original workflow",
        ).model_dump(mode="json"),
        "environment_contract": _binding(
            repository_root,
            environment_path,
            label="Reference frozen environment contract",
        ).model_dump(mode="json"),
        "dependency_lock": _binding(
            repository_root,
            lock_path,
            label="Reference frozen dependency lock",
        ).model_dump(mode="json"),
        "g3_handoff": _binding(
            repository_root,
            REFERENCE_G3_HANDOFF,
            label="Reference frozen G3 handoff",
        ).model_dump(mode="json"),
        "phase6_development_acceptance": _binding(
            repository_root,
            REFERENCE_PHASE6_ACCEPTANCE,
            label="Reference frozen Phase 6 acceptance",
        ).model_dump(mode="json"),
        "canonical_phase6_execution_receipt": _binding(
            repository_root,
            REFERENCE_CANONICAL_PHASE6_RECEIPT,
            label="Reference frozen canonical Phase 6 receipt",
        ).model_dump(mode="json"),
        "authorization_tag": REFERENCE_VALIDATION_TAG,
        "source_commit_required": True,
        "protected_seed_values": [],
    }
    return ReferenceBaseValidationFreeze(
        **body,
        freeze_digest=hashlib.sha256(canonical_json_bytes(body)).hexdigest(),
    )


def verify_reference_validation_freeze(repository_root: Path) -> ReferenceBaseValidationFreeze:
    """Reject any protocol, workflow, environment, lock, or source substitution."""

    expected = load_reference_validation_freeze(repository_root)
    actual = build_reference_validation_freeze(repository_root)
    if actual != expected:
        raise ValueError("Reference base-validation freeze record is not current")
    return expected


def require_original_execution_identity(
    environment: Mapping[str, str],
) -> ReferenceOriginalExecutionIdentity:
    """Accept only the once-authorized GitHub tag execution identity."""

    expected = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REF": f"refs/tags/{REFERENCE_VALIDATION_TAG}",
        "GITHUB_RUN_ATTEMPT": "1",
        "TRACE_REFERENCE_EXECUTION_ROLE": "original-base-reference-validation",
        "TRACE_REFERENCE_AUTHORIZATION_TAG": REFERENCE_VALIDATION_TAG,
        "TRACE_REFERENCE_WORKFLOW_FILE": REFERENCE_VALIDATION_WORKFLOW.name,
        "TRACE_REFERENCE_PRIOR_SUCCESS_GUARD": "verified-no-prior-success",
        "TRACE_REFERENCE_ANNOTATED_TAG_GUARD": "verified-annotated-tag-points-to-sha",
    }
    mismatches = tuple(
        name for name, expected_value in expected.items() if environment.get(name) != expected_value
    )
    if mismatches:
        raise ValueError(
            "Reference original execution identity is incomplete: " + ", ".join(mismatches)
        )
    sha = environment.get("GITHUB_SHA", "")
    if len(sha) != 40 or any(character not in "0123456789abcdef" for character in sha):
        raise ValueError("Reference original execution has an invalid source commit")
    try:
        run_id = int(environment.get("GITHUB_RUN_ID", ""))
    except ValueError as exc:
        raise ValueError("Reference original execution has an invalid workflow run ID") from exc
    return ReferenceOriginalExecutionIdentity(
        execution_role="original-base-reference-validation",
        source_commit=sha,
        authorization_tag=REFERENCE_VALIDATION_TAG,
        git_ref=f"refs/tags/{REFERENCE_VALIDATION_TAG}",
        workflow_file=REFERENCE_VALIDATION_WORKFLOW.name,
        workflow_run_id=run_id,
        workflow_run_attempt=1,
        repository=environment.get("GITHUB_REPOSITORY", ""),
    )


def require_original_validation_boundary(
    repository_root: Path,
    environment: Mapping[str, str],
) -> tuple[
    ReferenceBaseValidationProtocol,
    ReferenceBaseValidationFreeze,
    ReferenceOriginalExecutionIdentity,
]:
    """Verify every frozen and remote boundary before protected study code runs."""

    protocol = load_reference_validation_protocol(repository_root)
    freeze = verify_reference_validation_freeze(repository_root)
    identity = require_original_execution_identity(environment)
    contract_path = _resolve(
        repository_root,
        Path(protocol.environment_contract_path),
        "Reference original environment contract",
    )
    lock_path = _resolve(
        repository_root,
        Path(protocol.dependency_lock_path),
        "Reference original dependency lock",
    )
    require_reference_environment(contract_path, lock_path)
    verification = inspect_reference_environment(contract_path, lock_path)
    if not verification.matches:
        raise ValueError("Reference original environment identity does not match")
    if sha256_file(contract_path) != freeze.environment_contract.sha256:
        raise ValueError("Reference original environment contract changed after freeze")
    if sha256_file(lock_path) != freeze.dependency_lock.sha256:
        raise ValueError("Reference original dependency lock changed after freeze")
    return protocol, freeze, identity
