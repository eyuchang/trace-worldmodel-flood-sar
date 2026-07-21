from __future__ import annotations

import argparse
import json
from pathlib import Path

from trace_jepa.worldmodels.live_qualification import verify_qualification_report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Independently verify a live world-model qualification bundle"
    )
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--verification-output", type=Path, required=True)
    args = parser.parse_args()
    result = verify_qualification_report(
        args.report,
        output_root=args.output_root,
    )
    args.verification_output.parent.mkdir(parents=True, exist_ok=True)
    args.verification_output.write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
