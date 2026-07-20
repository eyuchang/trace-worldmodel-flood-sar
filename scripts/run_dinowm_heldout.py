from __future__ import annotations

import argparse
import json
from pathlib import Path

from trace_jepa.worldmodels.dinowm_freeze import verify_dinowm_freeze_manifest
from trace_jepa.worldmodels.dinowm_training import run_dinowm_heldout_evaluation


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the single frozen DINO-WM held-out evaluation without fitting"
    )
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--development-dir", type=Path, required=True)
    parser.add_argument("--test-dataset", type=Path, required=True)
    parser.add_argument("--freeze-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = verify_dinowm_freeze_manifest(
        args.repository_root,
        args.freeze_manifest,
    )
    results = args.development_dir / "results"
    report = run_dinowm_heldout_evaluation(
        args.test_dataset,
        args.output,
        freeze_manifest=manifest,
        freeze_manifest_path=args.freeze_manifest,
        dynamics_checkpoint_path=results / "dinowm_dynamics_development_v1.pt",
        outcome_bundle_path=results / "dinowm_outcome_models_development_v1.npz",
        current_control_bundle_path=results
        / "dinov2_current_outcome_models_control_v1.npz",
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
