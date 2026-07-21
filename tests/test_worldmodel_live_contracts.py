from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from trace_jepa.contracts import PlanPrediction
from trace_jepa.worldmodels.contracts import (
    InferenceProvenance,
    ModelArtifactIdentity,
    ObservationProvenance,
    RouteWorldModelOutput,
    RouteWorldModelRequest,
    RouteWorldModelRequestV2,
    SemanticWorldStatePrediction,
)


def _hash(character: str) -> str:
    return character * 64


def _model_identity(**updates) -> ModelArtifactIdentity:
    values = {
        "family": "vjepa2.1",
        "integration_kind": "official-upstream",
        "source_repository": "https://github.com/facebookresearch/vjepa2",
        "source_commit": "a" * 40,
        "encoder_version": "vjepa2.1-vitb",
        "encoder_checkpoint_sha256": _hash("1"),
        "dynamics_version": "vjepa2.1-predictor",
        "dynamics_checkpoint_sha256": _hash("2"),
        "outcome_head_version": "flood-semantic-probe-v2",
        "outcome_head_sha256": _hash("3"),
        "calibration_version": "flood-calibration-v2",
        "calibration_artifact_sha256": _hash("4"),
        "training_snapshot_sha256": _hash("5"),
        "preprocessing_version": "vjepa2.1-384-v1",
        "feature_schema_version": "vjepa-spatiotemporal-v2",
        "action_schema_version": "flood-actions-v2",
        "supported_action_types": ("dispatch_rescue_boat",),
    }
    values.update(updates)
    return ModelArtifactIdentity(**values)


def _request_v1() -> dict[str, object]:
    return {
        "plan_id": "plan-1",
        "route_id": "north",
        "asset_id": "boat-1",
        "action_type": "dispatch_rescue_boat",
        "belief_status": "open",
        "belief_confidence": 0.8,
        "observation_age_s": 10.0,
        "observed_depth_m": 0.3,
        "projected_depth_m": 0.4,
        "route_closure_depth_m": 0.72,
        "route_susceptibility": 1.0,
        "travel_time_s": 600.0,
        "water_rise_rate": 0.00015,
        "rain_intensity": 0.4,
        "upstream_inflow": 0.3,
        "weather_forecast": 0.25,
        "sensor_noise": 0.1,
        "packet_loss": 0.02,
        "declared_ood_severity": 0.2,
        "sensor_quality": 0.9,
        "asset_resource": 0.95,
        "asset_weather_tolerance": 0.8,
    }


def _request_v2(model: ModelArtifactIdentity) -> RouteWorldModelRequestV2:
    return RouteWorldModelRequestV2(
        **_request_v1(),
        visual_observation_id="simobs-a1",
        visual_observation_hash=_hash("6"),
        visual_frames_sha256=_hash("7"),
        visual_sensor_version="flood-camera-v2",
        visual_observed_at=90.0,
        expected_model_bundle_sha256=model.bundle_sha256,
        prediction_horizons_s=(60.0, 180.0),
        action_parameters={"duration_s": 600.0, "route_choice": "north"},
    )


def test_v1_request_contract_remains_unchanged() -> None:
    request = RouteWorldModelRequest(**_request_v1())
    assert request.request_schema_version == "route-world-model-request-v1"
    assert "visual_observation_hash" not in request.model_dump()


def test_model_identity_computes_and_verifies_complete_bundle_hash() -> None:
    model = _model_identity()
    assert len(model.bundle_sha256) == 64
    assert _model_identity(bundle_sha256=model.bundle_sha256) == model

    with pytest.raises(ValidationError, match="bundle hash"):
        _model_identity(bundle_sha256=_hash("f"))
    with pytest.raises(ValidationError, match="declared together"):
        _model_identity(dynamics_checkpoint_sha256=None)


def test_model_identity_rejects_duplicate_or_unsorted_actions() -> None:
    with pytest.raises(ValidationError, match="unique and sorted"):
        _model_identity(supported_action_types=("z", "a", "a"))


def test_live_request_rejects_audit_truth_and_noncanonical_parameters() -> None:
    model = _model_identity()
    request = _request_v2(model)
    assert request.visual_observation_hash == _hash("6")

    payload = request.model_dump()
    payload["action_parameters"] = {"audit_snapshot": {"water_depth": 0.7}}
    with pytest.raises(ValidationError, match="audit-only"):
        RouteWorldModelRequestV2(**payload)

    payload["action_parameters"] = {"opaque": object()}
    with pytest.raises(ValidationError, match="canonical JSON"):
        RouteWorldModelRequestV2(**payload)

    payload = request.model_dump()
    payload["audit_snapshot"] = {"water_depth": 0.7}
    with pytest.raises(ValidationError, match="Extra inputs"):
        RouteWorldModelRequestV2(**payload)


def test_live_request_requires_strictly_increasing_unique_horizons() -> None:
    request = _request_v2(_model_identity())
    with pytest.raises(ValidationError, match="unique and increasing"):
        RouteWorldModelRequestV2(**(request.model_dump() | {"prediction_horizons_s": (180, 60)}))


def test_atomic_output_binds_model_observation_inference_and_semantics() -> None:
    model = _model_identity()
    request = _request_v2(model)
    observation = ObservationProvenance(
        observation_id=request.visual_observation_id,
        observation_sha256=request.visual_observation_hash,
        frames_sha256=request.visual_frames_sha256,
        controller_manifest_sha256=_hash("8"),
        sensor_model_version=request.visual_sensor_version,
        observed_at=request.visual_observed_at,
        study_partition="development-v2",
    )
    now = datetime.now(timezone.utc)
    inference = InferenceProvenance(
        inference_id="inference-1",
        request_sha256=_hash("9"),
        model_bundle_sha256=model.bundle_sha256,
        output_sha256=_hash("b"),
        requested_at=now,
        started_at=now + timedelta(milliseconds=1),
        completed_at=now + timedelta(milliseconds=4),
        wall_duration_ms=3.0,
        cache_hit=False,
        device_type="cuda",
        precision="bfloat16",
        environment_manifest_sha256=_hash("c"),
    )
    state = SemanticWorldStatePrediction(
        horizons_s=(60.0, 180.0),
        water_depth_m=(0.4, 0.5),
        obstruction_probability=(0.1, 0.2),
        flow_severity=(0.3, 0.4),
        visibility=(0.8, 0.7),
        operational_state={"asset_resource": 0.9},
        epistemic_uncertainty=(0.1, 0.2),
        support=(0.9, 0.8),
        ood_score=(0.05, 0.1),
    )
    prediction = PlanPrediction(
        plan_id="plan-1",
        success_probability=0.8,
        arrival_time_s=600.0,
        hazard_score=0.2,
        resource_margin=0.5,
        model_support=0.8,
        out_of_distribution_score=0.1,
        uncertainty=0.2,
        rollout_horizon=2,
    )
    output = RouteWorldModelOutput(
        semantic_state=state,
        prediction=prediction,
        planner_version="route-evaluator-v2",
        model=model,
        observation=observation,
        inference=inference,
        prediction_timestamp=100.0,
        valid_until=180.0,
    )
    assert output.model.bundle_sha256 == output.inference.model_bundle_sha256

    mismatched = inference.model_copy(update={"model_bundle_sha256": _hash("d")})
    with pytest.raises(ValidationError, match="bundle link"):
        RouteWorldModelOutput(**(output.model_dump() | {"inference": mismatched}))


def test_semantic_state_rejects_mismatched_or_unbounded_vectors() -> None:
    values = {
        "horizons_s": (60.0, 180.0),
        "water_depth_m": (0.4, 0.5),
        "obstruction_probability": (0.1, 0.2),
        "flow_severity": (0.3, 0.4),
        "visibility": (0.8, 0.7),
        "epistemic_uncertainty": (0.1, 0.2),
        "support": (0.9, 0.8),
        "ood_score": (0.05, 0.1),
    }
    with pytest.raises(ValidationError, match="horizon count"):
        SemanticWorldStatePrediction(**(values | {"visibility": (0.8,)}))
    with pytest.raises(ValidationError, match=r"in \[0, 1\]"):
        SemanticWorldStatePrediction(**(values | {"ood_score": (0.05, 1.1)}))
