#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np

from trace_jepa.util import sha256_file
from trace_jepa.worldmodels.benchmark_v2 import (
    benchmark_v2_episode_ids,
    generate_exogenous_trajectory_v2,
)
from trace_jepa.worldmodels.simulator_observations_v2 import (
    camera_profile_v2,
    capture_controller_observation_v2,
)
from trace_jepa.worldmodels.upstream_dinowm import (
    DINOWM_SOURCE_COMMIT,
    UpstreamDINOWMConfig,
    build_upstream_compatible_vit_predictor,
)
from trace_jepa.worldmodels.vjepa_predictive import (
    VJEPA21_SOURCE_COMMIT,
    VJEPA21FuturePredictor,
)
from run_live_worldmodel_qualification import verify_upstream_checkout


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False)
    with tempfile.NamedTemporaryFile(
        dir=path.parent,
        mode="w",
        encoding="utf-8",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def check_dinowm(repository: Path) -> dict[str, object]:
    import torch

    checkout = verify_upstream_checkout(
        repository,
        expected_origin="https://github.com/gaoyuezhou/dino_wm",
        expected_commit=DINOWM_SOURCE_COMMIT,
    )
    commit = str(checkout["commit"])
    sys.path.insert(0, str(repository))
    try:
        from models.vit import ViTPredictor
    finally:
        sys.path.pop(0)

    torch.manual_seed(1907)
    config = UpstreamDINOWMConfig(
        num_patches=4,
        num_hist=3,
        visual_dim=6,
        action_dim=3,
        operational_dim=2,
        action_embedding_dim=2,
        operational_embedding_dim=2,
        depth=2,
        heads=2,
        mlp_dim=16,
        dim_head=4,
        dropout=0.0,
        embedding_dropout=0.0,
    )
    official = ViTPredictor(
        num_patches=config.num_patches,
        num_frames=config.num_hist,
        dim=config.predictor_dim,
        depth=config.depth,
        heads=config.heads,
        mlp_dim=config.mlp_dim,
        dim_head=config.dim_head,
        dropout=config.dropout,
        emb_dropout=config.embedding_dropout,
        pool="mean",
    ).cuda().eval()
    port = build_upstream_compatible_vit_predictor(config).cuda().eval()
    official_keys = tuple(sorted(official.state_dict()))
    port_keys = tuple(sorted(port.state_dict()))
    if official_keys != port_keys:
        raise AssertionError("DINO-WM port and upstream state dictionaries differ")
    port.load_state_dict(official.state_dict(), strict=True)
    values = torch.randn(
        2,
        config.num_hist * config.num_patches,
        config.predictor_dim,
        device="cuda",
    )
    with torch.inference_mode():
        official_output = official(values)
        port_output = port(values)
    maximum_error = float(torch.max(torch.abs(official_output - port_output)).item())
    if maximum_error > 1e-6:
        raise AssertionError(f"DINO-WM forward parity failed: {maximum_error}")
    return {
        "component": "dinowm",
        "upstream_repository": "https://github.com/gaoyuezhou/dino_wm",
        "upstream_commit": commit,
        "upstream_checkout": checkout,
        "state_dict_key_count": len(official_keys),
        "state_dict_keys_identical": True,
        "forward_maximum_absolute_error": maximum_error,
        "tolerance": 1e-6,
        "passed": True,
    }


def _benchmark_frames() -> tuple[np.ndarray, str, str]:
    episode_id = benchmark_v2_episode_ids(1, campaign_seed=20260721)[0]
    trajectory = generate_exogenous_trajectory_v2(
        episode_id,
        data_seed=20260722,
        geography_name="river_valley",
        weather_name="stratiform",
        ood_name="in_domain",
        observation_times_s=(0.0, 300.0, 600.0),
    )
    package, _ = capture_controller_observation_v2(
        trajectory.states[1],
        camera_profile_v2("drone_oblique"),
    )
    return (
        package.frames.copy(),
        package.record.observation_id,
        package.record.observation_hash,
    )


def check_vjepa(repository: Path, checkpoint: Path) -> dict[str, object]:
    import torch

    checkout = verify_upstream_checkout(
        repository,
        expected_origin="https://github.com/facebookresearch/vjepa2",
        expected_commit=VJEPA21_SOURCE_COMMIT,
    )
    commit = str(checkout["commit"])
    adapter = VJEPA21FuturePredictor.from_official_checkpoint(
        checkpoint_dir=checkpoint.parent,
        device="cuda",
        local_repo=repository,
    )
    if adapter.checkpoint_path.resolve() != checkpoint.resolve():
        raise ValueError("V-JEPA loader resolved a different checkpoint file")
    frames, observation_id, observation_hash = _benchmark_frames()
    model_clip = adapter.prepare_model_clip(frames, target_fill=0)
    context_mask, target_mask = adapter.masks(len(model_clip))
    with torch.inference_mode():
        encoded = adapter.encoder(model_clip, [context_mask])
        encoded = adapter._tensor_output(encoded)
        direct = adapter.predictor(
            encoded,
            [context_mask],
            [target_mask],
            mod="video",
        )
        if isinstance(direct, tuple):
            direct = direct[0]
        direct = adapter._tensor_output(direct).detach().cpu().float().numpy()
    wrapped = adapter.predict_future_tokens(frames, target_fill=0)
    alternate_placeholder = adapter.predict_future_tokens(frames, target_fill=255)
    direct_error = float(np.max(np.abs(direct - wrapped)))
    leakage_error = float(np.max(np.abs(wrapped - alternate_placeholder)))
    if direct_error > 1e-6:
        raise AssertionError(f"V-JEPA direct-call parity failed: {direct_error}")
    if leakage_error > 1e-6:
        raise AssertionError(f"V-JEPA masked-target leakage test failed: {leakage_error}")
    return {
        "component": "vjepa2.1",
        "upstream_repository": "https://github.com/facebookresearch/vjepa2",
        "upstream_commit": commit,
        "upstream_checkout": checkout,
        "checkpoint_sha256": sha256_file(checkpoint),
        "benchmark_observation_id": observation_id,
        "benchmark_observation_hash": observation_hash,
        "context_token_count": adapter.spec.context_token_count,
        "target_token_count": adapter.spec.target_token_count,
        "prediction_shape": list(wrapped.shape),
        "direct_forward_maximum_absolute_error": direct_error,
        "masked_placeholder_maximum_absolute_error": leakage_error,
        "tolerance": 1e-6,
        "passed": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify TRACE world-model adapters against pinned upstream implementations"
    )
    parser.add_argument("--component", choices=("dinowm", "vjepa"), required=True)
    parser.add_argument("--upstream-repo", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.component == "dinowm":
        result = check_dinowm(args.upstream_repo)
    else:
        if args.checkpoint is None:
            parser.error("--checkpoint is required for V-JEPA parity")
        result = check_vjepa(args.upstream_repo, args.checkpoint)
    import torch

    result["torch_version"] = torch.__version__
    result["cuda_version"] = torch.version.cuda
    result["gpu_name"] = torch.cuda.get_device_name(0)
    _write_json_atomic(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
