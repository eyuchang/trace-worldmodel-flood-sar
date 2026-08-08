"""Compatibility facade for the canonical v8 observation channel."""

from trace_jepa.scenario.delta.generation.observation_channel import (
    BASE_REPORTING_BY_HOUR_V2,
    DESCRIPTOR_VOCABULARY_V1,
    FALSE_REPORT_HOUR_WEIGHTS_V1,
    ObservationChannel,
    ReportDraft,
    channel_probabilities_v8,
    generate_observations_v8,
    reporting_probability_v8,
)
from trace_jepa.scenario.delta.generation.observation_primitives import (
    location_error_scale as location_error_scale_v7,
)
from trace_jepa.scenario.delta.generation.observation_primitives import (
    location_method_mixture as location_method_mixture_v7,
)

__all__ = [
    "BASE_REPORTING_BY_HOUR_V2",
    "DESCRIPTOR_VOCABULARY_V1",
    "FALSE_REPORT_HOUR_WEIGHTS_V1",
    "ObservationChannel",
    "ReportDraft",
    "channel_probabilities_v8",
    "generate_observations_v8",
    "location_error_scale_v7",
    "location_method_mixture_v7",
    "reporting_probability_v8",
]
