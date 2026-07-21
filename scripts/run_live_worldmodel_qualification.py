from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

import numpy as np

from trace_jepa.perception.dinov2 import (
    DINOV2_SOURCE_REVISION,
    DINOv2EncoderSpec,
    DINOv2PatchEncoder,
    resolve_dinov2_checkpoint,
)
from trace_jepa.util import sha256_file, sha256_value
from trace_jepa.worldmodels.benchmark_v2 import (
    BenchmarkV2Spec,
    generate_benchmark_episodes_v2,
)
from trace_jepa.worldmodels.contracts import ModelArtifactIdentity
from trace_jepa.worldmodels.dataset import ACTION_NAMES
from trace_jepa.worldmodels.dinowm import load_dinowm_checkpoint
from trace_jepa.worldmodels.live_backends import (
    DeterministicFeatureControlBackend,
    DINOWMPredictiveLatentBackend,
    VJEPAPredictiveLatentBackend,
)
from trace_jepa.worldmodels.live_qualification import (
    build_qualification_observations,
    qualification_request,
    run_live_qualification,
    write_qualification_observation_bundle,
    write_qualification_report,
)
from trace_jepa.worldmodels.upstream_dinowm import (
    DINOWM_SOURCE_COMMIT,
    DINOWM_SOURCE_REPOSITORY,
)
from trace_jepa.worldmodels.vjepa_predictive import (
    VJEPA21_SOURCE_COMMIT,
    VJEPA21_SOURCE_REPOSITORY,
    VJEPA21_VITB_CHECKPOINT_SHA256,
    VJEPA21FuturePredictor,
)


DINOV2_EXPECTED_CHECKPOINT_SHA256 = (
    "b938bf1bc15cd2ec0feacfe3a1bb553fe8ea9ca46a7e1d8d00217f29aef60cd9"
)
TRACE_SOURCE_REPOSITORY = "https://github.com/eyuchang/trace-jepa-flood-sar"
TRACE_BASE_COMMIT = "5dc982b40af169cd224d5d59a5ac06c159492123"
VJEPA_EXPECTED_ORIGIN = "https://github.com/facebookresearch/vjepa2"
DINOV2_EXPECTED_ORIGIN = "https://github.com/facebookresearch/dinov2"


def integration_source_tree_sha256() -> str:
    root = Path(__file__).resolve().parents[1]
    paths = sorted((root / "src").rglob("*.py")) + [
        root / "scripts" / "run_live_worldmodel_qualification.py",
        root / "scripts" / "run_live_trace_evidence_smoke.py",
        root / "scripts" / "verify_live_worldmodel_qualification.py",
    ]
    return sha256_value(
        [
            {
                "path": str(path.relative_to(root)),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in paths
        ]
    )


def verify_upstream_checkout(
    path: Path,
    *,
    expected_origin: str,
    expected_commit: str,
) -> dict[str, object]:
    path = Path(path)
    if not path.is_dir() or path.is_symlink():
        raise ValueError("upstream checkout is absent or unsafe")

    def git(*arguments: str) -> str:
        result = subprocess.run(
            ("git", *arguments),
            cwd=path,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout.strip()

    origin = git("remote", "get-url", "origin").removesuffix(".git")
    commit = git("rev-parse", "HEAD")
    status = git("status", "--porcelain=v1", "--untracked-files=all")
    submodules = git("submodule", "status", "--recursive")
    if origin != expected_origin or commit != expected_commit or status:
        raise ValueError("upstream checkout identity or cleanliness check failed")
    if any(line and line[0] in {"-", "+", "U"} for line in submodules.splitlines()):
        raise ValueError("upstream checkout has an uninitialized or modified submodule")
    inventory = git("ls-files", "-s")
    return {
        "origin": origin,
        "commit": commit,
        "tree": git("rev-parse", "HEAD^{tree}"),
        "tracked_inventory_sha256": hashlib.sha256(
            inventory.encode("utf-8")
        ).hexdigest(),
        "clean": True,
        "submodule_status": submodules,
    }


def state_mapping_sha256(state_dict) -> str:
    digest = hashlib.sha256()
    for name, tensor in sorted(state_dict.items()):
        values = tensor.detach().cpu().contiguous()
        digest.update(name.encode("utf-8"))
        digest.update(str(values.dtype).encode("ascii"))
        digest.update(json.dumps(list(values.shape), separators=(",", ":")).encode())
        digest.update(values.numpy().tobytes())
    return digest.hexdigest()


def model_state_sha256(model) -> str:
    return state_mapping_sha256(model.state_dict())


def environment_manifest(device: str) -> dict[str, object]:
    import torch

    return {
        "python": sys.version,
        "platform": platform.platform(),
        "torch": torch.__version__,
        "cuda_runtime": torch.version.cuda,
        "cudnn": torch.backends.cudnn.version(),
        "device": device,
        "gpu": torch.cuda.get_device_name(device) if device.startswith("cuda") else None,
        "deterministic_algorithms": torch.are_deterministic_algorithms_enabled(),
        "cudnn_benchmark": torch.backends.cudnn.benchmark,
        "tf32_matmul": torch.backends.cuda.matmul.allow_tf32,
        "tf32_cudnn": torch.backends.cudnn.allow_tf32,
        "numpy": np.__version__,
    }


def _not_applicable_hash(role: str) -> str:
    return sha256_value(
        {
            "role": role,
            "status": "not_applicable_for_non_licensing_latent_qualification",
        }
    )


def build_vjepa_backend(args, environment_sha256: str):
    upstream_manifest = verify_upstream_checkout(
        args.vjepa_upstream,
        expected_origin=VJEPA_EXPECTED_ORIGIN,
        expected_commit=VJEPA21_SOURCE_COMMIT,
    )
    predictor = VJEPA21FuturePredictor.from_official_checkpoint(
        checkpoint_dir=args.vjepa_checkpoint_dir,
        device=args.device,
        local_repo=args.vjepa_upstream,
    )
    head_hash = _not_applicable_hash("outcome_head")
    calibration_hash = _not_applicable_hash("calibration")
    identity = ModelArtifactIdentity(
        family="vjepa2.1-predictive-support",
        integration_kind="official-upstream",
        source_repository=VJEPA21_SOURCE_REPOSITORY,
        source_commit=VJEPA21_SOURCE_COMMIT,
        integration_source_tree_sha256=integration_source_tree_sha256(),
        encoder_version="vjepa2.1-vitb-384",
        encoder_checkpoint_sha256=VJEPA21_VITB_CHECKPOINT_SHA256,
        dynamics_version="vjepa2.1-official-predictor",
        dynamics_checkpoint_sha256=VJEPA21_VITB_CHECKPOINT_SHA256,
        outcome_head_version="not-applicable-supporting",
        outcome_head_sha256=head_hash,
        calibration_version="not-applicable-supporting",
        calibration_artifact_sha256=calibration_hash,
        training_snapshot_sha256=sha256_value(
            {
                "source_commit": VJEPA21_SOURCE_COMMIT,
                "checkpoint": VJEPA21_VITB_CHECKPOINT_SHA256,
            }
        ),
        preprocessing_version="vjepa2.1-preprocessor-384-v1",
        feature_schema_version="vjepa2.1-future-spatiotemporal-tokens-v1",
        action_schema_version="flood-actions-dynamic-v1",
        supported_action_types=("dispatch_rescue_boat",),
    )
    backend = VJEPAPredictiveLatentBackend(
        predictor=predictor,
        identity=identity,
        environment_manifest_sha256=environment_sha256,
    )
    backend.upstream_checkout_manifest = upstream_manifest
    return backend, ("dispatch_rescue_boat",)


def build_dinowm_backend(args, environment_sha256: str):
    model, config, metadata = load_dinowm_checkpoint(args.dinowm_checkpoint)
    upstream_manifest = verify_upstream_checkout(
        args.dinov2_upstream,
        expected_origin=DINOV2_EXPECTED_ORIGIN,
        expected_commit=DINOV2_SOURCE_REVISION,
    )
    encoder_metadata = metadata.get("encoder")
    if not isinstance(encoder_metadata, dict):
        raise ValueError("DINO-WM checkpoint omits its encoder metadata")
    expected_encoder_metadata = {
        "checkpoint_sha256": DINOV2_EXPECTED_CHECKPOINT_SHA256,
        "feature_dim": config.feature_dim,
        "feature_key": "x_norm_patchtokens",
        "frozen": True,
        "input_size": 112,
        "model_name": "dinov2_vits14",
        "patch_count": config.patch_count,
        "patch_size": 14,
        "source_revision": DINOV2_SOURCE_REVISION,
    }
    if any(
        encoder_metadata.get(key) != value
        for key, value in expected_encoder_metadata.items()
    ):
        raise ValueError("DINO-WM checkpoint encoder metadata is incompatible")
    if metadata.get("development_only") is not True or metadata.get(
        "test_rows_accessed"
    ) is not False:
        raise ValueError("DINO-WM checkpoint violates the development-only boundary")
    encoder = DINOv2PatchEncoder(
        spec=DINOv2EncoderSpec(input_size=112),
        local_repo=args.dinov2_upstream,
        device=args.device,
    )
    encoder_checkpoint = resolve_dinov2_checkpoint()
    encoder_sha256 = sha256_file(encoder_checkpoint)
    if encoder_sha256 != DINOV2_EXPECTED_CHECKPOINT_SHA256:
        raise ValueError("official DINOv2 checkpoint hash mismatch")
    import torch

    checkpoint_state = torch.load(
        encoder_checkpoint,
        map_location="cpu",
        weights_only=True,
    )
    if not isinstance(checkpoint_state, dict):
        raise ValueError("official DINOv2 checkpoint state is malformed")
    loaded_encoder_state_sha256 = model_state_sha256(encoder.model)
    if state_mapping_sha256(checkpoint_state) != loaded_encoder_state_sha256:
        raise ValueError("loaded DINOv2 model state differs from the registered checkpoint")
    dynamics_sha256 = sha256_file(args.dinowm_checkpoint)
    action_names = tuple(ACTION_NAMES)
    if config.action_count != len(action_names):
        raise ValueError("DINO-WM checkpoint action count does not match the schema")
    identity = ModelArtifactIdentity(
        family="dinowm-flood-sar-support",
        integration_kind="upstream-inspired-adaptation",
        source_repository=TRACE_SOURCE_REPOSITORY,
        source_commit=TRACE_BASE_COMMIT,
        integration_source_tree_sha256=integration_source_tree_sha256(),
        upstream_basis_repository=DINOWM_SOURCE_REPOSITORY,
        upstream_basis_commit=DINOWM_SOURCE_COMMIT,
        encoder_version=f"dinov2_vits14:{DINOV2_SOURCE_REVISION[:12]}",
        encoder_checkpoint_sha256=encoder_sha256,
        loaded_encoder_state_sha256=loaded_encoder_state_sha256,
        dynamics_version="flood-sar-dinowm-predictor-v1",
        dynamics_checkpoint_sha256=dynamics_sha256,
        outcome_head_version="not-applicable-supporting",
        outcome_head_sha256=_not_applicable_hash("outcome_head"),
        calibration_version="not-applicable-supporting",
        calibration_artifact_sha256=_not_applicable_hash("calibration"),
        training_snapshot_sha256=str(metadata["training_dataset_sha256"]),
        preprocessing_version="dinov2-vits14-112-frame-index-last-v1",
        feature_schema_version="dinowm-predicted-future-patch-tokens-v1",
        action_schema_version="flood-actions-dynamic-v1",
        supported_action_types=tuple(sorted(action_names)),
    )
    backend = DINOWMPredictiveLatentBackend(
        encoder=encoder,
        predictor=model,
        predictor_config=config,
        action_names=action_names,
        identity=identity,
        environment_manifest_sha256=environment_sha256,
        device=args.device,
        frame_index=1,
    )
    backend.upstream_checkout_manifest = upstream_manifest
    return backend, ("dispatch_rescue_boat",)


def _latency_summary(rows: list[dict[str, object]]) -> dict[str, object]:
    summary = {}
    for arm in sorted({str(row["arm"]) for row in rows}):
        selected = [
            float(row["external_end_to_end_ms"])
            for row in rows
            if row["arm"] == arm
        ]
        summary[arm] = {
            "count": len(selected),
            "median_ms": float(np.quantile(selected, 0.5)),
            "p95_ms": float(np.quantile(selected, 0.95)),
            "p99_ms": float(np.quantile(selected, 0.99)),
            "maximum_ms": float(max(selected)),
        }
    return summary


def build_control_backend(
    control: str,
    *,
    action_types: tuple[str, ...],
    environment_sha256: str,
) -> DeterministicFeatureControlBackend:
    definition_sha256 = sha256_value(
        {
            "control": control,
            "definition_version": "live-feature-controls-v1",
            "source_commit": TRACE_BASE_COMMIT,
        }
    )
    identity = ModelArtifactIdentity(
        family=f"{control}-feature-control",
        integration_kind="deterministic-control",
        source_repository=TRACE_SOURCE_REPOSITORY,
        source_commit=TRACE_BASE_COMMIT,
        integration_source_tree_sha256=integration_source_tree_sha256(),
        encoder_version=f"{control}-features-v1",
        encoder_checkpoint_sha256=definition_sha256,
        outcome_head_version="not-applicable-supporting",
        outcome_head_sha256=_not_applicable_hash("outcome_head"),
        calibration_version="not-applicable-supporting",
        calibration_artifact_sha256=_not_applicable_hash("calibration"),
        training_snapshot_sha256=definition_sha256,
        preprocessing_version=f"{control}-preprocessing-v1",
        feature_schema_version=f"{control}-features-v1",
        action_schema_version="flood-actions-dynamic-v1",
        supported_action_types=tuple(sorted(action_types)),
    )
    return DeterministicFeatureControlBackend(
        control=control,
        identity=identity,
        environment_manifest_sha256=environment_sha256,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a development-only live learned-model engineering qualification"
    )
    parser.add_argument("--model", choices=("vjepa", "dinowm"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--episode-count", type=int, default=12)
    parser.add_argument("--campaign-seed", type=int, default=20260760)
    parser.add_argument("--split-seed", type=int, default=20260761)
    parser.add_argument("--vjepa-checkpoint-dir", type=Path)
    parser.add_argument("--vjepa-upstream", type=Path)
    parser.add_argument("--dinowm-checkpoint", type=Path)
    parser.add_argument("--dinov2-upstream", type=Path)
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        raise ValueError("qualification output must be new or empty")
    if args.episode_count != 12:
        raise ValueError("qualification-v1 freezes exactly 12 development episodes")
    if args.model == "vjepa" and (
        args.vjepa_checkpoint_dir is None or args.vjepa_upstream is None
    ):
        parser.error("V-JEPA requires --vjepa-checkpoint-dir and --vjepa-upstream")
    if args.model == "dinowm" and (
        args.dinowm_checkpoint is None or args.dinov2_upstream is None
    ):
        parser.error("DINO-WM requires --dinowm-checkpoint and --dinov2-upstream")

    import torch

    torch.manual_seed(20260765)
    np.random.seed(20260765)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark = False
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    environment = environment_manifest(args.device)
    environment_sha256 = sha256_value(environment)
    backend, action_types = (
        build_vjepa_backend(args, environment_sha256)
        if args.model == "vjepa"
        else build_dinowm_backend(args, environment_sha256)
    )
    spec = BenchmarkV2Spec(
        campaign_seed=args.campaign_seed,
        split_seed=args.split_seed,
        episode_count=args.episode_count,
    )
    episodes = generate_benchmark_episodes_v2(spec)
    observations = build_qualification_observations(episodes)
    actual = [item for item in observations if item.arm == "actual"]
    for item in actual[:2]:
        backend.infer(
            frames=item.frames,
            request=qualification_request(
                item,
                backend.identity,
                action_type=action_types[0],
            ),
        )
    report = run_live_qualification(
        backend=backend,
        observations=observations,
        action_types=action_types,
        output_root=args.output,
    )
    control_reports = {}
    for control in ("structured", "simple_visual"):
        control_backend = build_control_backend(
            control,
            action_types=action_types,
            environment_sha256=environment_sha256,
        )
        control_report = run_live_qualification(
            backend=control_backend,
            observations=observations,
            action_types=action_types,
            output_root=args.output / "reference-controls" / control,
            observation_arms=("actual",),
        )
        control_reports[control] = {
            "model_identity": control_report["model_identity"],
            "episode_count": control_report["episode_count"],
            "post_warmup_uncached_request_count": control_report[
                "post_warmup_uncached_request_count"
            ],
            "cache_replay_count": control_report["cache_replay_count"],
            "evaluated_action_types": control_report["evaluated_action_types"],
            "rows": control_report["rows"],
            "cache_replays": control_report["cache_replays"],
            "latency_summary": _latency_summary(control_report["rows"]),
        }
    observation_bundle = write_qualification_observation_bundle(
        args.output / "input-observations",
        observations,
    )
    report.update(
        {
            "benchmark_spec": spec.model_dump(mode="json"),
            "benchmark_spec_sha256": spec.spec_sha256,
            "environment": environment,
            "environment_manifest_sha256": environment_sha256,
            "upstream_checkout": backend.upstream_checkout_manifest,
            "latency_summary": _latency_summary(report["rows"]),
            "warmup_requests": 2,
            "reference_controls": control_reports,
            "required_reference_controls": ["structured", "simple_visual"],
            "observation_bundle": observation_bundle,
            "sha256_sidecar_required": True,
            "claim_boundary": (
                "This development-only run checks live inference, integrity, cache "
                "replay, input-channel wiring, and descriptive post-warmup batch-one "
                "latency on the registered H100 environment. It does not test "
                "predictive quality, operational safety, or TRACE RQ1-RQ5."
            ),
        }
    )
    report_path = write_qualification_report(
        args.output / f"{args.model}_live_qualification_report.json",
        report,
    )
    checksum_path = report_path.with_suffix(report_path.suffix + ".sha256")
    checksum_path.write_text(
        f"{sha256_file(report_path)}  {report_path.name}\n", encoding="utf-8"
    )
    print(json.dumps(report["latency_summary"], indent=2, sort_keys=True))
    print(f"report={report_path}")
    print(f"report_sha256={sha256_file(report_path)}")


if __name__ == "__main__":
    main()
