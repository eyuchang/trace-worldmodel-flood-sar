"""Statistical studies and registered execution boundaries."""

from .registered import (
    canonical_v9_paths,
    run_v8_development_validation,
    run_v8_registered_validation,
    run_v9_development_validation,
    run_v9_registered_validation,
    verify_registered_v8_inputs,
    verify_registered_v9_inputs,
)

__all__ = [
    "canonical_v9_paths",
    "run_v8_development_validation",
    "run_v8_registered_validation",
    "run_v9_development_validation",
    "run_v9_registered_validation",
    "verify_registered_v8_inputs",
    "verify_registered_v9_inputs",
]
