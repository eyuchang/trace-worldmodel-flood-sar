#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from trace_jepa.evaluation import RunDiagnostics, classify_failure


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply the fixed-priority TRACE experiment failure classifier."
    )
    parser.add_argument("diagnostics", type=Path, help="RunDiagnostics JSON file")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    path = args.diagnostics.resolve(strict=True)
    if not path.is_file() or path.stat().st_size > 1_000_000:
        raise ValueError("diagnostics must be a regular JSON file no larger than 1 MB")
    raw = json.loads(path.read_text(encoding="utf-8"))
    diagnostics = RunDiagnostics.model_validate(raw)
    classification = classify_failure(diagnostics)
    print(
        json.dumps(
            classification.model_dump(mode="json") if classification else None,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
