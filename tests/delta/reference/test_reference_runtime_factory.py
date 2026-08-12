from __future__ import annotations

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
