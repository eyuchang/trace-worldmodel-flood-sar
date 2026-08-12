"""Frozen public-state, proposal, eligibility, bundle, and cost contracts."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import Field, model_validator

from trace_jepa.contracts import CommitmentDecision
from trace_jepa.scenario.delta.domain.base import DeltaModel


class PublicEnvironmentBelief(DeltaModel):
    belief_id: str
    kind: Literal["weather", "gauge", "crossing", "levee", "facility", "access"]
    entity_id: str
    value: str
    observed_at_s: int = Field(ge=-172_800, le=345_600)
    evidence_id: str


class PublicResourceBelief(DeltaModel):
    resource_id: str = Field(pattern=r"^RR-[0-9a-f]{16}$")
    resource_class: str
    capabilities: tuple[str, ...] = Field(min_length=1)
    service_units: int = Field(ge=1, le=8)
    reported_state: str
    owning_authority_id: str = Field(pattern=r"^AUTH-0[1-4]$")
    staged_node_id: str
    observed_at_s: int = Field(ge=-172_800, lt=345_600)
    telemetry_id: str = Field(pattern=r"^RT-[0-9a-f]{16}$")


class PublicCommitmentBelief(DeltaModel):
    commitment_id: str
    resource_id: str
    action_class: str
    active_from_s: int = Field(ge=-172_800)
    active_until_s: int
    authorizing_trace_record_id: str
    authorizing_trace_record_version: int = Field(ge=1)


class PublicOutcomeBelief(DeltaModel):
    outcome_id: str
    commitment_id: str
    status: str
    observed_at_s: int = Field(ge=-172_800, le=345_600)


class ControllerVisibleSnapshot(DeltaModel):
    """Explicit allowlist projection; it cannot recursively contain hidden runtime state."""

    schema_version: Literal["delta-reference-public-snapshot-v1"]
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    mission_id: str
    decision_id: str
    at_s: int = Field(ge=-172_800, le=345_600)
    evidence_prefix_digest: str = Field(pattern=r"^(GENESIS|[0-9a-f]{64})$")
    trace_prefix_digest: str = Field(pattern=r"^(GENESIS|[0-9a-f]{64})$")
    commitment_prefix_digest: str = Field(pattern=r"^(GENESIS|[0-9a-f]{64})$")
    environment_beliefs: tuple[PublicEnvironmentBelief, ...]
    resource_beliefs: tuple[PublicResourceBelief, ...]
    delivered_coordination_ids: tuple[str, ...]
    active_commitments: tuple[PublicCommitmentBelief, ...]
    known_outcomes: tuple[PublicOutcomeBelief, ...]
    predictor_version: str
    predictor_model_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    calibration_version: str
    calibration_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    qualification_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    prior_profile_id: str
    policy_version: str
    environment_contract_version: str
    decision_extension_id: None = None
    snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_orders(self) -> ControllerVisibleSnapshot:
        if self.environment_beliefs != tuple(
            sorted(self.environment_beliefs, key=lambda item: item.belief_id)
        ):
            raise ValueError("Reference environment beliefs must be canonically ordered")
        if self.resource_beliefs != tuple(
            sorted(self.resource_beliefs, key=lambda item: item.resource_id)
        ):
            raise ValueError("Reference resource beliefs must be canonically ordered")
        if self.delivered_coordination_ids != tuple(sorted(set(self.delivered_coordination_ids))):
            raise ValueError("Reference coordination identifiers must be unique and ordered")
        return self


class ReferenceActionSpec(DeltaModel):
    action_id: str
    action_class: str
    actor_resource_id: str | None
    actor_crew_id: str | None
    origin_node_id: str | None
    destination_public_id: str
    route_id: str | None
    required_capability: str
    execution_not_before_s: int = Field(ge=-172_800)
    execution_not_after_s: int
    commitment_horizon_end_s: int
    deterministic_service_duration_s: int = Field(ge=300, le=86_400)
    action_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_action_window(self) -> ReferenceActionSpec:
        if not (
            self.execution_not_before_s
            <= self.execution_not_after_s
            <= self.commitment_horizon_end_s
        ):
            raise ValueError("Reference action execution and commitment windows are invalid")
        return self


class ProposalRequest(DeltaModel):
    schema_version: Literal["delta-reference-proposal-request-v1"]
    decision_id: str
    public_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_public_incident_id: str
    public_taxonomy: str
    decision_deadline_s: int = Field(ge=-172_800, le=345_600)
    policy_version: str
    proposal_namespace: Literal["reference-public-proposal-grammar-v1"]


class PhysicalActionProposal(DeltaModel):
    proposal_id: str
    proposal_kind: Literal["physical-action"]
    action: ReferenceActionSpec
    consequence_class: Literal["low", "moderate", "high"]
    reversible: bool
    authority_requirement: str | None
    current_authority_evidence_ids: tuple[str, ...]
    required_claim_ids: tuple[str, ...]
    dependency_ids: tuple[str, ...]
    predictor_request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    predictor_evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class CostAmount(DeltaModel):
    cost_id: str
    quantity_microunits: int = Field(ge=0)
    unit: Literal["reference-decision-cost-microunits"]
    schedule_version: Literal["reference-decision-cost-schedule-v1"]


class EvidenceAcquisitionOffer(DeltaModel):
    proposal_id: str
    proposal_kind: Literal["evidence-acquisition"]
    offer_id: str
    channel_id: str
    target_claim_ids: tuple[str, ...] = Field(min_length=1)
    evidence_schema_version: str
    clear_probability_micros: int = Field(ge=0, le=1_000_000)
    required_clear_probability_micros: int = Field(ge=0, le=1_000_000)
    value_of_information_microunits: int = Field(ge=0)
    physical_cost: CostAmount
    requested_at_s: int = Field(ge=-172_800, le=345_600)
    expected_latency_s: int = Field(ge=1, le=43_200)
    latest_useful_delivery_s: int = Field(ge=-172_800, le=345_600)
    provider_id: str
    provider_available: bool
    authority_present: bool
    minimum_interval_clear: bool
    no_pending_request: bool
    provenance_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class SafeAlternativeProposal(DeltaModel):
    proposal_id: str
    proposal_kind: Literal["safe-alternative"]
    action: ReferenceActionSpec
    consequence_class: Literal["low"]
    reversible: Literal[True]
    authority_requirement: str | None
    current_authority_evidence_ids: tuple[str, ...]
    required_claim_ids: tuple[str, ...]
    dependency_ids: tuple[str, ...]
    predictor_request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    predictor_evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class ProposalEnumerationReceipt(DeltaModel):
    grammar_version: Literal["reference-public-proposal-grammar-v1"]
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    public_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    generated_count: int = Field(ge=0)
    semantic_deduplication_count: int = Field(ge=0)
    complete_for_declared_grammar: bool
    unsupported_cardinality: bool
    receipt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class ProposalSet(DeltaModel):
    schema_version: Literal["delta-reference-proposal-set-v1"]
    decision_id: str
    physical_actions: tuple[PhysicalActionProposal, ...]
    acquisition_offers: tuple[EvidenceAcquisitionOffer, ...]
    safe_alternatives: tuple[SafeAlternativeProposal, ...]
    enumeration_receipt: ProposalEnumerationReceipt
    proposal_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReferenceTraceAssessment(DeltaModel):
    proposal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    commitment_decision: CommitmentDecision
    trace_record_id: str
    trace_record_version: int = Field(ge=1)
    evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    failed_gates: tuple[str, ...]
    missing_items: tuple[str, ...]
    authorization_sufficient_for_action: bool
    assessment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class EligibilityKind(str, Enum):
    ACT_NOW = "act-now"
    ACQUIRE_THEN_REASSESS = "acquire-then-reassess"
    SAFE_ALTERNATIVE = "safe-alternative"
    EXCLUDED = "excluded"


class ProposalEligibility(DeltaModel):
    proposal_id: str
    proposal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    eligibility_kind: EligibilityKind
    eligible: bool
    trace_assessment_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    failed_gates: tuple[str, ...]
    reason: str
    classification_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class EligibilityReceipt(DeltaModel):
    schema_version: Literal["delta-reference-eligibility-receipt-v1"]
    decision_id: str
    public_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    classified_at_s: int = Field(ge=-172_800, le=345_600)
    classifications: tuple[ProposalEligibility, ...]
    eligibility_receipt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class ResponseBundleKind(str, Enum):
    ACT_NOW = "act_now"
    ACQUIRE_THEN_REASSESS = "acquire_then_reassess"
    SAFE_ALTERNATIVE = "safe_alternative"


class ResponseBundle(DeltaModel):
    schema_version: Literal["delta-reference-response-bundle-v1"]
    decision_id: str
    bundle_id: str
    kind: ResponseBundleKind
    proposal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    classification_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    public_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    action: ReferenceActionSpec | None
    acquisition: EvidenceAcquisitionOffer | None
    deadline_s: int = Field(ge=-172_800, le=345_600)
    consequence_class: Literal["low", "moderate", "high"]
    fallback_disposition: CommitmentDecision
    bundle_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_kind_payload(self) -> ResponseBundle:
        acquisition_kind = self.kind == ResponseBundleKind.ACQUIRE_THEN_REASSESS
        if acquisition_kind != (self.acquisition is not None):
            raise ValueError("Reference acquisition bundle payload is inconsistent")
        if acquisition_kind == (self.action is not None):
            raise ValueError("Reference response bundle must contain exactly one payload")
        if self.fallback_disposition == CommitmentDecision.CLEAR:
            raise ValueError("Reference fallback disposition cannot itself authorize action")
        return self


class ResponseBundleCatalog(DeltaModel):
    schema_version: Literal["delta-reference-response-bundle-catalog-v1"]
    decision_id: str
    bundles: tuple[ResponseBundle, ...]
    excluded_classification_digests: tuple[str, ...]
    proposal_enumeration_receipt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    eligibility_receipt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    complete_for_declared_grammar: bool
    trace_prefix_digest: str = Field(pattern=r"^(GENESIS|[0-9a-f]{64})$")
    catalog_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class BaseSelectionRequest(DeltaModel):
    catalog_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    public_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    trace_prefix_digest: str = Field(pattern=r"^(GENESIS|[0-9a-f]{64})$")
    at_s: int = Field(ge=-172_800, le=345_600)


class BaseSelectionReceipt(DeltaModel):
    schema_version: Literal["delta-reference-base-selection-v1"]
    selector_id: Literal["reference-base-selector-v1"]
    catalog_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    public_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    trace_prefix_digest: str = Field(pattern=r"^(GENESIS|[0-9a-f]{64})$")
    selected_bundle_id: str | None
    fallback_disposition: CommitmentDecision | None
    ordered_values: tuple[tuple[str, int], ...]
    tie_rule: Literal["highest-fixed-base-value-then-canonical-bundle-id"]
    simulated_compute_latency_s: int = Field(ge=0, le=60)
    reason: str
    selection_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class DecisionCostDelta(DeltaModel):
    schema_version: Literal["delta-reference-decision-cost-v1"]
    physical_acquisition_costs: tuple[CostAmount, ...]
    predictor_inference_count: int = Field(ge=0)
    planning_transition_count: int = Field(ge=0)
    primitive_operation_count: int = Field(ge=0)
    bytes_read: int = Field(ge=0)
    bytes_written: int = Field(ge=0)
    decision_latency_s: int = Field(ge=0)
    acquisition_latency_s: int = Field(ge=0)
    service_delay_s: int = Field(ge=0)
    compensation_costs: tuple[CostAmount, ...]
    consistency_violation_units: int = Field(ge=0)
    unserved_service_units: int = Field(ge=0)
    receipt_ids: tuple[str, ...]
    cost_delta_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class PublicModelState(DeltaModel):
    schema_version: Literal["delta-reference-public-model-state-v1"]
    source_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    at_s: int = Field(ge=-172_800, le=345_600)
    fact_values: tuple[tuple[str, str], ...]
    state_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class CounterfactualStepRequest(DeltaModel):
    state_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    bundle_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    horizon_increment_s: int = Field(ge=1, le=3_600)
    maximum_primitive_operations: int = Field(ge=1, le=10_000)
    model_version: Literal["reference-public-one-step-model-v1"]


class CounterfactualStepResult(DeltaModel):
    schema_version: Literal["delta-reference-counterfactual-step-v1"]
    semantic_role: Literal["simulation_only"]
    source_state_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    bundle_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    predicted_at_s: int = Field(ge=-172_800, le=349_200)
    predicted_fact_values: tuple[tuple[str, str], ...]
    success_probability_micros: int = Field(ge=0, le=1_000_000)
    censor_status: Literal["within-horizon", "scenario-censored"]
    assumptions: tuple[str, ...]
    primitive_operations: int = Field(ge=1, le=10_000)
    result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
