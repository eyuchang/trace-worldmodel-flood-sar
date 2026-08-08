"""One-release compatibility facade for deterministic Delta randomness."""

from trace_jepa.scenario.delta.generation.randomness import (
    KeyedRandom,
    derive_stage_seed,
    sample_poisson,
    seeded_random,
)

__all__ = ["KeyedRandom", "derive_stage_seed", "sample_poisson", "seeded_random"]
