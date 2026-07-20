from __future__ import annotations

import argparse
import json
from pathlib import Path

from trace_jepa.worldmodels.dinowm_training import (
    DINOWMTrainingConfig,
    run_dinowm_development_confirmation,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the registered DINO-WM development confirmation and prospective gate"
    )
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    report = run_dinowm_development_confirmation(
        args.dataset,
        args.output_dir,
        config=DINOWMTrainingConfig(),
    )
    print(json.dumps(report["gate"], indent=2, sort_keys=True))
    print(f"report={args.output_dir / 'dinowm_development_confirmation_report.json'}")


if __name__ == "__main__":
    main()
