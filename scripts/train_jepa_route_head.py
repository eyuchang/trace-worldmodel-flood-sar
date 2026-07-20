from __future__ import annotations

import argparse
from pathlib import Path

from trace_jepa.worldmodels.training import train_development_models


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tune and validate the development flood-domain head over frozen V-JEPA features"
    )
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=23)
    args = parser.parse_args()
    report = train_development_models(args.dataset, args.checkpoint, args.report, seed=args.seed)
    fused = report["models"]["fused"]
    print(f"fused_validation_brier={fused['brier']:.6f}")
    print(f"fused_validation_target_mse={fused['mse_all_targets']:.6f}")
    print(f"Wrote development checkpoint: {args.checkpoint}")
    print(f"Wrote development report: {args.report}")


if __name__ == "__main__":
    main()
