from __future__ import annotations

import os
from pathlib import Path

import pytest

from trace_reference.validation import original_execution
from trace_reference.validation.registration import (
    REFERENCE_VALIDATION_TAG,
    load_reference_validation_protocol,
    require_original_execution_identity,
    verify_reference_validation_freeze,
)

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github/workflows/reference-base-validation-v2-original.yml"


def _valid_identity_environment() -> dict[str, str]:
    return {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REF": f"refs/tags/{REFERENCE_VALIDATION_TAG}",
        "GITHUB_REPOSITORY": "eyuchang/trace-worldmodel-flood-sar",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_RUN_ID": "123456",
        "GITHUB_SHA": "a" * 40,
        "TRACE_REFERENCE_ANNOTATED_TAG_GUARD": "verified-annotated-tag-points-to-sha",
        "TRACE_REFERENCE_AUTHORIZATION_TAG": REFERENCE_VALIDATION_TAG,
        "TRACE_REFERENCE_EXECUTION_ROLE": "original-base-reference-validation",
        "TRACE_REFERENCE_PRIOR_SUCCESS_GUARD": "verified-no-prior-success",
        "TRACE_REFERENCE_WORKFLOW_FILE": "reference-base-validation-v2-original.yml",
    }


def test_validation_v2_protocol_contains_no_protected_values() -> None:
    protocol = load_reference_validation_protocol(ROOT)
    assert protocol.protected_seed_values == ()
    assert protocol.mission_count == 100
    assert protocol.shard_count == 20
    declarations = {item.role: item for item in protocol.study_declarations}
    assert declarations["selection-v2"].execution_boundary == "disabled"
    assert declarations["validation-v2"].execution_boundary == "remote-original-once-only"
    assert declarations["selection-v1"].lifecycle == "superseded-before-scientific-use"
    assert declarations["validation-v1"].lifecycle == "superseded-before-scientific-use"
    assert all(not item.numerical_threshold for item in protocol.exact_gates)
    assert all(not item.numerical_acceptance_gate for item in protocol.report_only_estimands)


@pytest.mark.parametrize(
    ("name", "value"),
    (
        ("GITHUB_ACTIONS", "false"),
        ("GITHUB_REF", "refs/heads/demo-delta-reference-scenario"),
        ("GITHUB_RUN_ATTEMPT", "2"),
        ("TRACE_REFERENCE_PRIOR_SUCCESS_GUARD", ""),
        ("TRACE_REFERENCE_ANNOTATED_TAG_GUARD", ""),
    ),
)
def test_original_identity_fails_closed(name: str, value: str) -> None:
    environment = _valid_identity_environment()
    environment[name] = value
    with pytest.raises(ValueError, match="identity is incomplete"):
        require_original_execution_identity(environment)


def test_original_identity_is_typed_and_source_bound() -> None:
    identity = require_original_execution_identity(_valid_identity_environment())
    assert identity.source_commit == "a" * 40
    assert identity.workflow_run_attempt == 1
    assert identity.authorization_tag == REFERENCE_VALIDATION_TAG


def test_protected_derivation_is_not_reached_before_boundary_verification(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    def reject_boundary(*_args: object, **_kwargs: object) -> object:
        calls.append("boundary")
        raise ValueError("blocked before protected derivation")

    def forbidden_seed_list() -> tuple[int, ...]:
        calls.append("seed-list")
        raise AssertionError("protected list must not be reached")

    monkeypatch.setattr(original_execution, "require_original_validation_boundary", reject_boundary)
    monkeypatch.setattr(original_execution, "_seed_list", forbidden_seed_list)
    with pytest.raises(ValueError, match="blocked before protected derivation"):
        original_execution.prepare_protected_seed_plan(
            ROOT,
            tmp_path / "seed-plan.json",
            environment=os.environ,
        )
    assert calls == ["boundary"]


def test_original_workflow_is_tag_only_once_only_and_offline() -> None:
    text = WORKFLOW.read_text("utf-8")
    assert "workflow_dispatch" not in text
    assert "wf-dfld-01-reference-validation-v2-original" in text
    assert 'test "${GITHUB_RUN_ATTEMPT}" = "1"' in text
    assert "git rev-parse HEAD" in text
    assert '.object.type\'\n          })" = "tag"' in text
    assert '.conclusion == \\"success\\"' in text
    assert "cancel-in-progress: false" in text
    assert text.count("--network none") == 3
    assert "user-supplied" not in text
    assert "--seed " not in text
    assert "selection-v2" not in text


def test_original_workflow_uses_pinned_actions_and_images() -> None:
    text = WORKFLOW.read_text("utf-8")
    assert "uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683" in text
    assert "uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02" in text
    assert "uses: actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093" in text
    assert "sha256:3b3706a90cb23f04fabb0d255824f9a70ceb46177041898133dd5a35f3a50f0a" in text
    assert "sha256:88b6d3132a0850db3587a4f4ff28d5568e7d65ff99f0ee34f42be864ddb4ca1d" in text


def test_validation_freeze_binds_current_inputs_and_development_evidence() -> None:
    freeze_path = ROOT / (
        "data/scenario/delta/reference_protocol/reference_base_validation_freeze_v2.json"
    )
    if not freeze_path.exists():
        pytest.skip("freeze record is generated only after corrected canonical Phase 6")
    freeze = verify_reference_validation_freeze(ROOT)
    assert freeze.protected_seed_values == ()
    assert freeze.scientific_input_member_count > 100
    assert freeze.authorization_tag == REFERENCE_VALIDATION_TAG
    assert freeze.g3_handoff.repository_relative_path.endswith("g3_handoff_manifest.json")
    assert freeze.phase6_development_acceptance.repository_relative_path.endswith(
        "phase6_development_acceptance_report.json"
    )
    assert freeze.canonical_phase6_execution_receipt.repository_relative_path.endswith(
        "canonical_execution_receipt.json"
    )
