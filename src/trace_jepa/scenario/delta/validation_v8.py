"""Compatibility facade for registered v8 validation APIs."""

from trace_jepa.scenario.delta.validation.registered import (
    ORIGINAL_CONFIRMATION_TOKEN,
    ValidationStudy,
    canonical_v8_paths,
    run_v8_development_validation,
    run_v8_registered_validation,
    verify_registered_v8_inputs,
)

__all__ = [
    "ORIGINAL_CONFIRMATION_TOKEN",
    "ValidationStudy",
    "canonical_v8_paths",
    "run_v8_development_validation",
    "run_v8_registered_validation",
    "verify_registered_v8_inputs",
]
