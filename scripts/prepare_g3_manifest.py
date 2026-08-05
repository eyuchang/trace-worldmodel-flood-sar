#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from trace_jepa.evaluation.validation import prepare_g3_manifest


def _parser() -> argparse.ArgumentParser:
    repository_root = Path(__file__).resolve().parents[1]
    private_root = repository_root.parent
    parser = argparse.ArgumentParser(
        description="Prepare an unsigned G3 review manifest from passed validation evidence."
    )
    parser.add_argument(
        "--validation-result",
        type=Path,
        default=private_root
        / "validation-evidence/r-b-v1/VALIDATION_SWEEP_RESULT.json",
    )
    parser.add_argument(
        "--g2-setting",
        type=Path,
        default=private_root
        / "day1-evidence/day1-protocol-amendment-2/g2/noise-0p35/g2-setting.json",
    )
    parser.add_argument(
        "--output", type=Path, default=repository_root / "manifest.yaml"
    )
    return parser


def main() -> None:
    arguments = _parser().parse_args()
    repository_root = Path(__file__).resolve().parents[1]
    manifest = prepare_g3_manifest(
        validation_result_path=arguments.validation_result,
        g2_setting_path=arguments.g2_setting,
        repository_root=repository_root,
        output_path=arguments.output,
    )
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "manifest_hash": manifest["manifest_hash"],
                "test_execution_authorized": manifest["g3"][
                    "test_execution_authorized"
                ],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
