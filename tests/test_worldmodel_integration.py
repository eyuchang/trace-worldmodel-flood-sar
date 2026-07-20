from __future__ import annotations

import numpy as np
import pytest
from pathlib import Path

from trace_jepa.contracts import (
    ActionInstance,
    Claim,
    ClaimLayer,
    PlanCandidate,
    PlanPrediction,
    WorldModelEvidence,
)
from trace_jepa.runtime import PolicyConfig, PolicyEngine
from trace_jepa.worldmodels.adapters import (
    CachedActionRouteFeatureProvider,
    CachedRouteFeatureProvider,
    FeatureObservation,
    LinearActionHead,
    VJEPARouteWorldModel,
)
from trace_jepa.worldmodels.calibration import IsotonicCalibrator
from trace_jepa.worldmodels.contracts import (
    RouteWorldModelRequest,
    WorldModelInputUnavailable,
    WorldModelProvenance,
)
from trace_jepa.worldmodels.dataset import generate_controlled_episodes, write_feature_dataset
from trace_jepa.worldmodels.rendering import ControlledVisualCue, render_controlled_route_clip
from trace_jepa.worldmodels.training import (
    _shuffle_visual_by_episode,
    train_development_models,
)
from trace_jepa.worldmodels.versioning import GuardedPolicyEngine, ModelQualification, ModelRegistry
from trace_jepa.workbench.engine import DynamicRun


SCENARIO = Path(__file__).parents[1] / "configs" / "scenarios" / "riverside_flood_v1.yaml"


def test_shuffled_visual_control_preserves_episode_unit() -> None:
    arrays = {
        "episode_ids": np.asarray(["a", "a", "b", "b", "c", "c"]),
        "visual": np.asarray([[1.0], [1.0], [2.0], [2.0], [3.0], [3.0]]),
    }
    shuffled = _shuffle_visual_by_episode(
        arrays, np.arange(6), np.random.default_rng(4)
    )
    assert shuffled.shape == (6, 1)
    assert np.array_equal(shuffled[::2], shuffled[1::2])
    assert sorted(shuffled[::2, 0].tolist()) == [1.0, 2.0, 3.0]


def request() -> RouteWorldModelRequest:
    return RouteWorldModelRequest(
        plan_id="plan-1",
        route_id="north",
        asset_id="boat-1",
        belief_status="open",
        belief_confidence=0.8,
        observation_age_s=10.0,
        observed_depth_m=0.3,
        projected_depth_m=0.4,
        route_closure_depth_m=0.72,
        route_susceptibility=1.0,
        travel_time_s=600.0,
        water_rise_rate=0.00015,
        rain_intensity=0.4,
        upstream_inflow=0.3,
        weather_forecast=0.25,
        sensor_noise=0.1,
        packet_loss=0.02,
        declared_ood_severity=0.2,
        sensor_quality=0.9,
        asset_resource=0.95,
        asset_weather_tolerance=0.8,
    )


def test_rendered_control_clip_is_deterministic_and_visually_sensitive() -> None:
    cue = ControlledVisualCue(0.5, 0.4, 0.8, 17)
    first = render_controlled_route_clip(request(), cue, num_frames=4, size=32)
    second = render_controlled_route_clip(request(), cue, num_frames=4, size=32)
    changed = render_controlled_route_clip(
        request(), ControlledVisualCue(0.9, 0.4, 0.8, 17), num_frames=4, size=32
    )
    assert np.array_equal(first.frames, second.frames)
    assert first.observation_hash == second.observation_hash
    assert first.observation_hash != changed.observation_hash


def test_isotonic_calibration_is_monotone() -> None:
    calibrator = IsotonicCalibrator.fit(
        np.array([0.1, 0.2, 0.3, 0.4]), np.array([0.0, 1.0, 0.0, 1.0])
    )
    transformed = calibrator.transform(np.linspace(0.0, 1.0, 30))
    assert np.all(np.diff(transformed) >= 0.0)
    assert np.all((transformed >= 0.0) & (transformed <= 1.0))


def test_isotonic_calibration_aggregates_identical_scores() -> None:
    calibrator = IsotonicCalibrator.fit(np.full(4, 0.4), np.array([0.0, 1.0, 0.0, 1.0]))
    assert calibrator.thresholds.tolist() == [0.4]
    assert calibrator.transform(0.4).item() == 0.5


def test_fused_adapter_emits_versioned_prediction() -> None:
    structured_dim = len(request().structured_features)
    action_names = ("dispatch_rescue_boat",)
    weights = np.zeros((structured_dim + 2 + len(action_names) + 1, 4))
    weights[-1] = np.array([0.8, 0.4, 0.2, 0.6])
    head = LinearActionHead(
        weights=weights,
        structured_mean=np.zeros(structured_dim),
        structured_std=np.ones(structured_dim),
        visual_mean=np.zeros(2),
        visual_std=np.ones(2),
        training_min=np.full(structured_dim + 2 + len(action_names), -10.0),
        training_max=np.full(structured_dim + 2 + len(action_names), 10.0),
        support_center=np.zeros(structured_dim + 2 + len(action_names)),
        support_scale=np.ones(structured_dim + 2 + len(action_names)),
        residual_rmse=np.full(4, 0.05),
        action_names=action_names,
        calibrator=IsotonicCalibrator(np.array([0.0, 1.0]), np.array([0.0, 1.0])),
        metadata={
            "encoder_version": "vjepa-test",
            "encoder_checkpoint_sha256": "encoder-hash",
            "predictor_version": "flood-head-test",
            "calibration_version": "calibration-test",
            "training_snapshot": "snapshot-test",
            "semantic_probe_versions": ["route-probe-test"],
        },
        checkpoint_sha256="head-hash",
    )
    head.validate()

    class Features:
        def features(self, model_request):
            return FeatureObservation(
                vector=np.array([0.1, 0.2]),
                observation_hash="observation-hash",
                encoder_version="vjepa-test",
                encoder_checkpoint_sha256="encoder-hash",
            )

    model = VJEPARouteWorldModel(Features(), head)
    prediction = model.predict(request())
    assert prediction.plan_id == "plan-1"
    assert prediction.success_probability == 1.0
    assert prediction.arrival_time_s == 720.0
    assert model.last_observation_hash == "observation-hash"


def test_cached_feature_provider_rejects_missing_and_unsafe_identifiers(tmp_path) -> None:
    provider = CachedRouteFeatureProvider(
        tmp_path,
        encoder_version="encoder-v1",
        encoder_checkpoint_sha256="encoder-hash",
    )
    with np.testing.assert_raises(WorldModelInputUnavailable):
        provider.features(request())
    unsafe = request().model_copy(update={"visual_observation_id": "../outside"})
    with np.testing.assert_raises(WorldModelInputUnavailable):
        provider.features(unsafe)


def test_cached_action_feature_provider_is_action_specific_and_fail_closed(tmp_path) -> None:
    model_request = request().model_copy(
        update={"visual_observation_id": "simobs-" + "a" * 24}
    )
    cache_id = f"{model_request.visual_observation_id}--{model_request.action_type}"
    np.savez_compressed(
        tmp_path / f"{cache_id}.npz",
        feature=np.asarray([0.2, 0.4], dtype=np.float32),
        observation_hash=np.asarray("observation-hash"),
        action_type=np.asarray(model_request.action_type),
    )
    provider = CachedActionRouteFeatureProvider(
        tmp_path,
        encoder_version="dinowm-v1",
        encoder_checkpoint_sha256="dynamics-hash",
    )
    feature = provider.features(model_request)
    assert feature.vector.tolist() == pytest.approx([0.2, 0.4])
    unsupported = model_request.model_copy(update={"action_type": "different-action"})
    with pytest.raises(WorldModelInputUnavailable, match="absent"):
        provider.features(unsupported)


def evidence(version: str, calibration: str = "cal-v1") -> WorldModelEvidence:
    return WorldModelEvidence(
        encoder_version="encoder-v1",
        fusion_version="fusion-v1",
        predictor_version=version,
        semantic_probe_versions=("probe-v1",),
        training_snapshot="snapshot-v1",
        observation_window_hash="observation-hash",
        fleet_state_hash="fleet-hash",
        candidate_plan_id="plan-1",
        action_schema_version="actions-v1",
        rollout_horizon=1,
        predicted_claims=("route is safe",),
        uncertainty=0.1,
        model_support=0.9,
        out_of_distribution_score=0.1,
        rollout_consistency=0.9,
        calibration_version=calibration,
        observation_age_s=1.0,
    )


def test_version_guard_prevents_unsafe_clear_after_replacement() -> None:
    base = PolicyEngine(
        PolicyConfig(
            policy_version="base-v1",
            min_model_support=0.5,
            max_ood_score=0.5,
            max_uncertainty=0.5,
            max_rollout_horizon=4,
            max_observation_age_s=60.0,
        )
    )
    registry = ModelRegistry()
    for version in ("old", "new"):
        registry.install(
            ModelQualification(
                predictor_version=version,
                predictor_checkpoint_sha256=f"{version}-hash",
                calibration_version="cal-v1",
                manifest_sha256=f"{version}-manifest",
                qualified_action_types=("dispatch_rescue_boat",),
                qualified=True,
            ),
            make_current=version == "old",
        )
    registry.replace("new")
    guard = GuardedPolicyEngine(base, registry)
    claim = Claim(layer=ClaimLayer.PREDICTIVE, text="route is safe")

    stale = guard.evaluate(
        claim,
        evidence("old"),
        action_name="dispatch_rescue_boat",
        reversible=False,
        authority_present=True,
    )
    current = guard.evaluate(
        claim,
        evidence("new"),
        action_name="dispatch_rescue_boat",
        reversible=False,
        authority_present=True,
    )
    assert stale.decision.value == "hold"
    assert "superseded_model_version" in stale.failed_gates
    assert current.decision.value == "clear"
    assert registry.verify_chain()


def test_default_controller_route_prediction_remains_at_surrogate_golden_value(tmp_path) -> None:
    run = DynamicRun(scenario_path=SCENARIO, artifact_root=tmp_path / "golden")
    prediction = run.controller._route_prediction(
        run.state,
        plan_id="golden",
        route_id="north_channel",
        asset_id="rescue_boat_1",
    )
    assert prediction.success_probability == 0.24072307106559993
    assert prediction.hazard_score == 0.74497212352
    assert prediction.model_support == 0.034729776000000004


def test_controller_injects_only_declared_controller_view_into_world_model(tmp_path) -> None:
    class SpyModel:
        provenance = WorldModelProvenance(
            encoder_version="encoder-spy",
            encoder_checkpoint_sha256="encoder-hash",
            predictor_version="predictor-spy",
            predictor_checkpoint_sha256="predictor-hash",
            calibration_version="calibration-spy",
            training_snapshot="snapshot-spy",
            semantic_probe_versions=("probe-spy",),
            supported_action_types=("dispatch_rescue_boat",),
        )

        def __init__(self):
            self.requests = []
            self.last_observation_hash = "spy-observation"

        def predict(self, model_request):
            self.requests.append(model_request)
            return PlanPrediction(
                plan_id=model_request.plan_id,
                success_probability=0.7,
                arrival_time_s=model_request.travel_time_s,
                hazard_score=0.2,
                resource_margin=0.5,
                model_support=0.8,
                out_of_distribution_score=0.1,
                uncertainty=0.1,
                rollout_horizon=2,
            )

    model = SpyModel()
    run = DynamicRun(
        scenario_path=SCENARIO,
        artifact_root=tmp_path / "injected",
        route_world_model=model,
    )
    run.state.truth.weather_severity = 1.0
    prediction = run.controller._route_prediction(
        run.state,
        plan_id="injected",
        route_id="north_channel",
        asset_id="rescue_boat_1",
    )
    assert prediction.success_probability == 0.7
    assert model.requests[0].weather_forecast == run.state.config.s5.sector_weather
    assert "truth" not in model.requests[0].model_dump()
    assert run.controller._route_observation_hashes["injected"] == "spy-observation"
    plan = PlanCandidate(
        plan_id="injected",
        name="injected route",
        actions=(
            ActionInstance(
                action_type="dispatch_rescue_boat",
                actor_id="rescue_boat_1",
                route_id="north_channel",
            ),
        ),
        utility=1.0,
        reversible_first_action=False,
        metadata={"route_id": "north_channel"},
    )
    model_evidence = run.controller._evidence(
        run.state,
        plan,
        prediction,
        Claim(layer=ClaimLayer.PREDICTIVE, text="route prediction"),
    )
    assert model_evidence.encoder_version == "encoder-spy"
    assert model_evidence.predictor_version == "predictor-spy"
    assert model_evidence.observation_window_hash == "spy-observation"
    assert (
        model_evidence.reachability_evidence["model_provenance"]["predictor_checkpoint_sha256"]
        == "predictor-hash"
    )


def test_controller_fails_closed_when_visual_evidence_is_missing(tmp_path) -> None:
    class MissingModel:
        provenance = WorldModelProvenance(
            encoder_version="encoder-missing",
            encoder_checkpoint_sha256="encoder-hash",
            predictor_version="predictor-missing",
            predictor_checkpoint_sha256="predictor-hash",
            calibration_version="calibration-missing",
            training_snapshot="snapshot-missing",
            semantic_probe_versions=("probe-missing",),
            supported_action_types=("dispatch_rescue_boat",),
        )

        def predict(self, model_request):
            raise WorldModelInputUnavailable("no synchronized clip")

    run = DynamicRun(
        scenario_path=SCENARIO,
        artifact_root=tmp_path / "missing",
        route_world_model=MissingModel(),
    )
    prediction = run.controller._route_prediction(
        run.state,
        plan_id="missing",
        route_id="north_channel",
        asset_id="rescue_boat_1",
    )
    assert prediction.model_support == 0.0
    assert prediction.out_of_distribution_score == 1.0
    assert "fail_closed_without_surrogate_fallback" in prediction.assumptions


def test_dynamic_controller_preserves_additive_model_guard(tmp_path) -> None:
    registry = ModelRegistry()
    run = DynamicRun(
        scenario_path=SCENARIO,
        artifact_root=tmp_path / "guarded-run",
        model_registry=registry,
    )
    run.controller._sync_gate_policy(run.state)
    assert isinstance(run.runtime.policy, GuardedPolicyEngine)
    assert run.runtime.policy.config.policy_version.endswith("+model-version-guard-v1")


def test_episode_split_and_training_pipeline_are_leak_resistant(tmp_path) -> None:
    episodes = generate_controlled_episodes(80, data_seed=101, split_seed=202)
    feature_by_episode = {
        episode.episode_id: np.asarray(
            [
                episode.cue.surface_debris,
                episode.cue.flow_turbulence,
                episode.cue.visibility,
            ],
            dtype=np.float32,
        )
        for episode in episodes
        if episode.split != "test"
    }
    hash_by_episode = {episode_id: f"hash-{episode_id}" for episode_id in feature_by_episode}
    dataset = tmp_path / "features.npz"
    write_feature_dataset(
        dataset,
        episodes,
        feature_by_episode,
        hash_by_episode,
        encoder_manifest={
            "version": "unit-encoder",
            "checkpoint_sha256": "unit-hash",
            "smoke_only": True,
        },
        include_test=False,
        data_seed=101,
        split_seed=202,
    )
    report = train_development_models(
        dataset,
        tmp_path / "head.npz",
        tmp_path / "report.json",
        seed=303,
    )
    assert report["test_rows_accessed"] is False
    assert set(report["models"]) == {
        "constant",
        "structured",
        "visual",
        "fused",
        "fused_shuffled_visual",
    }
    assert LinearActionHead.load(tmp_path / "head.npz").metadata["development_only"] is True
