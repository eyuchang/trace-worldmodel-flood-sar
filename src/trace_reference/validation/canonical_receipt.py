"""Canonical Phase 6 execution-receipt construction after an exact container run."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from trace_jepa.support import (
    ArtifactLocator,
    atomic_write_bytes,
    canonical_json_bytes,
    safe_directory,
    sha256_file,
)
from trace_reference.provenance.scientific_inputs import (
    build_reference_scientific_input_manifest,
)

from .acceptance_models import ReferencePhase6CoreReceipt
from .registration_models import (
    ReferenceCanonicalPhase6ExecutionReceipt,
    ReferenceValidationBinding,
)

_ENVIRONMENT = Path(
    "data/scenario/delta/reference/environment/reference_python311_linux_amd64_v1.json"
)
_LOCK = Path("requirements-delta-python311.lock")
_MAX_RECEIPT_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class ReferenceCanonicalReceiptInput:
    repository_root: Path
    trusted_core_root: Path
    core_receipt_relative_path: Path
    output_path: Path
    source_commit: str
    derived_reference_image_digest: str
    docker_engine_version: str
    recorded_utc: str


def _binding(root: Path, relative_path: Path, label: str) -> ReferenceValidationBinding:
    path = ArtifactLocator(
        root=root,
        relative_name=relative_path,
        maximum_bytes=_MAX_RECEIPT_BYTES,
        label=label,
    ).resolve()
    return ReferenceValidationBinding(
        repository_relative_path=relative_path.as_posix(),
        sha256=sha256_file(path),
    )


def write_reference_canonical_phase6_receipt(
    values: ReferenceCanonicalReceiptInput,
) -> ReferenceCanonicalPhase6ExecutionReceipt:
    """Verify the raw canonical runner receipt and bind container execution identity."""

    core_path = ArtifactLocator(
        root=values.trusted_core_root,
        relative_name=values.core_receipt_relative_path,
        maximum_bytes=_MAX_RECEIPT_BYTES,
        label="Reference raw canonical Phase 6 core receipt",
    ).resolve()
    core = ReferencePhase6CoreReceipt.model_validate_json(core_path.read_text("utf-8"))
    resource = core.resource_receipt
    if (
        resource.schema_version != "delta-reference-phase6-resource-receipt-v2"
        or resource.measurement_role != "canonical"
        or resource.canonical_gate_status != "passed"
        or not core.all_checks_pass
        or not core.exact_replay_byte_identical
        or not core.publication_regeneration_byte_identical
    ):
        raise ValueError("Reference raw Phase 6 receipt is not corrected canonical evidence")
    scientific = build_reference_scientific_input_manifest(values.repository_root)
    if core.scientific_input_aggregate_sha256 != scientific.aggregate_sha256:
        raise ValueError("Reference raw Phase 6 receipt binds another scientific inventory")
    environment_binding = _binding(
        values.repository_root,
        _ENVIRONMENT,
        "Reference canonical environment contract",
    )
    lock_binding = _binding(
        values.repository_root,
        _LOCK,
        "Reference canonical dependency lock",
    )
    environment = json.loads((values.repository_root / _ENVIRONMENT).read_text("utf-8"))
    if environment["dependency_lock_sha256"] != lock_binding.sha256:
        raise ValueError("Reference canonical environment and lock disagree")
    body = {
        "schema_version": "delta-reference-canonical-phase6-execution-receipt-v2",
        "scientific_status": "canonical-development-preflight-not-validation-evidence",
        "execution_role": "canonical-development-preflight",
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "source_commit": values.source_commit,
        "scientific_input_aggregate_sha256": scientific.aggregate_sha256,
        "environment_contract_sha256": environment_binding.sha256,
        "dependency_lock_sha256": lock_binding.sha256,
        "oci_index_sha256": environment["oci_index_sha256"],
        "oci_platform_manifest_sha256": environment["oci_platform_manifest_sha256"],
        "oci_platform": environment["oci_platform"],
        "derived_reference_image_digest": values.derived_reference_image_digest,
        "docker_engine_version": values.docker_engine_version,
        "recorded_utc": values.recorded_utc,
        "raw_core_receipt": ReferenceValidationBinding(
            repository_relative_path=values.core_receipt_relative_path.as_posix(),
            sha256=sha256_file(core_path),
        ).model_dump(mode="json"),
        "raw_core_receipt_digest": core.receipt_digest,
        "raw_resource_receipt_digest": resource.receipt_digest,
        "raw_runner_measurement_role": "canonical",
        "raw_runner_canonical_gate_status": "passed",
        "environment_verification_matches": True,
        "registered_resource_ceilings_observed_within_limits": True,
        "exact_replay_byte_identical": True,
        "publication_regeneration_byte_identical": True,
        "leap_behavior_present": False,
        "selection_validation_or_confirmatory_authority": False,
    }
    receipt = ReferenceCanonicalPhase6ExecutionReceipt(
        **body,
        receipt_digest=hashlib.sha256(canonical_json_bytes(body)).hexdigest(),
    )
    root = safe_directory(
        values.output_path.parent,
        declared_root=values.output_path.parent,
        label="Reference canonical receipt output root",
    )
    if values.output_path.exists():
        raise ValueError("Reference canonical Phase 6 receipt output already exists")
    atomic_write_bytes(
        values.output_path,
        canonical_json_bytes(receipt.model_dump(mode="json")),
        root=root,
        label="Reference canonical Phase 6 execution receipt",
    )
    return receipt
