from __future__ import annotations

import platform
import sys
from pathlib import Path


def main() -> None:
    print(f"Python: {sys.version.split()[0]}")
    print(f"Platform: {platform.platform()}")
    if sys.version_info < (3, 10):
        raise SystemExit("Python 3.10 or newer is required; Python 3.12 is recommended")

    for directory in (
        Path("configs"),
        Path("data/raw"),
        Path("data/processed"),
        Path("models/checkpoints"),
        Path("models/manifests"),
        Path("artifacts/records"),
        Path("artifacts/evidence"),
        Path("artifacts/commitments"),
        Path("artifacts/runs"),
    ):
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        print(f"OK directory: {directory}")

    try:
        import torch

        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"PyTorch: {torch.__version__} ({device})")
    except ImportError:
        print("PyTorch: not installed (core TRACE demo still works)")
    print("Verification passed.")


if __name__ == "__main__":
    main()
