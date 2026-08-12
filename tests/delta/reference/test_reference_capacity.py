from __future__ import annotations

import itertools
import json
from pathlib import Path

import pytest

from trace_reference.generation import generate_reference_scenario
from trace_reference.runtime import build_reference_runtime
from trace_reference.validation import (
    ReferenceCapacityEvaluation,
    evaluate_reference_capacity,
    maximum_divisible_capped_units,
    maximum_strict_matched_units,
)

ROOT = Path(__file__).resolve().parents[3]


def _brute_maximum(
    demand_units: dict[str, int],
    compatible: dict[str, tuple[str, ...]],
) -> int:
    incidents = tuple(sorted(demand_units))
    resources = tuple(sorted({item for values in compatible.values() for item in values}))
    best = 0
    for count in range(len(incidents) + 1):
        for selected in itertools.combinations(incidents, count):
            for assigned in itertools.permutations(resources, count):
                if all(
                    resource in compatible[incident]
                    for incident, resource in zip(selected, assigned, strict=True)
                ):
                    best = max(best, sum(demand_units[item] for item in selected))
                    break
    return best


def test_strict_matching_equals_exhaustive_weighted_matching() -> None:
    incidents = ("incident-a", "incident-b", "incident-c")
    resources = ("resource-1", "resource-2", "resource-3")
    demand = {"incident-a": 4, "incident-b": 3, "incident-c": 2}
    edges = tuple((incident, resource) for incident in incidents for resource in resources)
    for mask in range(1 << len(edges)):
        compatible = {
            incident: tuple(
                resource
                for edge_index, (edge_incident, resource) in enumerate(edges)
                if edge_incident == incident and mask & (1 << edge_index)
            )
            for incident in incidents
        }
        assert maximum_strict_matched_units(demand, compatible) == _brute_maximum(
            demand, compatible
        )


def test_historical_divisible_units_are_distinct_from_physical_concurrency() -> None:
    demand = {("water-rescue", "ISL-01"): 1, ("welfare-check", "ISL-02"): 1}
    compatible = {"resource-1": (("water-rescue", "ISL-01"), ("welfare-check", "ISL-02"))}

    assert maximum_divisible_capped_units(demand, compatible, {"resource-1": 2}) == 2
    assert (
        maximum_strict_matched_units(
            {"incident-a": 1, "incident-b": 1},
            {"incident-a": ("resource-1",), "incident-b": ("resource-1",)},
        )
        == 1
    )


@pytest.fixture(scope="module")
def capacity_result(tmp_path_factory: pytest.TempPathFactory) -> ReferenceCapacityEvaluation:
    scenario = generate_reference_scenario(ROOT, seed=20260812)
    output = tmp_path_factory.mktemp("reference-capacity-runtime")
    run = build_reference_runtime(scenario, output).runtime.run()
    return evaluate_reference_capacity(scenario, run)


def test_capacity_evaluation_is_aggregate_deterministic_and_report_only(
    capacity_result: ReferenceCapacityEvaluation,
) -> None:
    assert capacity_result.window_count == 384
    assert capacity_result.scientific_status == "development-report-only-no-numerical-load-gate"
    assert capacity_result.windows[0].inventory_count > 0
    assert any(item.active_demand_units > 0 for item in capacity_result.windows)
    assert any(
        item.mobilized_inventory_count < item.inventory_count for item in capacity_result.windows
    )
    assert any(item.arrived_inventory_count > 0 for item in capacity_result.windows)
    payload = capacity_result.model_dump_json()
    for forbidden in ("truth_incident_id", "truth_person_id", "RI-", "RP-"):
        assert forbidden not in payload


def test_capacity_evaluation_digest_detects_tampering(
    capacity_result: ReferenceCapacityEvaluation,
) -> None:
    payload = json.loads(capacity_result.model_dump_json())
    payload["evaluation_digest"] = "0" * 64
    with pytest.raises(ValueError, match="digest"):
        ReferenceCapacityEvaluation.model_validate(payload)
