from __future__ import annotations

from pathlib import Path

from trace_reference import load_reference_config
from trace_reference.scale import (
    benchmark_reference_event_ordering,
    benchmark_reference_workload_scale,
    characterize_reference_scale,
)

ROOT = Path(__file__).resolve().parents[3]
CONFIG = Path("configs/scenarios/wf_dfld_01_reference_development.yaml")


def test_reference_scale_characterization_matches_draft_grids() -> None:
    config = load_reference_config(ROOT, CONFIG)
    result = characterize_reference_scale(config)
    assert result.physical_output_ticks == 1_728
    assert result.decision_ticks == 5_760
    assert result.capacity_windows == 384
    assert result.minimum_scheduled_event_count == 10_772
    assert result.naive_person_position_rows == 2_419_200
    assert result.status == "engineering-estimate-development-only"


def test_reference_event_ordering_digest_is_deterministic() -> None:
    config = load_reference_config(ROOT, CONFIG)
    characterization = characterize_reference_scale(config)
    first = benchmark_reference_event_ordering(characterization, repeats=1)
    second = benchmark_reference_event_ordering(characterization, repeats=1)
    assert first.ordered_key_sha256 == second.ordered_key_sha256
    assert first.event_count == characterization.minimum_scheduled_event_count
    assert first.status == "descriptive-local-engineering-benchmark"


def test_constructed_workload_benchmark_is_bounded_and_non_scientific() -> None:
    result = benchmark_reference_workload_scale(
        latent_incident_target=100,
        public_report_target=200,
        authority_count=4,
    )

    assert result.processed_graph_observations == 800
    assert result.status == "constructed-engineering-proxy-not-simulator-evidence"
    assert result.projected_bundle_bytes_conservative < 1024**3
    assert result.projected_peak_memory_bytes_conservative < 2 * 1024**3
