"""Governed remote entry point for Reference validation-v2 recovery."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from trace_reference_recovery.execution import (
    RecoveryInterruptionRequest,
    aggregate_recovery_report,
    authorize_recovery,
    build_recovery_continuation_plan,
    run_recovery_shard,
    write_recovery_interruption_record,
)
from trace_reference_recovery.manifest import (
    verify_recovery_governance_manifest,
    write_recovery_governance_manifest,
)

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Execute one guarded stage of Reference validation-v2 recovery."
    )
    parser.add_argument("--repository-root", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("authorize")
    commands.add_parser("verify-manifest")
    manifest = commands.add_parser("write-manifest")
    manifest.add_argument("--output", type=Path, required=True)
    shard = commands.add_parser("shard")
    shard.add_argument("--shard-index", type=int, required=True)
    shard.add_argument("--output", type=Path, required=True)
    continuation = commands.add_parser("continuation")
    continuation.add_argument("--shard-root", type=Path, required=True)
    continuation.add_argument("--output", type=Path, required=True)
    failure = commands.add_parser("failure")
    failure.add_argument("--shard-root", type=Path, required=True)
    failure.add_argument("--output", type=Path, required=True)
    failure.add_argument(
        "--failure-stage",
        choices=(
            "incomplete-shards",
            "normalization",
            "aggregation",
            "artifact-preflight",
            "artifact-upload",
        ),
        required=True,
    )
    failure.add_argument("--final-report-written", action="store_true")
    failure.add_argument("--raw-plan-written", action="store_true")
    aggregate = commands.add_parser("aggregate")
    aggregate.add_argument("--shard-root", type=Path, required=True)
    aggregate.add_argument("--output", type=Path, required=True)
    aggregate.add_argument("--disclosed-plan-output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    arguments = build_parser().parse_args(argv)
    root = arguments.repository_root
    if arguments.command == "authorize":
        identity = authorize_recovery(root)
        LOGGER.info("recovery authorization verified: run_id=%d", identity.workflow_run_id)
    elif arguments.command == "verify-manifest":
        manifest = verify_recovery_governance_manifest(root)
        LOGGER.info("recovery governance verified: members=%d", len(manifest.recovery_members))
    elif arguments.command == "write-manifest":
        manifest = write_recovery_governance_manifest(root, arguments.output)
        LOGGER.info(
            "recovery governance manifest written: members=%d", len(manifest.recovery_members)
        )
    elif arguments.command == "shard":
        receipt = run_recovery_shard(
            root,
            arguments.output,
            shard_index=arguments.shard_index,
        )
        LOGGER.info(
            "recovery shard completed: index=%d digest=%s",
            receipt.shard_index,
            receipt.shard_digest,
        )
    elif arguments.command == "continuation":
        plan = build_recovery_continuation_plan(
            root,
            arguments.output,
            shard_root=arguments.shard_root,
        )
        LOGGER.info(
            "recovery interrupted: completed_shards=%d missing_shards=%d digest=%s",
            len(plan.completed_shard_indices),
            len(plan.missing_shard_indices),
            plan.plan_digest,
        )
    elif arguments.command == "failure":
        record = write_recovery_interruption_record(
            root,
            arguments.output,
            RecoveryInterruptionRequest(
                shard_root=arguments.shard_root,
                failure_stage=arguments.failure_stage,
                final_report_written=arguments.final_report_written,
                raw_plan_written=arguments.raw_plan_written,
            ),
        )
        LOGGER.info(
            "recovery failure preserved: stage=%s valid_shards=%d digest=%s",
            record.failure_stage,
            len(record.valid_completed_shard_indices),
            record.record_digest,
        )
    else:
        report = aggregate_recovery_report(
            root,
            arguments.output,
            shard_root=arguments.shard_root,
            disclosed_plan_output_path=arguments.disclosed_plan_output,
        )
        LOGGER.info(
            "recovery validation aggregated: complete=%s digest=%s",
            report.mission_execution_status == "complete",
            report.report_digest,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
