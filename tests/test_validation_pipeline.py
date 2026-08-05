from __future__ import annotations

from pathlib import Path

import pytest

from trace_jepa.evaluation.validation import (
    VALIDATION_SEEDS,
    _quantile_type7,
    load_validation_config,
    select_operating_points,
    summarize_configurations,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_validation_config_is_exactly_the_registered_19_by_25_grid() -> None:
    config, path = load_validation_config(
        "validation_r_b_v1.yaml", repository_root=REPOSITORY_ROOT
    )
    assert path.name == "validation_r_b_v1.yaml"
    assert config.seed_start == 101
    assert config.seed_end == 125
    assert len(config.policy_specs) == 19
    assert config.expected_cells == 475
    assert config.policy_specs[0] == "none"
    assert config.policy_specs[-1] == "adaptive:7"


def test_type7_quantiles_are_declared_and_deterministic() -> None:
    values = [0.0, 1.0, 2.0, 3.0, 4.0]
    assert _quantile_type7(values, 0.25) == pytest.approx(1.0)
    assert _quantile_type7(values, 0.50) == pytest.approx(2.0)
    assert _quantile_type7(values, 0.75) == pytest.approx(3.0)
    assert _quantile_type7(values, 1.00) == pytest.approx(4.0)


def _cells(policy: str, *, cost: float, stale: int, executed: int) -> list[dict]:
    return [
        {
            "policy": policy,
            "seed": seed,
            "verification_cost": cost,
            "executed": executed,
            "executed_stale": stale,
            "proposed": max(executed, 1),
        }
        for seed in VALIDATION_SEEDS
    ]


def test_operating_point_selection_excludes_undefined_staleness_and_ties_by_cost() -> None:
    cells = (
        _cells("none", cost=0.2, stale=1, executed=2)
        + _cells("fixed-k:5", cost=4.0, stale=0, executed=0)
        + _cells("fixed-k:15", cost=3.0, stale=1, executed=4)
        + _cells("fixed-k:45", cost=2.0, stale=1, executed=4)
        + _cells("clock:0.1", cost=1.0, stale=1, executed=2)
        + _cells("adaptive:1", cost=1.0, stale=1, executed=2)
    )
    summaries = summarize_configurations(cells)
    selected = select_operating_points(summaries, {"B1": 4.0})["B1"]
    assert selected["fixed_k"]["policy"] == "fixed-k:45"
    assert selected["fixed_k"]["pooled_stale_execution_rate"] == pytest.approx(0.25)
    assert selected["no_refresh"]["policy"] == "none"
    assert selected["validity_clock"]["policy"] == "clock:0.1"
    assert selected["adaptive"]["policy"] == "adaptive:1"
