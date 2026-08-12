"""Generate reduced-order meteorology, hydrology, breach, and access state."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence

from trace_jepa.support import canonical_json_bytes
from trace_reference.domain.events import ReferenceEventType, ReferenceEventVisibility
from trace_reference.domain.physical import (
    ReferenceBreachSample,
    ReferenceCrossingRule,
    ReferenceCrossingStateSample,
    ReferenceGaugeParameter,
    ReferenceGaugeStageSample,
    ReferenceMeteorologyPhase,
    ReferencePhysicalParameters,
    ReferencePhysicalSample,
    ReferencePhysicalScenario,
    ReferenceWeatherSample,
)
from trace_reference.runtime.event_store import ReferenceEventLog

_EVALUATION_NOMINAL_RAIN_MILLI_IN = 15_180
_SECONDS_PER_HOUR = 3_600
_CUBIC_FEET_PER_ACRE_FOOT = 43_560


def _phase_at(phases: Sequence[ReferenceMeteorologyPhase], at_s: int) -> ReferenceMeteorologyPhase:
    for phase in phases:
        if phase.start_s <= at_s < phase.end_s:
            return phase
    if at_s == phases[-1].end_s:
        return phases[-1]
    raise ValueError(f"no Reference meteorology phase contains t={at_s}")


def _weather(
    parameters: ReferencePhysicalParameters,
    at_s: int,
    sigma: float,
) -> ReferenceWeatherSample:
    phase = _phase_at(parameters.meteorology_phases, at_s)
    scaled_nominal = round(phase.nominal_rain_milli_in_per_hour * sigma)
    effective = round(
        scaled_nominal
        * parameters.evaluation_rainfall_target_milli_in
        / _EVALUATION_NOMINAL_RAIN_MILLI_IN
    )
    return ReferenceWeatherSample(
        at_s=at_s,
        phase_id=phase.phase_id,
        nominal_rain_milli_in_per_hour=scaled_nominal,
        effective_rain_milli_in_per_hour=effective,
        wind_milli_knots=round(phase.wind_milli_knots * sigma),
        ceiling_ft=phase.ceiling_ft,
        air_operability=phase.air_operability,
    )


def _spring_envelope(at_s: int, center_s: int) -> float:
    distance = (at_s - center_s) / 86_400
    return 1.0 + 0.5 * math.exp(-(distance * distance) / 2.0)


def _lagged_rain_rate(
    weather_by_time: dict[int, ReferenceWeatherSample],
    at_s: int,
    lag_s: int,
) -> int:
    target = at_s - lag_s
    if target < min(weather_by_time):
        return 0
    return weather_by_time.get(
        target, weather_by_time[max(time for time in weather_by_time if time <= target)]
    ).effective_rain_milli_in_per_hour


def _gauge_sample(
    parameter: ReferenceGaugeParameter,
    physical: ReferencePhysicalParameters,
    weather: ReferenceWeatherSample,
    weather_by_time: dict[int, ReferenceWeatherSample],
) -> ReferenceGaugeStageSample:
    angle = (2.0 * math.pi * weather.at_s / physical.m2_period_s) + (
        parameter.tide_phase_milliradians / 1_000
    )
    amplitude = parameter.tide_amplitude_milli_ft * _spring_envelope(
        weather.at_s, physical.perigean_spring_center_s
    )
    tide = round(amplitude * math.sin(angle))
    lagged_rain = _lagged_rain_rate(weather_by_time, weather.at_s, parameter.runoff_lag_s)
    runoff = round(lagged_rain * parameter.runoff_gain_milli_ft_per_inch / 1_000)
    wind_setup = min(800, max(0, round((weather.wind_milli_knots - 15_000) * 800 / 25_000)))
    if weather.at_s < 72_000:
        release = 0
    elif weather.at_s < 93_600:
        release = round(parameter.release_gain_milli_ft * (weather.at_s - 72_000) / 21_600)
    else:
        release = parameter.release_gain_milli_ft
    stage = parameter.baseline_milli_ft + tide + runoff + wind_setup + release
    return ReferenceGaugeStageSample(
        gauge_id=parameter.gauge_id,
        baseline_milli_ft=parameter.baseline_milli_ft,
        tide_milli_ft=tide,
        runoff_milli_ft=runoff,
        wind_setup_milli_ft=wind_setup,
        upstream_release_milli_ft=release,
        stage_milli_ft=stage,
        threshold_status=parameter.threshold_status,
    )


def _breach_sample(
    parameters: ReferencePhysicalParameters,
    at_s: int,
    previous_storage_milli_acre_ft: int,
) -> ReferenceBreachSample:
    breach = parameters.breach
    if at_s < breach.activation_s:
        return ReferenceBreachSample(
            breach_id=breach.breach_id,
            segment_id=breach.segment_id,
            active=False,
            width_milli_ft=0,
            net_inflow_cfs=0,
            stored_milli_acre_ft=0,
            isleton_flood_state="not-threatened",
        )
    elapsed = at_s - breach.activation_s
    width_fraction = min(1.0, elapsed / breach.widening_duration_s)
    width = round(
        breach.initial_width_milli_ft
        + (breach.final_width_milli_ft - breach.initial_width_milli_ft) * width_fraction
    )
    tide_angle = 2.0 * math.pi * at_s / parameters.m2_period_s
    width_ratio = width / breach.final_width_milli_ft
    net_inflow = round(
        width_ratio
        * (breach.mean_inflow_cfs + breach.tidal_inflow_amplitude_cfs * math.sin(tide_angle))
    )
    delta_storage = round(net_inflow * parameters.output_tick_s * 1_000 / _CUBIC_FEET_PER_ACRE_FOOT)
    storage = min(
        breach.storage_capacity_acre_ft * 1_000,
        max(0, previous_storage_milli_acre_ft + delta_storage),
    )
    if elapsed >= breach.one_third_city_delay_s:
        flood_state = "one-third-city-synthetic-extent"
    elif elapsed >= breach.first_street_flooding_delay_s:
        flood_state = "first-street-flooding"
    else:
        flood_state = "not-threatened"
    return ReferenceBreachSample(
        breach_id=breach.breach_id,
        segment_id=breach.segment_id,
        active=True,
        width_milli_ft=width,
        net_inflow_cfs=net_inflow,
        stored_milli_acre_ft=storage,
        isleton_flood_state=flood_state,
    )


def _crossing_state(
    rule: ReferenceCrossingRule,
    at_s: int,
    weather: ReferenceWeatherSample,
    gauges: Sequence[ReferenceGaugeStageSample],
) -> ReferenceCrossingStateSample:
    if rule.rule == "unavailable-because-current-type-unresolved":
        status, reason = (
            "unavailable-unresolved",
            "current crossing type and operability unresolved",
        )
    elif rule.rule == "close-at-t53-after-scripted-breach" and at_s >= 190_800:
        status, reason = "closed", "scripted breach access effect at T+53h"
    elif rule.rule == "ferry-suspend-on-model-wind-or-stage":
        stage = next(item.stage_milli_ft for item in gauges if item.gauge_id == "RVB")
        assert rule.wind_suspend_milli_knots is not None
        assert rule.stage_suspend_milli_ft is not None
        if weather.wind_milli_knots >= rule.wind_suspend_milli_knots:
            status, reason = "suspended", "model wind suspension rule"
        elif stage >= rule.stage_suspend_milli_ft:
            status, reason = "suspended", "model stage suspension rule"
        else:
            status, reason = "open", "model ferry rule permits operation"
    else:
        status, reason = "open", "model crossing rule permits operation"
    return ReferenceCrossingStateSample(
        crossing_id=rule.crossing_id,
        status=status,
        reason=reason,
        source_semantics="model-state-not-current-operability",
    )


def _public_environment_payload(sample: ReferencePhysicalSample) -> dict[str, object]:
    return {
        "weather": sample.weather.model_dump(mode="json"),
        "gauges": [item.model_dump(mode="json") for item in sample.gauges],
        "crossings": [item.model_dump(mode="json") for item in sample.crossings],
    }


def _hidden_physical_payload(sample: ReferencePhysicalSample) -> dict[str, object]:
    return {"breach": sample.breach.model_dump(mode="json")}


def generate_reference_physical_scenario(
    parameters: ReferencePhysicalParameters,
    *,
    sigma: float = 1.0,
) -> ReferencePhysicalScenario:
    """Generate the complete deterministic burn-in and 96-hour physical timeline."""

    if not 0.2 <= sigma <= 2.0:
        raise ValueError("Reference sigma must remain within the registered axis range")
    times = tuple(range(-172_800, 345_600 + parameters.output_tick_s, parameters.output_tick_s))
    weather_by_time = {at_s: _weather(parameters, at_s, sigma) for at_s in times}
    samples: list[ReferencePhysicalSample] = []
    storage = 0
    for at_s in times:
        weather = weather_by_time[at_s]
        gauges = tuple(
            _gauge_sample(gauge, parameters, weather, weather_by_time)
            for gauge in parameters.gauges
        )
        breach = _breach_sample(parameters, at_s, storage)
        storage = breach.stored_milli_acre_ft
        crossings = tuple(
            _crossing_state(rule, at_s, weather, gauges) for rule in parameters.crossing_rules
        )
        samples.append(
            ReferencePhysicalSample(
                at_s=at_s,
                weather=weather,
                gauges=gauges,
                breach=breach,
                crossings=crossings,
            )
        )

    log = ReferenceEventLog()
    previous_crossings: dict[str, str] = {}
    for sample in samples:
        log.append(
            at_s=sample.at_s,
            event_type=ReferenceEventType.HIDDEN_PHYSICAL_TRUTH,
            visibility=ReferenceEventVisibility.HIDDEN_EVALUATION_ONLY,
            payload=_hidden_physical_payload(sample),
        )
        if sample.at_s == parameters.breach.activation_s:
            log.append(
                at_s=sample.at_s,
                event_type=ReferenceEventType.BREACH_ACTIVATED,
                visibility=ReferenceEventVisibility.HIDDEN_EVALUATION_ONLY,
                payload={
                    "breach_id": parameters.breach.breach_id,
                    "segment_id": parameters.breach.segment_id,
                },
            )
        for crossing in sample.crossings:
            if previous_crossings.get(crossing.crossing_id) != crossing.status:
                log.append(
                    at_s=sample.at_s,
                    event_type=ReferenceEventType.CROSSING_STATE_CHANGED,
                    visibility=ReferenceEventVisibility.CONTROLLER_VISIBLE,
                    payload=crossing.model_dump(mode="json"),
                )
                previous_crossings[crossing.crossing_id] = crossing.status
        log.append(
            at_s=sample.at_s,
            event_type=ReferenceEventType.PUBLIC_ENVIRONMENT_SAMPLE,
            visibility=ReferenceEventVisibility.CONTROLLER_VISIBLE,
            payload=_public_environment_payload(sample),
        )
    body = {
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "schema_version": "delta-reference-physical-scenario-v1",
        "parameter_version": parameters.parameter_version,
        "samples": [item.model_dump(mode="json") for item in samples],
        "events": [item.model_dump(mode="json") for item in log.events],
    }
    return ReferencePhysicalScenario(
        **body,
        physical_digest=hashlib.sha256(canonical_json_bytes(body)).hexdigest(),
    )
