from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from trace_jepa.evaluation.workloads import (
    EvaluationWorkload,
    load_evaluation_workload,
)


WORKLOAD_ROOT = Path("configs/workloads")


def _valid_payload() -> dict:
    return {
        "schema_version": "trace-evaluation-workload-v1",
        "workload_id": "workload-v1",
        "amendment_id": "amendment-1",
        "partition": "development",
        "regime": "R-B",
        "design_basis": "Late incident with a common baseline.",
        "scheduler_version": "registered-evaluation-workload-v1",
        "event_order": "shocks-gauge-samples-gauge-deliveries-incidents-tick-v1",
        "common_gauge_observations": [
            {
                "observation_id": "gauge-1",
                "route_id": "south_detour",
                "sampled_at": 6420.0,
                "delivered_at": 6425.0,
                "cost": 0.2,
            }
        ],
        "incidents": [
            {
                "incident_id": "later-1",
                "group_id": "group-later-1",
                "scheduled_at": 6443.0,
                "location_label": "Riverside Apartments",
                "position": {"x": 88.0, "y": 66.0},
                "people": 4,
                "severity": 0.55,
                "deadline_s": 7643.0,
                "safe_location_id": "safe_transfer_dock",
            }
        ],
    }


def test_versioned_later_horizon_workload_loads_strictly() -> None:
    workload = load_evaluation_workload(
        "g2_later_horizon_v1.yaml",
        workload_root=WORKLOAD_ROOT,
        expected_amendment_id="g2-workload-amendment-1",
        expected_regime="R-B",
    )
    assert workload.workload_id == "g2-later-horizon-v1"
    assert workload.common_gauge_observations[0].sampled_at == 6420.0
    assert workload.incidents[0].scheduled_at == 6443.0
    assert workload.incidents[0].deadline_s == 7643.0


def test_measurement_amendment_preserves_workload_event_schedule() -> None:
    original = load_evaluation_workload(
        "g2_later_horizon_v1.yaml",
        workload_root=WORKLOAD_ROOT,
        expected_amendment_id="g2-workload-amendment-1",
        expected_regime="R-B",
    )
    corrected = load_evaluation_workload(
        "g2_later_horizon_v2.yaml",
        workload_root=WORKLOAD_ROOT,
        expected_amendment_id="day1-measurement-amendment-2",
        expected_regime="R-B",
    )
    assert corrected.common_gauge_observations == original.common_gauge_observations
    assert corrected.incidents == original.incidents
    assert corrected.event_order == original.event_order
    assert corrected.scheduler_version == original.scheduler_version


@pytest.mark.parametrize(
    "mutation, message",
    [
        (
            lambda payload: payload["incidents"].append(
                payload["incidents"][0].copy()
            ),
            "incident_id values must be unique",
        ),
        (
            lambda payload: payload["common_gauge_observations"].append(
                payload["common_gauge_observations"][0].copy()
            ),
            "observation_id values must be unique",
        ),
        (
            lambda payload: payload.update({"unexpected": True}),
            "Extra inputs",
        ),
    ],
)
def test_workload_rejects_duplicate_and_unknown_fields(mutation, message) -> None:
    payload = _valid_payload()
    mutation(payload)
    with pytest.raises(ValidationError, match=message):
        EvaluationWorkload.model_validate(payload)


@pytest.mark.parametrize(
    "sampled_at, delivered_at", [(0.0, 5.0), (6420.0, 6420.0), (6425.0, 6420.0)]
)
def test_workload_rejects_invalid_gauge_times(
    sampled_at: float, delivered_at: float
) -> None:
    payload = _valid_payload()
    payload["common_gauge_observations"][0]["sampled_at"] = sampled_at
    payload["common_gauge_observations"][0]["delivered_at"] = delivered_at
    with pytest.raises(ValidationError):
        EvaluationWorkload.model_validate(payload)


def test_workload_rejects_deadline_before_incident() -> None:
    payload = _valid_payload()
    payload["incidents"][0]["deadline_s"] = 6443.0
    with pytest.raises(ValidationError, match="deadline"):
        EvaluationWorkload.model_validate(payload)


def test_loader_rejects_path_escape_and_unsafe_yaml(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.yaml"
    outside.write_text(yaml.safe_dump(_valid_payload()), encoding="utf-8")
    with pytest.raises(ValueError, match="escapes"):
        load_evaluation_workload(outside, workload_root=root)

    unsafe = root / "unsafe.yaml"
    unsafe.write_text("!!python/object/apply:os.system ['false']\n", encoding="utf-8")
    with pytest.raises(yaml.YAMLError):
        load_evaluation_workload(unsafe, workload_root=root)


def test_loader_checks_expected_amendment_and_regime() -> None:
    with pytest.raises(ValueError, match="amendment"):
        load_evaluation_workload(
            "g2_later_horizon_v1.yaml",
            workload_root=WORKLOAD_ROOT,
            expected_amendment_id="different-amendment",
        )
    with pytest.raises(ValueError, match="regime"):
        load_evaluation_workload(
            "g2_later_horizon_v1.yaml",
            workload_root=WORKLOAD_ROOT,
            expected_regime="R-C",
        )
