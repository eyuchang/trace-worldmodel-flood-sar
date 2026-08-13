"""Build and verify the final non-LEAP Reference G3 engineering handoff."""

from __future__ import annotations

import hashlib
import json
import platform
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from trace_jepa.support import (
    ArtifactLocator,
    atomic_write_bytes,
    canonical_json_bytes,
    sha256_file,
)
from trace_reference import verify_small_baseline
from trace_reference.decision.canonical import decision_digest
from trace_reference.provenance.scientific_inputs import (
    ReferenceScientificInputManifest,
    build_reference_scientific_input_manifest,
)

from .g3_characterization_models import ReferenceG3CharacterizationIndex
from .g3_handoff_models import (
    REFERENCE_G3_GATE_IDS,
    ReferenceG3AcceptanceReceipt,
    ReferenceG3AcceptanceRegistry,
    ReferenceG3ComponentBinding,
    ReferenceG3FileBinding,
    ReferenceG3GateResult,
    ReferenceG3HandoffManifest,
)

_MAX_INPUT_BYTES = 256 * 1024 * 1024
_ADR = Path("docs/delta/reference/REFERENCE_G3_TRACE_LEAP_HANDOFF_ADR_V2.md")
_MECHANISM_AUDIT = Path(
    "docs/delta/reference/TRACE_LEAP_MECHANISM_IDENTITY_AND_ADAPTATION_AUDIT_V1.md"
)
_REGISTRY = Path("data/scenario/delta/reference_protocol/reference_g3_acceptance_registry_v1.json")
_SMALL = Path("data/scenario/delta/reference_protocol/small_baseline_v1.json")
_ENVIRONMENT = Path(
    "data/scenario/delta/reference/environment/reference_python311_linux_amd64_v1.json"
)
_LOCK = Path("requirements-delta-python311.lock")
_CORRECTED_ADR_SHA256 = "2af2b3b9e24040cb7fa0efa146b6e5cc9a3ad0805e53050494888a095b54403d"
_MECHANISM_AUDIT_SHA256 = "3a833c7faa68bd4d43f05f130d1f099d14165a385552715bfd6ec217953725b4"
_ModelT = TypeVar("_ModelT", bound=BaseModel)
_PUBLIC_SCHEMAS = tuple(
    sorted(
        {
            "delta-reference-acquisition-outcome-v1",
            "delta-reference-acquisition-request-v2",
            "delta-reference-base-selection-v1",
            "delta-reference-counterfactual-step-v1",
            "delta-reference-decision-cost-v1",
            "delta-reference-decision-handoff-artifact-v1",
            "delta-reference-eligibility-receipt-v1",
            "delta-reference-evidence-acquisition-offer-v2",
            "delta-reference-physical-evidence-v1",
            "delta-reference-proposal-request-v2",
            "delta-reference-proposal-set-v1",
            "delta-reference-provider-receipt-v1",
            "delta-reference-public-model-state-v1",
            "delta-reference-public-snapshot-v2",
            "delta-reference-response-bundle-catalog-v1",
            "delta-reference-response-bundle-v1",
        }
    )
)


def _resolve(repository_root: Path, relative_path: Path, label: str) -> Path:
    return ArtifactLocator(
        root=repository_root,
        relative_name=relative_path,
        maximum_bytes=_MAX_INPUT_BYTES,
        label=label,
    ).resolve()


def _binding(repository_root: Path, relative_path: Path) -> ReferenceG3FileBinding:
    path = _resolve(repository_root, relative_path, f"Reference G3 {relative_path}")
    return ReferenceG3FileBinding(
        relative_path=relative_path.as_posix(),
        byte_length=path.stat().st_size,
        sha256=sha256_file(path),
    )


def _load_registry(repository_root: Path) -> ReferenceG3AcceptanceRegistry:
    path = _resolve(repository_root, _REGISTRY, "Reference G3 acceptance registry")
    return ReferenceG3AcceptanceRegistry.model_validate_json(path.read_text("utf-8"))


def _test_source_aggregate(
    repository_root: Path,
    test_node_ids: tuple[str, ...],
) -> str:
    digest = hashlib.sha256()
    for relative_name in sorted({item.split("::", maxsplit=1)[0] for item in test_node_ids}):
        binding = _binding(repository_root, Path(relative_name))
        payload = canonical_json_bytes(binding.model_dump(mode="json"))
        digest.update(str(len(payload)).encode("ascii"))
        digest.update(b"\0")
        digest.update(payload)
        digest.update(b"\0")
    return digest.hexdigest()


def build_reference_g3_acceptance_receipt(
    repository_root: Path,
    *,
    passed_gate_ids: tuple[str, ...],
) -> ReferenceG3AcceptanceReceipt:
    """Bind results only after the caller has executed every registered gate."""

    if passed_gate_ids != REFERENCE_G3_GATE_IDS:
        raise ValueError("Reference G3 receipt requires every corrected-ADR gate in order")
    registry = _load_registry(repository_root)
    test_paths = tuple(
        sorted(
            {
                node_id.split("::", maxsplit=1)[0]
                for gate in registry.gates
                for node_id in gate.test_node_ids
            }
        )
    )
    test_sources = tuple(_binding(repository_root, Path(item)) for item in test_paths)
    results = []
    for gate in registry.gates:
        gate_body: dict[str, object] = {
            "gate_id": gate.gate_id,
            "test_node_ids": gate.test_node_ids,
            "test_source_aggregate_sha256": _test_source_aggregate(
                repository_root,
                gate.test_node_ids,
            ),
            "outcome": "passed",
        }
        results.append(
            ReferenceG3GateResult(
                **gate_body,
                passing_result_sha256=decision_digest(gate_body),
            )
        )
    receipt_body: dict[str, object] = {
        "schema_version": "delta-reference-g3-acceptance-receipt-v1",
        "scientific_status": "development-engineering-gate-not-validation-evidence",
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "registry": _binding(repository_root, _REGISTRY).model_dump(mode="json"),
        "test_sources": [item.model_dump(mode="json") for item in test_sources],
        "gate_results": [item.model_dump(mode="json") for item in results],
        "all_gates_pass": True,
        "execution_python": platform.python_version(),
    }
    return ReferenceG3AcceptanceReceipt(
        **receipt_body,
        receipt_digest=decision_digest(receipt_body),
    )


def write_reference_g3_acceptance_receipt(
    repository_root: Path,
    output_relative_path: Path,
    *,
    passed_gate_ids: tuple[str, ...],
) -> ReferenceG3AcceptanceReceipt:
    """Write one deterministic result receipt beneath the trusted repository."""

    receipt = build_reference_g3_acceptance_receipt(
        repository_root,
        passed_gate_ids=passed_gate_ids,
    )
    output = repository_root / output_relative_path
    atomic_write_bytes(
        output,
        canonical_json_bytes(receipt.model_dump(mode="json")),
        root=repository_root,
        label="Reference G3 acceptance receipt",
    )
    return receipt


def _components(repository_root: Path) -> tuple[ReferenceG3ComponentBinding, ...]:
    values = (
        ("base-selector", "reference-base-selector-v1", "selector.py"),
        ("cost-ledger", "delta-reference-decision-cost-v1", "costs.py"),
        (
            "physical-channel",
            "reference-physical-route-verification-v1",
            "acquisition.py",
        ),
        ("public-model", "reference-public-one-step-model-v1", "counterfactual.py"),
    )
    return tuple(
        ReferenceG3ComponentBinding(
            component=component,
            version=version,
            source=_binding(
                repository_root,
                Path("src/trace_reference/decision") / source_name,
            ),
        )
        for component, version, source_name in values
    )


def _load_json_model(
    repository_root: Path,
    relative_path: Path,
    model_type: type[_ModelT],
) -> _ModelT:
    path = _resolve(repository_root, relative_path, f"Reference G3 {relative_path}")
    return model_type.model_validate_json(path.read_text("utf-8"))


def build_reference_g3_handoff_manifest(
    repository_root: Path,
    *,
    scientific_input_relative_path: Path,
    acceptance_receipt_relative_path: Path,
    characterization_root_relative_path: Path,
) -> ReferenceG3HandoffManifest:
    """Verify every handoff input before creating the final non-LEAP manifest."""

    if sha256_file(_resolve(repository_root, _ADR, "Reference corrected G3 ADR")) != (
        _CORRECTED_ADR_SHA256
    ):
        raise ValueError("Reference G3 handoff does not bind the corrected ADR")
    if (
        sha256_file(_resolve(repository_root, _MECHANISM_AUDIT, "Reference mechanism audit"))
        != _MECHANISM_AUDIT_SHA256
    ):
        raise ValueError("Reference G3 handoff mechanism audit changed")
    scientific = _load_json_model(
        repository_root,
        scientific_input_relative_path,
        ReferenceScientificInputManifest,
    )
    if scientific != build_reference_scientific_input_manifest(repository_root):
        raise ValueError("Reference G3 scientific-input manifest is not current")
    acceptance = _load_json_model(
        repository_root,
        acceptance_receipt_relative_path,
        ReferenceG3AcceptanceReceipt,
    )
    if tuple(item.gate_id for item in acceptance.gate_results) != REFERENCE_G3_GATE_IDS:
        raise ValueError("Reference G3 acceptance receipt is incomplete")
    registry = _load_registry(repository_root)
    if acceptance.registry != _binding(repository_root, _REGISTRY):
        raise ValueError("Reference G3 acceptance receipt names another registry")
    if tuple(item.test_node_ids for item in registry.gates) != tuple(
        item.test_node_ids for item in acceptance.gate_results
    ):
        raise ValueError("Reference G3 acceptance receipt names another test set")

    characterization_index_path = (
        characterization_root_relative_path / "g3_characterization_index.json"
    )
    characterization = _load_json_model(
        repository_root,
        characterization_index_path,
        ReferenceG3CharacterizationIndex,
    )
    fixture_paths = tuple(
        characterization_root_relative_path / f"{item.fixture_id}_fixture_manifest.json"
        for item in characterization.fixtures
    )
    for path, expected in zip(fixture_paths, characterization.fixtures, strict=True):
        payload = json.loads(
            _resolve(repository_root, path, f"Reference G3 fixture {path}").read_text("utf-8")
        )
        if payload != expected.model_dump(mode="json"):
            raise ValueError("Reference G3 fixture file disagrees with its index")

    small = verify_small_baseline(repository_root, _SMALL)
    environment = json.loads(
        _resolve(repository_root, _ENVIRONMENT, "Reference G3 environment").read_text("utf-8")
    )
    if environment.get("dependency_lock_sha256") != sha256_file(
        _resolve(repository_root, _LOCK, "Reference G3 dependency lock")
    ):
        raise ValueError("Reference G3 dependency lock disagrees with its environment contract")
    body = {
        "schema_version": "delta-reference-g3-handoff-manifest-v1",
        "scientific_status": "development-engineering-gate-not-validation-evidence",
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "adr_version": "reference-leap-handoff-adr-v2",
        "adr": _binding(repository_root, _ADR).model_dump(mode="json"),
        "mechanism_identity_audit": _binding(repository_root, _MECHANISM_AUDIT).model_dump(
            mode="json"
        ),
        "scientific_input_manifest": _binding(
            repository_root, scientific_input_relative_path
        ).model_dump(mode="json"),
        "scientific_input_aggregate_sha256": scientific.aggregate_sha256,
        "scientific_input_member_count": len(scientific.members),
        "public_schema_versions": _PUBLIC_SCHEMAS,
        "components": [item.model_dump(mode="json") for item in _components(repository_root)],
        "acceptance_registry": _binding(repository_root, _REGISTRY).model_dump(mode="json"),
        "acceptance_receipt": _binding(
            repository_root, acceptance_receipt_relative_path
        ).model_dump(mode="json"),
        "acceptance_receipt_digest": acceptance.receipt_digest,
        "characterization_index": _binding(repository_root, characterization_index_path).model_dump(
            mode="json"
        ),
        "characterization_index_digest": characterization.index_digest,
        "characterization_fixtures": [
            _binding(repository_root, path).model_dump(mode="json") for path in fixture_paths
        ],
        "small_baseline_registry": _binding(repository_root, _SMALL).model_dump(mode="json"),
        "small_baseline_source_commit": small.source_commit,
        "small_baseline_verified_file_count": len(small.files),
        "environment_contract": _binding(repository_root, _ENVIRONMENT).model_dump(mode="json"),
        "dependency_lock": _binding(repository_root, _LOCK).model_dump(mode="json"),
        "leap_implementation_present": False,
        "effectiveness_evidence_present": False,
        "g3_ready": True,
    }
    return ReferenceG3HandoffManifest(**body, manifest_digest=decision_digest(body))


def write_reference_scientific_input_manifest(
    repository_root: Path,
    output_relative_path: Path,
) -> ReferenceScientificInputManifest:
    """Persist the current complete, non-self-referential G3 input inventory."""

    manifest = build_reference_scientific_input_manifest(repository_root)
    atomic_write_bytes(
        repository_root / output_relative_path,
        canonical_json_bytes(manifest.model_dump(mode="json")),
        root=repository_root,
        label="Reference G3 scientific-input manifest",
    )
    return manifest


def write_reference_g3_handoff_manifest(
    repository_root: Path,
    output_relative_path: Path,
    *,
    scientific_input_relative_path: Path,
    acceptance_receipt_relative_path: Path,
    characterization_root_relative_path: Path,
) -> ReferenceG3HandoffManifest:
    """Persist the final handoff manifest after verifying every bound member."""

    manifest = build_reference_g3_handoff_manifest(
        repository_root,
        scientific_input_relative_path=scientific_input_relative_path,
        acceptance_receipt_relative_path=acceptance_receipt_relative_path,
        characterization_root_relative_path=characterization_root_relative_path,
    )
    atomic_write_bytes(
        repository_root / output_relative_path,
        canonical_json_bytes(manifest.model_dump(mode="json")),
        root=repository_root,
        label="Reference G3 handoff manifest",
    )
    return manifest
