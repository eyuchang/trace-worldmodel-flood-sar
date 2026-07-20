from __future__ import annotations

import argparse
import json
from pathlib import Path

from trace_jepa.worldmodels.dinowm_freeze import freeze_dinowm_test_manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Freeze the passed DINO-WM development gate and authorize one held-out run"
    )
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--development-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.development_dir
    results = root / "results"
    manifest = freeze_dinowm_test_manifest(
        args.repository_root,
        args.output,
        protocol_path=args.repository_root
        / "configs/experiments/dinowm_development_confirmation_v1.yaml",
        transition_dataset_path=root / "spatial_transitions.npz",
        development_report_path=results / "dinowm_development_confirmation_report.json",
        dynamics_checkpoint_path=results / "dinowm_dynamics_development_v1.pt",
        outcome_checkpoint_path=results / "dinowm_route_head_development_v1.npz",
        outcome_bundle_path=results / "dinowm_outcome_models_development_v1.npz",
        current_control_bundle_path=results
        / "dinov2_current_outcome_models_control_v1.npz",
        test_data_seed=20260801,
        test_split_seed=20260802,
        test_episode_count=400,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
