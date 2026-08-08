"""Compatibility facade for Delta artifact and replay provenance APIs."""

from trace_jepa.scenario.delta.provenance.artifacts import (
    ArtifactDescriptor,
    ArtifactMismatchError,
    ProvenanceInput,
    ReplayManifest,
    StageSeedRecord,
    canonical_json_bytes,
    current_git_commit,
    sha256_bytes,
    sha256_file,
    source_tree_sha256,
    verify_scenario_artifacts,
    write_scenario_artifacts,
)

__all__ = [
    "ArtifactDescriptor",
    "ArtifactMismatchError",
    "ProvenanceInput",
    "ReplayManifest",
    "StageSeedRecord",
    "canonical_json_bytes",
    "current_git_commit",
    "sha256_bytes",
    "sha256_file",
    "source_tree_sha256",
    "verify_scenario_artifacts",
    "write_scenario_artifacts",
]
