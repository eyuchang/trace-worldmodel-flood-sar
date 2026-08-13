"""Deterministic Reference artifacts, provenance, and replay verification."""

from .artifacts import (
    ReferenceArtifactMismatchError,
    verify_reference_artifacts,
    verify_reference_input_inventory,
    write_reference_artifacts,
)
from .inventory import reference_source_tree_sha256
from .models import (
    ReferenceArtifactDescriptor,
    ReferenceFileInput,
    ReferenceReplayManifest,
    ReferenceResultSummary,
    ReferenceValueInput,
)
from .replay import (
    ReferenceExecution,
    ReferenceExecutionInspection,
    execute_reference_scenario,
    execute_reference_scenario_with_inspection,
    verify_exact_reference_replay,
)
from .scientific_inputs import (
    ReferenceScientificInputManifest,
    ReferenceScientificInputMember,
    build_reference_scientific_input_manifest,
    verify_reference_scientific_input_manifest,
)
from .specifications import ReferenceArtifactWriteRequest

__all__ = [
    "ReferenceArtifactDescriptor",
    "ReferenceArtifactMismatchError",
    "ReferenceArtifactWriteRequest",
    "ReferenceExecution",
    "ReferenceExecutionInspection",
    "ReferenceFileInput",
    "ReferenceReplayManifest",
    "ReferenceResultSummary",
    "ReferenceScientificInputManifest",
    "ReferenceScientificInputMember",
    "ReferenceValueInput",
    "build_reference_scientific_input_manifest",
    "execute_reference_scenario",
    "execute_reference_scenario_with_inspection",
    "reference_source_tree_sha256",
    "verify_exact_reference_replay",
    "verify_reference_artifacts",
    "verify_reference_input_inventory",
    "verify_reference_scientific_input_manifest",
    "write_reference_artifacts",
]
