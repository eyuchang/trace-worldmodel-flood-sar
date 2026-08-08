"""Enforce reviewed coverage gates for high-consequence Task 1/2 mechanics.

The gate covers predictor governance, secure artifact handling, scientific
generation mechanics, reconciliation, capacity, and mission execution. The
script also prints the complete measured Delta surface so lower-risk DTO,
publication, and offline-builder code is never hidden from review.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from trace_jepa.support.coverage import evaluate_coverage


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--minimum-line", type=float, default=90.0)
    parser.add_argument("--minimum-branch", type=float, default=85.0)
    args = parser.parse_args()
    critical, complete = evaluate_coverage(args.report)
    print(
        "High-consequence Task 1/2 coverage: "
        f"line={critical.line_percent:.2f}% branch={critical.branch_percent:.2f}% "
        f"({critical.statements} statements, {critical.branches} branches)"
    )
    print(
        "Complete measured Delta/predictor/support surface (informational): "
        f"line={complete.line_percent:.2f}% branch={complete.branch_percent:.2f}%"
    )
    if critical.line_percent < args.minimum_line:
        raise SystemExit("high-consequence line coverage is below the registered threshold")
    if critical.branch_percent < args.minimum_branch:
        raise SystemExit("high-consequence branch coverage is below the registered threshold")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
