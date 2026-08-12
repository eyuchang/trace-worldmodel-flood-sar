"""Bounded, deterministic fitting for the Reference observation channel."""

from __future__ import annotations

import hashlib
import math
import time
import tracemalloc
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import yaml

from trace_jepa.support import (
    ArtifactLocator,
    atomic_write_bytes,
    canonical_json_bytes,
    safe_directory,
    sha256_file,
)
from trace_reference import load_reference_exposure_parameters, load_reference_physical_parameters
from trace_reference.domain.exposure import ReferenceExposureParameters, ReferenceExposureScenario
from trace_reference.domain.physical import ReferencePhysicalScenario
from trace_reference.domain.truth import ReferenceTruthScenario
from trace_reference.generation import (
    generate_reference_exposure,
    generate_reference_physical_scenario,
    generate_reference_truth,
)
from trace_reference.generation.observation_fit_kernel import (
    build_reference_observation_fit_incidents,
    build_reference_observation_fit_potentials,
    summarize_reference_observation_fit_incidents,
)
from trace_reference.generation.observation_parameters import (
    ReferenceObservationDrawSummary,
    ReferenceObservationFitIncident,
    ReferenceObservationFitPotentials,
    ReferenceObservationGenerationCoefficients,
)
from trace_reference.geography import ReferenceGeographyCatalog, load_reference_geography
from trace_reference.provenance import build_reference_scientific_input_manifest
from trace_reference.seeds import derive_seed_prefix

from .loading import load_reference_truth_coefficients
from .observation_models import (
    ReferenceNamedCount,
    ReferenceObservationCandidateEvaluation,
    ReferenceObservationCoefficientSet,
    ReferenceObservationFitBenchmarkReceipt,
    ReferenceObservationFitProtocol,
    ReferenceObservationFitReport,
    ReferenceObservationHourlyCoefficient,
    ReferenceObservationSeedResult,
)

_PROTOCOL = Path(
    "data/scenario/delta/reference/calibration/reference_observation_fit_protocol_v1.yaml"
)
_TRUTH_REPORT = Path("data/scenario/delta/reference/calibration/reference_truth_fit_report_v1.json")
_TRUTH_COEFFICIENTS = Path(
    "data/scenario/delta/reference/calibration/reference_truth_coefficients_v2.json"
)
_PHYSICAL = Path("data/scenario/delta/reference/physical/reference_physical_parameters_v1.yaml")
_EXPOSURE = Path("data/scenario/delta/reference/exposure/reference_exposure_parameters_v1.yaml")
_GEOGRAPHY = Path("data/scenario/delta/reference/geography")
_MAX_INPUT_BYTES = 4 * 1024 * 1024
_OUTPUT_BOUND_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class _WorldInputs:
    physical: ReferencePhysicalScenario
    exposure_parameters: ReferenceExposureParameters
    geography: ReferenceGeographyCatalog
    truth_intercepts: dict[object, int]
    truth_coefficient_digest: str


@dataclass
class _AggregatePotentials:
    initial: list[int]
    duplicate: list[int]
    multi_channel: list[int]
    conflict: list[int]
    third_party_welfare: list[int]
    stranded_revision: list[int]
    false_benign_levee: list[int]
    witness_opportunities: list[int]

    @classmethod
    def empty(cls) -> _AggregatePotentials:
        return cls(*([0] * 96 for _ in range(8)))

    def add(self, item: ReferenceObservationFitPotentials) -> None:
        for destination, source in (
            (self.initial, item.initial),
            (self.duplicate, item.duplicate),
            (self.multi_channel, item.multi_channel),
            (self.conflict, item.conflict),
            (self.third_party_welfare, item.third_party_welfare),
            (self.stranded_revision, item.stranded_revision),
            (self.false_benign_levee, item.false_benign_levee),
            (self.witness_opportunities, item.witness_opportunities),
        ):
            for index, count in enumerate(source):
                destination[index] += count


def _round_fraction(value: Fraction) -> int:
    return (value.numerator * 2 + value.denominator) // (2 * value.denominator)


def reference_observation_target_schedule_micros() -> tuple[int, ...]:
    """Return the exact apportioned 96-hour curve frozen in amendment v4."""

    raw: list[Fraction] = []
    for hour in range(96):
        if hour < 12:
            rate = Fraction(9)
        elif hour < 30:
            rate = Fraction(9) + Fraction(17 * (2 * (hour - 12) + 1), 36)
        elif hour < 42:
            rate = Fraction(26)
        elif hour < 52:
            rate = Fraction(26) + Fraction(69 * (2 * (hour - 42) + 1), 20)
        elif hour < 64:
            rate = Fraction(95)
        else:
            rate = Fraction(40)
        raw.append(rate)
    if sum(raw[index] for index in range(96) if not 52 <= index < 64) != 2_620:
        raise RuntimeError("Reference inherited non-breach schedule integral drifted")
    scaled = [
        Fraction(95_000_000) if 52 <= index < 64 else value * 1_000_000 * 88 / 131
        for index, value in enumerate(raw)
    ]
    floors = [value.numerator // value.denominator for value in scaled]
    remainder = 2_900_000_000 - sum(floors)
    ranked = sorted(
        (scaled[index] - floors[index], -index, index)
        for index in range(96)
        if not 52 <= index < 64
    )
    for _, _, index in reversed(ranked[-remainder:] if remainder else ()):
        floors[index] += 1
    if sum(floors) != 2_900_000_000 or floors[52:64] != [95_000_000] * 12:
        raise RuntimeError("Reference apportioned observation schedule is invalid")
    return tuple(floors)


def load_reference_observation_fit_protocol(
    repository_root: Path,
) -> ReferenceObservationFitProtocol:
    """Load the caller-rooted observation fit protocol."""

    path = ArtifactLocator(
        root=repository_root,
        relative_name=_PROTOCOL,
        maximum_bytes=_MAX_INPUT_BYTES,
        label="Reference observation fit protocol",
    ).resolve()
    try:
        return ReferenceObservationFitProtocol.model_validate(yaml.safe_load(path.read_text()))
    except (OSError, UnicodeError, yaml.YAMLError, ValueError) as exc:
        raise ValueError("Reference observation fit protocol is invalid") from exc


def _protocol_sha256(repository_root: Path) -> str:
    return sha256_file(
        ArtifactLocator(
            root=repository_root,
            relative_name=_PROTOCOL,
            maximum_bytes=_MAX_INPUT_BYTES,
            label="Reference observation fit protocol",
        ).resolve()
    )


def _verify_upstream_fit(repository_root: Path, protocol: ReferenceObservationFitProtocol) -> None:
    truth_report = ArtifactLocator(
        root=repository_root,
        relative_name=_TRUTH_REPORT,
        maximum_bytes=_MAX_INPUT_BYTES,
        label="Reference frozen truth fit report",
    ).resolve()
    truth_coefficients = ArtifactLocator(
        root=repository_root,
        relative_name=_TRUTH_COEFFICIENTS,
        maximum_bytes=_MAX_INPUT_BYTES,
        label="Reference frozen truth coefficients",
    ).resolve()
    if sha256_file(truth_report) != protocol.truth_fit_report_sha256:
        raise ValueError("Reference observation fit truth report binding is invalid")
    if sha256_file(truth_coefficients) != protocol.truth_coefficients_file_sha256:
        raise ValueError("Reference observation fit truth coefficient file binding is invalid")


def _world_inputs(repository_root: Path) -> _WorldInputs:
    physical = generate_reference_physical_scenario(
        load_reference_physical_parameters(repository_root, _PHYSICAL)
    )
    exposure_parameters = load_reference_exposure_parameters(repository_root, _EXPOSURE)
    geography = load_reference_geography(geography_root=repository_root / _GEOGRAPHY)
    truth_coefficients = load_reference_truth_coefficients(repository_root, _TRUTH_COEFFICIENTS)
    return _WorldInputs(
        physical=physical,
        exposure_parameters=exposure_parameters,
        geography=geography,
        truth_intercepts={
            item.incident_type: item.intercept_micros for item in truth_coefficients.selected
        },
        truth_coefficient_digest=truth_coefficients.coefficient_digest,
    )


def _world(
    inputs: _WorldInputs,
    seed: int,
) -> tuple[ReferenceExposureScenario, ReferenceTruthScenario]:
    exposure = generate_reference_exposure(inputs.exposure_parameters, inputs.geography, seed=seed)
    truth = generate_reference_truth(
        inputs.physical,
        exposure,
        seed=seed,
        coefficient_intercepts=inputs.truth_intercepts,  # type: ignore[arg-type]
        coefficient_digest=inputs.truth_coefficient_digest,
    )
    return exposure, truth


def benchmark_reference_observation_fit(
    repository_root: Path,
    *,
    pilot_seed_count: int = 5,
) -> ReferenceObservationFitBenchmarkReceipt:
    """Measure the exact two-pass fit before authorizing all development seeds."""

    repository_root = repository_root.resolve(strict=True)
    protocol = load_reference_observation_fit_protocol(repository_root)
    _verify_upstream_fit(repository_root, protocol)
    if not 1 <= pilot_seed_count <= 10:
        raise ValueError("Reference observation pilot must contain between one and ten seeds")
    seeds = derive_seed_prefix("development", pilot_seed_count)
    inputs = _world_inputs(repository_root)
    placeholder = ReferenceObservationGenerationCoefficients(
        coefficient_version="observation-fit-benchmark-placeholder",
        coefficient_digest="observation-fit-benchmark-placeholder",
        randomness_namespace="reference-observations-v2",
        initial_report_probability_micros=100_000,
        supplemental_witness_slots_per_incident=(protocol.supplemental_witness_slots_per_incident),
        hourly_witness_probability_micros=(500_000,) * 96,
    )
    started = time.perf_counter_ns()
    truth_count = 0
    witness_count = 0
    compact_by_seed: list[tuple[ReferenceObservationFitIncident, ...]] = []
    for seed in seeds:
        exposure, truth = _world(inputs, seed)
        potentials = build_reference_observation_fit_potentials(
            truth,
            exposure,
            seed=seed,
            witness_slots=protocol.supplemental_witness_slots_per_incident,
        )
        truth_count += sum(item.onset_s >= 0 for item in truth.incidents)
        witness_count += sum(potentials.witness_opportunities)
        compact_by_seed.append(build_reference_observation_fit_incidents(truth, exposure))
    for seed, records in zip(seeds, compact_by_seed, strict=True):
        summarize_reference_observation_fit_incidents(
            records,
            seed=seed,
            coefficients=placeholder,
        )
    elapsed_ms = round((time.perf_counter_ns() - started) / 1_000_000)
    memory_seed = seeds[0]
    tracemalloc.start()
    memory_exposure, memory_truth = _world(inputs, memory_seed)
    build_reference_observation_fit_potentials(
        memory_truth,
        memory_exposure,
        seed=memory_seed,
        witness_slots=protocol.supplemental_witness_slots_per_incident,
    )
    memory_records = build_reference_observation_fit_incidents(memory_truth, memory_exposure)
    summarize_reference_observation_fit_incidents(
        memory_records,
        seed=memory_seed,
        coefficients=placeholder,
    )
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    projected_ms = math.ceil(
        elapsed_ms * protocol.seed_count / pilot_seed_count * 1_100_000 / 1_000_000
    )
    projected_disk = 64 * 1024 * 1024
    within = (
        projected_ms <= protocol.resource_stop_bounds.maximum_wall_time_s * 1_000
        and peak <= protocol.resource_stop_bounds.maximum_peak_memory_bytes
        and projected_disk <= protocol.resource_stop_bounds.maximum_additional_disk_bytes
    )
    body = {
        "schema_version": "delta-reference-observation-fit-benchmark-v2",
        "scientific_status": "development-resource-gate-not-fit-evidence",
        "measurement_method": ("single-world-pass-compact-replay-and-separate-tracemalloc-v2"),
        "wall_time_margin_micros": 1_100_000,
        "protocol_sha256": _protocol_sha256(repository_root),
        "seed_indices": tuple(range(pilot_seed_count)),
        "elapsed_ms": elapsed_ms,
        "projected_full_fit_ms": projected_ms,
        "traced_python_peak_bytes": peak,
        "projected_additional_disk_bytes": projected_disk,
        "potential_witness_count": witness_count,
        "truth_incident_count": truth_count,
        "within_registered_bounds": within,
    }
    return ReferenceObservationFitBenchmarkReceipt(
        **body,
        receipt_digest=hashlib.sha256(canonical_json_bytes(body)).hexdigest(),
    )


def _joint_probability_micros(first: int, second: int) -> int:
    return (first * second + 500_000) // 1_000_000


def _baseline_expected(
    aggregate: _AggregatePotentials,
    protocol: ReferenceObservationFitProtocol,
    initial_probability: int,
) -> tuple[int, ...]:
    fixed = protocol.fixed_base_probabilities_micros
    joint = {
        "duplicate": _joint_probability_micros(initial_probability, fixed.duplicate),
        "multi_channel": _joint_probability_micros(initial_probability, fixed.multi_channel),
        "conflict": _joint_probability_micros(initial_probability, fixed.conflict),
        "third_party_welfare": _joint_probability_micros(
            initial_probability, fixed.third_party_welfare
        ),
        "stranded_revision": _joint_probability_micros(
            initial_probability, fixed.stranded_revision
        ),
    }
    return tuple(
        aggregate.initial[index] * initial_probability
        + aggregate.duplicate[index] * joint["duplicate"]
        + aggregate.multi_channel[index] * joint["multi_channel"]
        + aggregate.conflict[index] * joint["conflict"]
        + aggregate.third_party_welfare[index] * joint["third_party_welfare"]
        + aggregate.stranded_revision[index] * joint["stranded_revision"]
        + aggregate.false_benign_levee[index] * fixed.false_benign_levee
        for index in range(96)
    )


def _candidate(
    protocol: ReferenceObservationFitProtocol,
    aggregate: _AggregatePotentials,
    targets: tuple[int, ...],
    initial_probability: int,
) -> tuple[ReferenceObservationCandidateEvaluation, tuple[int, ...]]:
    baseline = _baseline_expected(aggregate, protocol, initial_probability)
    probabilities: list[int] = []
    infeasible: list[int] = []
    for hour_index, baseline_micros in enumerate(baseline):
        missing = targets[hour_index] * protocol.seed_count - baseline_micros
        opportunities = aggregate.witness_opportunities[hour_index]
        if missing < 0 or (missing > 0 and opportunities == 0):
            infeasible.append(hour_index)
            probabilities.append(0 if missing <= 0 else 1_000_000)
            continue
        probability = 0 if missing == 0 else (missing + opportunities // 2) // opportunities
        probabilities.append(probability)
        if probability > protocol.maximum_witness_probability_micros:
            infeasible.append(hour_index)
    evaluation = ReferenceObservationCandidateEvaluation(
        initial_report_probability_micros=initial_probability,
        analytical_baseline_evaluation_reports_micros=(sum(baseline) + protocol.seed_count // 2)
        // protocol.seed_count,
        infeasible_hour_indices=tuple(infeasible),
        minimum_witness_probability_micros=min(probabilities),
        maximum_witness_probability_micros=max(probabilities),
        feasible=not infeasible,
    )
    return evaluation, tuple(probabilities)


def _named_counts(values: Counter[str]) -> tuple[ReferenceNamedCount, ...]:
    return tuple(
        ReferenceNamedCount(name=name, count=count) for name, count in sorted(values.items())
    )


def fit_reference_observation_coefficients(
    repository_root: Path,
    benchmark: ReferenceObservationFitBenchmarkReceipt,
) -> tuple[ReferenceObservationCoefficientSet, ReferenceObservationFitReport]:
    """Fit the global channel to spent development worlds without seed normalization."""

    return _fit_reference_observation_coefficients(
        repository_root.resolve(strict=True),
        benchmark,
    )


def _fit_reference_observation_coefficients(
    repository_root: Path,
    benchmark: ReferenceObservationFitBenchmarkReceipt,
) -> tuple[ReferenceObservationCoefficientSet, ReferenceObservationFitReport]:
    protocol = load_reference_observation_fit_protocol(repository_root)
    protocol_sha = _protocol_sha256(repository_root)
    _verify_upstream_fit(repository_root, protocol)
    if benchmark.protocol_sha256 != protocol_sha or not benchmark.within_registered_bounds:
        raise ValueError("Reference observation fit requires a matching passing benchmark")
    if benchmark.seed_indices != tuple(range(len(benchmark.seed_indices))):
        raise ValueError("Reference observation benchmark is not a canonical development prefix")
    started = time.perf_counter_ns()
    scientific_manifest = build_reference_scientific_input_manifest(repository_root)
    seeds = derive_seed_prefix("development", protocol.seed_count)
    seed_list_sha = hashlib.sha256(canonical_json_bytes(seeds)).hexdigest()
    inputs = _world_inputs(repository_root)
    if inputs.truth_coefficient_digest != protocol.truth_coefficient_digest:
        raise ValueError("Reference observation fit loaded a different truth coefficient set")
    aggregate = _AggregatePotentials.empty()
    compact_by_seed: list[tuple[ReferenceObservationFitIncident, ...]] = []
    for index, seed in enumerate(seeds, start=1):
        exposure, truth = _world(inputs, seed)
        aggregate.add(
            build_reference_observation_fit_potentials(
                truth,
                exposure,
                seed=seed,
                witness_slots=protocol.supplemental_witness_slots_per_incident,
            )
        )
        compact_by_seed.append(build_reference_observation_fit_incidents(truth, exposure))
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
        projected = elapsed_ms * protocol.seed_count / index * 1.1
        if index >= 5 and projected > protocol.resource_stop_bounds.maximum_wall_time_s * 1_000:
            raise RuntimeError("Reference observation fit exceeded its wall-time stop bound")
    targets = reference_observation_target_schedule_micros()
    candidate_pairs = tuple(
        _candidate(protocol, aggregate, targets, candidate)
        for candidate in protocol.initial_report_probability_candidates_micros
    )
    feasible = tuple(item for item in candidate_pairs if item[0].feasible)
    if not feasible:
        raise RuntimeError("No preregistered Reference initial-report candidate was feasible")
    selected_evaluation, selected_probabilities = max(
        feasible,
        key=lambda item: (
            item[0].initial_report_probability_micros,
            -item[0].maximum_witness_probability_micros,
        ),
    )
    baseline = _baseline_expected(
        aggregate,
        protocol,
        selected_evaluation.initial_report_probability_micros,
    )
    hourly = tuple(
        ReferenceObservationHourlyCoefficient(
            hour_index=index,
            target_expected_reports_micros=targets[index],
            baseline_expected_reports_micros=_round_fraction(
                Fraction(baseline[index], protocol.seed_count)
            ),
            witness_opportunities=aggregate.witness_opportunities[index],
            witness_probability_micros=selected_probabilities[index],
            fitted_expected_reports_micros=(
                fitted := _round_fraction(
                    Fraction(
                        baseline[index]
                        + aggregate.witness_opportunities[index] * selected_probabilities[index],
                        protocol.seed_count,
                    )
                )
            ),
            analytical_residual_micros=fitted - targets[index],
        )
        for index in range(96)
    )
    coefficient_body = {
        "schema_version": "delta-reference-observation-coefficients-v2",
        "scientific_status": "frozen-spent-development-fit-not-validation-evidence",
        "coefficient_version": "delta-reference-observation-development-coefficients-v2",
        "randomness_namespace": "reference-observations-v2",
        "fit_protocol_sha256": protocol_sha,
        "truth_coefficient_digest": protocol.truth_coefficient_digest,
        "development_seed_list_sha256": seed_list_sha,
        "initial_report_probability_micros": (
            selected_evaluation.initial_report_probability_micros
        ),
        "supplemental_witness_slots_per_incident": (
            protocol.supplemental_witness_slots_per_incident
        ),
        "hourly": [item.model_dump(mode="json") for item in hourly],
    }
    coefficients = ReferenceObservationCoefficientSet(
        **coefficient_body,
        coefficient_digest=hashlib.sha256(canonical_json_bytes(coefficient_body)).hexdigest(),
    )
    generation_coefficients = ReferenceObservationGenerationCoefficients(
        coefficient_version=coefficients.coefficient_version,
        coefficient_digest=coefficients.coefficient_digest,
        randomness_namespace=coefficients.randomness_namespace,
        initial_report_probability_micros=coefficients.initial_report_probability_micros,
        supplemental_witness_slots_per_incident=(
            coefficients.supplemental_witness_slots_per_incident
        ),
        hourly_witness_probability_micros=tuple(
            item.witness_probability_micros for item in coefficients.hourly
        ),
    )
    seed_results: list[ReferenceObservationSeedResult] = []
    aggregate_relationships: Counter[str] = Counter()
    aggregate_taxonomies: Counter[str] = Counter()
    for index, (seed, records) in enumerate(zip(seeds, compact_by_seed, strict=True)):
        summary: ReferenceObservationDrawSummary = summarize_reference_observation_fit_incidents(
            records,
            seed=seed,
            coefficients=generation_coefficients,
        )
        relationships = Counter(dict(summary.relationship_counts))
        taxonomies = Counter(dict(summary.taxonomy_counts))
        aggregate_relationships.update(relationships)
        aggregate_taxonomies.update(taxonomies)
        seed_results.append(
            ReferenceObservationSeedResult(
                seed_index=index,
                seed=seed,
                evaluation_reports=summary.evaluation_reports,
                breach_hour_counts=summary.hourly_counts[52:64],
                relationship_counts=_named_counts(relationships),
                taxonomy_counts=_named_counts(taxonomies),
            )
        )
    realized_total = sum(item.evaluation_reports for item in seed_results)
    breach_means = tuple(
        round(sum(item.breach_hour_counts[index] for item in seed_results) * 1_000 / len(seeds))
        for index in range(12)
    )
    elapsed_ms = round((time.perf_counter_ns() - started) / 1_000_000)
    adverse = (
        "The inherited unscaled hourly rate table integrates to 3,760 reports, not 2,900; amendment v4 preserves 95/hour in R3 and scales non-breach rates by 88/131.",
        "The original peak public-taxonomy shares conflict with the approved low-severity latent composition; no truth incident was relabelled to match them.",
        "Supplemental independent-witness reports are synthetic channel multiplicity, not empirical caller-behavior calibration.",
    )
    report_body = {
        "schema_version": "delta-reference-observation-fit-report-v1",
        "scientific_status": "spent-development-calibration-not-validation-evidence",
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "protocol_sha256": protocol_sha,
        "scientific_input_manifest_sha256": scientific_manifest.aggregate_sha256,
        "truth_coefficient_digest": protocol.truth_coefficient_digest,
        "development_seeds": seeds,
        "development_seed_list_sha256": seed_list_sha,
        "benchmark_receipt_digest": benchmark.receipt_digest,
        "candidate_evaluations": [item[0].model_dump(mode="json") for item in candidate_pairs],
        "selected_initial_report_probability_micros": (
            selected_evaluation.initial_report_probability_micros
        ),
        "hourly": [item.model_dump(mode="json") for item in hourly],
        "seed_results": [item.model_dump(mode="json") for item in seed_results],
        "analytical_expected_evaluation_reports_micros": sum(
            item.fitted_expected_reports_micros for item in hourly
        ),
        "realized_mean_evaluation_reports_milli": round(realized_total * 1_000 / len(seeds)),
        "realized_breach_hour_means_milli": breach_means,
        "aggregate_relationship_counts": [
            item.model_dump(mode="json") for item in _named_counts(aggregate_relationships)
        ],
        "aggregate_taxonomy_counts": [
            item.model_dump(mode="json") for item in _named_counts(aggregate_taxonomies)
        ],
        "elapsed_ms": elapsed_ms,
        "adverse_findings": adverse,
        "coefficient_digest": coefficients.coefficient_digest,
    }
    report = ReferenceObservationFitReport(
        **report_body,
        report_digest=hashlib.sha256(canonical_json_bytes(report_body)).hexdigest(),
    )
    return coefficients, report


def write_reference_observation_fit_benchmark(
    receipt: ReferenceObservationFitBenchmarkReceipt,
    output_root: Path,
) -> Path:
    output = safe_directory(
        output_root,
        declared_root=output_root,
        label="Reference observation benchmark output",
    )
    if any(output.iterdir()):
        raise ValueError("Reference observation benchmark output must be empty")
    destination = output / "observation_fit_benchmark_receipt.json"
    atomic_write_bytes(
        destination,
        canonical_json_bytes(receipt.model_dump(mode="json")),
        root=output,
        label="Reference observation benchmark receipt",
    )
    return destination


def load_reference_observation_fit_benchmark(
    trusted_root: Path,
    relative_name: Path,
) -> ReferenceObservationFitBenchmarkReceipt:
    path = ArtifactLocator(
        root=trusted_root,
        relative_name=relative_name,
        maximum_bytes=_MAX_INPUT_BYTES,
        label="Reference observation benchmark receipt",
    ).resolve()
    try:
        return ReferenceObservationFitBenchmarkReceipt.model_validate_json(path.read_text())
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError("Reference observation benchmark receipt is invalid") from exc


def write_reference_observation_fit(
    coefficients: ReferenceObservationCoefficientSet,
    report: ReferenceObservationFitReport,
    output_root: Path,
) -> tuple[Path, Path]:
    output = safe_directory(
        output_root,
        declared_root=output_root,
        label="Reference observation fit output",
    )
    if any(output.iterdir()):
        raise ValueError("Reference observation fit output must be empty")
    coefficient_path = output / "reference_observation_coefficients_v2.json"
    report_path = output / "reference_observation_fit_report_v1.json"
    coefficient_bytes = canonical_json_bytes(coefficients.model_dump(mode="json"))
    report_bytes = canonical_json_bytes(report.model_dump(mode="json"))
    if len(coefficient_bytes) + len(report_bytes) > _OUTPUT_BOUND_BYTES:
        raise ValueError("Reference observation fit outputs exceed their disk bound")
    atomic_write_bytes(
        coefficient_path,
        coefficient_bytes,
        root=output,
        label="Reference observation coefficients",
    )
    atomic_write_bytes(
        report_path,
        report_bytes,
        root=output,
        label="Reference observation fit report",
    )
    return coefficient_path, report_path
