"""Explicit development-only commands for Reference coefficient fitting."""

from __future__ import annotations

import argparse
from pathlib import Path

from .observation_fit import (
    benchmark_reference_observation_fit,
    fit_reference_observation_coefficients,
    load_reference_observation_fit_benchmark,
    write_reference_observation_fit,
    write_reference_observation_fit_benchmark,
)
from .truth_fit import (
    benchmark_reference_truth_fit,
    fit_reference_truth_coefficients,
    load_reference_truth_fit_benchmark,
    write_reference_truth_fit,
    write_reference_truth_fit_benchmark,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    benchmark = commands.add_parser("benchmark")
    benchmark.add_argument("--repository-root", type=Path, required=True)
    benchmark.add_argument("--pilot-seed-count", type=int, default=5)
    benchmark.add_argument("--output", type=Path, required=True)
    fit = commands.add_parser("fit")
    fit.add_argument("--repository-root", type=Path, required=True)
    fit.add_argument("--trusted-benchmark-root", type=Path, required=True)
    fit.add_argument("--benchmark-relative-path", type=Path, required=True)
    fit.add_argument("--output", type=Path, required=True)
    observation_benchmark = commands.add_parser("observation-benchmark")
    observation_benchmark.add_argument("--repository-root", type=Path, required=True)
    observation_benchmark.add_argument("--pilot-seed-count", type=int, default=5)
    observation_benchmark.add_argument("--output", type=Path, required=True)
    observation_fit = commands.add_parser("observation-fit")
    observation_fit.add_argument("--repository-root", type=Path, required=True)
    observation_fit.add_argument("--trusted-benchmark-root", type=Path, required=True)
    observation_fit.add_argument("--benchmark-relative-path", type=Path, required=True)
    observation_fit.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.command == "benchmark":
        truth_benchmark_receipt = benchmark_reference_truth_fit(
            arguments.repository_root,
            pilot_seed_count=arguments.pilot_seed_count,
        )
        write_reference_truth_fit_benchmark(truth_benchmark_receipt, arguments.output)
        return 0 if truth_benchmark_receipt.within_registered_bounds else 2
    if arguments.command == "observation-benchmark":
        observation_benchmark_receipt = benchmark_reference_observation_fit(
            arguments.repository_root,
            pilot_seed_count=arguments.pilot_seed_count,
        )
        write_reference_observation_fit_benchmark(observation_benchmark_receipt, arguments.output)
        return 0 if observation_benchmark_receipt.within_registered_bounds else 2
    if arguments.command == "observation-fit":
        observation_receipt = load_reference_observation_fit_benchmark(
            arguments.trusted_benchmark_root,
            arguments.benchmark_relative_path,
        )
        observation_coefficients, observation_report = fit_reference_observation_coefficients(
            arguments.repository_root,
            observation_receipt,
        )
        write_reference_observation_fit(
            observation_coefficients,
            observation_report,
            arguments.output,
        )
        return 0
    truth_receipt = load_reference_truth_fit_benchmark(
        arguments.trusted_benchmark_root,
        arguments.benchmark_relative_path,
    )
    truth_coefficients, truth_report = fit_reference_truth_coefficients(
        arguments.repository_root, truth_receipt
    )
    write_reference_truth_fit(truth_coefficients, truth_report, arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
