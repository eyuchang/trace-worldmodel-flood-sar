"""One-release compatibility facade for Delta physical-state generation."""

from trace_jepa.scenario.delta.generation.physical import (
    generate_crossing_states,
    generate_gauges,
    generate_geography,
    generate_weather,
    physical_parameter_table,
)

__all__ = [
    "generate_crossing_states",
    "generate_gauges",
    "generate_geography",
    "generate_weather",
    "physical_parameter_table",
]
