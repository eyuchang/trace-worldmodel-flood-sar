"""One-release facade for the historical pre-v7 population generator."""

from trace_jepa.scenario.delta.legacy.population_v6 import (
    _channel_probabilities,
    _hourly_channel_probabilities,
    _latent_hour_rates,
    generate_observations,
    generate_prior_profile,
    generate_resources,
    generate_truth,
    population_parameter_table,
)

__all__ = [
    "_channel_probabilities",
    "_hourly_channel_probabilities",
    "_latent_hour_rates",
    "generate_observations",
    "generate_prior_profile",
    "generate_resources",
    "generate_truth",
    "population_parameter_table",
]
