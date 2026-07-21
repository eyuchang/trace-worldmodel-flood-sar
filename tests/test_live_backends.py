from __future__ import annotations

import numpy as np
import pytest

from trace_jepa.worldmodels.contracts import (
    ModelArtifactIdentity,
    ObservationProvenance,
    RouteWorldModelRequestV2,
)
from trace_jepa.worldmodels.dinowm import (
    DINOWMPredictorConfig,
    build_dinowm_predictor,
)
from trace_jepa.worldmodels.live_backends import (
    DeterministicFeatureControlBackend,
    DINOWMPredictiveLatentBackend,
    VJEPAPredictiveLatentBackend,
    simple_visual_features,
)


torch = pytest.importorskip("torch")


def _hash(character: str) -> str:
    return character * 64


def _identity(family: str, actions: tuple[str, ...]) -> ModelArtifactIdentity:
    return ModelArtifactIdentity(
        family=family,
        integration_kind=(
            "official-upstream"
            if family == "vjepa2.1"
            else "upstream-inspired-adaptation"
        ),
        source_repository="https://example.invalid/upstream",
        source_commit="a" * 40,
        encoder_version=f"{family}-encoder",
        encoder_checkpoint_sha256=_hash("1"),
        dynamics_version=f"{family}-predictor",
        dynamics_checkpoint_sha256=_hash("2"),
        outcome_head_version="not-applicable-supporting",
        outcome_head_sha256=_hash("3"),
        calibration_version="not-applicable-supporting",
        calibration_artifact_sha256=_hash("4"),
        training_snapshot_sha256=_hash("5"),
        preprocessing_version=f"{family}-preprocess-v1",
        feature_schema_version=f"{family}-latent-v1",
        action_schema_version="flood-actions-dynamic-v1",
        supported_action_types=tuple(sorted(actions)),
    )


def _control_identity(control: str) -> ModelArtifactIdentity:
    return ModelArtifactIdentity(
        family=f"{control}-feature-control",
        integration_kind="deterministic-control",
        source_repository="https://example.invalid/trace",
        source_commit="a" * 40,
        encoder_version=f"{control}-features-v1",
        encoder_checkpoint_sha256=_hash("1"),
        outcome_head_version="not-applicable-supporting",
        outcome_head_sha256=_hash("3"),
        calibration_version="not-applicable-supporting",
        calibration_artifact_sha256=_hash("4"),
        training_snapshot_sha256=_hash("5"),
        preprocessing_version=f"{control}-preprocess-v1",
        feature_schema_version=f"{control}-features-v1",
        action_schema_version="flood-actions-dynamic-v1",
        supported_action_types=("dispatch_rescue_boat",),
    )


def _request(identity: ModelArtifactIdentity, action: str) -> RouteWorldModelRequestV2:
    observation = ObservationProvenance(
        observation_id="simobs-" + "a" * 24,
        observation_sha256=_hash("6"),
        frames_sha256=_hash("7"),
        controller_manifest_sha256=_hash("8"),
        sensor_model_version="flood-camera-v2",
        observed_at=0.0,
        study_partition="development",
    )
    return RouteWorldModelRequestV2(
        plan_id="plan-1",
        route_id="north",
        asset_id="boat-1",
        action_type=action,
        belief_status="open",
        belief_confidence=0.8,
        observation_age_s=0.0,
        observed_depth_m=0.2,
        projected_depth_m=0.3,
        route_closure_depth_m=0.72,
        route_susceptibility=1.0,
        travel_time_s=600.0,
        water_rise_rate=0.0001,
        rain_intensity=0.2,
        upstream_inflow=0.2,
        weather_forecast=0.2,
        sensor_noise=0.1,
        packet_loss=0.0,
        declared_ood_severity=0.0,
        sensor_quality=0.9,
        asset_resource=0.9,
        asset_weather_tolerance=0.8,
        visual_observation_id=observation.observation_id,
        visual_observation_hash=observation.observation_sha256,
        visual_frames_sha256=observation.frames_sha256,
        visual_sensor_version=observation.sensor_model_version,
        visual_observed_at=observation.observed_at,
        expected_model_bundle_sha256=identity.bundle_sha256,
        prediction_horizons_s=(60.0, 180.0, 600.0),
    )


class _VJEPAPredictor:
    device = "cpu"

    def predict_future_tokens(self, frames: np.ndarray) -> np.ndarray:
        return np.full((1, 6, 4), frames.mean() / 255.0, dtype=np.float32)


class _DINOEncoder:
    def encode_images(self, images: np.ndarray) -> np.ndarray:
        means = images.mean(axis=(1, 2, 3), keepdims=False).astype(np.float32)
        return np.repeat(means[:, None, None], 4 * 8, axis=1).reshape(len(images), 4, 8)


def test_vjepa_live_backend_runs_official_predictive_seam_without_semantic_claims() -> None:
    identity = _identity("vjepa2.1", ("dispatch_rescue_boat",))
    backend = VJEPAPredictiveLatentBackend(
        predictor=_VJEPAPredictor(),
        identity=identity,
        environment_manifest_sha256=_hash("9"),
    )
    frames = np.ones((4, 32, 32, 3), dtype=np.uint8)
    output = backend.infer(
        frames=frames,
        request=_request(identity, "dispatch_rescue_boat"),
    )
    assert output.semantic_state is None
    assert output.latent_tokens.shape == (1, 6, 4)
    assert output.diagnostics["action_conditioned"] is False


def test_dinowm_live_backend_uses_action_and_preserves_spatial_tokens() -> None:
    actions = ("deploy_ground_team", "dispatch_rescue_boat")
    identity = _identity("dinowm", actions)
    config = DINOWMPredictorConfig(
        patch_count=4,
        feature_dim=8,
        action_count=2,
        predictor_dim=8,
        depth=1,
        heads=2,
        mlp_dim=16,
        dropout=0.0,
    )
    torch.manual_seed(7)
    model = build_dinowm_predictor(config)
    with torch.no_grad():
        model.action_embedding.weight[0].fill_(0.0)
        model.action_embedding.weight[1].copy_(torch.arange(8, dtype=torch.float32))
        model.delta_projection.weight.copy_(torch.eye(8))
    backend = DINOWMPredictiveLatentBackend(
        encoder=_DINOEncoder(),
        predictor=model,
        predictor_config=config,
        action_names=actions,
        identity=identity,
        environment_manifest_sha256=_hash("9"),
        device="cpu",
    )
    frames = np.ones((3, 32, 32, 3), dtype=np.uint8)
    first = backend.infer(
        frames=frames,
        request=_request(identity, "deploy_ground_team"),
    )
    second = backend.infer(
        frames=frames,
        request=_request(identity, "dispatch_rescue_boat"),
    )
    assert first.semantic_state is None
    assert first.latent_tokens.shape == (1, 4, 8)
    assert not np.array_equal(first.latent_tokens, second.latent_tokens)
    assert second.diagnostics["action_index"] == 1

def test_deterministic_feature_controls_are_fixed_and_parameter_free() -> None:
    frames = np.zeros((2, 8, 8, 3), dtype=np.uint8)
    frames[1, :, :, 0] = 255
    simple_identity = _control_identity("simple_visual")
    simple = DeterministicFeatureControlBackend(
        control="simple_visual",
        identity=simple_identity,
        environment_manifest_sha256=_hash("9"),
    ).infer(
        frames=frames,
        request=_request(simple_identity, "dispatch_rescue_boat"),
    )
    structured_identity = _control_identity("structured")
    structured = DeterministicFeatureControlBackend(
        control="structured",
        identity=structured_identity,
        environment_manifest_sha256=_hash("9"),
    ).infer(
        frames=frames,
        request=_request(structured_identity, "dispatch_rescue_boat"),
    )
    assert simple.latent_tokens.shape == (1, 1, 10)
    assert np.array_equal(simple.latent_tokens[0, 0], simple_visual_features(frames))
    assert structured.latent_tokens.shape[-1] == len(
        _request(structured_identity, "dispatch_rescue_boat").structured_features
    )
    assert simple.diagnostics["fitted_parameters"] is False
    assert structured.diagnostics["fitted_parameters"] is False
