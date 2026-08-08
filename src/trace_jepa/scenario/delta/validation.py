"""One-release facade for the historical pre-v7 validation entry point."""

from trace_jepa.scenario.delta.legacy.validation_v6 import run_registered_validation

__all__ = ["run_registered_validation"]
