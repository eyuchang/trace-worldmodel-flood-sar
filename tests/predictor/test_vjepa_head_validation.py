"""Exhaustive schema checks for the separately calibrated V-JEPA flood head."""

from __future__ import annotations

import numpy as np
import pytest

from trace_jepa.predictor.vjepa_adapter import CalibratedVJEPAHead, _stable_sigmoid


def _head(**updates: object) -> CalibratedVJEPAHead:
    values: dict[str, object] = {
        "weights": np.zeros((3, 7), dtype=np.float64),
        "bias": np.zeros(7, dtype=np.float64),
        "feature_mean": np.zeros(3, dtype=np.float64),
        "feature_std": np.ones(3, dtype=np.float64),
        "action_names": ("dispatch_rescue_boat",),
        "metadata": {
            "predictor_version": "head-v1",
            "calibration_version": "cal-v1",
            "calibration_hash": "1" * 64,
            "training_snapshot": "training-v1",
            "encoder_version": "encoder-v1",
            "encoder_checkpoint_hash": "2" * 64,
            "feature_schema_version": "action-prefix-features-v2",
            "action_schema_version": "delta-response-actions-v2",
        },
        "checkpoint_hash": "3" * 64,
    }
    values.update(updates)
    return CalibratedVJEPAHead(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"weights": np.zeros((3, 6))}, "seven outputs"),
        ({"bias": np.zeros(6)}, "bias must have seven"),
        ({"feature_mean": np.zeros(2)}, "mean does not match"),
        ({"feature_std": np.ones(2)}, "scale does not match"),
        ({"feature_std": np.asarray([1.0, 0.0, 1.0])}, "must be positive"),
        ({"weights": np.full((3, 7), np.nan)}, "non-finite"),
        ({"metadata": {}}, "metadata is incomplete"),
    ],
)
def test_vjepa_head_rejects_malformed_calibration(updates: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _head(**updates).validate()


def test_vjepa_sigmoid_rejects_non_finite_and_is_stable() -> None:
    with pytest.raises(ValueError, match="non-finite"):
        _stable_sigmoid(float("inf"))
    assert _stable_sigmoid(1_000.0) == 1.0
    assert _stable_sigmoid(-1_000.0) == 0.0
