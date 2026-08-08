"""Contract tests for experimental-profile predictor-version provenance."""

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from trace_jepa.contracts import (
    ActionInstance,
    PlanCandidate,
    WorldModelEvidence,
)
from trace_jepa.experimental import (
    AdequacyStatus,
    ExperimentalProfileExtension,
    build_experimental_profile,
)
from trace_jepa.predictor import (
    ActionPrefixPredictor,
    ArtifactLocator,
    CachedVJEPAFeatureProvider,
    CalibratedVJEPAHead,
    MLPActionPrefixPredictor,
    MLPCalibrationArtifact,
    PredictorContext,
    PredictorInputUnavailable,
    PredictorObservation,
    PredictorPriorProfile,
    PredictorRequest,
    PredictorRouteObservation,
    PredictorVisualFeatureRef,
    QualificationArtifact,
    ToyActionPrefixPredictor,
    VerifiedQualification,
    VJEPABackedActionPrefixPredictor,
    load_qualification_artifact,
    write_deterministic_feature_cache,
    write_deterministic_npz,
)
from trace_jepa.util import sha256_file


def _base_evidence(**updates) -> WorldModelEvidence:
    base = {
        "encoder_version": "encoder-v1",
        "fusion_version": "fusion-v1",
        "predictor_version": "predictor-v1",
        "semantic_probe_versions": ("probe-v1",),
        "training_snapshot": "data-v1",
        "observation_window_hash": "obs",
        "fleet_state_hash": "state",
        "candidate_plan_id": "plan",
        "action_schema_version": "actions-v1",
        "rollout_horizon": 3,
        "predicted_claims": ("route open",),
        "uncertainty": 0.1,
        "model_support": 0.9,
        "out_of_distribution_score": 0.1,
        "rollout_consistency": 0.9,
        "calibration_version": "cal-v1",
    }
    base.update(updates)
    return WorldModelEvidence(**base)


def test_experimental_profile_carries_required_provenance_fields():
    stamp = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
    profile = build_experimental_profile(
        predictor_version="predictor-v2",
        calibration_version="cal-v2",
        claim_family="high_consequence_rescue",
        adequacy_status=AdequacyStatus.UNQUALIFIED,
        prediction_timestamp=stamp,
        model_hash="abc123",
    )
    assert profile.predictor_version == "predictor-v2"
    assert profile.calibration_version == "cal-v2"
    assert profile.prediction_timestamp == stamp
    assert profile.claim_family == "high_consequence_rescue"
    assert profile.adequacy_status == AdequacyStatus.UNQUALIFIED
    assert profile.model_hash == "abc123"


def test_world_model_evidence_accepts_experimental_profile_extension():
    profile = ExperimentalProfileExtension(
        predictor_version="predictor-v1",
        calibration_version="cal-v1",
        claim_family="route_access",
        adequacy_status=AdequacyStatus.QUALIFIED,
    )
    evidence = _base_evidence(experimental_profile=profile)
    assert evidence.experimental_profile is not None
    assert evidence.experimental_profile.claim_family == "route_access"
    assert evidence.experimental_profile.adequacy_status == AdequacyStatus.QUALIFIED


def test_world_model_evidence_coerces_profile_mapping():
    evidence = _base_evidence(
        experimental_profile={
            "predictor_version": "predictor-v1",
            "calibration_version": "cal-v1",
            "claim_family": "dispatch_success",
            "adequacy_status": "pending_revalidation",
        }
    )
    assert evidence.experimental_profile.adequacy_status == (AdequacyStatus.PENDING_REVALIDATION)


def test_baseline_evidence_without_profile_still_validates():
    evidence = _base_evidence()
    assert evidence.experimental_profile is None


def test_experimental_profile_rejects_unknown_fields():
    try:
        ExperimentalProfileExtension(
            predictor_version="p",
            calibration_version="c",
            claim_family="f",
            adequacy_status=AdequacyStatus.QUALIFIED,
            unexpected=True,
        )
        raised = False
    except ValidationError:
        raised = True
    assert raised


def test_toy_predictor_satisfies_versioned_predictor_protocol() -> None:
    predictor = ToyActionPrefixPredictor()
    assert isinstance(predictor, ActionPrefixPredictor)
    provenance = predictor.provenance()
    assert provenance.predictor_version == predictor.predictor_version
    assert provenance.calibration_version == predictor.calibration_version
    assert provenance.model_hash == predictor.model_hash
    assert provenance.calibration_hash == predictor.calibration_hash
    assert provenance.qualification_artifact_sha256 is not None
    assert provenance.qualified_action_types == predictor.supported_action_types


def _write_qualification(
    tmp_path,
    *,
    predictor_version: str,
    model_hash: str,
    calibration_version: str,
    calibration_hash: str,
    feature_schema_version: str = "action-prefix-features-v2",
    action_schema_version: str = "delta-response-actions-v2",
    encoder_version: str | None = None,
    encoder_checkpoint_hash: str | None = None,
) -> VerifiedQualification:
    payload = QualificationArtifact(
        schema_version="predictor-qualification-v1",
        qualification_id="test-qualification-v1",
        qualification_scope="experimental",
        predictor_version=predictor_version,
        model_hash=model_hash,
        calibration_version=calibration_version,
        calibration_hash=calibration_hash,
        encoder_version=encoder_version,
        encoder_checkpoint_hash=encoder_checkpoint_hash,
        feature_schema_version=feature_schema_version,
        action_schema_version=action_schema_version,
        qualified_action_types=("dispatch_rescue_boat",),
        adequacy_status=AdequacyStatus.QUALIFIED,
        evaluation_protocol_sha256="5" * 64,
        evaluation_report_sha256="6" * 64,
        issuer_name="test issuer",
        issuer_role="test-only qualification fixture",
        issued_at_utc=datetime(2026, 8, 6, tzinfo=timezone.utc),
        claim_limit="test fixture only",
    )
    path = tmp_path / "qualification.json"
    path.write_text(payload.model_dump_json(), encoding="utf-8")
    return load_qualification_artifact(path, trusted_root=tmp_path)


def test_learned_predictor_cannot_self_assert_qualified_status(tmp_path) -> None:
    with pytest.raises(ValueError, match="verified artifact"):
        MLPActionPrefixPredictor(
            backend=DeterministicMLPBackend(),
            predictor_version="mlp-v1",
            calibration_version="mlp-cal-v1",
            training_snapshot="training-v1",
            model_hash="1" * 64,
            calibration_hash="2" * 64,
            adequacy_status=AdequacyStatus.QUALIFIED,
        )

    qualification = _write_qualification(
        tmp_path,
        predictor_version="mlp-v1",
        model_hash="1" * 64,
        calibration_version="mlp-cal-v1",
        calibration_hash="2" * 64,
    )
    predictor = MLPActionPrefixPredictor(
        backend=DeterministicMLPBackend(),
        predictor_version="mlp-v1",
        calibration_version="mlp-cal-v1",
        training_snapshot="training-v1",
        model_hash="1" * 64,
        calibration_hash="2" * 64,
        qualification=qualification,
    )
    assert predictor.provenance().adequacy_status == AdequacyStatus.QUALIFIED
    assert predictor.provenance().qualified_action_types == ("dispatch_rescue_boat",)


def test_qualification_artifact_rejects_any_bound_field_mismatch(tmp_path) -> None:
    qualification = _write_qualification(
        tmp_path,
        predictor_version="mlp-v1",
        model_hash="9" * 64,
        calibration_version="mlp-cal-v1",
        calibration_hash="2" * 64,
    )
    with pytest.raises(ValueError, match="model_hash mismatch"):
        MLPActionPrefixPredictor(
            backend=DeterministicMLPBackend(),
            predictor_version="mlp-v1",
            calibration_version="mlp-cal-v1",
            training_snapshot="training-v1",
            model_hash="1" * 64,
            calibration_hash="2" * 64,
            qualification=qualification,
        )


def test_mlp_loader_binds_separate_model_and_calibration_artifacts(tmp_path) -> None:
    action_names = np.asarray(["dispatch_rescue_boat"])
    metadata = {
        "predictor_version": "mlp-safe-v1",
        "training_snapshot": "synthetic-test-v1",
        "feature_schema_version": "action-prefix-features-v2",
        "action_schema_version": "delta-response-actions-v2",
    }
    checkpoint = tmp_path / "mlp.npz"
    write_deterministic_npz(
        checkpoint,
        {
            "weight_1": np.zeros((12, 2), dtype=np.float64),
            "bias_1": np.zeros(2, dtype=np.float64),
            "weight_2": np.zeros((2, 7), dtype=np.float64),
            "bias_2": np.asarray([-1e6, 5.0, 0.0, 0.0, 1e6, 0.0, 0.0]),
            "action_names": action_names,
            "metadata_json": np.asarray(json.dumps(metadata, sort_keys=True)),
        },
        output_root=tmp_path,
    )
    calibration = MLPCalibrationArtifact(
        schema_version="mlp-calibration-v1",
        predictor_version="mlp-safe-v1",
        calibration_version="mlp-safe-cal-v1",
        feature_schema_version="action-prefix-features-v2",
        action_schema_version="delta-response-actions-v2",
        output_link_version="delta-plan-prediction-links-v1",
    )
    calibration_path = tmp_path / "mlp-calibration.json"
    calibration_path.write_text(calibration.model_dump_json(), encoding="utf-8")

    predictor = MLPActionPrefixPredictor.from_checkpoint(
        checkpoint,
        model_root=tmp_path,
        calibration_path=calibration_path,
        calibration_root=tmp_path,
    )
    provenance = predictor.provenance()
    assert provenance.model_hash == sha256_file(checkpoint)
    assert provenance.calibration_hash == sha256_file(calibration_path)
    assert provenance.adequacy_status == AdequacyStatus.UNQUALIFIED
    prediction = predictor.predict(_protocol_request())
    assert prediction.success_probability == 0.0
    assert prediction.model_support == 1.0

    malformed = tmp_path / "mlp-extra-array.npz"
    write_deterministic_npz(
        malformed,
        {
            "weight_1": np.zeros((12, 2), dtype=np.float64),
            "bias_1": np.zeros(2, dtype=np.float64),
            "weight_2": np.zeros((2, 7), dtype=np.float64),
            "bias_2": np.zeros(7, dtype=np.float64),
            "action_names": action_names,
            "metadata_json": np.asarray(json.dumps(metadata, sort_keys=True)),
            "unexpected": np.asarray([1]),
        },
        output_root=tmp_path,
    )
    with pytest.raises(ValueError, match="exact array schema"):
        MLPActionPrefixPredictor.from_checkpoint(
            malformed,
            model_root=tmp_path,
            calibration_path=calibration_path,
            calibration_root=tmp_path,
        )


def test_artifact_locator_rejects_escape_and_intermediate_symlink(tmp_path) -> None:
    trusted = tmp_path / "trusted"
    trusted.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    artifact = outside / "model.npz"
    artifact.write_bytes(b"fixture")
    with pytest.raises(ValueError, match="outside its caller-trusted root"):
        ArtifactLocator.from_path(
            root=trusted,
            path=artifact,
            maximum_bytes=100,
            label="test model",
        )

    linked_parent = trusted / "linked"
    linked_parent.symlink_to(outside, target_is_directory=True)
    locator = ArtifactLocator(
        root=trusted,
        relative_name=Path("linked/model.npz"),
        maximum_bytes=100,
        label="test model",
    )
    with pytest.raises(ValueError, match=r"escapes|parent must not be a symlink"):
        locator.resolve()


def test_custom_toy_qualification_requires_a_trusted_root(tmp_path) -> None:
    qualification = Path(__file__).resolve().parents[1] / (
        "src/trace_jepa/predictor/toy_qualification_v1.json"
    )
    with pytest.raises(ValueError, match="qualification_root is required"):
        ToyActionPrefixPredictor(qualification)


def test_vjepa_qualification_requires_exact_frozen_head_and_encoder(tmp_path) -> None:
    provider, head = _write_vjepa_fixture(tmp_path)
    with pytest.raises(ValueError, match="verified artifact"):
        VJEPABackedActionPrefixPredictor(
            provider,
            head,
            adequacy_status=AdequacyStatus.QUALIFIED,
        )
    qualification = _write_qualification(
        tmp_path,
        predictor_version=str(head.metadata["predictor_version"]),
        model_hash=head.checkpoint_hash,
        calibration_version=str(head.metadata["calibration_version"]),
        calibration_hash=str(head.metadata["calibration_hash"]),
        feature_schema_version=str(head.metadata["feature_schema_version"]),
        action_schema_version=str(head.metadata["action_schema_version"]),
        encoder_version=provider.encoder_version,
        encoder_checkpoint_hash=provider.encoder_checkpoint_hash,
    )
    predictor = VJEPABackedActionPrefixPredictor(
        provider,
        head,
        qualification=qualification,
    )
    assert predictor.provenance().adequacy_status == AdequacyStatus.QUALIFIED
    assert predictor.provenance().qualified_action_types == ("dispatch_rescue_boat",)


def test_learned_predictor_loaders_reject_symlink_roots_and_extra_head_arrays(
    tmp_path: Path,
) -> None:
    real_cache = tmp_path / "real-cache"
    real_cache.mkdir()
    cache_link = tmp_path / "cache-link"
    cache_link.symlink_to(real_cache, target_is_directory=True)
    with pytest.raises(ValueError, match="root must not be a symlink"):
        CachedVJEPAFeatureProvider(
            cache_link,
            encoder_version="vjepa-test",
            encoder_checkpoint_hash="e" * 64,
        )

    metadata = {
        "predictor_version": "vjepa-head-v1",
        "calibration_version": "vjepa-cal-v1",
        "calibration_hash": "4" * 64,
        "training_snapshot": "training-v1",
        "encoder_version": "vjepa2.1-test",
        "encoder_checkpoint_hash": "e" * 64,
        "feature_schema_version": "action-prefix-features-v2",
        "action_schema_version": "delta-response-actions-v2",
    }
    extra_head = tmp_path / "head-extra.npz"
    write_deterministic_npz(
        extra_head,
        {
            "weights": np.zeros((14, 7), dtype=np.float64),
            "bias": np.zeros(7, dtype=np.float64),
            "feature_mean": np.zeros(14, dtype=np.float64),
            "feature_std": np.ones(14, dtype=np.float64),
            "action_names": np.asarray(["dispatch_rescue_boat"]),
            "metadata_json": np.asarray(json.dumps(metadata, sort_keys=True)),
            "unexpected": np.asarray([1]),
        },
        output_root=tmp_path,
    )
    with pytest.raises(PredictorInputUnavailable, match="exact array schema"):
        CalibratedVJEPAHead.load(extra_head, trusted_root=tmp_path)


def test_world_model_evidence_rejects_mismatched_profile_versions() -> None:
    profile = build_experimental_profile(
        predictor_version="predictor-v2",
        calibration_version="cal-v2",
        claim_family="high_consequence_rescue",
        adequacy_status=AdequacyStatus.QUALIFIED,
    )
    with pytest.raises(ValidationError, match="predictor_version"):
        _base_evidence(experimental_profile=profile)


class DeterministicMLPBackend:
    def infer(self, request: PredictorRequest) -> list[float]:
        assert request.plan.plan_id == "protocol-plan"
        return [0.0, 5.0, -1.0, 0.2, 2.0, -2.0, -1.0]


def _protocol_request(
    *,
    visual: bool = False,
    feature_cache_sha256: str = "f" * 64,
) -> PredictorRequest:
    visual_reference = (
        PredictorVisualFeatureRef(
            observation_id="visual-test",
            observation_sha256="a" * 64,
            feature_cache_sha256=feature_cache_sha256,
            feature_schema_version="vjepa-frozen-feature-v1",
            encoder_version="vjepa2.1-test",
            encoder_checkpoint_hash="e" * 64,
            captured_at_s=0,
        )
        if visual
        else None
    )
    return PredictorRequest(
        plan=PlanCandidate(
            plan_id="protocol-plan",
            name="Protocol substitution fixture",
            actions=(
                ActionInstance(
                    action_type="dispatch_rescue_boat",
                    actor_id="boat",
                    route_id="XNG-04",
                ),
            ),
            utility=1.0,
            reversible_first_action=False,
        ),
        observation=PredictorObservation(
            routes=[
                PredictorRouteObservation(
                    route_id="XNG-04",
                    report="open",
                    nominal_travel_s=900.0,
                )
            ],
            context=PredictorContext(
                prior_profile=PredictorPriorProfile(
                    profile_id="delta-prior-high-v1",
                    calibration_version="vjepa-cal-v1",
                    prior_accuracy_milli=900,
                ),
                visual_feature=visual_reference,
            ),
        ),
    )


def _write_vjepa_fixture(tmp_path) -> tuple[CachedVJEPAFeatureProvider, CalibratedVJEPAHead]:
    encoder_hash = "e" * 64
    write_deterministic_feature_cache(
        tmp_path / "visual-test.npz",
        feature=np.asarray([0.1, 0.2], dtype=np.float32),
        observation_sha256="a" * 64,
        encoder_version="vjepa2.1-test",
        encoder_checkpoint_hash=encoder_hash,
        output_root=tmp_path,
    )
    action_names = np.asarray(["dispatch_rescue_boat"])
    structured_dimension = 11 + len(action_names)
    metadata = {
        "predictor_version": "vjepa-head-v1",
        "calibration_version": "vjepa-cal-v1",
        "calibration_hash": "4" * 64,
        "training_snapshot": "training-v1",
        "encoder_version": "vjepa2.1-test",
        "encoder_checkpoint_hash": encoder_hash,
        "feature_schema_version": "action-prefix-features-v2",
        "action_schema_version": "delta-response-actions-v2",
    }
    head_path = tmp_path / "vjepa-head.npz"
    np.savez_compressed(
        head_path,
        weights=np.zeros((structured_dimension + 2, 7), dtype=np.float64),
        bias=np.asarray([1.0, 5.0, -1.0, 0.2, 2.0, -2.0, -1.0]),
        feature_mean=np.zeros(structured_dimension + 2, dtype=np.float64),
        feature_std=np.ones(structured_dimension + 2, dtype=np.float64),
        action_names=action_names,
        metadata_json=np.asarray(json.dumps(metadata, sort_keys=True)),
    )
    return (
        CachedVJEPAFeatureProvider(
            tmp_path,
            encoder_version="vjepa2.1-test",
            encoder_checkpoint_hash=encoder_hash,
        ),
        CalibratedVJEPAHead.load(head_path, trusted_root=tmp_path),
    )


def test_mlp_and_vjepa_adapters_share_the_versioned_protocol(tmp_path) -> None:
    mlp = MLPActionPrefixPredictor(
        backend=DeterministicMLPBackend(),
        predictor_version="mlp-v1",
        calibration_version="mlp-cal-v1",
        training_snapshot="training-v1",
        model_hash="1" * 64,
        calibration_hash="2" * 64,
        adequacy_status=AdequacyStatus.UNQUALIFIED,
    )
    feature_provider, head = _write_vjepa_fixture(tmp_path)
    vjepa = VJEPABackedActionPrefixPredictor(
        feature_provider,
        head,
        adequacy_status=AdequacyStatus.PENDING_REVALIDATION,
    )
    request = _protocol_request()
    assert isinstance(mlp, ActionPrefixPredictor)
    assert isinstance(vjepa, ActionPrefixPredictor)
    assert mlp.predict(request).plan_id == request.plan.plan_id
    visual_request = _protocol_request(
        visual=True,
        feature_cache_sha256=sha256_file(tmp_path / "visual-test.npz"),
    )
    assert vjepa.predict(visual_request).plan_id == request.plan.plan_id
    assert vjepa.encoder_version != vjepa.predictor_version
    assert vjepa.provenance().adequacy_status == AdequacyStatus.PENDING_REVALIDATION
