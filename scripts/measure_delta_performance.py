"""Measure five clean generate/run/replay cycles for the Small reference path."""

from __future__ import annotations

import argparse
import statistics
import tempfile
import time
from pathlib import Path

from trace_jepa.predictor import ToyActionPrefixPredictor
from trace_jepa.scenario.delta.pipeline import execute_delta_small, verify_exact_replay

try:
    from trace_jepa.support import atomic_write_bytes, canonical_json_bytes
except ImportError:  # b8dd299 historical worktree predates the shared support package.
    from trace_jepa.scenario.delta.artifacts import canonical_json_bytes

    atomic_write_bytes = None  # type: ignore[assignment]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--geography", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--baseline-median-s", type=float, required=True)
    args = parser.parse_args()
    if args.iterations != 5:
        raise ValueError("the registered pre-push comparison requires exactly five iterations")

    timings: list[float] = []
    for _index in range(args.iterations):
        with tempfile.TemporaryDirectory(prefix="trace-delta-performance-") as temporary:
            work_root = Path(temporary)
            reference = work_root / "reference"
            replay = work_root / "replay"
            started = time.perf_counter()
            execute_delta_small(
                args.config,
                args.geography,
                args.policy,
                reference,
                ToyActionPrefixPredictor(),
            )
            verify_exact_replay(
                args.config,
                args.geography,
                args.policy,
                reference,
                replay,
                ToyActionPrefixPredictor(),
            )
            timings.append(time.perf_counter() - started)

    median_s = statistics.median(timings)
    regression_fraction = (median_s - args.baseline_median_s) / args.baseline_median_s
    report = {
        "schema_version": "delta-refactor-performance-v1",
        "execution_surface": "generate-run-clean-replay",
        "iteration_count": args.iterations,
        "iterations_s": timings,
        "median_s": median_s,
        "baseline_commit": "b8dd299",
        "baseline_median_s": args.baseline_median_s,
        "median_regression_fraction": regression_fraction,
        "maximum_runtime_s": 55.0,
        "maximum_regression_fraction": 0.10,
        "runtime_gate_passed": median_s < 55.0,
        "regression_gate_passed": regression_fraction <= 0.10,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json_bytes(report)
    if atomic_write_bytes is None:
        args.output.write_bytes(payload)
    else:
        atomic_write_bytes(
            args.output,
            payload,
            root=args.output.parent,
            label="Delta performance report",
        )
    if not report["runtime_gate_passed"] or not report["regression_gate_passed"]:
        raise SystemExit("Delta refactor performance gate failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
