from __future__ import annotations

import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

from trace_jepa.contracts import (
    ActionInstance,
    Claim,
    ClaimLayer,
    CommitmentDecision,
    WorldModelEvidence,
)
from trace_jepa.experimental.revalidation import RevalidationGuard
from trace_jepa.predictor import (
    ActionPrefixPredictor,
    PredictorRequest,
    PredictorVisualFeatureRef,
)
from trace_jepa.runtime import (
    CommitmentLog,
    EvidenceLedger,
    PolicyConfig,
    PolicyEngine,
    TraceRepository,
    TraceRuntime,
)
from trace_jepa.scenario.delta.domain import (
    CallRecord,
    GeneratedScenario,
)
from trace_jepa.scenario.delta.evaluation import (
    evaluate_reconciliation,
)
from trace_jepa.scenario.delta.reconciliation import (
    EvidenceGraphReconciler,
    baseline_v7_visible_relationship,
)
from trace_jepa.scenario.delta.reconciliation_selection import (
    CANONICAL_RECONCILIATION_ALGORITHM,
)
from trace_jepa.scenario.delta.runtime.capacity import evaluate_capacity_windows
from trace_jepa.scenario.delta.runtime.models import (
    DeltaDecisionEvent,
    DeltaResourceOutcome,
    DeltaRunResult,
)
from trace_jepa.scenario.delta.runtime.predictor_context import PredictorEvidenceBuilder
from trace_jepa.scenario.delta.runtime.routing import ScenarioIndex

CALL_ACTION = {
    "C-STR": ("dispatch_rescue_boat", "water_rescue"),
    "C-VEH": ("deploy_ground_team", "road_rescue"),
    "C-LEV": ("inspect_levee", "levee_inspection"),
    "C-MED": ("deploy_ground_team", "medical_first_response"),
    "C-WEL": ("perform_welfare_check", "welfare_check"),
    "C-MIS": ("perform_welfare_check", "missing_person_search"),
}


@contextmanager
def _runtime_root(path: Path | None) -> Iterator[Path]:
    if path is not None:
        path.mkdir(parents=True, exist_ok=True)
        yield path
        return
    with tempfile.TemporaryDirectory(prefix="trace-delta-runtime-") as temporary:
        yield Path(temporary)


def run_delta_small(
    scenario: GeneratedScenario,
    predictor: ActionPrefixPredictor,
    policy_path: Path,
    *,
    runtime_root: Path | None = None,
    visual_features: dict[str, PredictorVisualFeatureRef] | None = None,
) -> DeltaRunResult:
    provenance = predictor.provenance()
    qualified_families = (
        provenance.qualified_action_types if provenance.adequacy_status.value == "qualified" else ()
    )
    guard = RevalidationGuard.bootstrap(
        predictor_version=provenance.predictor_version,
        calibration_version=provenance.calibration_version,
        model_hash=provenance.model_hash,
        calibration_hash=provenance.calibration_hash,
        qualified_families=qualified_families,
    )
    policy_config = PolicyConfig.from_yaml(policy_path)
    if not policy_config.enable_revalidation_guard:
        raise ValueError("Delta Small requires enable_revalidation_guard=true")
    policy = PolicyEngine(policy_config, revalidation=guard)
    decisions: list[DeltaDecisionEvent] = []
    evidence_items: list[WorldModelEvidence] = []
    predictor_requests: list[PredictorRequest] = []
    outcomes: list[DeltaResourceOutcome] = []
    busy_until = {unit.resource_id: unit.available_from_s for unit in scenario.resources.units}
    scenario_index = ScenarioIndex.build(scenario)
    evidence_builder = PredictorEvidenceBuilder(
        scenario,
        predictor,
        busy_until,
        scenario_index,
    )
    reconciler = (
        EvidenceGraphReconciler(CANONICAL_RECONCILIATION_ALGORITHM)
        if scenario.config.generator_version == "delta-small-generator-v8"
        else None
    )
    earlier_calls: list[CallRecord] = []
    cluster_by_call: dict[str, str] = {}
    delivery_by_call = (
        {item.call_id: item.available_to_controller_s for item in scenario.coordination.deliveries}
        if scenario.coordination is not None
        else {item.call_id: item.received_s for item in scenario.observations.calls}
    )
    active_call_ids = {item.call_id for item in scenario.observations.calls}
    missing_deliveries = active_call_ids - set(delivery_by_call)
    if missing_deliveries:
        raise ValueError(f"coordination deliveries are missing calls: {sorted(missing_deliveries)}")
    controller_calls = sorted(
        scenario.observations.calls,
        key=lambda item: (delivery_by_call[item.call_id], item.received_s, item.call_id),
    )

    with _runtime_root(runtime_root) as store_root:
        repository = TraceRepository(store_root / "trace_records.jsonl")
        ledger = EvidenceLedger(store_root / "evidence")
        commitment_log = CommitmentLog(store_root / "commitments.jsonl")
        runtime = TraceRuntime(
            repository=repository,
            ledger=ledger,
            commitments=commitment_log,
            policy=policy,
        )
        for call in controller_calls:
            controller_time_s = delivery_by_call[call.call_id]
            controller_timestamp = scenario.config.timeline.epoch_utc + timedelta(
                seconds=controller_time_s
            )
            if reconciler is not None:
                reconciliation_step = reconciler.process(call, controller_time_s)
                cluster_id = reconciliation_step.belief_cluster_id
                evidence_basis = reconciliation_step.visible_evidence_basis
            else:
                cluster_id, evidence_basis = baseline_v7_visible_relationship(
                    call, earlier_calls, cluster_by_call
                )
                cluster_by_call[call.call_id] = cluster_id
                earlier_calls.append(call)
            action_name, capability = CALL_ACTION[call.reported.call_type]
            route_id = scenario_index.route_for_call(call)
            candidate = scenario_index.candidate_resource(
                capability, controller_time_s, route_id, busy_until
            )
            actor_id = candidate[0].resource_id if candidate else "unassigned-local-resource"
            action = ActionInstance(
                action_id=f"action-{call.call_id}",
                action_type=action_name,
                actor_id=actor_id,
                origin="FAC-FIRE-01",
                destination="reported-location",
                route_id=route_id,
                parameters={"call_id": call.call_id, "required_capability": capability},
            )
            evidence, predictor_request = evidence_builder.build(
                call,
                action,
                controller_time_s,
                (visual_features or {}).get(call.call_id),
            )
            evidence_items.append(evidence)
            predictor_requests.append(predictor_request)
            claim = Claim(
                claim_id=f"claim-{call.call_id}",
                layer=ClaimLayer.PREDICTIVE,
                text="Registered compatible capacity can reach the reported location.",
                grounding={"call_id": call.call_id, "action_type": action_name},
                confidence=0.82,
                confidence_semantics="predictor action-prefix probability support",
                created_at=controller_timestamp,
            )
            record, evaluation = runtime.assess(
                claim=claim,
                evidence=evidence,
                action_name=action_name,
                reversible=False,
                authority_present=True,
                repair_hint="Obtain current route evidence or qualified calibration.",
                metadata={
                    "call_id": call.call_id,
                    "belief_cluster_id": cluster_id,
                    "visible_evidence_basis": evidence_basis,
                },
                lineage_key=f"delta-small-belief:{cluster_id}",
                trigger_event_id=call.call_id,
                created_at=controller_timestamp,
            )
            consumed = runtime.consume(
                record,
                evaluation,
                consumer="delta-mission-controller",
                consumer_action_id=f"consumer-{call.call_id}",
                created_at=controller_timestamp,
            )
            if evidence_basis:
                decisions.append(
                    DeltaDecisionEvent(
                        sequence=len(decisions) + 1,
                        call_id=call.call_id,
                        simulation_time_s=controller_time_s,
                        event_type="repair",
                        resource_id="",
                        reason="controller revised a belief using controller-visible evidence",
                        visible_evidence_basis=evidence_basis,
                        belief_cluster_id=cluster_id,
                        trace_decision=evaluation.decision.value,
                        trace_record_id=consumed.record_id,
                        trace_record_version=consumed.record_version,
                    )
                )
                continue
            if evaluation.decision == CommitmentDecision.CLEAR and candidate is not None:
                unit, travel_s = candidate
                scheduled_completion_s = controller_time_s + travel_s + unit.service_duration_s
                busy_until[unit.resource_id] = scheduled_completion_s
                commitment = runtime.commit(
                    record=consumed,
                    action=action,
                    commitment_id=f"commitment-{call.call_id}",
                    created_at=controller_timestamp,
                )
                event_type = "allocation"
                reason = "TRACE cleared and compatible reachable capacity was assigned"
                resource_id = unit.resource_id
                observed_completion_s = (
                    scheduled_completion_s
                    if scheduled_completion_s <= scenario.config.timeline.duration_s
                    else None
                )
                outcome_status = (
                    "completed_within_window"
                    if observed_completion_s is not None
                    else "active_at_scenario_censoring"
                )
                outcomes.append(
                    DeltaResourceOutcome(
                        outcome_id=f"outcome-{call.call_id}",
                        call_id=call.call_id,
                        resource_id=unit.resource_id,
                        status=outcome_status,
                        scheduled_completion_s=scheduled_completion_s,
                        observed_completion_s=observed_completion_s,
                        censoring_s=scenario.config.timeline.duration_s,
                        authorizing_commitment_id=commitment.commitment_id,
                        authorizing_trace_record_id=commitment.authorizing_record_id,
                        authorizing_trace_record_version=(commitment.authorizing_record_version),
                    )
                )
                commitment_id = commitment.commitment_id
            else:
                event_type = "refusal"
                resource_id = ""
                scheduled_completion_s = None
                observed_completion_s = None
                outcome_status = None
                commitment_id = None
                reason = (
                    "TRACE held the unqualified or unsupported action"
                    if evaluation.decision != CommitmentDecision.CLEAR
                    else "no compatible mobilized reachable uncommitted capacity"
                )
            decisions.append(
                DeltaDecisionEvent(
                    sequence=len(decisions) + 1,
                    call_id=call.call_id,
                    simulation_time_s=controller_time_s,
                    event_type=event_type,
                    resource_id=resource_id,
                    reason=reason,
                    belief_cluster_id=cluster_id,
                    trace_decision=evaluation.decision.value,
                    trace_record_id=consumed.record_id,
                    trace_record_version=consumed.record_version,
                    commitment_id=commitment_id,
                    scheduled_completion_s=scheduled_completion_s,
                    observed_completion_s=observed_completion_s,
                    censoring_s=(
                        scenario.config.timeline.duration_s
                        if scheduled_completion_s is not None
                        else None
                    ),
                    outcome_status=outcome_status,
                )
            )
        trace_records = repository.all()
        commitments = commitment_log.all()
        chain_verified = repository.verify_chain()

    windows = evaluate_capacity_windows(scenario, decisions)
    strict_ratios = [
        item.strict_concurrent_load_ratio_milli
        for item in windows
        if item.strict_concurrent_load_ratio_milli is not None
    ]
    uncapped_ratios = [
        item.uncapped_compatible_load_ratio_milli
        for item in windows
        if item.uncapped_compatible_load_ratio_milli is not None
    ]
    historical_ratios = [
        item.registered_normalized_coverable_load_index_milli
        for item in windows
        if item.registered_normalized_coverable_load_index_milli is not None
    ]
    residual_strict_ratios = [
        item.residual_strict_pressure_ratio_milli
        for item in windows
        if item.residual_strict_pressure_ratio_milli is not None
    ]
    reconciliation = evaluate_reconciliation(scenario, decisions)
    return DeltaRunResult(
        schema_version="delta-small-run-result-v5",
        scenario_id=scenario.config.scenario_id,
        predictor_version=provenance.predictor_version,
        calibration_version=provenance.calibration_version,
        decisions=decisions,
        demand_windows=windows,
        trace_records=trace_records,
        evidence=evidence_items,
        predictor_requests=predictor_requests,
        commitments=commitments,
        outcomes=outcomes,
        reconciliation_artifact=reconciler.artifact() if reconciler is not None else None,
        reconciliation_evaluation=reconciliation,
        trace_chain_verified=chain_verified,
        peak_finite_strict_concurrent_load_ratio_milli=max(strict_ratios, default=0),
        strict_unserviceable_windows=sum(item.strict_unserviceable for item in windows),
        peak_finite_uncapped_compatible_load_ratio_milli=max(uncapped_ratios, default=0),
        uncapped_unserviceable_windows=sum(
            item.active_demand_units > 0
            and item.uncapped_compatible_service_unit_capacity_units == 0
            for item in windows
        ),
        peak_finite_registered_normalized_coverable_load_index_milli=max(
            historical_ratios, default=0
        ),
        historical_capped_unserviceable_windows=sum(
            item.active_demand_units > 0 and item.historical_capped_coverable_capacity_units == 0
            for item in windows
        ),
        peak_finite_residual_strict_pressure_ratio_milli=max(residual_strict_ratios, default=0),
        residual_strict_unserviceable_windows=sum(
            item.residual_strict_unserviceable for item in windows
        ),
        allocated=sum(event.event_type == "allocation" for event in decisions),
        refused=sum(event.event_type == "refusal" for event in decisions),
        repaired=sum(event.event_type == "repair" for event in decisions),
    )
