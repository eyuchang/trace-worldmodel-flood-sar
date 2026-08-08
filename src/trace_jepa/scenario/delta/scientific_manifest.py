"""Compatibility facade for the scientific-input freeze API."""

from trace_jepa.scenario.delta.provenance.scientific_inputs import (
    ScientificInputError,
    ScientificInputManifest,
    ScientificInputMember,
    build_scientific_input_manifest,
    scientific_input_paths,
    verify_scientific_input_manifest,
    write_scientific_input_manifest,
)

__all__ = [
    "ScientificInputError",
    "ScientificInputManifest",
    "ScientificInputMember",
    "build_scientific_input_manifest",
    "scientific_input_paths",
    "verify_scientific_input_manifest",
    "write_scientific_input_manifest",
]
