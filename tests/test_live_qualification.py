from __future__ import annotations

from pathlib import Path

import numpy as np

from trace_jepa.util import sha256_value
from trace_jepa.worldmodels.benchmark_v2 import (
    BenchmarkV2Spec,
    generate_benchmark_episodes_v2,
)
from trace_jepa.worldmodels.contracts import ModelArtifactIdentity
from trace_jepa.worldmodels.live_qualification import (
    _recompute_latency_summary,
    build_qualification_observations,
    run_live_qualification,
    simple_visual_features,
    verify_qualification_report,
    write_qualification_observation_bundle,
    write_qualification_report,
)
from trace_jepa.worldmodels.live_service import LiveBackendOutput


def _hash(character: str) -> str:
    return character * 64


TEST_ENVIRONMENT = {"runtime": "test"}
TEST_ENVIRONMENT_SHA256 = sha256_value(TEST_ENVIRONMENT)


def _identity() -> ModelArtifactIdentity:
    return ModelArtifactIdentity(
        family="qualification-fake",
        integration_kind="frozen-representation",
        source_repository="https://example.invalid/model",
        source_commit="a" * 40,
        integration_source_tree_sha256=_hash("f"),
        encoder_version="fake-encoder-v1",
        encoder_checkpoint_sha256=_hash("1"),
        outcome_head_version="not-applicable-supporting",
        outcome_head_sha256=_hash("3"),
        calibration_version="not-applicable-supporting",
        calibration_artifact_sha256=_hash("4"),
        training_snapshot_sha256=_hash("5"),
        preprocessing_version="fake-preprocess-v1",
        feature_schema_version="fake-latent-v1",
        action_schema_version="flood-actions-v2",
        supported_action_types=("dispatch_rescue_boat",),
    )


class _Backend:
    device_type = "cpu"
    precision = "float32"

    @property
    def identity(self):
        return _identity()

    @property
    def environment_manifest_sha256(self):
        return TEST_ENVIRONMENT_SHA256

    def infer(self, *, frames, request):
        feature = np.concatenate(
            [
                frames.mean(axis=(0, 1, 2)),
                frames.std(axis=(0, 1, 2)),
                np.asarray([frames[-1].mean()]),
            ]
        ).astype(np.float32)
        return LiveBackendOutput(None, feature, {"supporting_only": True})


def _episodes():
    return generate_benchmark_episodes_v2(
        BenchmarkV2Spec(
            campaign_seed=20260760,
            split_seed=20260761,
            episode_count=12,
        )
    )


def test_control_construction_is_deterministic_stratified_and_nonleaking() -> None:
    episodes = _episodes()
    first = build_qualification_observations(episodes)
    second = build_qualification_observations(episodes)
    assert [item.provenance for item in first] == [item.provenance for item in second]
    assert len(first) == 36
    for episode in episodes:
        items = [item for item in first if item.episode_id == episode.episode_id]
        assert {item.arm for item in items} == {
            "actual",
            "static_visual",
            "shuffled_visual",
        }
        actual = next(item for item in items if item.arm == "actual")
        shuffled = next(item for item in items if item.arm == "shuffled_visual")
        assert actual.camera_name == shuffled.camera_name
        assert actual.provenance.observation_sha256 != shuffled.provenance.observation_sha256
        assert "truth" not in actual.provenance.model_dump_json().lower()
        assert simple_visual_features(actual.frames).shape == (10,)


def test_limited_qualification_runs_cold_integrity_and_cache_replay(
    tmp_path: Path,
) -> None:
    observations = build_qualification_observations(_episodes())
    report = run_live_qualification(
        backend=_Backend(),
        observations=observations,
        action_types=("dispatch_rescue_boat",),
        output_root=tmp_path,
    )
    assert report["episode_count"] == 12
    assert report["post_warmup_uncached_request_count"] == 36
    assert report["cache_replay_count"] == 36
    assert report["test_data_accessed"] is False
    assert all(item["cache_hit"] for item in report["cache_replays"])
    assert report["actual_vs_shuffled_latent_difference_count"] > 0
    assert len(set(report["structured_feature_hashes"].values())) > 1
    spec = BenchmarkV2Spec(
        campaign_seed=20260760,
        split_seed=20260761,
        episode_count=12,
    )
    environment = TEST_ENVIRONMENT
    observation_bundle = write_qualification_observation_bundle(
        tmp_path / "input-observations",
        observations,
    )
    report.update(
        {
            "benchmark_spec": spec.model_dump(mode="json"),
            "benchmark_spec_sha256": spec.spec_sha256,
            "environment": environment,
            "environment_manifest_sha256": TEST_ENVIRONMENT_SHA256,
            "latency_summary": _recompute_latency_summary(report["rows"]),
            "warmup_requests": 2,
            "upstream_checkout": {
                "origin": "https://example.invalid/model",
                "commit": "a" * 40,
                "tree": "b" * 40,
                "tracked_inventory_sha256": "c" * 64,
                "clean": True,
                "submodule_status": "",
            },
            "observation_bundle": observation_bundle,
        }
    )
    report_path = write_qualification_report(tmp_path / "report.json", report)
    verified = verify_qualification_report(report_path, output_root=tmp_path)
    assert verified["passed"] is True
    assert verified["verified_request_count"] == 36


def test_single_arm_reference_control_uses_same_verified_store(tmp_path: Path) -> None:
    observations = build_qualification_observations(_episodes())
    report = run_live_qualification(
        backend=_Backend(),
        observations=observations,
        action_types=("dispatch_rescue_boat",),
        output_root=tmp_path,
        observation_arms=("actual",),
    )
    assert report["observation_arms"] == ["actual"]
    assert report["post_warmup_uncached_request_count"] == 12
    assert report["cache_replay_count"] == 12
    assert {row["arm"] for row in report["rows"]} == {"actual"}
