from __future__ import annotations

import math

from trace_jepa.scenario.delta.domain import (
    CrossingState,
    DeltaScenarioConfig,
    GaugeSample,
    WeatherSample,
)
from trace_jepa.scenario.delta.geography_models import (
    Crossing,
    Gauge,
    GeographyCatalog,
    Island,
)

# Frozen reduced-order teaching parameters. These are not forecast coefficients.
TIDE_PERIOD_S = 44_700  # M2 constituent: 12 h 25 min.
TIDE_AMPLITUDE_MILLIFEET = {"RVB": 2_400, "MRU": 1_600, "FPT": 1_100}
GAUGE_PHASE_RAD = {"RVB": 0.0, "MRU": 0.72, "FPT": -0.38}
RUNOFF_LAG_S = {"RVB": 10_800, "MRU": 14_400, "FPT": 18_000}
RUNOFF_GAIN_MILLIFEET_PER_INCH = {"RVB": 680, "MRU": 410, "FPT": 530}
WIND_GAIN_MILLIFEET_PER_KNOT = {"RVB": 19, "MRU": 11, "FPT": 8}
UPSTREAM_RELEASE_MILLIFEET = {"RVB": 0, "MRU": 0, "FPT": 180}
RAIN_PROFILE_MILLI_INCHES_PER_HOUR = [60, 90, 150, 210, 120, 60]
WIND_PROFILE_MILLI_KNOTS = [8_000, 12_000, 18_000, 22_000, 16_000, 10_000]


def physical_parameter_table() -> dict[str, object]:
    """Return every frozen coefficient that defines the reduced-order model."""
    return {
        "schema_version": "delta-reduced-order-physical-parameters-v2",
        "tide_period_s": TIDE_PERIOD_S,
        "tide_amplitude_millifeet": TIDE_AMPLITUDE_MILLIFEET,
        "gauge_phase_rad": GAUGE_PHASE_RAD,
        "runoff_lag_s": RUNOFF_LAG_S,
        "runoff_gain_millifeet_per_inch": RUNOFF_GAIN_MILLIFEET_PER_INCH,
        "wind_gain_millifeet_per_knot": WIND_GAIN_MILLIFEET_PER_KNOT,
        "upstream_release_millifeet": UPSTREAM_RELEASE_MILLIFEET,
        "rain_profile_milli_inches_per_hour": RAIN_PROFILE_MILLI_INCHES_PER_HOUR,
        "wind_profile_milli_knots": WIND_PROFILE_MILLI_KNOTS,
        "claim_limit": "reduced-order-teaching-model-not-a-CDEC-forecast",
    }


def _select_by_id(items: list[object], allowed_ids: list[str], attribute: str) -> list[object]:
    selected = [item for item in items if str(getattr(item, attribute)) in allowed_ids]
    observed = {str(getattr(item, attribute)) for item in selected}
    missing = set(allowed_ids) - observed
    if missing:
        raise ValueError(f"geography catalog is missing required IDs: {sorted(missing)}")
    return selected


def generate_geography(config: DeltaScenarioConfig, catalog: GeographyCatalog) -> GeographyCatalog:
    return GeographyCatalog(
        schema_version=catalog.schema_version,
        coordinate_reference=catalog.coordinate_reference,
        coordinate_warning=catalog.coordinate_warning,
        build_manifest_sha256=catalog.build_manifest_sha256,
        sources=catalog.sources,
        islands=[
            Island.model_validate(item)
            for item in _select_by_id(list(catalog.islands), config.extent.island_ids, "island_id")
        ],
        communities=[
            item for item in catalog.communities if item.community_id in config.extent.community_ids
        ],
        crossings=[
            Crossing.model_validate(item)
            for item in _select_by_id(
                list(catalog.crossings), config.extent.crossing_ids, "crossing_id"
            )
        ],
        gauges=[
            Gauge.model_validate(item)
            for item in _select_by_id(list(catalog.gauges), config.extent.gauge_ids, "gauge_id")
        ],
        waterways=catalog.waterways,
        facilities=catalog.facilities,
        governance=catalog.governance,
    )


def generate_weather(config: DeltaScenarioConfig) -> list[WeatherSample]:
    samples: list[WeatherSample] = []
    for simulation_time_s in range(0, config.timeline.duration_s + 1, config.timeline.tick_s):
        hour = min(simulation_time_s // 3600, 5)
        rain = round(RAIN_PROFILE_MILLI_INCHES_PER_HOUR[hour] * config.axes.sigma / 0.3)
        wind = round(WIND_PROFILE_MILLI_KNOTS[hour] * config.axes.sigma / 0.3)
        ceiling_ft = max(800, 4_800 - 5 * rain - max(0, wind - 10_000) // 8)
        samples.append(
            WeatherSample(
                simulation_time_s=simulation_time_s,
                rain_milli_inches_per_hour=rain,
                wind_milli_knots=wind,
                ceiling_ft=ceiling_ft,
                aviation_operable=ceiling_ft >= 1_500 and wind <= 35_000,
            )
        )
    return samples


def _runoff_series(
    config: DeltaScenarioConfig,
    gauge_id: str,
    weather: list[WeatherSample],
) -> dict[int, int]:
    lag_s = RUNOFF_LAG_S[gauge_id]
    persistence = math.exp(-config.timeline.tick_s / lag_s)
    storage_inches = 0.0
    result: dict[int, int] = {}
    for sample in weather:
        rain_inches = sample.rain_milli_inches_per_hour / 1000.0 * config.timeline.tick_s / 3600.0
        storage_inches = storage_inches * persistence + rain_inches
        result[sample.simulation_time_s] = round(
            storage_inches * RUNOFF_GAIN_MILLIFEET_PER_INCH[gauge_id]
        )
    return result


def generate_gauges(
    config: DeltaScenarioConfig,
    geography: GeographyCatalog,
    weather: list[WeatherSample],
) -> list[GaugeSample]:
    weather_by_time = {sample.simulation_time_s: sample for sample in weather}
    samples: list[GaugeSample] = []
    for gauge in geography.gauges:
        runoff_by_time = _runoff_series(config, gauge.gauge_id, weather)
        for simulation_time_s in range(0, config.timeline.duration_s + 1, config.timeline.tick_s):
            tide = round(
                TIDE_AMPLITUDE_MILLIFEET[gauge.gauge_id]
                * math.sin(
                    2.0 * math.pi * simulation_time_s / TIDE_PERIOD_S
                    + GAUGE_PHASE_RAD[gauge.gauge_id]
                )
            )
            wind_setup = round(
                weather_by_time[simulation_time_s].wind_milli_knots
                / 1000.0
                * WIND_GAIN_MILLIFEET_PER_KNOT[gauge.gauge_id]
            )
            upstream = UPSTREAM_RELEASE_MILLIFEET[gauge.gauge_id]
            runoff = runoff_by_time[simulation_time_s]
            stage = gauge.baseline_stage_millifeet + tide + runoff + wind_setup + upstream
            samples.append(
                GaugeSample(
                    gauge_id=gauge.gauge_id,
                    simulation_time_s=simulation_time_s,
                    baseline_millifeet=gauge.baseline_stage_millifeet,
                    tide_millifeet=tide,
                    runoff_millifeet=runoff,
                    wind_setup_millifeet=wind_setup,
                    upstream_release_millifeet=upstream,
                    stage_millifeet=stage,
                    action_threshold_crossed=(
                        gauge.action_stage_millifeet >= 0 and stage >= gauge.action_stage_millifeet
                    ),
                )
            )
    return samples


def generate_crossing_states(
    config: DeltaScenarioConfig,
    geography: GeographyCatalog,
    weather: list[WeatherSample],
    gauges: list[GaugeSample],
) -> list[CrossingState]:
    weather_by_time = {sample.simulation_time_s: sample for sample in weather}
    rvb_by_time = {
        sample.simulation_time_s: sample for sample in gauges if sample.gauge_id == "RVB"
    }
    states: list[CrossingState] = []
    for crossing in geography.crossings:
        for simulation_time_s in range(0, config.timeline.duration_s + 1, config.timeline.tick_s):
            weather_sample = weather_by_time[simulation_time_s]
            gauge_sample = rvb_by_time[simulation_time_s]
            blocked = (
                gauge_sample.stage_millifeet >= 12_500 or weather_sample.wind_milli_knots >= 45_000
            )
            friction_milli = (
                weather_sample.rain_milli_inches_per_hour + weather_sample.wind_milli_knots // 100
            )
            states.append(
                CrossingState(
                    crossing_id=crossing.crossing_id,
                    simulation_time_s=simulation_time_s,
                    status="blocked" if blocked else "open",
                    travel_time_s=round(crossing.nominal_travel_s * (1000 + friction_milli) / 1000),
                    confidence_milli=950,
                    evidence="generated-road-and-crossing-state-v1",
                )
            )
    return states
