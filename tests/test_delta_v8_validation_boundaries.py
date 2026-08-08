from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from trace_jepa.scenario.delta.cli import build_parser
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
        return {"study_id": "development-v8", "seed_count": len(observed["study"])}

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
