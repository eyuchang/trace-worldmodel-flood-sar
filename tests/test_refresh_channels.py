from __future__ import annotations

import pytest

from trace_jepa.refresh.channels import (
    binary_observation_value,
    build_channel_menu,
)


def test_perfect_gauge_has_exact_binary_decision_value() -> None:
    result = binary_observation_value(
        failure_probability=0.10,
        accuracy=1.0,
        failure_loss=100.0,
        safe_loss=15.0,
    )
    # Prior fast loss is 10; perfect information leaves only p * safe_loss.
    assert result.value_of_information == pytest.approx(8.5)
    assert result.clear_probability == pytest.approx(0.9)


def test_no_information_channel_has_zero_value() -> None:
    result = binary_observation_value(
        failure_probability=0.10,
        accuracy=0.5,
        failure_loss=100.0,
        safe_loss=15.0,
    )
    assert result.value_of_information == pytest.approx(0.0)


def test_channel_menu_uses_declared_cost_and_latency_units() -> None:
    gauge, drone = build_channel_menu(
        failure_probability=0.1,
        failure_loss=100.0,
        safe_loss=15.0,
        drone_accuracy=0.92,
        drone_flight_time_s=40.0,
    )
    assert gauge.channel == "gauge_poll"
    assert gauge.cost == pytest.approx(0.2)
    assert gauge.latency_s == pytest.approx(5.0)
    assert drone.channel == "drone_survey"
    assert drone.cost == pytest.approx(5.0 + 40.0 * 0.0009)
    assert drone.latency_s == pytest.approx(40.0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"failure_probability": -0.1, "accuracy": 0.9},
        {"failure_probability": 0.1, "accuracy": 0.49},
    ],
)
def test_invalid_probability_models_are_rejected(kwargs) -> None:
    with pytest.raises(ValueError):
        binary_observation_value(
            **kwargs,
            failure_loss=100.0,
            safe_loss=15.0,
        )
