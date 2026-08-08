from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

from trace_jepa.scenario.delta.artifacts import sha256_file
from trace_jepa.scenario.delta.cli import build_parser
from trace_jepa.scenario.delta.loading import load_acceptance_config
from trace_jepa.scenario.delta.validation_v8 import (
    ORIGINAL_CONFIRMATION_TOKEN,
    _require_original_remote_context,
    canonical_v8_paths,
    run_v8_development_validation,
    verify_registered_v8_inputs,
)

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = canonical_v8_paths(ROOT)


def test_validate_requires_an_explicit_study_role(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["validate", "--output", str(tmp_path / "report.json")])


def test_registered_validation_rejects_substituted_config_before_loading(
    tmp_path: Path,
) -> None:
    alternate = tmp_path / "same-bytes-different-path.yaml"
    shutil.copyfile(CANONICAL["config"], alternate)
    with pytest.raises(ValueError, match="path was substituted"):
        verify_registered_v8_inputs(
            config_path=alternate,
            geography_path=CANONICAL["geography"],
            policy_path=CANONICAL["policy"],
            scientific_manifest_path=CANONICAL["scientific_manifest"],
        )


def test_development_mode_uses_only_declared_development_seeds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, list[int]] = {}

    def fake_study(**kwargs: object) -> dict[str, object]:
        observed["study"] = list(kwargs["seeds"])  # type: ignore[arg-type]
        return {
            "study_id": "development-v8",
            "seed_count": len(observed["study"]),
            "operations": {"all_episode_keys_unique": True},
        }

    def fake_paired(**kwargs: object) -> dict[str, object]:
        observed["paired"] = list(kwargs["seeds"])  # type: ignore[arg-type]
        return {"seed_count": len(observed["paired"])}

    monkeypatch.setattr("trace_jepa.scenario.delta.validation_v8.run_v7_study", fake_study)
    monkeypatch.setattr(
        "trace_jepa.scenario.delta.validation_v8._paired_reconciliation", fake_paired
    )
    report = run_v8_development_validation(
        config_path=CANONICAL["config"],
        geography_path=CANONICAL["geography"],
        policy_path=CANONICAL["policy"],
        scientific_manifest_path=CANONICAL["scientific_manifest"],
        output_path=tmp_path / "development.json",
    )
    expected = list(range(20260803, 20260903))
    assert observed == {"study": expected, "paired": expected}
    assert report["confirmatory_seeds_accessed"] is False


def test_original_confirmation_is_inaccessible_outside_dedicated_remote_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("TRACE_DELTA_EXECUTION_ROLE", raising=False)
    monkeypatch.delenv("GITHUB_RUN_ID", raising=False)
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    with pytest.raises(ValueError, match="restricted to GitHub Actions"):
        _require_original_remote_context(ORIGINAL_CONFIRMATION_TOKEN)


def test_original_confirmation_rejects_wrong_token_before_any_execution() -> None:
    with pytest.raises(ValueError, match="explicit authorization token"):
        _require_original_remote_context("wrong-token")


def test_confirmatory_v7_preregistration_binds_exact_new_seeds_and_manifest() -> None:
    protocol = load_acceptance_config(CANONICAL["acceptance"])
    assert protocol.schema_version == "delta-small-acceptance-v8"
    assert protocol.v8_confirmatory_ensemble is not None
    expected = [
        int.from_bytes(
            hashlib.sha256(f"WF-DFLD-01-SMALL|confirmatory-v7|{index}".encode()).digest()[:4],
            "big",
        )
        & 0x7FFFFFFF
        for index in range(100)
    ]
    assert protocol.v8_confirmatory_ensemble.seeds == expected
    assert len(set(expected)) == 100
    assert protocol.scientific_input_manifest_sha256 == sha256_file(
        CANONICAL["scientific_manifest"]
    )
    assert protocol.demand_capacity.strict_numerical_gate is None
    assert protocol.reconciliation_comparison is not None
    assert protocol.reconciliation_comparison.selected_algorithm_id == "evidence-graph-q075"


def test_original_mode_rejects_local_execution_before_studies_start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)

    def forbidden_study(**_kwargs: object) -> dict[str, object]:
        raise AssertionError("holdout study was reached outside the remote guard")

    monkeypatch.setattr("trace_jepa.scenario.delta.validation_v8.run_v7_study", forbidden_study)
    from trace_jepa.scenario.delta.validation_v8 import run_v8_registered_validation

    with pytest.raises(ValueError, match="restricted to GitHub Actions"):
        run_v8_registered_validation(
            study="original-confirmatory",
            config_path=CANONICAL["config"],
            geography_path=CANONICAL["geography"],
            policy_path=CANONICAL["policy"],
            acceptance_path=CANONICAL["acceptance"],
            scientific_manifest_path=CANONICAL["scientific_manifest"],
            output_path=tmp_path / "must-not-exist.json",
            confirmation_token=ORIGINAL_CONFIRMATION_TOKEN,
        )
    assert not (tmp_path / "must-not-exist.json").exists()


def test_remote_workflows_disable_v6_and_bind_v7_original_execution() -> None:
    superseded = (ROOT / ".github/workflows/delta-confirmatory-v6.yml").read_text("utf-8")
    original = (ROOT / ".github/workflows/delta-confirmatory-v7.yml").read_text("utf-8")
    assert "trace-jepa-delta-small validate" not in superseded
    assert "superseded-before-execution" in superseded
    assert "--study original-confirmatory" in original
    assert ORIGINAL_CONFIRMATION_TOKEN in original
    assert "wf_dfld_01_small_acceptance_v4.yaml" in original
    assert "v8_scientific_input_manifest_v1.json" in original
    assert "88b6d3132a0850db3587a4f4ff28d5568e7d65ff99f0ee34f42be864ddb4ca1d" in original
    assert "Refuse a second original evidence artifact" in original
