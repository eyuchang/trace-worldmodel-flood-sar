"""Headless development commands for the non-LEAP Reference simulator."""

from __future__ import annotations

import argparse
import logging
import time
from collections.abc import Sequence
from pathlib import Path

from .provenance import execute_reference_scenario, verify_exact_reference_replay
from .publication import publish_reference_bundle
from .validation import (
    run_reference_g3_characterization,
    run_reference_g3_integrity,
)
from .validation.acceptance import (
    ReferencePhase6FinalizeInput,
    finalize_reference_phase6_acceptance,
    run_reference_phase6_core,
    run_reference_phase6_fault,
    run_reference_phase6_isolation,
)

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
    characterize = commands.add_parser(
        "characterize-g3",
        help="Write the five bounded feature-off G3 fixture manifests.",
    )
    _add_common(characterize)
    characterize.add_argument("--seed", type=int, required=True)
    characterize.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Existing empty caller-controlled characterization directory.",
    )
    phase6_core = commands.add_parser(
        "phase6-core",
        help="Run development-only nominal replay, publication, and resource checks.",
    )
    _add_common(phase6_core)
    phase6_core.add_argument("--output", type=Path, required=True)
    phase6_isolation = commands.add_parser(
        "phase6-isolation",
        help="Run development-only hidden-lineage and causal-axis checks.",
    )
    _add_common(phase6_isolation)
    phase6_isolation.add_argument("--output", type=Path, required=True)
    phase6_isolation.add_argument("--trusted-nominal-root", type=Path, required=True)
    phase6_isolation.add_argument("--nominal-relative-path", type=Path, required=True)
    phase6_fault = commands.add_parser(
        "phase6-fault",
        help="Run the development-only registered fault/restart path offline.",
    )
    _add_common(phase6_fault)
    phase6_fault.add_argument("--output", type=Path, required=True)
    phase6_finalize = commands.add_parser(
        "phase6-finalize",
        help="Bind completed development-only Phase 6 stage receipts.",
    )
    _add_common(phase6_finalize)
    phase6_finalize.add_argument("--output", type=Path, required=True)
    phase6_finalize.add_argument("--core-root", type=Path, required=True)
    phase6_finalize.add_argument("--core-receipt-relative-path", type=Path, required=True)
    phase6_finalize.add_argument("--isolation-root", type=Path, required=True)
    phase6_finalize.add_argument("--isolation-receipt-relative-path", type=Path, required=True)
    phase6_finalize.add_argument("--fault-root", type=Path, required=True)
    phase6_finalize.add_argument("--fault-receipt-relative-path", type=Path, required=True)
    phase6_finalize.add_argument("--g3-handoff-relative-path", type=Path, required=True)
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
    elif arguments.command == "characterize-g3":
        index = run_reference_g3_characterization(
            arguments.repository_root,
            arguments.output,
            seed=arguments.seed,
        )
        LOGGER.info(
            "Reference G3 feature-off characterization fixtures=%d digest=%s",
            len(index.fixtures),
            index.index_digest,
        )
    elif arguments.command == "phase6-core":
        core_receipt = run_reference_phase6_core(
            arguments.repository_root,
            arguments.output,
        )
        LOGGER.info(
            "Reference Phase 6 core checks=%s elapsed_seconds=%.3f output_bytes=%d",
            "pass" if core_receipt.all_checks_pass else "fail",
            core_receipt.resource_receipt.elapsed_milliseconds / 1_000,
            core_receipt.resource_receipt.transient_output_bytes,
        )
    elif arguments.command == "phase6-isolation":
        isolation_receipt = run_reference_phase6_isolation(
            arguments.repository_root,
            arguments.output,
            trusted_nominal_root=arguments.trusted_nominal_root,
            nominal_relative_path=arguments.nominal_relative_path,
        )
        LOGGER.info(
            "Reference Phase 6 isolation checks=%s axes=%d",
            "pass" if isolation_receipt.all_checks_pass else "fail",
            len(isolation_receipt.axis_results),
        )
    elif arguments.command == "phase6-fault":
        fault_receipt = run_reference_phase6_fault(
            arguments.repository_root,
            arguments.output,
        )
        LOGGER.info(
            "Reference Phase 6 fault/restart checks=%s",
            "pass" if fault_receipt.all_checks_pass else "fail",
        )
    elif arguments.command == "phase6-finalize":
        acceptance_report = finalize_reference_phase6_acceptance(
            ReferencePhase6FinalizeInput(
                repository_root=arguments.repository_root,
                output_root=arguments.output,
                core_root=arguments.core_root,
                core_receipt_relative_path=arguments.core_receipt_relative_path,
                isolation_root=arguments.isolation_root,
                isolation_receipt_relative_path=arguments.isolation_receipt_relative_path,
                fault_root=arguments.fault_root,
                fault_receipt_relative_path=arguments.fault_receipt_relative_path,
                g3_handoff_relative_path=arguments.g3_handoff_relative_path,
            )
        )
        LOGGER.info(
            "Reference Phase 6 development acceptance=%s canonical_performance=%s",
            "pass" if acceptance_report.all_nonperformance_checks_pass else "fail",
            acceptance_report.canonical_performance_status,
        )
    else:  # pragma: no cover - argparse restricts the command set.
        raise RuntimeError(f"unsupported Reference command: {arguments.command}")
    LOGGER.info("elapsed_seconds=%.3f", time.perf_counter() - started)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
