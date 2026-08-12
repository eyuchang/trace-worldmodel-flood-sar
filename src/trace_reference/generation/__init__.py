"""Deterministic generation stages for Reference."""

from .coordination import generate_reference_coordination
from .exposure import generate_reference_exposure
from .observations import generate_reference_observations, verify_reference_envelope
from .physical import generate_reference_physical_scenario
from .pipeline import generate_reference_scenario
from .resources import generate_reference_resources
from .truth import generate_reference_truth

__all__ = [
    "generate_reference_coordination",
    "generate_reference_exposure",
    "generate_reference_observations",
    "generate_reference_physical_scenario",
    "generate_reference_resources",
    "generate_reference_scenario",
    "generate_reference_truth",
    "verify_reference_envelope",
]
