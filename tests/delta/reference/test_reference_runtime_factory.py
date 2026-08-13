from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from trace_reference.generation import generate_reference_scenario
from trace_reference.runtime import build_reference_runtime

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def scenario():
    return generate_reference_scenario(ROOT, seed=20260812)


def test_runtime_factory_executes_the_base_non_leap_surface(scenario, tmp_path: Path) -> None:
    bundle = build_reference_runtime(scenario, tmp_path)
    result = bundle.runtime.run(through_s=0)

    assert result.fault_profile_id == "reference-nominal-v1"
    assert bundle.event_log.verify()
    assert bundle.trace_repository.verify_chain()
    assert bundle.evidence_ledger.verify_chain()
    assert bundle.commitment_log.verify_chain()


def test_runtime_factory_rejects_symlinked_output_root(scenario, tmp_path: Path) -> None:
    actual = tmp_path / "actual"
    actual.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(actual, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        build_reference_runtime(scenario, alias)


def test_runtime_public_decisions_are_independent_of_hidden_report_lineage(
    scenario,
    tmp_path: Path,
) -> None:
    removed_hidden = scenario.observations.hidden.model_copy(
        update={"entries": (), "hidden_digest": "0" * 64}
    )
    without_lineage = replace(
        scenario,
        observations=scenario.observations.model_copy(update={"hidden": removed_hidden}),
    )
    first_root = tmp_path / "with-lineage"
    second_root = tmp_path / "without-lineage"
    first_root.mkdir()
    second_root.mkdir()

    first = build_reference_runtime(scenario, first_root)
    second = build_reference_runtime(without_lineage, second_root)
    first_run = first.runtime.run(through_s=0)
    second_run = second.runtime.run(through_s=0)

    assert first_run.decisions == second_run.decisions
    assert first.trace_repository.chain_entries() == second.trace_repository.chain_entries()
    assert first.evidence_ledger.chain_entries() == second.evidence_ledger.chain_entries()
    assert first.commitment_log.chain_entries() == second.commitment_log.chain_entries()
    assert first.event_log.events == second.event_log.events
    assert not hasattr(first.runtime.engine.dependencies.public_inputs, "observations")
    assert not hasattr(first.runtime.engine.dependencies.public_inputs, "truth")
