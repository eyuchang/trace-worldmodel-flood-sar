"""Thin public facade for the modular Delta mission controller."""

from .mission_controller import DeltaMissionRunner, run_delta_small

__all__ = ["DeltaMissionRunner", "run_delta_small"]
