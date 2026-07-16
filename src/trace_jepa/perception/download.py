from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trace_jepa.util import sha256_file


# These are the checkpoint names linked from the official V-JEPA 2 repository.
# We construct the architecture with pretrained=False and then load the official
# checkpoint ourselves. This keeps the course independent of transient changes to
# the upstream Hub helper while still using the upstream architecture and weights.
OFFICIAL_VJEPA21_CHECKPOINTS: dict[str, dict[str, str]] = {
    "vjepa2_1_vit_base_384": {
        "url": "https://dl.fbaipublicfiles.com/vjepa2/vjepa2_1_vitb_dist_vitG_384.pt",
        "file_name": "vjepa2_1_vitb_dist_vitG_384.pt",
        "encoder_key": "ema_encoder",
    },
    "vjepa2_1_vit_large_384": {
        "url": "https://dl.fbaipublicfiles.com/vjepa2/vjepa2_1_vitl_dist_vitG_384.pt",
        "file_name": "vjepa2_1_vitl_dist_vitG_384.pt",
        "encoder_key": "ema_encoder",
    },
    "vjepa2_1_vit_giant_384": {
        "url": "https://dl.fbaipublicfiles.com/vjepa2/vjepa2_1_vitg_384.pt",
        "file_name": "vjepa2_1_vitg_384.pt",
        "encoder_key": "ema_encoder",
    },
    "vjepa2_1_vit_gigantic_384": {
        "url": "https://dl.fbaipublicfiles.com/vjepa2/vjepa2_1_vitG_384.pt",
        "file_name": "vjepa2_1_vitG_384.pt",
        "encoder_key": "ema_encoder",
    },
}


def clean_backbone_state_dict(state_dict: dict[str, Any]) -> dict[str, Any]:
    """Remove distributed-training prefixes used in official checkpoints."""
    cleaned: dict[str, Any] = {}
    for key, value in state_dict.items():
        key = key.replace("module.", "").replace("backbone.", "")
        cleaned[key] = value
    return cleaned


def _split_loaded_model(loaded: Any) -> tuple[Any, Any | None]:
    if isinstance(loaded, tuple):
        if not loaded:
            raise TypeError("The V-JEPA Hub entry returned an empty tuple")
        return loaded[0], loaded[1] if len(loaded) > 1 else None
    return loaded, None


def load_official_vjepa21(
    *,
    model_name: str = "vjepa2_1_vit_base_384",
    crop_size: int = 384,
    checkpoint_dir: Path = Path("models/external/vjepa2"),
    hub_repo: str = "facebookresearch/vjepa2:204698b45b3712590f06245fbfba32d3be539812",
    source: str = "github",
    local_repo: Path | None = None,
    device: str = "cpu",
) -> tuple[Any, Any | None, Any, Path]:
    """Load an official V-JEPA 2.1 encoder with a reproducible local checkpoint.

    The official Hub function is used to construct the architecture with
    ``pretrained=False``. The checkpoint linked by the official repository is then
    downloaded into this project's model cache and loaded explicitly. The course
    uses the encoder; the self-supervised pretraining predictor is returned only so
    its presence can be recorded and inspected.
    """

    try:
        import torch
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("PyTorch is required. Install the appropriate build first.") from exc

    if model_name not in OFFICIAL_VJEPA21_CHECKPOINTS:
        supported = ", ".join(sorted(OFFICIAL_VJEPA21_CHECKPOINTS))
        raise ValueError(f"Unsupported V-JEPA 2.1 model {model_name!r}. Choose one of: {supported}")

    repo_or_dir = str(local_repo) if source == "local" and local_repo else hub_repo
    loaded = torch.hub.load(
        repo_or_dir,
        model_name,
        source=source,
        pretrained=False,
        trust_repo=True,
    )
    encoder, pretraining_predictor = _split_loaded_model(loaded)

    spec = OFFICIAL_VJEPA21_CHECKPOINTS[model_name]
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = torch.hub.load_state_dict_from_url(
        spec["url"],
        model_dir=str(checkpoint_dir),
        file_name=spec["file_name"],
        map_location="cpu",
        progress=True,
    )
    if spec["encoder_key"] not in checkpoint:
        raise KeyError(
            f"Official checkpoint did not contain encoder key {spec['encoder_key']!r}; "
            f"available keys: {sorted(checkpoint)}"
        )
    encoder_state = clean_backbone_state_dict(checkpoint[spec["encoder_key"]])
    encoder.load_state_dict(encoder_state, strict=True)
    encoder.to(device).eval()

    processor = torch.hub.load(
        repo_or_dir,
        "vjepa2_preprocessor",
        source=source,
        crop_size=crop_size,
        pretrained=False,
        trust_repo=True,
    )
    checkpoint_path = checkpoint_dir / spec["file_name"]
    return encoder, pretraining_predictor, processor, checkpoint_path


def download_model(
    model_name: str,
    output_dir: Path,
    crop_size: int = 384,
    checkpoint_dir: Path = Path("models/external/vjepa2"),
    hub_repo: str = "facebookresearch/vjepa2:204698b45b3712590f06245fbfba32d3be539812",
) -> Path:
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("PyTorch is required. Install the appropriate build before downloading JEPA.") from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    encoder, predictor, _, checkpoint_path = load_official_vjepa21(
        model_name=model_name,
        crop_size=crop_size,
        checkpoint_dir=checkpoint_dir,
        hub_repo=hub_repo,
        device="cpu",
    )

    manifest = {
        "manifest_version": "vjepa-download-v2",
        "hub_repo": hub_repo,
        "hub_entry": model_name,
        "preprocessor_entry": "vjepa2_preprocessor",
        "crop_size": crop_size,
        "encoder_type": type(encoder).__name__,
        "pretraining_predictor_type": type(predictor).__name__ if predictor is not None else None,
        "torch_version": torch.__version__,
        "python_version": sys.version,
        "platform": platform.platform(),
        "torch_hub_dir": str(Path(torch.hub.get_dir()).resolve()),
        "checkpoint": {
            "path": str(checkpoint_path.resolve()),
            "url": OFFICIAL_VJEPA21_CHECKPOINTS[model_name]["url"],
            "size_bytes": checkpoint_path.stat().st_size,
            "sha256": sha256_file(checkpoint_path),
            "encoder_key": OFFICIAL_VJEPA21_CHECKPOINTS[model_name]["encoder_key"],
        },
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "role": "frozen_visual_encoder",
        "warning": (
            "The returned self-supervised pretraining predictor is not the flood-domain "
            "action-conditioned predictor. Train the latter on synchronized rescue trajectories."
        ),
    }
    path = output_dir / f"{model_name}.manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and record an official V-JEPA 2.1 model")
    parser.add_argument("--model", default="vjepa2_1_vit_base_384")
    parser.add_argument("--crop-size", type=int, default=384)
    parser.add_argument("--output", type=Path, default=Path("models/manifests"))
    parser.add_argument("--checkpoint-dir", type=Path, default=Path("models/external/vjepa2"))
    parser.add_argument("--hub-repo", default="facebookresearch/vjepa2:204698b45b3712590f06245fbfba32d3be539812")
    args = parser.parse_args()
    path = download_model(
        args.model,
        args.output,
        args.crop_size,
        args.checkpoint_dir,
        args.hub_repo,
    )
    print(f"Wrote model manifest: {path}")


if __name__ == "__main__":
    main()
