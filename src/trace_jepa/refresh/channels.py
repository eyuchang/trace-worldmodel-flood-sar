from __future__ import annotations

from dataclasses import dataclass

from trace_jepa.refresh.base import ChannelValue


@dataclass(frozen=True)
class BinaryObservationValue:
    clear_probability: float
    value_of_information: float


def binary_observation_value(
    *,
    failure_probability: float,
    accuracy: float,
    failure_loss: float,
    safe_loss: float,
) -> BinaryObservationValue:
    """Exact two-outcome Bayes value for a symmetric binary channel."""

    if not 0.0 <= failure_probability <= 1.0:
        raise ValueError("failure_probability must lie in [0, 1]")
    if not 0.5 <= accuracy <= 1.0:
        raise ValueError("binary channel accuracy must lie in [0.5, 1]")
    if not 0.0 < safe_loss < failure_loss:
        raise ValueError("losses require 0 < safe_loss < failure_loss")

    p = failure_probability
    probability_open_report = (1.0 - p) * accuracy + p * (1.0 - accuracy)
    probability_blocked_report = 1.0 - probability_open_report

    posterior_failure_open = (
        p * (1.0 - accuracy) / probability_open_report
        if probability_open_report > 0.0
        else 0.0
    )
    posterior_failure_blocked = (
        p * accuracy / probability_blocked_report
        if probability_blocked_report > 0.0
        else 1.0
    )
    boundary = safe_loss / failure_loss

    prior_loss = min(p * failure_loss, safe_loss)
    posterior_loss = (
        probability_open_report
        * min(posterior_failure_open * failure_loss, safe_loss)
        + probability_blocked_report
        * min(posterior_failure_blocked * failure_loss, safe_loss)
    )
    clear_probability = 0.0
    if posterior_failure_open <= boundary:
        clear_probability += probability_open_report
    if posterior_failure_blocked <= boundary:
        clear_probability += probability_blocked_report
    return BinaryObservationValue(
        clear_probability=clear_probability,
        value_of_information=max(0.0, prior_loss - posterior_loss),
    )


def build_channel_menu(
    *,
    failure_probability: float,
    failure_loss: float,
    safe_loss: float,
    drone_accuracy: float,
    drone_flight_time_s: float,
    gauge_gate_clear_probability: float | None = None,
    drone_gate_clear_probability: float | None = None,
) -> tuple[ChannelValue, ...]:
    gauge = binary_observation_value(
        failure_probability=failure_probability,
        accuracy=1.0,
        failure_loss=failure_loss,
        safe_loss=safe_loss,
    )
    drone = binary_observation_value(
        failure_probability=failure_probability,
        accuracy=max(0.5, min(1.0, drone_accuracy)),
        failure_loss=failure_loss,
        safe_loss=safe_loss,
    )
    return (
        ChannelValue(
            channel="gauge_poll",
            clear_probability=(
                gauge.clear_probability
                if gauge_gate_clear_probability is None
                else gauge_gate_clear_probability
            ),
            value_of_information=gauge.value_of_information,
            cost=0.2,
            latency_s=5.0,
        ),
        ChannelValue(
            channel="drone_survey",
            clear_probability=(
                drone.clear_probability
                if drone_gate_clear_probability is None
                else drone_gate_clear_probability
            ),
            value_of_information=drone.value_of_information,
            cost=5.0 + max(0.0, drone_flight_time_s) * 0.0009,
            latency_s=max(0.0, drone_flight_time_s),
        ),
    )
