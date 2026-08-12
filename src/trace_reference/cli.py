"""Headless development commands for the non-LEAP Reference simulator."""

from __future__ import annotations

import argparse
import logging
import time
from collections.abc import Sequence
from pathlib import Path

from .provenance import execute_reference_scenario, verify_exact_reference_replay
from .publication import publish_reference_bundle
from .validation import run_reference_g3_integrity

LOGGER = logging.getLogger(__name__)


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=_repository_root(),
        help="Repository checkout containing the versioned Reference inputs.",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build a CLI that cannot invoke an unregistered statistical study."""

    parser = argparse.ArgumentParser(
        description=(
            "Run, exactly replay, publish, and verify WF-DFLD-01-REFERENCE development scenarios."
        )
    )
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="Generate and execute one development scenario.")
    _add_common(run)
    run.add_argument("--seed", type=int, required=True)
    run.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Existing empty caller-controlled output directory.",
    )

    replay = commands.add_parser(
        "replay",
        help="Verify a caller-rooted bundle and regenerate every registered byte.",
    )
    _add_common(replay)
    replay.add_argument("--trusted-reference-root", type=Path, required=True)
    replay.add_argument(
        "--reference-relative-path",
        type=Path,
        required=True,
        help="Reference bundle path relative to its explicitly trusted root.",
    )
    replay.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Existing empty caller-controlled replay directory.",
    )
    publish = commands.add_parser(
        "publish",
        help="Regenerate development figures and the result table from a verified replay bundle.",
    )
    publish.add_argument("--trusted-reference-root", type=Path, required=True)
    publish.add_argument("--reference-relative-path", type=Path, required=True)
    publish.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Existing empty caller-controlled publication directory.",
    )
    g3 = commands.add_parser(
        "verify-g3",
        help="Run the registered non-LEAP fault/restart integrity characterization.",
    )
    _add_common(g3)
    g3.add_argument("--seed", type=int, required=True)
    g3.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Existing empty caller-controlled G3 output directory.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one explicitly selected non-statistical Reference command."""

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    arguments = build_parser().parse_args(argv)
    started = time.perf_counter()
    if arguments.command == "run":
        execution = execute_reference_scenario(
            arguments.repository_root,
            arguments.output,
            seed=arguments.seed,
        )
        LOGGER.info(
            "completed WF-DFLD-01-REFERENCE development run: "
            "decisions=%d finite_strict_load=%.3f strict_unserviceable_windows=%d artifacts=%d",
            len(execution.run.decisions),
            execution.capacity.peak_finite_strict_concurrent_load_ratio_milli / 1_000,
            execution.capacity.strict_unserviceable_window_count,
            len(execution.manifest.artifacts),
        )
    elif arguments.command == "replay":
        verify_exact_reference_replay(
            arguments.repository_root,
            trusted_reference_root=arguments.trusted_reference_root,
            reference_relative_path=arguments.reference_relative_path,
            replay_output_root=arguments.output,
        )
        LOGGER.info("Reference replay is byte-identical")
    elif arguments.command == "publish":
        manifest = publish_reference_bundle(
            trusted_reference_root=arguments.trusted_reference_root,
            reference_relative_path=arguments.reference_relative_path,
            output_root=arguments.output,
        )
        LOGGER.info("Reference publication artifacts=%d", len(manifest.artifacts))
    elif arguments.command == "verify-g3":
        report = run_reference_g3_integrity(
            arguments.repository_root,
            arguments.output,
            seed=arguments.seed,
        )
        LOGGER.info(
            "Reference G3 integrity checks=%s faults=%d compensations=%d debts=%d",
            "pass" if report.all_checks_pass else "fail",
            len(report.observed_fault_families),
            report.faulted_counts.compensations,
            report.faulted_counts.consistency_debts,
        )
    else:  # pragma: no cover - argparse restricts the command set.
        raise RuntimeError(f"unsupported Reference command: {arguments.command}")
    LOGGER.info("elapsed_seconds=%.3f", time.perf_counter() - started)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
