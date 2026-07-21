from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from trace_jepa.util import sha256_file, sha256_value
from trace_jepa.worldmodels.benchmark_v2 import (
    BenchmarkEpisodeV2,
    BenchmarkV2Spec,
    generate_benchmark_episodes_v2,
    geography_profile_v2,
)
from trace_jepa.worldmodels.contracts import (
    ModelArtifactIdentity,
    ObservationProvenance,
    RouteWorldModelRequestV2,
)
from trace_jepa.worldmodels.live_artifacts import ContentAddressedInferenceStore
from trace_jepa.worldmodels.live_backends import simple_visual_features
from trace_jepa.worldmodels.live_service import (
    LiveInferenceRequest,
    LiveInferenceState,
    LiveWorldModelService,
)


QUALIFICATION_PROTOCOL_VERSION = "learned-live-support-qualification-v1"


@dataclass(frozen=True)
class QualificationObservation:
    provenance: ObservationProvenance
    frames: np.ndarray
    camera_name: str
    episode_id: str
    source_episode_id: str
    source_observation_sha256: str
    arm: str
    reported_route_status: str
    report_confidence: float
    reported_weather_band: str
    route_closure_depth_m: float
    route_susceptibility: float
    nominal_travel_time_s: float


class QualificationObservationReader:
    def __init__(self, observations: tuple[QualificationObservation, ...]):
        self._frames = {
            item.provenance.observation_id: np.asarray(item.frames).copy()
            for item in observations
        }

    def read_frames(self, observation: ObservationProvenance) -> np.ndarray:
        frames = self._frames.get(observation.observation_id)
        if frames is None:
            raise ValueError("qualification observation is absent")
        return frames.copy()


def write_qualification_observation_bundle(
    root: Path,
    observations: tuple[QualificationObservation, ...],
) -> dict[str, object]:
    """Persist every transformed qualification input for exact offline replay."""

    root = Path(root)
    if root.exists() and any(root.iterdir()):
        raise ValueError("qualification observation bundle root must be new or empty")
    root.mkdir(parents=True, exist_ok=True)
    entries = []
    for observation in sorted(
        observations, key=lambda item: item.provenance.observation_id
    ):
        observation_id = observation.provenance.observation_id
        if not re.fullmatch(r"qualification-[0-9a-f]{24}", observation_id):
            raise ValueError("qualification observation identifier is unsafe")
        tensor_name = f"{observation_id}.npz"
        tensor_path = root / tensor_name
        with tempfile.NamedTemporaryFile(
            dir=root,
            suffix=".npz.tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            np.savez_compressed(handle, frames=observation.frames)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, tensor_path)
        entry = {
            "observation_id": observation_id,
            "provenance": observation.provenance.model_dump(mode="json"),
            "tensor_file": tensor_name,
            "tensor_file_sha256": sha256_file(tensor_path),
            "frame_shape": list(observation.frames.shape),
            "frame_dtype": str(observation.frames.dtype),
            "camera_name": observation.camera_name,
            "episode_id": observation.episode_id,
            "source_episode_id": observation.source_episode_id,
            "source_observation_sha256": observation.source_observation_sha256,
            "arm": observation.arm,
            "reported_route_status": observation.reported_route_status,
            "report_confidence": observation.report_confidence,
            "reported_weather_band": observation.reported_weather_band,
            "route_closure_depth_m": observation.route_closure_depth_m,
            "route_susceptibility": observation.route_susceptibility,
            "nominal_travel_time_s": observation.nominal_travel_time_s,
        }
        entries.append(entry)
    logical = {
        "bundle_schema_version": "qualification-observation-bundle-v1",
        "observation_count": len(entries),
        "entries": entries,
    }
    manifest = {**logical, "bundle_sha256": sha256_value(logical)}
    manifest_path = root / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )
    return {
        "manifest_file": manifest_path.name,
        "manifest_file_sha256": sha256_file(manifest_path),
        "bundle_sha256": manifest["bundle_sha256"],
        "observation_count": len(entries),
    }


def verify_qualification_observation_bundle(
    root: Path,
    expected: dict[str, object],
) -> dict[str, ObservationProvenance]:
    root = Path(root)
    manifest_path = root / "manifest.json"
    if (
        not manifest_path.is_file()
        or manifest_path.is_symlink()
        or sha256_file(manifest_path) != expected.get("manifest_file_sha256")
    ):
        raise ValueError("qualification observation manifest identity is invalid")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("qualification observation manifest is unreadable") from exc
    logical = {
        key: value for key, value in manifest.items() if key != "bundle_sha256"
    }
    if (
        sha256_value(logical) != manifest.get("bundle_sha256")
        or manifest.get("bundle_sha256") != expected.get("bundle_sha256")
        or manifest.get("observation_count") != expected.get("observation_count")
    ):
        raise ValueError("qualification observation bundle hash is invalid")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or len(entries) != manifest.get(
        "observation_count"
    ):
        raise ValueError("qualification observation inventory is malformed")
    verified = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("qualification observation entry is malformed")
        provenance = ObservationProvenance.model_validate(entry.get("provenance"))
        if provenance.observation_id in verified:
            raise ValueError("qualification observation identifier is duplicated")
        tensor_path = root / str(entry.get("tensor_file"))
        if (
            tensor_path.name != entry.get("tensor_file")
            or not tensor_path.is_file()
            or tensor_path.is_symlink()
            or tensor_path.stat().st_size > 256 * 1024 * 1024
            or sha256_file(tensor_path) != entry.get("tensor_file_sha256")
        ):
            raise ValueError("qualification observation tensor identity is invalid")
        try:
            with zipfile.ZipFile(tensor_path) as archive:
                members = archive.infolist()
            if (
                len(members) != 1
                or members[0].filename != "frames.npy"
                or members[0].file_size > 256 * 1024 * 1024
            ):
                raise ValueError("qualification observation archive exceeds limits")
            with np.load(tensor_path, allow_pickle=False) as payload:
                if set(payload.files) != {"frames"}:
                    raise ValueError("qualification observation archive is malformed")
                frames = payload["frames"]
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            raise ValueError("qualification observation archive is unreadable") from exc
        if (
            frames.dtype != np.uint8
            or frames.ndim != 4
            or frames.shape[-1] != 3
            or frames.shape[0] > 64
            or frames.shape[1] > 1024
            or frames.shape[2] > 1024
            or list(frames.shape) != entry.get("frame_shape")
            or str(frames.dtype) != entry.get("frame_dtype")
            or hashlib.sha256(np.ascontiguousarray(frames).tobytes()).hexdigest()
            != provenance.frames_sha256
        ):
            raise ValueError("qualification observation frames fail verification")
        verified[provenance.observation_id] = provenance
    return verified


def build_qualification_observations(
    episodes: tuple[BenchmarkEpisodeV2, ...],
    *,
    state_index: int = 2,
    shuffle_seed: int = 20260763,
) -> tuple[QualificationObservation, ...]:
    """Build actual, static, and camera-stratified shuffled development arms."""

    if len(episodes) < 6:
        raise ValueError("qualification controls require at least six episodes")
    selected = []
    for episode in episodes:
        if state_index < 0 or state_index >= len(episode.controller_observations):
            raise ValueError("qualification state index is outside an episode")
        selected.append((episode, episode.controller_observations[state_index]))
    donor_by_episode: dict[str, tuple[BenchmarkEpisodeV2, object]] = {}
    cameras = sorted({episode.camera_name for episode, _ in selected})
    for camera in cameras:
        stratum = sorted(
            [item for item in selected if item[0].camera_name == camera],
            key=lambda item: item[0].episode_id,
        )
        if len(stratum) < 2:
            raise ValueError("each camera stratum needs at least two shuffle donors")
        offset = 1 + int(
            sha256_value({"shuffle_seed": shuffle_seed, "camera": camera})[:8], 16
        ) % (len(stratum) - 1)
        for index, item in enumerate(stratum):
            donor_by_episode[item[0].episode_id] = stratum[(index + offset) % len(stratum)]

    observations: list[QualificationObservation] = []
    for episode, package in selected:
        actual = np.asarray(package.frames).copy()
        static = np.repeat(actual[:1], len(actual), axis=0)
        donor_episode, donor_package = donor_by_episode[episode.episode_id]
        shuffled = np.asarray(donor_package.frames).copy()
        for arm, frames, source in (
            ("actual", actual, episode.episode_id),
            ("static_visual", static, episode.episode_id),
            ("shuffled_visual", shuffled, donor_episode.episode_id),
        ):
            frames_sha256 = hashlib.sha256(
                np.ascontiguousarray(frames).tobytes()
            ).hexdigest()
            identity_payload = {
                "protocol": QUALIFICATION_PROTOCOL_VERSION,
                "recipient_episode_id": episode.episode_id,
                "source_episode_id": source,
                "camera_name": episode.camera_name,
                "arm": arm,
                "state_index": state_index,
                "frames_sha256": frames_sha256,
                "recipient_observation_hash": package.record.observation_hash,
                "source_observation_hash": (
                    package.record.observation_hash
                    if arm != "shuffled_visual"
                    else donor_package.record.observation_hash
                ),
            }
            observation_sha256 = sha256_value(identity_payload)
            observation_id = f"qualification-{observation_sha256[:24]}"
            provenance = ObservationProvenance(
                observation_id=observation_id,
                observation_sha256=observation_sha256,
                frames_sha256=frames_sha256,
                controller_manifest_sha256=sha256_value(
                    {
                        **identity_payload,
                        "observation_id": observation_id,
                        "frame_shape": list(frames.shape),
                        "sensor_model_version": package.record.sensor_model_version,
                    }
                ),
                sensor_model_version=package.record.sensor_model_version,
                observed_at=package.record.sampled_at_s,
                study_partition="development-live-qualification",
            )
            observations.append(
                QualificationObservation(
                    provenance=provenance,
                    frames=frames,
                    camera_name=episode.camera_name,
                    episode_id=episode.episode_id,
                    source_episode_id=source,
                    source_observation_sha256=(
                        package.record.observation_hash
                        if arm != "shuffled_visual"
                        else donor_package.record.observation_hash
                    ),
                    arm=arm,
                    reported_route_status=package.record.reported_route_status,
                    report_confidence=package.record.report_confidence,
                    reported_weather_band=package.record.reported_weather_band,
                    route_closure_depth_m=geography_profile_v2(
                        episode.trajectory.geography_profile
                    ).closure_depth_m,
                    route_susceptibility=geography_profile_v2(
                        episode.trajectory.geography_profile
                    ).hydrologic_susceptibility,
                    nominal_travel_time_s=(
                        geography_profile_v2(
                            episode.trajectory.geography_profile
                        ).route_length_m
                        / 1.8
                    ),
                )
            )
    return tuple(observations)


def qualification_request(
    observation: QualificationObservation,
    identity: ModelArtifactIdentity,
    *,
    action_type: str,
) -> RouteWorldModelRequestV2:
    weather_forecast = {
        "mild": 0.25,
        "adverse": 0.60,
        "severe": 0.90,
    }[observation.reported_weather_band]
    return RouteWorldModelRequestV2(
        plan_id=f"qualification:{observation.episode_id}:{observation.arm}:{action_type}",
        route_id=f"qualification-route:{observation.episode_id}",
        asset_id="qualification-asset",
        action_type=action_type,
        belief_status=observation.reported_route_status,
        belief_confidence=observation.report_confidence,
        observation_age_s=0.0,
        observed_depth_m=None,
        projected_depth_m=0.36,
        route_closure_depth_m=observation.route_closure_depth_m,
        route_susceptibility=observation.route_susceptibility,
        travel_time_s=observation.nominal_travel_time_s,
        water_rise_rate=0.00015,
        rain_intensity=0.5,
        upstream_inflow=0.5,
        weather_forecast=weather_forecast,
        sensor_noise=0.1,
        packet_loss=0.0,
        declared_ood_severity=0.0,
        sensor_quality=observation.report_confidence,
        asset_resource=0.9,
        asset_weather_tolerance=0.8,
        visual_observation_id=observation.provenance.observation_id,
        visual_observation_age_s=0.0,
        visual_observation_hash=observation.provenance.observation_sha256,
        visual_frames_sha256=observation.provenance.frames_sha256,
        visual_sensor_version=observation.provenance.sensor_model_version,
        visual_observed_at=observation.provenance.observed_at,
        expected_model_bundle_sha256=identity.bundle_sha256,
        prediction_horizons_s=(60.0, 180.0, 600.0),
        action_parameters={"qualification_only": True},
    )


def run_live_qualification(
    *,
    backend,
    observations: tuple[QualificationObservation, ...],
    action_types: tuple[str, ...],
    output_root: Path,
    observation_arms: tuple[str, ...] = (
        "actual",
        "static_visual",
        "shuffled_visual",
    ),
    timeout_s: float = 120.0,
) -> dict[str, object]:
    """Run post-warmup uncached inference and verified-cache replay on development data."""

    output_root = Path(output_root)
    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError("qualification output root must be new or empty")
    output_root.mkdir(parents=True, exist_ok=True)
    store = ContentAddressedInferenceStore(output_root / "inference-store")
    service = LiveWorldModelService(
        backend=backend,
        observation_reader=QualificationObservationReader(observations),
        artifact_store=store,
        queue_capacity=1,
    )
    service.start()
    rows: list[dict[str, object]] = []
    requests: list[LiveInferenceRequest] = []
    if not observation_arms or len(set(observation_arms)) != len(observation_arms):
        raise ValueError("qualification observation arms must be nonempty and unique")
    selected_observations = tuple(
        item for item in observations if item.arm in observation_arms
    )
    by_episode_arm = {
        (item.episode_id, item.arm): item for item in selected_observations
    }
    episode_ids = sorted({item.episode_id for item in observations})
    if any(
        (episode_id, arm) not in by_episode_arm
        for episode_id in episode_ids
        for arm in observation_arms
    ):
        raise ValueError("qualification observation inventory is incomplete")
    arm_orders = tuple(
        observation_arms[index:] + observation_arms[:index]
        for index in range(len(observation_arms))
    )
    for episode_index, episode_id in enumerate(episode_ids):
        for arm in arm_orders[episode_index % len(arm_orders)]:
            observation = by_episode_arm[(episode_id, arm)]
            for action_type in action_types:
                request = LiveInferenceRequest(
                    route_request=qualification_request(
                        observation,
                        backend.identity,
                        action_type=action_type,
                    ),
                    observation=observation.provenance,
                    model=backend.identity,
                )
                external_started = time.perf_counter_ns()
                service.submit(request)
                deadline = time.monotonic() + timeout_s
                receipt = service.poll(request.request_sha256)
                while (
                    receipt is not None
                    and receipt.state
                    not in {LiveInferenceState.COMPLETED, LiveInferenceState.FAILED}
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.001)
                    receipt = service.poll(request.request_sha256)
                external_ms = (time.perf_counter_ns() - external_started) / 1_000_000.0
                if receipt is None or receipt.state != LiveInferenceState.COMPLETED:
                    raise RuntimeError("qualification inference failed or timed out")
                if receipt.cache_hit:
                    raise RuntimeError("qualification primary inference was not uncached")
                artifact_result = service.artifact(request.request_sha256)
                if artifact_result is None:
                    raise RuntimeError("qualification inference produced no verified artifact")
                artifact, _ = artifact_result
                rows.append(
                    {
                        "episode_id": episode_id,
                        "source_episode_id": observation.source_episode_id,
                        "source_observation_sha256": (
                            observation.source_observation_sha256
                        ),
                        "camera_name": observation.camera_name,
                        "arm": arm,
                        "action_type": action_type,
                        "request_sha256": request.request_sha256,
                        "observation_sha256": observation.provenance.observation_sha256,
                        "artifact_sha256": artifact.artifact_sha256,
                        "latent_sha256": artifact.latent_sha256,
                        "cache_hit": False,
                        "external_end_to_end_ms": external_ms,
                        "queue_wait_ms": receipt.queue_wait_ms,
                        "backend_duration_ms": receipt.backend_duration_ms,
                        "persistence_duration_ms": receipt.persistence_duration_ms,
                        "total_service_ms": receipt.total_service_ms,
                    }
                )
                requests.append(request)
    service.close()

    replay_service = LiveWorldModelService(
        backend=backend,
        observation_reader=QualificationObservationReader(observations),
        artifact_store=store,
        queue_capacity=1,
    )
    replay_rows = []
    for request in requests:
        started = time.perf_counter_ns()
        receipt = replay_service.submit(request)
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000.0
        if (
            receipt.state != LiveInferenceState.COMPLETED
            or not receipt.cache_hit
            or receipt.artifact_sha256 is None
        ):
            raise RuntimeError("qualification cache replay failed verification")
        replay_rows.append(
            {
                "request_sha256": request.request_sha256,
                "artifact_sha256": receipt.artifact_sha256,
                "cache_hit": True,
                "external_end_to_end_ms": elapsed_ms,
            }
        )

    simple = {}
    structured = {}
    for observation in observations:
        if observation.arm != "actual":
            continue
        simple[observation.episode_id] = hashlib.sha256(
            simple_visual_features(observation.frames).tobytes()
        ).hexdigest()
        request = qualification_request(
            observation,
            backend.identity,
            action_type=action_types[0],
        )
        structured[observation.episode_id] = sha256_value(
            list(request.structured_features)
        )
    return {
        "protocol_version": QUALIFICATION_PROTOCOL_VERSION,
        "scope": "development-only live-chain engineering qualification",
        "used_for_trace_gate": False,
        "predictive_superiority_evaluated": False,
        "test_data_accessed": False,
        "model_identity": backend.identity.model_dump(mode="json"),
        "episode_count": len(episode_ids),
        "observation_arms": list(observation_arms),
        "evaluated_action_types": list(action_types),
        "post_warmup_uncached_request_count": len(rows),
        "cache_replay_count": len(replay_rows),
        "rows": rows,
        "cache_replays": replay_rows,
        "simple_visual_feature_hashes": simple,
        "structured_feature_hashes": structured,
        "actual_vs_static_latent_difference_count": sum(
            _paired_latents_differ(rows, episode_id, "actual", "static_visual")
            for episode_id in episode_ids
            for _ in (None,)
        ),
        "actual_vs_shuffled_latent_difference_count": sum(
            _paired_latents_differ(rows, episode_id, "actual", "shuffled_visual")
            for episode_id in episode_ids
            for _ in (None,)
        ),
    }


def _paired_latents_differ(
    rows: list[dict[str, object]], episode_id: str, first_arm: str, second_arm: str
) -> bool:
    first = sorted(
        str(row["latent_sha256"])
        for row in rows
        if row["episode_id"] == episode_id and row["arm"] == first_arm
    )
    second = sorted(
        str(row["latent_sha256"])
        for row in rows
        if row["episode_id"] == episode_id and row["arm"] == second_arm
    )
    return bool(first and second and first != second)


def write_qualification_report(path: Path, report: dict[str, object]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )
    return path


def verify_qualification_report(
    report_path: Path,
    *,
    output_root: Path,
) -> dict[str, object]:
    """Independently reload every reported content-addressed artifact."""

    report_path = Path(report_path)
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("qualification report is unreadable") from exc
    if not isinstance(report, dict):
        raise ValueError("qualification report root must be an object")
    if report.get("test_data_accessed") is not False:
        raise ValueError("qualification report does not preserve the test-data lock")
    if report.get("predictive_superiority_evaluated") is not False:
        raise ValueError("qualification report exceeds its registered engineering scope")
    environment = report.get("environment")
    environment_sha256 = report.get("environment_manifest_sha256")
    if (
        not isinstance(environment, dict)
        or not isinstance(environment_sha256, str)
        or sha256_value(environment) != environment_sha256
    ):
        raise ValueError("qualification environment manifest hash is invalid")
    benchmark_spec = report.get("benchmark_spec")
    if not isinstance(benchmark_spec, dict):
        raise ValueError("qualification benchmark specification is missing")
    parsed_spec = BenchmarkV2Spec.model_validate(benchmark_spec)
    if (
        parsed_spec.spec_sha256 != report.get("benchmark_spec_sha256")
        or parsed_spec.episode_count != 12
    ):
        raise ValueError("qualification benchmark specification hash is invalid")
    expected_episode_ids = {
        episode.episode_id for episode in generate_benchmark_episodes_v2(parsed_spec)
    }
    if {str(row.get("episode_id")) for row in report.get("rows", [])} != (
        expected_episode_ids
    ):
        raise ValueError("qualification episode inventory does not match the benchmark")
    if report.get("warmup_requests") != 2:
        raise ValueError("qualification warm-up policy is invalid")
    upstream = report.get("upstream_checkout")
    if (
        not isinstance(upstream, dict)
        or upstream.get("clean") is not True
        or not isinstance(upstream.get("origin"), str)
        or not re.fullmatch(r"[0-9a-f]{40}", str(upstream.get("commit")))
        or not re.fullmatch(r"[0-9a-f]{40}", str(upstream.get("tree")))
        or not re.fullmatch(
            r"[0-9a-f]{64}", str(upstream.get("tracked_inventory_sha256"))
        )
    ):
        raise ValueError("qualification upstream checkout evidence is invalid")
    if report.get("observation_arms") != [
        "actual",
        "static_visual",
        "shuffled_visual",
    ]:
        raise ValueError("qualification learned observation-arm inventory is invalid")
    observation_bundle = report.get("observation_bundle")
    if not isinstance(observation_bundle, dict):
        raise ValueError("qualification observation bundle identity is missing")
    observations_by_id = verify_qualification_observation_bundle(
        Path(output_root) / "input-observations",
        observation_bundle,
    )
    verified, replay_count = _verify_report_section(
        report,
        Path(output_root),
        expected_environment_sha256=environment_sha256,
        observations_by_id=observations_by_id,
    )
    if report.get("latency_summary") != _recompute_latency_summary(report["rows"]):
        raise ValueError("qualification latency summary does not match raw rows")
    for arm, field in (
        ("static_visual", "actual_vs_static_latent_difference_count"),
        ("shuffled_visual", "actual_vs_shuffled_latent_difference_count"),
    ):
        expected_count = sum(
            _paired_latents_differ(report["rows"], episode_id, "actual", arm)
            for episode_id in expected_episode_ids
        )
        if report.get(field) != expected_count:
            raise ValueError("qualification latent-sensitivity count is invalid")
    control_counts = {}
    controls = report.get("reference_controls", {})
    if not isinstance(controls, dict):
        raise ValueError("qualification reference controls are malformed")
    required_controls = report.get("required_reference_controls", [])
    if required_controls not in ([], ["structured", "simple_visual"]):
        raise ValueError("qualification reference-control requirement is invalid")
    for control in ("structured", "simple_visual"):
        section = controls.get(control)
        if section is None:
            if control in required_controls:
                raise ValueError("qualification required reference control is missing")
            continue
        if not isinstance(section, dict):
            raise ValueError("qualification reference control is malformed")
        if {str(row.get("episode_id")) for row in section.get("rows", [])} != (
            expected_episode_ids
        ):
            raise ValueError("qualification control episode inventory is incomplete")
        model = section.get("model_identity")
        if not isinstance(model, dict) or model.get("integration_kind") != (
            "deterministic-control"
        ):
            raise ValueError("qualification reference control identity is invalid")
        control_verified, control_replays = _verify_report_section(
            section,
            Path(output_root) / "reference-controls" / control,
            expected_environment_sha256=environment_sha256,
            observations_by_id=observations_by_id,
        )
        if section.get("latency_summary") != _recompute_latency_summary(
            section["rows"]
        ):
            raise ValueError("qualification control latency summary is invalid")
        control_counts[control] = {
            "verified_request_count": control_verified,
            "verified_cache_replay_count": control_replays,
        }
        verified += control_verified
        replay_count += control_replays
    if report.get("sha256_sidecar_required") is True:
        sidecar = report_path.with_suffix(report_path.suffix + ".sha256")
        expected_line = (
            f"{hashlib.sha256(report_path.read_bytes()).hexdigest()}  "
            f"{report_path.name}\n"
        )
        if (
            not sidecar.is_file()
            or sidecar.is_symlink()
            or sidecar.read_text(encoding="utf-8") != expected_line
        ):
            raise ValueError("qualification report checksum sidecar is invalid")
    return {
        "verification_schema_version": "live-qualification-verification-v1",
        "passed": True,
        "report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
        "verified_request_count": verified,
        "verified_cache_replay_count": replay_count,
        "reference_controls": control_counts,
        "test_data_accessed": False,
    }


def _verify_report_section(
    section: dict[str, object],
    output_root: Path,
    *,
    expected_environment_sha256: str,
    observations_by_id: dict[str, ObservationProvenance],
) -> tuple[int, int]:
    rows = section.get("rows")
    replays = section.get("cache_replays")
    if not isinstance(rows, list) or not isinstance(replays, list):
        raise ValueError("qualification report rows are malformed")
    if len(rows) != section.get("post_warmup_uncached_request_count") or len(
        replays
    ) != section.get("cache_replay_count"):
        raise ValueError("qualification report counts do not match its ledgers")
    request_ids = [str(row.get("request_sha256")) for row in rows]
    if len(set(request_ids)) != len(request_ids):
        raise ValueError("qualification report repeats a cold request")
    replay_by_request = {
        str(row.get("request_sha256")): row for row in replays
    }
    if set(replay_by_request) != set(request_ids):
        raise ValueError("qualification cache replay inventory is incomplete")
    model = section.get("model_identity")
    if not isinstance(model, dict):
        raise ValueError("qualification report omits model identity")
    parsed_model = ModelArtifactIdentity.model_validate(model)
    if parsed_model.integration_source_tree_sha256 is None:
        raise ValueError("qualification model identity omits the executed source tree")
    store = ContentAddressedInferenceStore(output_root / "inference-store")
    verified = 0
    for row in rows:
        source_episode_id = str(row.get("source_episode_id"))
        source_observation_sha256 = str(row.get("source_observation_sha256"))
        if not re.fullmatch(r"[0-9a-f]{64}", source_observation_sha256):
            raise ValueError("qualification source observation identity is invalid")
        if row.get("arm") == "shuffled_visual":
            if source_episode_id == row.get("episode_id"):
                raise ValueError("qualification shuffled control self-matches an episode")
        elif source_episode_id != row.get("episode_id"):
            raise ValueError("qualification unshuffled control changes source episode")
        if row.get("cache_hit") is not False:
            raise ValueError("qualification primary row is not an uncached inference")
        for field in (
            "external_end_to_end_ms",
            "queue_wait_ms",
            "backend_duration_ms",
            "persistence_duration_ms",
            "total_service_ms",
        ):
            value = row.get(field)
            if not isinstance(value, (int, float)) or not np.isfinite(value) or value < 0:
                raise ValueError("qualification latency row is invalid")
        if float(row["external_end_to_end_ms"]) + 1e-6 < float(
            row["total_service_ms"]
        ):
            raise ValueError("qualification external latency is shorter than service time")
        request_sha256 = str(row["request_sha256"])
        request = LiveInferenceRequest.model_validate(
            store.get_request(request_sha256)
        )
        if observations_by_id.get(request.observation.observation_id) != (
            request.observation
        ):
            raise ValueError("qualification request observation is not replayable")
        result = store.get_for_request(request_sha256)
        if result is None:
            raise ValueError("qualification request has no stored artifact")
        artifact, latent = result
        if (
            artifact.artifact_sha256 != row["artifact_sha256"]
            or artifact.latent_sha256 != row["latent_sha256"]
            or artifact.observation_sha256 != row["observation_sha256"]
            or artifact.model_bundle_sha256 != parsed_model.bundle_sha256
            or artifact.environment_manifest_sha256
            != expected_environment_sha256
            or request.model.bundle_sha256 != parsed_model.bundle_sha256
            or request.observation.observation_sha256 != row["observation_sha256"]
            or request.route_request.action_type != row["action_type"]
            or not np.isfinite(latent).all()
        ):
            raise ValueError("qualification artifact links do not match the report")
        replay = replay_by_request[request_sha256]
        if (
            replay.get("cache_hit") is not True
            or replay.get("artifact_sha256") != artifact.artifact_sha256
        ):
            raise ValueError("qualification cache replay does not preserve artifact identity")
        verified += 1
    evaluated_actions = section.get("evaluated_action_types")
    if (
        not isinstance(evaluated_actions, list)
        or not evaluated_actions
        or len(set(evaluated_actions)) != len(evaluated_actions)
        or not set(evaluated_actions).issubset(parsed_model.supported_action_types)
    ):
        raise ValueError("qualification evaluated action inventory is invalid")
    expected_actions = set(evaluated_actions)
    episodes = {str(row["episode_id"]) for row in rows}
    arms = set(section.get("observation_arms", ["actual"]))
    if any(not episode.startswith("flood-bmv2-dev-") for episode in episodes):
        raise ValueError("qualification row leaves the development namespace")
    expected_inventory = {
        (episode, arm, action)
        for episode in episodes
        for arm in arms
        for action in expected_actions
    }
    actual_inventory = {
        (str(row["episode_id"]), str(row["arm"]), str(row["action_type"]))
        for row in rows
    }
    if actual_inventory != expected_inventory:
        raise ValueError("qualification request inventory is incomplete or unbalanced")
    return verified, len(replays)


def _recompute_latency_summary(
    rows: list[dict[str, object]],
) -> dict[str, object]:
    summary = {}
    for arm in sorted({str(row["arm"]) for row in rows}):
        values = [
            float(row["external_end_to_end_ms"])
            for row in rows
            if row["arm"] == arm
        ]
        summary[arm] = {
            "count": len(values),
            "median_ms": float(np.quantile(values, 0.5)),
            "p95_ms": float(np.quantile(values, 0.95)),
            "p99_ms": float(np.quantile(values, 0.99)),
            "maximum_ms": float(max(values)),
        }
    return summary
