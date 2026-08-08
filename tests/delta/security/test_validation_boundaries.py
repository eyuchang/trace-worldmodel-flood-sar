from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from trace_jepa.scenario.delta.artifacts import canonical_json_bytes, sha256_file
from trace_jepa.scenario.delta.cli import build_parser
from trace_jepa.scenario.delta.loading import load_acceptance_config
from trace_jepa.scenario.delta.validation.models import (
    OriginalReportIdentity,
    OriginalReportRegistry,
    verify_registered_original_report,
)
from trace_jepa.scenario.delta.validation_v8 import (
    ORIGINAL_CONFIRMATION_TOKEN,
    _require_original_remote_context,
    canonical_v9_paths,
    run_v8_development_validation,
    verify_registered_v8_inputs,
)

ROOT = Path(__file__).resolve().parents[3]
CANONICAL = canonical_v9_paths(ROOT)


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

    monkeypatch.setattr("trace_jepa.scenario.delta.validation.registered.run_v7_study", fake_study)
    monkeypatch.setattr(
        "trace_jepa.scenario.delta.validation.registered.paired_reconciliation_report",
        fake_paired,
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


def test_original_confirmation_requires_exact_tag_and_first_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = {
        "GITHUB_ACTIONS": "true",
        "TRACE_DELTA_EXECUTION_ROLE": "original-confirmatory",
        "GITHUB_REF": "refs/tags/wrong",
        "GITHUB_RUN_ATTEMPT": "1",
        "TRACE_DELTA_WORKFLOW_FILE": "delta-confirmatory-v8.yml",
        "GITHUB_RUN_ID": "123",
        "GITHUB_SHA": "a" * 40,
        "GITHUB_WORKFLOW": "Delta confirmatory-v8 original",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match="exact authorization tag"):
        _require_original_remote_context(ORIGINAL_CONFIRMATION_TOKEN)
    monkeypatch.setenv("GITHUB_REF", "refs/tags/wf-dfld-01-small-confirmatory-v8-original")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "2")
    with pytest.raises(ValueError, match="attempt one"):
        _require_original_remote_context(ORIGINAL_CONFIRMATION_TOKEN)


def test_replication_requires_byte_identical_committed_original_registry(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "evidence/original.json"
    report_path.parent.mkdir()
    report: dict[str, object] = {
        "schema_version": "delta-statistical-validation-v5",
        "execution_role": "original-confirmatory",
        "source_commit": "a" * 40,
        "authorization_tag": "wf-dfld-01-small-confirmatory-v8-original",
        "workflow_run_id": "123",
        "workflow_name": "Delta confirmatory-v8 original",
        "workflow_file": "delta-confirmatory-v8.yml",
        "protocol_sha256": "b" * 64,
        "scientific_input_manifest_sha256": "c" * 64,
        "scientific_input_aggregate_sha256": "d" * 64,
        "scientific_input_core_aggregate_sha256": "e" * 64,
        "environment_contract_sha256": "f" * 64,
        "dependency_lock_sha256": "1" * 64,
        "scenario_configuration_sha256": "2" * 64,
        "geography_sha256": "3" * 64,
        "policy_sha256": "4" * 64,
        "seed_list": list(range(100)),
        "studies": [
            {"study_id": "development-v9", "seed_count": 100},
            {"study_id": "confirmatory-v8-primary", "seed_count": 100},
        ],
        "paired_reconciliation": {
            "baseline_algorithm_id": "baseline-v7-heuristic",
            "selected_algorithm_id": "evidence-graph-q075",
        },
    }
    report_path.write_bytes(canonical_json_bytes(report))
    identity = OriginalReportIdentity.from_report(report)
    registry_path = tmp_path / "registry.json"
    registry = OriginalReportRegistry(
        schema_version="delta-original-report-registry-v1",
        report_path="evidence/original.json",
        report_sha256=sha256_file(report_path),
        identity_sha256=identity.canonical_sha256,
    )
    registry_path.write_bytes(canonical_json_bytes(registry.model_dump(mode="json")))
    loaded, loaded_identity = verify_registered_original_report(
        tmp_path, report_path, registry_path
    )
    assert loaded == report
    assert loaded_identity == identity

    altered = json.loads(report_path.read_text("utf-8"))
    altered["workflow_run_id"] = "124"
    report_path.write_bytes(canonical_json_bytes(altered))
    with pytest.raises(ValueError, match="digest"):
        verify_registered_original_report(tmp_path, report_path, registry_path)


def test_confirmatory_v8_preregistration_binds_exact_new_seeds_and_manifest() -> None:
    if not CANONICAL["acceptance"].is_file():
        pytest.skip("confirmatory-v8 is intentionally not derived before the final freeze")
    protocol = load_acceptance_config(CANONICAL["acceptance"])
    assert protocol.schema_version == "delta-small-acceptance-v9"
    assert protocol.v8_confirmatory_ensemble is not None
    expected = [
        int.from_bytes(
            hashlib.sha256(f"WF-DFLD-01-SMALL|confirmatory-v8|{index}".encode()).digest()[:4],
            "big",
        )
        & 0x7FFFFFFF
        for index in range(100)
    ]
    assert protocol.v8_confirmatory_ensemble.seeds == expected
    assert len(set(expected)) == 100
    assert protocol.scientific_input_manifest_sha256 is None
    assert protocol.scientific_input_core_aggregate_sha256 is not None
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

    monkeypatch.setattr(
        "trace_jepa.scenario.delta.validation.registered.run_v7_study",
        forbidden_study,
    )
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


def test_remote_workflow_uses_exact_tag_and_expiration_independent_once_only_guard() -> None:
    superseded = (ROOT / ".github/workflows/delta-confirmatory-v6.yml").read_text("utf-8")
    original = (ROOT / ".github/workflows/delta-confirmatory-v8.yml").read_text("utf-8")
    assert "trace-jepa-delta-small validate" not in superseded
    assert "superseded-before-execution" in superseded
    assert "workflow_dispatch" not in original
    assert "wf-dfld-01-small-confirmatory-v8-original" in original
    assert 'test "${GITHUB_RUN_ATTEMPT}" = "1"' in original
    assert "actions/workflows/${TRACE_DELTA_WORKFLOW_FILE}/runs" in original
    assert "listArtifactsForRepo" not in original
    assert "--study original-confirmatory" in original
    assert ORIGINAL_CONFIRMATION_TOKEN in original
    assert "wf_dfld_01_small_acceptance_v5.yaml" in original
    assert "v8_scientific_input_manifest_v2.json" in original
    assert "88b6d3132a0850db3587a4f4ff28d5568e7d65ff99f0ee34f42be864ddb4ca1d" in original
    assert "Refuse any prior successful original" in original
