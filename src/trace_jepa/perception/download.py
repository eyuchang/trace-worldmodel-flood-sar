from __future__ import annotations

import argparse
import json
import os
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
        "sha256": "848a77c33cc9e6649ed2119c9bea1e2c569bcdab9539ff3e7c02ccc2959ddf4d",
        "size_bytes": "1664223428",
    },
}


def load_encoder_pin(path: Path) -> dict[str, Any]:
    """Load the immutable encoder pin shared by downloader and offline inference."""
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise ValueError("V-JEPA encoder pin must be a safe regular file")
    pin = json.loads(path.read_text(encoding="utf-8"))
    if pin.get("manifest_version") != "trace-vjepa-encoder-pin-v1":
        raise ValueError("unexpected V-JEPA encoder-pin schema")
    required = {
        "checkpoint",
        "crop_size",
        "encoder_version",
        "hub_entry",
        "hub_repo",
        "source_commit",
    }
    if required - set(pin):
        raise ValueError("V-JEPA encoder pin metadata is incomplete")
    checkpoint = pin.get("checkpoint")
    if not isinstance(checkpoint, dict):
        raise TypeError("V-JEPA encoder pin has no checkpoint block")
    required_checkpoint = {"file_name", "sha256", "size_bytes", "url", "encoder_key"}
    if required_checkpoint - set(checkpoint):
        raise ValueError("V-JEPA encoder pin checkpoint metadata is incomplete")
    model_name = str(pin["hub_entry"])
    if model_name not in OFFICIAL_VJEPA21_CHECKPOINTS:
        raise ValueError("V-JEPA encoder pin names an unsupported model")
    official = OFFICIAL_VJEPA21_CHECKPOINTS[model_name]
    for field_name in required_checkpoint:
        if str(checkpoint[field_name]) != str(official[field_name]):
            raise ValueError(f"V-JEPA encoder pin {field_name} disagrees with source registry")
    return pin


def _verified_checkpoint(torch: Any, spec: dict[str, str], checkpoint_dir: Path) -> Path:
    """Download once, verify before deserialization, and reject filesystem indirection."""
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = checkpoint_dir / spec["file_name"]
    if checkpoint_path.is_symlink():
        raise RuntimeError("V-JEPA checkpoint must not be a symlink")
    if not checkpoint_path.is_file():
        partial = checkpoint_path.with_suffix(checkpoint_path.suffix + ".partial")
        if partial.exists():
            if partial.is_symlink() or not partial.is_file():
                raise RuntimeError("unsafe partial V-JEPA checkpoint path")
            partial.unlink()
        torch.hub.download_url_to_file(spec["url"], str(partial), progress=True)
        if partial.stat().st_size != int(spec["size_bytes"]):
            partial.unlink()
            raise RuntimeError("downloaded V-JEPA checkpoint has the wrong byte length")
        if sha256_file(partial) != spec["sha256"]:
            partial.unlink()
            raise RuntimeError("downloaded V-JEPA checkpoint digest mismatch")
        os.replace(partial, checkpoint_path)
    if checkpoint_path.stat().st_size != int(spec["size_bytes"]):
        raise RuntimeError("cached V-JEPA checkpoint has the wrong byte length")
    if sha256_file(checkpoint_path) != spec["sha256"]:
        raise RuntimeError("cached V-JEPA checkpoint digest mismatch")
    return checkpoint_path


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
    checkpoint_path = _verified_checkpoint(torch, spec, checkpoint_dir)
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
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
    return encoder, pretraining_predictor, processor, checkpoint_path


def download_model(
    pin_manifest: Path,
    receipt_path: Path,
    checkpoint_dir: Path = Path("models/external/vjepa2"),
) -> Path:
    pin_manifest = Path(pin_manifest)
    receipt_path = Path(receipt_path)
    if receipt_path.resolve() == pin_manifest.resolve():
        raise ValueError("download receipt must not overwrite the immutable encoder pin")
    if receipt_path.is_symlink() or (receipt_path.exists() and not receipt_path.is_file()):
        raise ValueError("V-JEPA download receipt path is unsafe")
    pin = load_encoder_pin(pin_manifest)
    checkpoint = pin["checkpoint"]
    assert isinstance(checkpoint, dict)
    model_name = str(pin["hub_entry"])
    source_commit = str(pin["source_commit"])
    hub_repo = f"{pin['hub_repo']}:{source_commit}"
    crop_size = int(pin["crop_size"])
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError(
            "PyTorch is required. Install the appropriate build before downloading JEPA."
        ) from exc

    encoder, predictor, _, checkpoint_path = load_official_vjepa21(
        model_name=model_name,
        crop_size=crop_size,
        checkpoint_dir=checkpoint_dir,
        hub_repo=hub_repo,
        device="cpu",
    )

    receipt = {
        "schema_version": "trace-vjepa-download-receipt-v1",
        "encoder_pin_sha256": sha256_file(pin_manifest),
        "encoder_version": pin["encoder_version"],
        "encoder_type": type(encoder).__name__,
        "pretraining_predictor_type": type(predictor).__name__ if predictor is not None else None,
        "torch_version": torch.__version__,
        "python_version": sys.version,
        "platform": platform.platform(),
        "torch_hub_dir": str(Path(torch.hub.get_dir()).resolve()),
        "checkpoint": {
            "file_name": checkpoint_path.name,
            "local_path_recorded": False,
            "size_bytes": checkpoint_path.stat().st_size,
            "sha256": sha256_file(checkpoint_path),
        },
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "role": "frozen_visual_encoder",
        "warning": (
            "The returned self-supervised pretraining predictor is not the flood-domain "
            "action-conditioned predictor. Train the latter on synchronized rescue trajectories."
        ),
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = receipt_path.with_suffix(receipt_path.suffix + ".partial")
    if temporary.is_symlink() or (temporary.exists() and not temporary.is_file()):
        raise ValueError("V-JEPA download receipt temporary path is unsafe")
    temporary.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, receipt_path)
    return receipt_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and record an official V-JEPA 2.1 model")
    parser.add_argument(
        "--pin-manifest",
        type=Path,
        default=Path("models/manifests/vjepa2_1_vit_base_384.manifest.json"),
    )
    parser.add_argument(
        "--receipt",
        type=Path,
        default=Path("models/receipts/vjepa2_1_vit_base_384.download.json"),
    )
    parser.add_argument("--checkpoint-dir", type=Path, default=Path("models/external/vjepa2"))
    args = parser.parse_args()
    path = download_model(
        args.pin_manifest,
        args.receipt,
        args.checkpoint_dir,
    )
    print(f"Wrote download receipt: {path}")


if __name__ == "__main__":
    main()
