"""Reversible engineering characterization for the draft Reference scale."""

from __future__ import annotations

import hashlib
import statistics
import time
from dataclasses import dataclass

from pydantic import Field

from trace_jepa.scenario.delta.domain.base import DeltaModel
from trace_jepa.support import canonical_json_bytes, sha256_bytes

from .models import ReferenceScenarioConfig


class ReferenceScaleCharacterization(DeltaModel):
    """Arithmetic workload estimate; it is not a performance acceptance result."""

    schema_version: str = "delta-reference-scale-characterization-v1"
    status: str = "engineering-estimate-development-only"
    physical_output_ticks: int = Field(gt=0)
    decision_ticks: int = Field(gt=0)
    capacity_windows: int = Field(gt=0)
    design_target_public_reports: int = Field(gt=0)
    minimum_scheduled_event_count: int = Field(gt=0)
    naive_person_position_rows: int = Field(gt=0)
    synthetic_people: int = Field(gt=0)


class ReferenceEventOrderingBenchmark(DeltaModel):
    """Local execution receipt for an engineering-only event-ordering benchmark."""

    schema_version: str = "delta-reference-event-ordering-benchmark-v1"
    status: str = "descriptive-local-engineering-benchmark"
    event_count: int = Field(gt=0)
    repeats: int = Field(gt=0)
    median_elapsed_ms: float = Field(ge=0.0)
    ordered_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


@dataclass(frozen=True, order=True)
class _EngineeringEventKey:
    simulation_time_s: int
    priority: int
    stable_entity_id: str
    event_digest: str


def characterize_reference_scale(
    config: ReferenceScenarioConfig,
) -> ReferenceScaleCharacterization:
    """Compute exact counts implied by the current development-only draft grids."""

    timeline = config.timeline
    total_duration = timeline.evaluation_end_s - timeline.burn_in_start_s
    evaluation_duration = timeline.evaluation_end_s - timeline.evaluation_start_s
    physical_ticks = total_duration // timeline.output_tick_s
    decision_ticks = evaluation_duration // timeline.decision_tick_s
    capacity_windows = evaluation_duration // timeline.capacity_evaluation_tick_s
    public_reports = config.process_targets.expected_public_reports_evaluation
    return ReferenceScaleCharacterization(
        physical_output_ticks=physical_ticks,
        decision_ticks=decision_ticks,
        capacity_windows=capacity_windows,
        design_target_public_reports=public_reports,
        minimum_scheduled_event_count=(
            physical_ticks + decision_ticks + capacity_windows + public_reports
        ),
        naive_person_position_rows=config.extent.synthetic_people * physical_ticks,
        synthetic_people=config.extent.synthetic_people,
    )


def _engineering_event_keys(
    characterization: ReferenceScaleCharacterization,
) -> tuple[_EngineeringEventKey, ...]:
    keys: list[_EngineeringEventKey] = []
    for index in range(characterization.minimum_scheduled_event_count):
        digest = hashlib.sha256(f"reference-phase0-event|{index}".encode()).hexdigest()
        keys.append(
            _EngineeringEventKey(
                simulation_time_s=int(digest[:8], 16) % 518_400 - 172_800,
                priority=int(digest[8:10], 16) % 16,
                stable_entity_id=(f"BENCH-{index % characterization.synthetic_people:04d}"),
                event_digest=digest,
            )
        )
    return tuple(keys)


def _ordered_key_digest(keys: tuple[_EngineeringEventKey, ...]) -> str:
    ordered = sorted(keys)
    payload = [
        (
            key.simulation_time_s,
            key.priority,
            key.stable_entity_id,
            key.event_digest,
        )
        for key in ordered
    ]
    return sha256_bytes(canonical_json_bytes(payload))


def benchmark_reference_event_ordering(
    characterization: ReferenceScaleCharacterization,
    *,
    repeats: int = 5,
) -> ReferenceEventOrderingBenchmark:
    """Measure deterministic key ordering without asserting a scientific runtime gate."""

    if repeats < 1:
        raise ValueError("benchmark repeats must be positive")
    keys = _engineering_event_keys(characterization)
    elapsed_ms: list[float] = []
    ordered_digest = ""
    for _ in range(repeats):
        start = time.perf_counter_ns()
        ordered_digest = _ordered_key_digest(keys)
        elapsed_ms.append((time.perf_counter_ns() - start) / 1_000_000)
    return ReferenceEventOrderingBenchmark(
        event_count=len(keys),
        repeats=repeats,
        median_elapsed_ms=statistics.median(elapsed_ms),
        ordered_key_sha256=ordered_digest,
    )
