"""Aggregate generated-scenario model."""

from pathlib import Path

from trace_jepa.scenario.delta.geography_models import GeographyCatalog

from .base import DeltaModel
from .config import DeltaScenarioConfig
from .observations import CoordinationArtifact, ObservationArtifact
from .resources import PriorProfileArtifact, ResourceArtifact
from .state import CrossingState, GaugeSample, GroundTruth, GroundTruthV8, WeatherSample


class GeneratedScenario(DeltaModel):
    config: DeltaScenarioConfig
    geography: GeographyCatalog
    weather: list[WeatherSample]
    gauges: list[GaugeSample]
    crossing_states: list[CrossingState]
    truth: GroundTruth | GroundTruthV8
    observations: ObservationArtifact
    coordination: CoordinationArtifact | None = None
    resources: ResourceArtifact
    prior_profile: PriorProfileArtifact
    stage_seeds: list[str]
    generation_order: list[str]
    source_path: Path
