from pathlib import Path

from trace_jepa.support import sha256_file
from trace_reference.provenance.scientific_inputs import (
    build_reference_scientific_input_manifest,
)
from trace_reference.validation.preregistration_models import (
    ReferenceBaseValidationPreregistrationDraft,
)

ROOT = Path(__file__).parents[3]
DRAFT_PATH = Path(
    "data/scenario/delta/reference_protocol/reference_base_validation_preregistration_draft_v1.json"
)


def _draft() -> ReferenceBaseValidationPreregistrationDraft:
    return ReferenceBaseValidationPreregistrationDraft.model_validate_json(
        (ROOT / DRAFT_PATH).read_text(encoding="utf-8")
    )


def test_draft_binds_current_development_inputs_without_seed_values() -> None:
    draft = _draft()

    assert draft.scientific_input_aggregate_sha256 == (
        build_reference_scientific_input_manifest(ROOT).aggregate_sha256
    )
    assert draft.selection_validation_confirmatory_seed_values == ()
    assert all(not item.contains_seed_values for item in draft.study_roles)
    for binding in draft.bindings:
        assert sha256_file(ROOT / binding.repository_relative_path) == binding.sha256


def test_draft_preserves_exposed_v1_namespaces_and_protects_v2() -> None:
    draft = _draft()
    roles = {item.role: item for item in draft.study_roles}

    assert roles["selection-v1-exposed"].execution_boundary == "never-use"
    assert roles["validation-v1-exposed"].execution_boundary == "never-use"
    assert roles["selection-v2-proposed"].execution_boundary == "disabled"
    assert roles["validation-v2-proposed"].execution_boundary == (
        "remote-original-once-only-after-approval"
    )
    existing_test = (ROOT / "tests/delta/reference/test_reference_protocol.py").read_text(
        encoding="utf-8"
    )
    assert 'derive_seed_prefix("selection", 100)' in existing_test
    assert 'derive_seed_prefix("validation", 100)' in existing_test


def test_draft_has_only_exact_integration_gates_and_report_only_estimands() -> None:
    draft = _draft()

    assert len(draft.exact_gates) == 10
    assert all(not item.numerical_acceptance_gate for item in draft.report_only_estimands)
    assert not draft.policy_effectiveness_claim_present
    assert not draft.leap_behavior_present
    assert draft.remote_original.authorization == "disabled-awaiting-owner-approval"
