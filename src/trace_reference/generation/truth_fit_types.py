"""Compact sufficient-statistic contracts for Reference truth fitting."""

from __future__ import annotations

from dataclasses import dataclass

from trace_reference.domain.truth import ReferenceIncidentType


@dataclass(frozen=True)
class ReferenceTruthFitInterval:
    """Intercept interval producing one evaluation incident from one episode."""

    incident_type: ReferenceIncidentType
    lower_intercept_inclusive: int
    upper_intercept_exclusive: int | None


@dataclass(frozen=True)
class ReferenceTruthFitSeedSummary:
    """Compact sufficient statistics for one spent development world."""

    seed: int
    eligible_episode_count: int
    evaluation_intervals: tuple[ReferenceTruthFitInterval, ...]
