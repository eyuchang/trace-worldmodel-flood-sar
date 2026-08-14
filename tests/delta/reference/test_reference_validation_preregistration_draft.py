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
        "9f12ed0993ac11fd3636e0a195fb21ae442829930f94f531135e7e2c0c4194b5"
    )
    assert (
        build_reference_scientific_input_manifest(ROOT).aggregate_sha256
        != draft.scientific_input_aggregate_sha256
    )
    assert draft.selection_validation_confirmatory_seed_values == ()
    assert all(not item.contains_seed_values for item in draft.study_roles)
    assert sha256_file(ROOT / DRAFT_PATH) == (
        "fc80c92d95347affcecc6460c3001828641d190fa2b4adcc3373a856c585b6e6"
    )


def test_draft_preserves_exposed_v1_namespaces_and_protects_v2() -> None:
    draft = _draft()
    roles = {item.role: item for item in draft.study_roles}

    assert roles["selection-v1-exposed"].execution_boundary == "never-use"
    assert roles["validation-v1-exposed"].execution_boundary == "never-use"
    assert roles["selection-v2-proposed"].execution_boundary == "disabled"
    assert roles["validation-v2-proposed"].execution_boundary == (
        "remote-original-once-only-after-approval"
    )
    amendment = (
        ROOT / "docs/delta/reference/WF_DFLD_01_REFERENCE_PROTOCOL_AMENDMENT_V6.md"
    ).read_text(encoding="utf-8")
    assert 'derive_seed_prefix("selection", 100)' in amendment
    assert 'derive_seed_prefix("validation", 100)' in amendment


def test_draft_has_only_exact_integration_gates_and_report_only_estimands() -> None:
    draft = _draft()

    assert len(draft.exact_gates) == 10
    assert all(not item.numerical_acceptance_gate for item in draft.report_only_estimands)
    assert not draft.policy_effectiveness_claim_present
    assert not draft.leap_behavior_present
    assert draft.remote_original.authorization == "disabled-awaiting-owner-approval"
