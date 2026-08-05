from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path
from typing import Any, cast

from trace_jepa.predictor import ToyActionPrefixPredictor
from trace_jepa.scenario.delta.pipeline import execute_delta_small, verify_exact_replay
from trace_jepa.scenario.delta.publication import publish_reference_bundle
from trace_jepa.scenario.delta.validation import run_registered_validation

LOGGER = logging.getLogger(__name__)


def _defaults() -> dict[str, Path]:
    repository_root = Path(__file__).resolve().parents[4]
    return {
        "config": repository_root / "configs/scenarios/wf_dfld_01_small.yaml",
        "geography": repository_root
        / "data/scenario/delta/geography/delta_small_geography_v2.yaml",
        "policy": repository_root / "configs/policies/trace_delta_small_v1.yaml",
        "acceptance": repository_root / "configs/scenarios/wf_dfld_01_small_acceptance.yaml",
    }


def _add_execution_inputs(parser: argparse.ArgumentParser) -> None:
    defaults = _defaults()
    parser.add_argument("--config", type=Path, default=defaults["config"])
    parser.add_argument("--geography", type=Path, default=defaults["geography"])
    parser.add_argument("--policy", type=Path, default=defaults["policy"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run, replay, validate, and publish frozen WF-DFLD-01-SMALL."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="Generate and execute one frozen Small run.")
    _add_execution_inputs(run)
    run.add_argument("--output", type=Path, required=True)

    replay = commands.add_parser(
        "replay", help="Regenerate in a clean directory and compare every byte."
    )
    _add_execution_inputs(replay)
    replay.add_argument("--reference", type=Path, required=True)
    replay.add_argument("--output", type=Path, required=True)

    validate = commands.add_parser(
        "validate", help="Execute all registered development and confirmatory seeds."
    )
    _add_execution_inputs(validate)
    validate.add_argument("--acceptance", type=Path, default=_defaults()["acceptance"])
    validate.add_argument("--output", type=Path, required=True)

    publish = commands.add_parser(
        "publish", help="Regenerate deterministic book figures from a verified bundle."
    )
    publish.add_argument("--reference", type=Path, required=True)
    publish.add_argument("--output", type=Path, required=True)
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    arguments = build_parser().parse_args()
    predictor = ToyActionPrefixPredictor()
    started = time.perf_counter()
    if arguments.command == "run":
        execution = execute_delta_small(
            arguments.config,
            arguments.geography,
            arguments.policy,
            arguments.output,
            predictor,
        )
        LOGGER.info(
            "completed %s: allocated=%d refused=%d repaired=%d ratio=%.3f artifacts=%d",
            execution.run_result.scenario_id,
            execution.run_result.allocated,
            execution.run_result.refused,
            execution.run_result.repaired,
            execution.run_result.peak_demand_capacity_ratio_milli / 1000.0,
            len(execution.manifest.artifacts),
        )
    elif arguments.command == "replay":
        verify_exact_replay(
            arguments.config,
            arguments.geography,
            arguments.policy,
            arguments.reference,
            arguments.output,
            predictor,
        )
        LOGGER.info("replay is byte-identical to %s", arguments.reference)
    elif arguments.command == "validate":
        output_path = (
            arguments.output
            if arguments.output.suffix == ".json"
            else arguments.output / "WF_DFLD_01_SMALL_VALIDATION.json"
        )
        report = run_registered_validation(
            arguments.config,
            arguments.geography,
            arguments.policy,
            arguments.acceptance,
            output_path,
        )
        studies = cast(list[dict[str, Any]], report["studies"])
        primary = next(study for study in studies if study["study_id"] == "confirmatory-v4-primary")
        LOGGER.info(
            "validation completed: seeds=%d primary_median_ratio=%.3f output=%s",
            sum(study["seed_count"] for study in studies),
            primary["peak_demand_capacity_ratio"]["estimate"],
            output_path,
        )
    elif arguments.command == "publish":
        manifest = publish_reference_bundle(arguments.reference, arguments.output)
        LOGGER.info(
            "publication bundle completed: artifacts=%d output=%s",
            len(cast(list[object], manifest["artifacts"])),
            arguments.output,
        )
    else:  # pragma: no cover - argparse enforces a registered command.
        raise RuntimeError(f"unsupported command: {arguments.command}")
    LOGGER.info("elapsed_seconds=%.3f", time.perf_counter() - started)


if __name__ == "__main__":
    main()
