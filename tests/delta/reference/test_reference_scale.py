from __future__ import annotations

from pathlib import Path

from trace_reference import load_reference_config
from trace_reference.scale import (
    benchmark_reference_event_ordering,
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
