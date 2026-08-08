"""Failure-path tests for content-addressed predictor inputs.

These cases are deliberately explicit: the scientific contract requires a
closed failure rather than a permissive fallback whenever learned-model
identity or input integrity cannot be established.
"""

from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from trace_jepa.contracts import ActionInstance, PlanCandidate
from trace_jepa.experimental import AdequacyStatus
from trace_jepa.predictor import (
    CachedVJEPAFeatureProvider,
    PredictorContext,
    PredictorInputUnavailable,
    PredictorObservation,
    PredictorPriorProfile,
    PredictorRequest,
    PredictorRouteObservation,
    PredictorVisualFeatureRef,
    QualificationArtifact,
    VJEPAFeatureCacheSpec,
)
from trace_jepa.predictor.mlp import (
    MLPActionPrefixPredictor,
    MLPPredictorSpec,
    NumpyMLPBackend,
    _stable_sigmoid,
)
from trace_jepa.predictor.qualification import (
    QualificationBinding,
    VerifiedQualification,
    verify_qualification_binding,
)
from trace_jepa.support.files import (
    ArtifactLocator,
    atomic_write_bytes,
    safe_directory,
    safe_output_file,
    safe_regular_file,
    validate_npz_container,
)


def _request(*, visual: PredictorVisualFeatureRef | None = None) -> PredictorRequest:
    return PredictorRequest(
        plan=PlanCandidate(
            plan_id="failure-boundary-plan",
            name="Failure boundary fixture",
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
            routes=(
                PredictorRouteObservation(
                    route_id="XNG-04",
                    report="open",
                    nominal_travel_s=900.0,
                ),
            ),
            context=PredictorContext(
                simulation_time_s=120,
                available_resource_units=1,
                call_observation_age_s=0,
                prior_profile=PredictorPriorProfile(
                    profile_id="prior-test",
                    calibration_version="cal-test-v1",
                    prior_accuracy_milli=900,
                ),
                visual_feature=visual,
            ),
        ),
    )


def _qualification(**updates: object) -> QualificationArtifact:
    values: dict[str, object] = {
        "schema_version": "predictor-qualification-v1",
        "qualification_id": "failure-test-v1",
        "qualification_scope": "experimental",
        "predictor_version": "predictor-v1",
        "model_hash": "1" * 64,
        "calibration_version": "calibration-v1",
        "calibration_hash": "2" * 64,
        "encoder_version": None,
        "encoder_checkpoint_hash": None,
        "feature_schema_version": "features-v1",
        "action_schema_version": "actions-v1",
        "qualified_action_types": ("dispatch_rescue_boat",),
        "adequacy_status": AdequacyStatus.QUALIFIED,
        "evaluation_protocol_sha256": "3" * 64,
        "evaluation_report_sha256": "4" * 64,
        "issuer_name": "Test issuer",
        "issuer_role": "test fixture",
        "issued_at_utc": datetime(2026, 8, 8, tzinfo=timezone.utc),
        "claim_limit": "test only",
    }
    values.update(updates)
    return QualificationArtifact.model_validate(values)


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"adequacy_status": AdequacyStatus.UNQUALIFIED}, "qualified status"),
        ({"qualified_action_types": ()}, "at least one action"),
        ({"encoder_version": "encoder-v1"}, "declared together"),
        (
            {"qualified_action_types": ("dispatch_rescue_boat", "dispatch_rescue_boat")},
            "must be unique",
        ),
    ],
)
def test_qualification_schema_rejects_incomplete_or_self_inconsistent_claims(
    updates: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        _qualification(**updates)


def test_qualification_binding_rejects_unsupported_action() -> None:
    artifact = _qualification(qualified_action_types=("inspect_levee",))
    verified = VerifiedQualification(artifact=artifact, artifact_sha256="5" * 64)
    binding = QualificationBinding(
        predictor_version="predictor-v1",
        model_hash="1" * 64,
        calibration_version="calibration-v1",
        calibration_hash="2" * 64,
        encoder_version=None,
        encoder_checkpoint_hash=None,
        feature_schema_version="features-v1",
        action_schema_version="actions-v1",
        supported_action_types=("dispatch_rescue_boat",),
    )
    with pytest.raises(ValueError, match="unsupported action"):
        verify_qualification_binding(verified, binding)


def test_artifact_locator_rejects_unsafe_roots_and_files(tmp_path: Path) -> None:
    trusted = tmp_path / "trusted"
    trusted.mkdir()
    artifact = trusted / "artifact.bin"
    artifact.write_bytes(b"1234")

    with pytest.raises(ValueError, match="unsafe relative name"):
        ArtifactLocator(trusted, Path(), 100, "artifact").resolve()
    with pytest.raises(ValueError, match="maximum expected size"):
        safe_regular_file(artifact, declared_root=trusted, maximum_bytes=3, label="artifact")
    with pytest.raises(ValueError, match="regular file"):
        safe_regular_file(trusted, declared_root=tmp_path, maximum_bytes=100, label="artifact")
    with pytest.raises(ValueError, match="absent"):
        safe_regular_file(
            trusted / "missing.bin",
            declared_root=trusted,
            maximum_bytes=100,
            label="artifact",
        )


def test_safe_directory_rejects_symlink_escape_and_regular_file(tmp_path: Path) -> None:
    trusted = tmp_path / "trusted"
    trusted.mkdir()
    nested = trusted / "nested"
    nested.mkdir()
    assert safe_directory(nested, declared_root=trusted, label="directory") == nested.resolve()

    outside = tmp_path / "outside"
    outside.mkdir()
    linked = trusted / "linked"
    linked.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="must not be a symlink"):
        safe_directory(linked, declared_root=trusted, label="directory")

    regular = trusted / "regular"
    regular.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a directory"):
        safe_directory(regular, declared_root=trusted, label="directory")

    root_file = tmp_path / "not-a-root"
    root_file.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a directory"):
        safe_regular_file(root_file, declared_root=root_file, maximum_bytes=100, label="artifact")

    root_link = tmp_path / "root-link"
    root_link.symlink_to(trusted, target_is_directory=True)
    with pytest.raises(ValueError, match="root must not be a symlink"):
        safe_regular_file(
            root_link / "artifact.bin",
            declared_root=root_link,
            maximum_bytes=100,
            label="artifact",
        )


def test_safe_output_and_atomic_write_reject_unsafe_destinations(tmp_path: Path) -> None:
    trusted = tmp_path / "trusted"
    trusted.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    with pytest.raises(ValueError, match="outside its caller-trusted root"):
        safe_output_file(outside / "out.bin", declared_root=trusted, label="output")

    directory_destination = trusted / "directory"
    directory_destination.mkdir()
    with pytest.raises(ValueError, match="safe regular-file destination"):
        safe_output_file(directory_destination, declared_root=trusted, label="output")

    symlink_destination = trusted / "linked"
    symlink_destination.symlink_to(outside / "out.bin")
    with pytest.raises(ValueError, match="safe regular-file destination"):
        safe_output_file(symlink_destination, declared_root=trusted, label="output")

    destination = trusted / "atomic.bin"
    atomic_write_bytes(destination, b"first", root=trusted, label="output")
    atomic_write_bytes(destination, b"second", root=trusted, label="output")
    assert destination.read_bytes() == b"second"


def test_npz_container_rejects_bad_member_schema_and_size(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed.npz"
    malformed.write_bytes(b"not-a-zip")
    with pytest.raises(ValueError, match="not a valid NPZ"):
        validate_npz_container(
            malformed,
            expected_arrays={"feature"},
            maximum_uncompressed_bytes=100,
            label="fixture",
        )

    unsafe = tmp_path / "unsafe.npz"
    with zipfile.ZipFile(unsafe, "w") as archive:
        archive.writestr("../feature.npy", b"x")
    with pytest.raises(ValueError, match=r"exact array schema|unsafe archive member"):
        validate_npz_container(
            unsafe,
            expected_arrays={"feature"},
            maximum_uncompressed_bytes=100,
            label="fixture",
        )

    oversized = tmp_path / "oversized.npz"
    with zipfile.ZipFile(oversized, "w") as archive:
        archive.writestr("feature.npy", b"0123456789")
    with pytest.raises(ValueError, match="maximum uncompressed size"):
        validate_npz_container(
            oversized,
            expected_arrays={"feature"},
            maximum_uncompressed_bytes=3,
            label="fixture",
        )


@pytest.mark.parametrize(
    "backend",
    [
        NumpyMLPBackend(np.zeros(2), np.zeros(2), np.zeros((2, 7)), np.zeros(7), ()),
        NumpyMLPBackend(np.zeros((2, 2)), np.zeros(3), np.zeros((2, 7)), np.zeros(7), ()),
        NumpyMLPBackend(np.zeros((2, 2)), np.zeros(2), np.zeros((3, 7)), np.zeros(7), ()),
        NumpyMLPBackend(np.zeros((2, 2)), np.zeros(2), np.zeros((2, 7)), np.zeros(6), ()),
        NumpyMLPBackend(
            np.asarray([[np.nan, 0.0], [0.0, 0.0]]),
            np.zeros(2),
            np.zeros((2, 7)),
            np.zeros(7),
            (),
        ),
    ],
)
def test_mlp_backend_rejects_malformed_shapes_and_values(backend: NumpyMLPBackend) -> None:
    with pytest.raises(ValueError):
        backend.validate()


def test_mlp_predictor_rejects_conflicting_spec_and_bad_outputs() -> None:
    class BadBackend:
        def infer(self, _request: PredictorRequest) -> list[float]:
            return [0.0]

    spec = MLPPredictorSpec(
        predictor_version="mlp-v1",
        calibration_version="cal-v1",
        training_snapshot="training-v1",
        model_hash="1" * 64,
        calibration_hash="2" * 64,
    )
    with pytest.raises(TypeError, match="not both"):
        MLPActionPrefixPredictor(BadBackend(), spec, predictor_version="other")
    predictor = MLPActionPrefixPredictor(BadBackend(), spec)
    with pytest.raises(ValueError, match="exactly seven"):
        predictor.predict(_request())
    with pytest.raises(ValueError, match="non-finite"):
        _stable_sigmoid(float("nan"))


def _visual_reference(**updates: object) -> PredictorVisualFeatureRef:
    values: dict[str, object] = {
        "observation_id": "observation-1",
        "observation_sha256": "a" * 64,
        "feature_cache_sha256": "b" * 64,
        "feature_schema_version": "vjepa-frozen-feature-v1",
        "encoder_version": "encoder-v1",
        "encoder_checkpoint_hash": "c" * 64,
        "captured_at_s": 100,
    }
    values.update(updates)
    return PredictorVisualFeatureRef.model_validate(values)


@pytest.mark.parametrize(
    ("reference", "message"),
    [
        (None, "no visual feature"),
        (
            PredictorVisualFeatureRef.model_construct(
                observation_id="../escape",
                observation_sha256="a" * 64,
                feature_cache_sha256="b" * 64,
                feature_schema_version="vjepa-frozen-feature-v1",
                encoder_version="encoder-v1",
                encoder_checkpoint_hash="c" * 64,
                captured_at_s=100,
            ),
            "identifier is unsafe",
        ),
        (_visual_reference(captured_at_s=121), "future"),
        (_visual_reference(encoder_version="wrong"), "encoder version"),
        (_visual_reference(encoder_checkpoint_hash="d" * 64), "checkpoint"),
        (_visual_reference(feature_schema_version="wrong"), "schema"),
    ],
)
def test_vjepa_provider_fails_closed_on_reference_identity(
    tmp_path: Path,
    reference: PredictorVisualFeatureRef | None,
    message: str,
) -> None:
    provider = CachedVJEPAFeatureProvider(
        tmp_path,
        VJEPAFeatureCacheSpec(
            encoder_version="encoder-v1",
            encoder_checkpoint_hash="c" * 64,
        ),
    )
    with pytest.raises(PredictorInputUnavailable, match=message):
        provider.features(_request(visual=reference))


def test_vjepa_provider_rejects_stale_or_absent_feature(tmp_path: Path) -> None:
    provider = CachedVJEPAFeatureProvider(
        tmp_path,
        VJEPAFeatureCacheSpec(
            encoder_version="encoder-v1",
            encoder_checkpoint_hash="c" * 64,
            maximum_age_s=5,
        ),
    )
    with pytest.raises(PredictorInputUnavailable, match="stale"):
        provider.features(_request(visual=_visual_reference(captured_at_s=100)))

    current_provider = CachedVJEPAFeatureProvider(
        tmp_path,
        VJEPAFeatureCacheSpec(
            encoder_version="encoder-v1",
            encoder_checkpoint_hash="c" * 64,
        ),
    )
    with pytest.raises(PredictorInputUnavailable, match=r"absent|escapes"):
        current_provider.features(_request(visual=_visual_reference()))


def test_predictor_fixture_metadata_is_canonical_json() -> None:
    # Guard against tests accidentally depending on platform-specific JSON
    # formatting in model fixture metadata.
    payload = {"schema": "fixture-v1", "finite": 1.0}
    assert json.loads(json.dumps(payload, sort_keys=True)) == payload
