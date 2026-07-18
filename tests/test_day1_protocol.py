from __future__ import annotations

import json
from pathlib import Path

import pytest
import trace_jepa.evaluation.day1 as day1_module

from trace_jepa.evaluation.day1 import (
    _cell_phase_provenance,
    _next_g2_noise,
    run_g2,
    run_smoke,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = REPOSITORY_ROOT / "tests/fixtures/experiment_protocol_stub.txt"
AMENDED_WORKLOAD = (
    REPOSITORY_ROOT / "configs/workloads/g2_later_horizon_v1.yaml"
)


def _history(noise: float, rate: float, *, complete: bool = True) -> dict:
    return {
        "noise": noise,
        "aggregate": {"stale_execution_rate": rate},
        "checks": {"exactly_20_complete_valid_cells": complete},
    }


def test_g2_tuning_rule_is_bounded_and_requires_monotone_bracketing() -> None:
    assert _next_g2_noise([_history(0.35, 0.05)]) == 0.70
    assert _next_g2_noise([_history(0.35, 0.50)]) == 0.00
    assert _next_g2_noise([_history(0.35, 0.20)]) is None
    assert _next_g2_noise(
        [_history(0.35, 0.05), _history(0.70, 0.50)]
    ) == pytest.approx(0.525)
    assert _next_g2_noise(
        [_history(0.35, 0.50), _history(0.00, 0.05)]
    ) == pytest.approx(0.175)
    assert _next_g2_noise(
        [_history(0.35, 0.05), _history(0.70, 0.04)]
    ) is None
    assert _next_g2_noise([_history(0.35, 0.05, complete=False)]) is None


def test_short_disposable_g2_is_complete_but_not_misreported_as_pass(
    tmp_path: Path,
) -> None:
    result = run_g2(
        output_root=tmp_path / "g2",
        repository_root=REPOSITORY_ROOT,
        protocol_path=PROTOCOL,
        duration_s=3.0,
        workers=1,
    )
    assert result["status"] == "failed"
    assert len(result["history"]) == 2
    assert [item["noise"] for item in result["history"]] == [0.35, 0.70]
    assert all(
        item["checks"]["exactly_20_complete_valid_cells"]
        for item in result["history"]
    )
    assert all(item["aggregate"]["executed"] > 0 for item in result["history"])
    assert all(
        item["aggregate"]["stale_execution_rate"] == 0.0
        for item in result["history"]
    )
    assert (tmp_path / "g2/G2_RESULT.json").is_file()


def test_short_disposable_smoke_checks_all_nine_cells_and_crn(
    tmp_path: Path,
) -> None:
    result = run_smoke(
        noise=0.35,
        output_root=tmp_path / "smoke",
        repository_root=REPOSITORY_ROOT,
        protocol_path=PROTOCOL,
        duration_s=3.0,
        workers=1,
    )
    assert result["status"] == "passed"
    assert len(result["attempts"]) == 9
    assert result["checks"] == {
        "exactly_nine_complete_valid_cells": True,
        "per_seed_exogenous_hashes_identical": True,
        "scientific_provenance_matches_g2": True,
    }
    assert all(
        len(hashes) == 1
        for hashes in result["exogenous_sha256_by_seed"].values()
    )
    first_directory = Path(result["attempts"][0]["directory"])
    manifest = json.loads(
        (first_directory / "manifest.json").read_text(encoding="utf-8")
    )
    mismatched_provenance = _cell_phase_provenance(
        manifest["scientific_identity"]
    )
    mismatched_provenance["forcing_noise_std"] = 0.70
    rejected = run_smoke(
        noise=0.35,
        output_root=tmp_path / "smoke",
        repository_root=REPOSITORY_ROOT,
        protocol_path=PROTOCOL,
        duration_s=3.0,
        workers=1,
        expected_g2_provenance=mismatched_provenance,
    )
    assert rejected["status"] == "failed"
    assert rejected["checks"]["scientific_provenance_matches_g2"] is False


def test_amended_g2_uses_one_frozen_setting_and_new_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(day1_module, "AMENDED_G2_SEEDS", (21,))
    result = run_g2(
        output_root=tmp_path / "amended-g2",
        repository_root=REPOSITORY_ROOT,
        protocol_path=PROTOCOL,
        duration_s=7800.0,
        workers=1,
        evaluation_workload_path=AMENDED_WORKLOAD,
        protocol_amendment_id="g2-workload-amendment-1",
        fixed_noise_settings=(0.35,),
    )
    assert len(result["history"]) == 1
    assert result["history"][0]["noise"] == 0.35
    assert result["max_settings"] == 1
    assert result["tuning_rule"] == "fixed_predeclared_settings"
    assert result["protocol_amendment_id"] == "g2-workload-amendment-1"
    assert result["cross_setting_scientific_provenance_consistent"] is True
    assert result["scientific_provenance"]["evaluation_workload"][
        "workload_id"
    ] == "g2-later-horizon-v1"
