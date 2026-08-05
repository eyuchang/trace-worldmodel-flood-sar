#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from trace_jepa.evaluation.validation import run_validation_sweep


def _parser() -> argparse.ArgumentParser:
    repository_root = Path(__file__).resolve().parents[1]
    private_root = repository_root.parent
    parser = argparse.ArgumentParser(
        description=(
            "Run the exact 19-config x 25-seed R-B validation sweep. This command "
            "cannot represent or access test seeds."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=repository_root / "configs/experiments/validation_r_b_v1.yaml",
    )
    parser.add_argument(
        "--protocol",
        type=Path,
        default=private_root / "README_EXPERIMENTS.md",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=private_root / "validation-evidence/r-b-v1",
    )
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--no-resume", action="store_true")
    return parser


def main() -> None:
    arguments = _parser().parse_args()
    repository_root = Path(__file__).resolve().parents[1]
    result = run_validation_sweep(
        config_path=arguments.config,
        output_root=arguments.output,
        repository_root=repository_root,
        protocol_path=arguments.protocol,
        workers=arguments.workers,
        resume=not arguments.no_resume,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "cells": len(result["cells"]),
                "result_hash": result["result_hash"],
            },
            sort_keys=True,
        )
    )
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
