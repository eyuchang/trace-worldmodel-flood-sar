"""Aggregate generated-scenario model."""

from pathlib import Path

from trace_jepa.scenario.delta.geography.models import GeographyCatalog

from .base import DeltaModel
from .config import DeltaScenarioConfig
from .observations import CoordinationArtifact, ObservationArtifact
from .resources import PriorProfileArtifact, ResourceArtifact
from .state import CrossingState, GaugeSample, GroundTruth, GroundTruthV8, WeatherSample


class GeneratedScenario(DeltaModel):
    config: DeltaScenarioConfig
    geography: GeographyCatalog
    weather: tuple[WeatherSample, ...]
    gauges: tuple[GaugeSample, ...]
    crossing_states: tuple[CrossingState, ...]
    truth: GroundTruth | GroundTruthV8
    observations: ObservationArtifact
    coordination: CoordinationArtifact | None = None
    resources: ResourceArtifact
    prior_profile: PriorProfileArtifact
    stage_seeds: tuple[str, ...]
    generation_order: tuple[str, ...]
    source_path: Path
