"""Streaming, deterministic truth-coefficient fitting on spent development seeds."""

from __future__ import annotations

import bisect
import hashlib
import math
import time
import tracemalloc
from collections import defaultdict
from pathlib import Path
from typing import Literal

import yaml

from trace_jepa.support import (
    ArtifactLocator,
    atomic_write_bytes,
    canonical_json_bytes,
    safe_directory,
    sha256_file,
)
from trace_reference import load_reference_exposure_parameters, load_reference_physical_parameters
from trace_reference.domain.exposure import ReferenceExposureParameters
from trace_reference.domain.physical import ReferencePhysicalScenario
from trace_reference.domain.truth import ReferenceIncidentType
from trace_reference.generation import (
    ReferenceTruthFitInterval,
    ReferenceTruthFitSeedSummary,
    build_reference_truth_fit_seed_summary,
    generate_reference_exposure,
    generate_reference_physical_scenario,
)
from trace_reference.geography import ReferenceGeographyCatalog, load_reference_geography
from trace_reference.provenance import build_reference_scientific_input_manifest
from trace_reference.seeds import derive_seed_prefix

from .models import (
    ReferenceTruthCandidateEvaluation,
    ReferenceTruthCoefficientSet,
    ReferenceTruthFitBenchmarkReceipt,
    ReferenceTruthFitProtocol,
    ReferenceTruthFitReport,
    ReferenceTruthSeedResult,
    ReferenceTruthSelectedCoefficient,
)

_PROTOCOL = Path("data/scenario/delta/reference/calibration/reference_truth_fit_protocol_v1.yaml")
_PHYSICAL = Path("data/scenario/delta/reference/physical/reference_physical_parameters_v1.yaml")
_EXPOSURE = Path("data/scenario/delta/reference/exposure/reference_exposure_parameters_v1.yaml")
_GEOGRAPHY = Path("data/scenario/delta/reference/geography")
_MAX_PROTOCOL_BYTES = 1_000_000
_MAX_RECEIPT_BYTES = 1_000_000


def load_reference_truth_fit_protocol(repository_root: Path) -> ReferenceTruthFitProtocol:
    """Load the exact caller-rooted spent-development fitting contract."""

    path = ArtifactLocator(
        root=repository_root,
        relative_name=_PROTOCOL,
        maximum_bytes=_MAX_PROTOCOL_BYTES,
        label="Reference truth fit protocol",
    ).resolve()
    try:
        payload = yaml.safe_load(path.read_text("utf-8"))
        return ReferenceTruthFitProtocol.model_validate(payload)
    except (OSError, UnicodeError, yaml.YAMLError, ValueError) as exc:
        raise ValueError("Reference truth fit protocol is invalid") from exc


def _protocol_sha256(repository_root: Path) -> str:
    return sha256_file(
        ArtifactLocator(
            root=repository_root,
            relative_name=_PROTOCOL,
            maximum_bytes=_MAX_PROTOCOL_BYTES,
            label="Reference truth fit protocol",
        ).resolve()
    )


def _scenario_inputs(
    repository_root: Path,
) -> tuple[ReferencePhysicalScenario, ReferenceExposureParameters, ReferenceGeographyCatalog]:
    physical = generate_reference_physical_scenario(
        load_reference_physical_parameters(repository_root, _PHYSICAL)
    )
    exposure_parameters = load_reference_exposure_parameters(repository_root, _EXPOSURE)
    geography = load_reference_geography(geography_root=repository_root / _GEOGRAPHY)
    return physical, exposure_parameters, geography


def benchmark_reference_truth_fit(
    repository_root: Path,
    *,
    pilot_seed_count: int = 5,
) -> ReferenceTruthFitBenchmarkReceipt:
    """Measure a bounded prefix before the complete 100-seed fit is authorized."""

    protocol = load_reference_truth_fit_protocol(repository_root)
    if not 1 <= pilot_seed_count <= 10:
        raise ValueError("Reference truth-fit pilot must contain between one and ten seeds")
    seeds = derive_seed_prefix("development", pilot_seed_count)
    tracemalloc.start()
    started = time.perf_counter_ns()
    physical, exposure_parameters, geography = _scenario_inputs(repository_root)
    episodes = 0
    intervals = 0
    for seed in seeds:
        exposure = generate_reference_exposure(exposure_parameters, geography, seed=seed)
        summary = build_reference_truth_fit_seed_summary(physical, exposure, seed=seed)
        episodes += summary.eligible_episode_count
        intervals += len(summary.evaluation_intervals)
    elapsed_ms = round((time.perf_counter_ns() - started) / 1_000_000)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    projected_ms = math.ceil(elapsed_ms * protocol.seed_count / pilot_seed_count)
    projected_disk = 64 * 1024 * 1024
    within = (
        projected_ms <= protocol.resource_stop_bounds.maximum_wall_time_s * 1_000
        and peak <= protocol.resource_stop_bounds.maximum_peak_memory_bytes
        and projected_disk <= protocol.resource_stop_bounds.maximum_additional_disk_bytes
    )
    body = {
        "schema_version": "delta-reference-truth-fit-benchmark-v2",
        "scientific_status": "development-resource-gate-not-fit-evidence",
        "kernel_id": "compact-primitive-exact-v2",
        "protocol_sha256": _protocol_sha256(repository_root),
        "seed_indices": tuple(range(pilot_seed_count)),
        "elapsed_ms": elapsed_ms,
        "projected_full_fit_ms": projected_ms,
        "traced_python_peak_bytes": peak,
        "projected_additional_disk_bytes": projected_disk,
        "observed_episode_count": episodes,
        "observed_interval_count": intervals,
        "within_registered_bounds": within,
    }
    return ReferenceTruthFitBenchmarkReceipt(
        **body,
        receipt_digest=hashlib.sha256(canonical_json_bytes(body)).hexdigest(),
    )


def write_reference_truth_fit_benchmark(
    receipt: ReferenceTruthFitBenchmarkReceipt,
    output_root: Path,
) -> Path:
    output = safe_directory(
        output_root,
        declared_root=output_root,
        label="Reference truth-fit benchmark output",
    )
    if any(output.iterdir()):
        raise ValueError("Reference truth-fit benchmark output must be empty")
    destination = output / "truth_fit_benchmark_receipt.json"
    atomic_write_bytes(
        destination,
        canonical_json_bytes(receipt.model_dump(mode="json")),
        root=output,
        label="Reference truth-fit benchmark receipt",
    )
    return destination


def load_reference_truth_fit_benchmark(
    trusted_root: Path,
    relative_name: Path,
) -> ReferenceTruthFitBenchmarkReceipt:
    path = ArtifactLocator(
        root=trusted_root,
        relative_name=relative_name,
        maximum_bytes=_MAX_RECEIPT_BYTES,
        label="Reference truth-fit benchmark receipt",
    ).resolve()
    try:
        return ReferenceTruthFitBenchmarkReceipt.model_validate_json(path.read_text("utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError("Reference truth-fit benchmark receipt is invalid") from exc


def _log_grid(lower: int, upper: int, count: int) -> tuple[int, ...]:
    if lower <= 0 or upper <= lower or count < 2:
        raise ValueError("Reference truth-fit grid bounds are invalid")
    log_lower = math.log(lower)
    step = (math.log(upper) - log_lower) / (count - 1)
    return tuple(sorted({round(math.exp(log_lower + step * index)) for index in range(count)}))


def _count_at(
    lower_values: list[int],
    upper_values: list[int],
    intercept: int,
) -> int:
    return bisect.bisect_right(lower_values, intercept) - bisect.bisect_right(
        upper_values, intercept
    )


def _evaluate_grid(
    incident_type: ReferenceIncidentType,
    grid: tuple[int, ...],
    lower_values: list[int],
    upper_values: list[int],
    target: int,
    stage: Literal["coarse", "refinement"],
) -> tuple[ReferenceTruthCandidateEvaluation, ...]:
    return tuple(
        ReferenceTruthCandidateEvaluation(
            incident_type=incident_type,
            intercept_micros=intercept,
            aggregate_evaluation_incidents=(
                count := _count_at(lower_values, upper_values, intercept)
            ),
            target_aggregate_incidents=target,
            absolute_residual=abs(count - target),
            search_stage=stage,
        )
        for intercept in grid
    )


def _select_coefficients(
    protocol: ReferenceTruthFitProtocol,
    summaries: tuple[ReferenceTruthFitSeedSummary, ...],
) -> tuple[
    tuple[ReferenceTruthCandidateEvaluation, ...],
    tuple[ReferenceTruthSelectedCoefficient, ...],
]:
    intervals_by_type: dict[ReferenceIncidentType, list[ReferenceTruthFitInterval]] = defaultdict(
        list
    )
    for summary in summaries:
        for interval in summary.evaluation_intervals:
            intervals_by_type[interval.incident_type].append(interval)
    candidates: list[ReferenceTruthCandidateEvaluation] = []
    selected: list[ReferenceTruthSelectedCoefficient] = []
    coarse_grid = _log_grid(
        protocol.intercept_lower,
        protocol.intercept_upper,
        protocol.coarse_grid_points,
    )
    for target_share in protocol.target_shares:
        incident_type = target_share.incident_type
        intervals = intervals_by_type[incident_type]
        lower_values = sorted(item.lower_intercept_inclusive for item in intervals)
        upper_values = sorted(
            item.upper_intercept_exclusive
            for item in intervals
            if item.upper_intercept_exclusive is not None
        )
        target_mean = protocol.target_total_midpoint * target_share.share_micros // 1_000_000
        target_aggregate = target_mean * protocol.seed_count
        coarse = _evaluate_grid(
            incident_type,
            coarse_grid,
            lower_values,
            upper_values,
            target_aggregate,
            "coarse",
        )
        best_coarse = min(coarse, key=lambda item: (item.absolute_residual, item.intercept_micros))
        best_index = coarse_grid.index(best_coarse.intercept_micros)
        refine_lower = coarse_grid[max(0, best_index - 1)]
        refine_upper = coarse_grid[min(len(coarse_grid) - 1, best_index + 1)]
        refinement_grid = (
            _log_grid(
                refine_lower,
                refine_upper,
                protocol.refinement_grid_points,
            )
            if refine_lower < refine_upper
            else ()
        )
        refinement_grid = tuple(item for item in refinement_grid if item not in coarse_grid)
        refinement = _evaluate_grid(
            incident_type,
            refinement_grid,
            lower_values,
            upper_values,
            target_aggregate,
            "refinement",
        )
        all_type_candidates = (*coarse, *refinement)
        best = min(
            all_type_candidates,
            key=lambda item: (item.absolute_residual, item.intercept_micros),
        )
        candidates.extend(all_type_candidates)
        selected.append(
            ReferenceTruthSelectedCoefficient(
                incident_type=incident_type,
                intercept_micros=best.intercept_micros,
                aggregate_evaluation_incidents=best.aggregate_evaluation_incidents,
                mean_evaluation_incidents_milli=round(
                    best.aggregate_evaluation_incidents * 1_000 / protocol.seed_count
                ),
                target_mean_incidents=target_mean,
                absolute_aggregate_residual=best.absolute_residual,
            )
        )
    return tuple(candidates), tuple(selected)


def _seed_results(
    summaries: tuple[ReferenceTruthFitSeedSummary, ...],
    seeds: tuple[int, ...],
    selected: tuple[ReferenceTruthSelectedCoefficient, ...],
) -> tuple[ReferenceTruthSeedResult, ...]:
    intercept_by_type = {item.incident_type: item.intercept_micros for item in selected}
    order = tuple(item.incident_type for item in selected)
    results = []
    for index, (seed, summary) in enumerate(zip(seeds, summaries, strict=True)):
        counts = dict.fromkeys(order, 0)
        for interval in summary.evaluation_intervals:
            intercept = intercept_by_type[interval.incident_type]
            if interval.lower_intercept_inclusive <= intercept and (
                interval.upper_intercept_exclusive is None
                or intercept < interval.upper_intercept_exclusive
            ):
                counts[interval.incident_type] += 1
        ordered = tuple(counts[item] for item in order)
        results.append(
            ReferenceTruthSeedResult(
                seed_index=index,
                seed=seed,
                evaluation_incidents=sum(ordered),
                counts_by_type=ordered,
            )
        )
    return tuple(results)


def fit_reference_truth_coefficients(
    repository_root: Path,
    benchmark: ReferenceTruthFitBenchmarkReceipt,
) -> tuple[ReferenceTruthCoefficientSet, ReferenceTruthFitReport]:
    """Fit one global intercept vector without per-seed normalization or holdout access."""

    protocol = load_reference_truth_fit_protocol(repository_root)
    protocol_sha = _protocol_sha256(repository_root)
    if benchmark.protocol_sha256 != protocol_sha or not benchmark.within_registered_bounds:
        raise ValueError("Reference truth fit requires a matching passing resource benchmark")
    if benchmark.seed_indices != tuple(range(len(benchmark.seed_indices))):
        raise ValueError("Reference truth-fit benchmark is not a canonical development prefix")
    started = time.perf_counter_ns()
    scientific_manifest = build_reference_scientific_input_manifest(repository_root)
    seeds = derive_seed_prefix("development", protocol.seed_count)
    seed_list_sha = hashlib.sha256(canonical_json_bytes(seeds)).hexdigest()
    physical, exposure_parameters, geography = _scenario_inputs(repository_root)
    summaries = []
    for index, seed in enumerate(seeds, start=1):
        exposure = generate_reference_exposure(exposure_parameters, geography, seed=seed)
        summaries.append(build_reference_truth_fit_seed_summary(physical, exposure, seed=seed))
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
        if index >= 5 and elapsed_ms * protocol.seed_count / index > (
            protocol.resource_stop_bounds.maximum_wall_time_s * 1_000
        ):
            raise RuntimeError("Reference truth fit exceeded its projected wall-time stop bound")
    summary_tuple = tuple(summaries)
    candidates, selected = _select_coefficients(protocol, summary_tuple)
    results = _seed_results(summary_tuple, seeds, selected)
    aggregate = sum(item.evaluation_incidents for item in results)
    mean_milli = round(aggregate * 1_000 / protocol.seed_count)
    coefficient_body = {
        "schema_version": "delta-reference-truth-coefficients-v2",
        "scientific_status": "frozen-spent-development-fit-not-validation-evidence",
        "coefficient_version": "delta-reference-truth-development-coefficients-v2",
        "probability_rounding": "integer-half-up",
        "randomness_namespace": "delta-reference-randomness-v1",
        "fit_protocol_sha256": protocol_sha,
        "development_seed_list_sha256": seed_list_sha,
        "selected": [item.model_dump(mode="json") for item in selected],
    }
    coefficients = ReferenceTruthCoefficientSet(
        **coefficient_body,
        coefficient_digest=hashlib.sha256(canonical_json_bytes(coefficient_body)).hexdigest(),
    )
    adverse = [
        "Protocol amendment v2's provisional 7% levee share was infeasible and was corrected before fitting."
    ]
    for item in selected:
        if item.absolute_aggregate_residual:
            adverse.append(
                f"{item.incident_type.value} aggregate residual was {item.absolute_aggregate_residual} incidents."
            )
    if not protocol.target_total_lower * 1_000 <= mean_milli <= protocol.target_total_upper * 1_000:
        adverse.append(
            "The fitted development mean fell outside the approved latent-workload band."
        )
    elapsed_ms = round((time.perf_counter_ns() - started) / 1_000_000)
    report_body = {
        "schema_version": "delta-reference-truth-fit-report-v1",
        "scientific_status": "spent-development-calibration-not-validation-evidence",
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "protocol_sha256": protocol_sha,
        "scientific_input_manifest_sha256": scientific_manifest.aggregate_sha256,
        "development_seeds": seeds,
        "development_seed_list_sha256": seed_list_sha,
        "benchmark_receipt_digest": benchmark.receipt_digest,
        "candidate_evaluations": [item.model_dump(mode="json") for item in candidates],
        "selected": [item.model_dump(mode="json") for item in selected],
        "seed_results": [item.model_dump(mode="json") for item in results],
        "aggregate_evaluation_incidents": aggregate,
        "mean_evaluation_incidents_milli": mean_milli,
        "mean_inside_approved_band": (
            protocol.target_total_lower * 1_000 <= mean_milli <= protocol.target_total_upper * 1_000
        ),
        "eligible_episode_count": sum(item.eligible_episode_count for item in summary_tuple),
        "retained_interval_count": sum(len(item.evaluation_intervals) for item in summary_tuple),
        "elapsed_ms": elapsed_ms,
        "adverse_findings": tuple(adverse),
        "coefficient_digest": coefficients.coefficient_digest,
    }
    report = ReferenceTruthFitReport(
        **report_body,
        report_digest=hashlib.sha256(canonical_json_bytes(report_body)).hexdigest(),
    )
    return coefficients, report


def write_reference_truth_fit(
    coefficients: ReferenceTruthCoefficientSet,
    report: ReferenceTruthFitReport,
    output_root: Path,
) -> tuple[Path, Path]:
    output = safe_directory(
        output_root,
        declared_root=output_root,
        label="Reference truth-fit output",
    )
    if any(output.iterdir()):
        raise ValueError("Reference truth-fit output must be empty")
    coefficient_path = output / "reference_truth_coefficients_v2.json"
    report_path = output / "reference_truth_fit_report_v1.json"
    coefficient_bytes = canonical_json_bytes(coefficients.model_dump(mode="json"))
    report_bytes = canonical_json_bytes(report.model_dump(mode="json"))
    if len(coefficient_bytes) + len(report_bytes) > 64 * 1024 * 1024:
        raise ValueError("Reference truth-fit outputs exceed their projected disk bound")
    atomic_write_bytes(
        coefficient_path,
        coefficient_bytes,
        root=output,
        label="Reference truth coefficients",
    )
    atomic_write_bytes(
        report_path,
        report_bytes,
        root=output,
        label="Reference truth fit report",
    )
    return coefficient_path, report_path
