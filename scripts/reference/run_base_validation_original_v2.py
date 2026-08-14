"""Protected remote entry point for the original base-Reference validation."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from trace_reference.validation.original_execution import (
    aggregate_reference_validation_report,
    prepare_protected_seed_plan,
    run_reference_validation_shard,
)

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one protected stage of the authorized Reference validation-v2 workflow."
    )
    parser.add_argument("--repository-root", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--output", type=Path, required=True)
    shard = commands.add_parser("shard")
    shard.add_argument("--shard-index", type=int, required=True)
    shard.add_argument("--seed-plan-root", type=Path, required=True)
    shard.add_argument("--seed-plan-relative-path", type=Path, required=True)
    shard.add_argument("--output", type=Path, required=True)
    aggregate = commands.add_parser("aggregate")
    aggregate.add_argument("--shard-root", type=Path, required=True)
    aggregate.add_argument("--seed-plan-root", type=Path, required=True)
    aggregate.add_argument("--seed-plan-relative-path", type=Path, required=True)
    aggregate.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    arguments = build_parser().parse_args(argv)
    root = arguments.repository_root
    if arguments.command == "prepare":
        plan = prepare_protected_seed_plan(root, arguments.output)
        LOGGER.info("protected seed plan prepared: digest=%s", plan.seed_list_sha256)
    elif arguments.command == "shard":
        receipt = run_reference_validation_shard(
            root,
            arguments.output,
            shard_index=arguments.shard_index,
            seed_plan_root=arguments.seed_plan_root,
            seed_plan_relative_path=arguments.seed_plan_relative_path,
        )
        LOGGER.info(
            "Reference validation shard completed: index=%d digest=%s",
            receipt.shard_index,
            receipt.shard_digest,
        )
    else:
        report = aggregate_reference_validation_report(
            root,
            arguments.output,
            shard_root=arguments.shard_root,
            seed_plan_root=arguments.seed_plan_root,
            seed_plan_relative_path=arguments.seed_plan_relative_path,
        )
        LOGGER.info(
            "Reference original validation aggregated: pass=%s digest=%s",
            report.all_exact_gates_pass,
            report.report_digest,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
