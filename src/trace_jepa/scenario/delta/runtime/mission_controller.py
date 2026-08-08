"""TRACE-backed mission execution for WF-DFLD-01-SMALL."""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from trace_jepa.contracts import (
    ActionInstance,
    Claim,
    ClaimLayer,
    CommitmentDecision,
    EvaluationResult,
    TraceRecord,
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
from trace_jepa.scenario.delta.domain import CallRecord, GeneratedScenario, ResourceUnit
from trace_jepa.scenario.delta.reconciliation import (
    EvidenceGraphReconciler,
    baseline_v7_visible_relationship,
)
from trace_jepa.scenario.delta.reconciliation.evaluation import evaluate_reconciliation
from trace_jepa.scenario.delta.reconciliation.selection import (
    CANONICAL_RECONCILIATION_ALGORITHM,
)

from .capacity import evaluate_capacity_windows
from .models import DeltaDecisionEvent, DeltaResourceOutcome, DeltaRunResult
from .predictor_context import PredictorEvidenceBuilder
from .routing import ScenarioIndex

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


@dataclass(frozen=True)
class MissionServices:
    runtime: TraceRuntime
    repository: TraceRepository
    commitment_log: CommitmentLog


@dataclass(frozen=True)
class CallPlan:
    call: CallRecord
    controller_time_s: int
    cluster_id: str
    evidence_basis: tuple[str, ...]
    action_name: str
    capability: str
    action: ActionInstance
    candidate: tuple[ResourceUnit, int] | None


@dataclass(frozen=True)
class AssessedCall:
    plan: CallPlan
    evidence: WorldModelEvidence
    request: PredictorRequest
    consumed_record: TraceRecord
    evaluation: EvaluationResult


@dataclass(frozen=True)
class OperationalDecision:
    event_type: str
    reason: str
    resource_id: str = ""
    commitment_id: str | None = None
    completion_s: int | None = None
    observed_s: int | None = None
    outcome_status: str | None = None


class DeltaMissionRunner:
    """Execute controller-visible calls through TRACE and compatible resources."""

    def __init__(
        self,
        scenario: GeneratedScenario,
        predictor: ActionPrefixPredictor,
        policy_path: Path,
        *,
        runtime_root: Path | None = None,
        visual_features: dict[str, PredictorVisualFeatureRef] | None = None,
    ) -> None:
        self.scenario = scenario
        self.predictor = predictor
        self.runtime_root = runtime_root
        self.visual_features = visual_features or {}
        self.provenance = predictor.provenance()
        self.policy = self._policy(policy_path)
        self.decisions: list[DeltaDecisionEvent] = []
        self.evidence_items: list[WorldModelEvidence] = []
        self.predictor_requests: list[PredictorRequest] = []
        self.outcomes: list[DeltaResourceOutcome] = []
        self.busy_until = {
            unit.resource_id: unit.available_from_s for unit in scenario.resources.units
        }
        self.index = ScenarioIndex.build(scenario)
        self.evidence_builder = PredictorEvidenceBuilder(
            scenario,
            predictor,
            self.busy_until,
            self.index,
        )
        self.reconciler = (
            EvidenceGraphReconciler(CANONICAL_RECONCILIATION_ALGORITHM)
            if scenario.config.generator_version == "delta-small-generator-v8"
            else None
        )
        self.earlier_calls: list[CallRecord] = []
        self.cluster_by_call: dict[str, str] = {}
        self.delivery_by_call = self._delivery_times()

    def _policy(self, policy_path: Path) -> PolicyEngine:
        qualified = (
            self.provenance.qualified_action_types
            if self.provenance.adequacy_status.value == "qualified"
            else ()
        )
        guard = RevalidationGuard.bootstrap(
            predictor_version=self.provenance.predictor_version,
            calibration_version=self.provenance.calibration_version,
            model_hash=self.provenance.model_hash,
            calibration_hash=self.provenance.calibration_hash,
            qualified_families=qualified,
        )
        config = PolicyConfig.from_yaml(policy_path)
        if not config.enable_revalidation_guard:
            raise ValueError("Delta Small requires enable_revalidation_guard=true")
        return PolicyEngine(config, revalidation=guard)

    def _delivery_times(self) -> dict[str, int]:
        calls = self.scenario.observations.calls
        deliveries = (
            {
                item.call_id: item.available_to_controller_s
                for item in self.scenario.coordination.deliveries
            }
            if self.scenario.coordination is not None
            else {item.call_id: item.received_s for item in calls}
        )
        missing = {item.call_id for item in calls} - set(deliveries)
        if missing:
            raise ValueError(f"coordination deliveries are missing calls: {sorted(missing)}")
        return deliveries

    def _services(self, root: Path) -> MissionServices:
        repository = TraceRepository(root / "trace_records.jsonl")
        commitment_log = CommitmentLog(root / "commitments.jsonl")
        runtime = TraceRuntime(
            repository=repository,
            ledger=EvidenceLedger(root / "evidence"),
            commitments=commitment_log,
            policy=self.policy,
        )
        return MissionServices(runtime, repository, commitment_log)

    def _relationship(
        self, call: CallRecord, controller_time_s: int
    ) -> tuple[str, tuple[str, ...]]:
        if self.reconciler is not None:
            step = self.reconciler.process(call, controller_time_s)
            return step.belief_cluster_id, step.visible_evidence_basis
        cluster_id, evidence_basis = baseline_v7_visible_relationship(
            call, self.earlier_calls, self.cluster_by_call
        )
        self.cluster_by_call[call.call_id] = cluster_id
        self.earlier_calls.append(call)
        return cluster_id, evidence_basis

    def _plan(self, call: CallRecord) -> CallPlan:
        controller_time_s = self.delivery_by_call[call.call_id]
        cluster_id, evidence_basis = self._relationship(call, controller_time_s)
        action_name, capability = CALL_ACTION[call.reported.call_type]
        route_id = self.index.route_for_call(call)
        candidate = self.index.candidate_resource(
            capability,
            controller_time_s,
            route_id,
            self.busy_until,
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
        return CallPlan(
            call,
            controller_time_s,
            cluster_id,
            evidence_basis,
            action_name,
            capability,
            action,
            candidate,
        )

    def _assess(self, plan: CallPlan, runtime: TraceRuntime) -> AssessedCall:
        timestamp = self.scenario.config.timeline.epoch_utc + timedelta(
            seconds=plan.controller_time_s
        )
        evidence, request = self.evidence_builder.build(
            plan.call,
            plan.action,
            plan.controller_time_s,
            self.visual_features.get(plan.call.call_id),
        )
        claim = Claim(
            claim_id=f"claim-{plan.call.call_id}",
            layer=ClaimLayer.PREDICTIVE,
            text="Registered compatible capacity can reach the reported location.",
            grounding={
                "call_id": plan.call.call_id,
                "action_type": plan.action_name,
            },
            confidence=0.82,
            confidence_semantics="predictor action-prefix probability support",
            created_at=timestamp,
        )
        record, evaluation = runtime.assess(
            claim=claim,
            evidence=evidence,
            action_name=plan.action_name,
            reversible=False,
            authority_present=True,
            repair_hint="Obtain current route evidence or qualified calibration.",
            metadata={
                "call_id": plan.call.call_id,
                "belief_cluster_id": plan.cluster_id,
                "visible_evidence_basis": plan.evidence_basis,
            },
            lineage_key=f"delta-small-belief:{plan.cluster_id}",
            trigger_event_id=plan.call.call_id,
            created_at=timestamp,
        )
        consumed = runtime.consume(
            record,
            evaluation,
            consumer="delta-mission-controller",
            consumer_action_id=f"consumer-{plan.call.call_id}",
            created_at=timestamp,
        )
        self.evidence_items.append(evidence)
        self.predictor_requests.append(request)
        return AssessedCall(plan, evidence, request, consumed, evaluation)

    def _append_repair(self, assessed: AssessedCall) -> None:
        plan = assessed.plan
        self.decisions.append(
            DeltaDecisionEvent(
                sequence=len(self.decisions) + 1,
                call_id=plan.call.call_id,
                simulation_time_s=plan.controller_time_s,
                event_type="repair",
                resource_id="",
                reason="controller revised a belief using controller-visible evidence",
                visible_evidence_basis=plan.evidence_basis,
                belief_cluster_id=plan.cluster_id,
                trace_decision=assessed.evaluation.decision.value,
                trace_record_id=assessed.consumed_record.record_id,
                trace_record_version=assessed.consumed_record.record_version,
            )
        )

    def _allocate(self, assessed: AssessedCall, runtime: TraceRuntime) -> None:
        plan = assessed.plan
        if plan.candidate is None:
            raise RuntimeError("allocation requires a resource candidate")
        unit, travel_s = plan.candidate
        completion_s = plan.controller_time_s + travel_s + unit.service_duration_s
        self.busy_until[unit.resource_id] = completion_s
        timestamp = self.scenario.config.timeline.epoch_utc + timedelta(
            seconds=plan.controller_time_s
        )
        commitment = runtime.commit(
            record=assessed.consumed_record,
            action=plan.action,
            commitment_id=f"commitment-{plan.call.call_id}",
            created_at=timestamp,
        )
        observed_s = (
            completion_s if completion_s <= self.scenario.config.timeline.duration_s else None
        )
        status = (
            "completed_within_window" if observed_s is not None else "active_at_scenario_censoring"
        )
        self.outcomes.append(
            DeltaResourceOutcome(
                outcome_id=f"outcome-{plan.call.call_id}",
                call_id=plan.call.call_id,
                resource_id=unit.resource_id,
                status=status,
                scheduled_completion_s=completion_s,
                observed_completion_s=observed_s,
                censoring_s=self.scenario.config.timeline.duration_s,
                authorizing_commitment_id=commitment.commitment_id,
                authorizing_trace_record_id=commitment.authorizing_record_id,
                authorizing_trace_record_version=commitment.authorizing_record_version,
            )
        )
        self._append_operational_decision(
            assessed,
            OperationalDecision(
                event_type="allocation",
                reason="TRACE cleared and compatible reachable capacity was assigned",
                resource_id=unit.resource_id,
                commitment_id=commitment.commitment_id,
                completion_s=completion_s,
                observed_s=observed_s,
                outcome_status=status,
            ),
        )

    def _append_operational_decision(
        self,
        assessed: AssessedCall,
        decision: OperationalDecision,
    ) -> None:
        plan = assessed.plan
        self.decisions.append(
            DeltaDecisionEvent(
                sequence=len(self.decisions) + 1,
                call_id=plan.call.call_id,
                simulation_time_s=plan.controller_time_s,
                event_type=decision.event_type,
                resource_id=decision.resource_id,
                reason=decision.reason,
                belief_cluster_id=plan.cluster_id,
                trace_decision=assessed.evaluation.decision.value,
                trace_record_id=assessed.consumed_record.record_id,
                trace_record_version=assessed.consumed_record.record_version,
                commitment_id=decision.commitment_id,
                scheduled_completion_s=decision.completion_s,
                observed_completion_s=decision.observed_s,
                censoring_s=(
                    self.scenario.config.timeline.duration_s
                    if decision.completion_s is not None
                    else None
                ),
                outcome_status=decision.outcome_status,
            )
        )

    def _process(self, call: CallRecord, runtime: TraceRuntime) -> None:
        assessed = self._assess(self._plan(call), runtime)
        if assessed.plan.evidence_basis:
            self._append_repair(assessed)
        elif (
            assessed.evaluation.decision == CommitmentDecision.CLEAR
            and assessed.plan.candidate is not None
        ):
            self._allocate(assessed, runtime)
        else:
            reason = (
                "TRACE held the unqualified or unsupported action"
                if assessed.evaluation.decision != CommitmentDecision.CLEAR
                else "no compatible mobilized reachable uncommitted capacity"
            )
            self._append_operational_decision(
                assessed,
                OperationalDecision(event_type="refusal", reason=reason),
            )

    def _result(self, services: MissionServices) -> DeltaRunResult:
        windows = evaluate_capacity_windows(self.scenario, self.decisions)
        strict = [
            item.strict_concurrent_load_ratio_milli
            for item in windows
            if item.strict_concurrent_load_ratio_milli is not None
        ]
        uncapped = [
            item.uncapped_compatible_load_ratio_milli
            for item in windows
            if item.uncapped_compatible_load_ratio_milli is not None
        ]
        historical = [
            item.registered_normalized_coverable_load_index_milli
            for item in windows
            if item.registered_normalized_coverable_load_index_milli is not None
        ]
        residual = [
            item.residual_strict_pressure_ratio_milli
            for item in windows
            if item.residual_strict_pressure_ratio_milli is not None
        ]
        return DeltaRunResult(
            schema_version="delta-small-run-result-v5",
            scenario_id=self.scenario.config.scenario_id,
            predictor_version=self.provenance.predictor_version,
            calibration_version=self.provenance.calibration_version,
            decisions=self.decisions,
            demand_windows=windows,
            trace_records=services.repository.all(),
            evidence=self.evidence_items,
            predictor_requests=self.predictor_requests,
            commitments=services.commitment_log.all(),
            outcomes=self.outcomes,
            reconciliation_artifact=(
                self.reconciler.artifact() if self.reconciler is not None else None
            ),
            reconciliation_evaluation=evaluate_reconciliation(self.scenario, self.decisions),
            trace_chain_verified=services.repository.verify_chain(),
            peak_finite_strict_concurrent_load_ratio_milli=max(strict, default=0),
            strict_unserviceable_windows=sum(item.strict_unserviceable for item in windows),
            peak_finite_uncapped_compatible_load_ratio_milli=max(uncapped, default=0),
            uncapped_unserviceable_windows=sum(
                item.active_demand_units > 0
                and item.uncapped_compatible_service_unit_capacity_units == 0
                for item in windows
            ),
            peak_finite_registered_normalized_coverable_load_index_milli=max(historical, default=0),
            historical_capped_unserviceable_windows=sum(
                item.active_demand_units > 0
                and item.historical_capped_coverable_capacity_units == 0
                for item in windows
            ),
            peak_finite_residual_strict_pressure_ratio_milli=max(residual, default=0),
            residual_strict_unserviceable_windows=sum(
                item.residual_strict_unserviceable for item in windows
            ),
            allocated=sum(item.event_type == "allocation" for item in self.decisions),
            refused=sum(item.event_type == "refusal" for item in self.decisions),
            repaired=sum(item.event_type == "repair" for item in self.decisions),
        )

    def run(self) -> DeltaRunResult:
        ordered_calls = sorted(
            self.scenario.observations.calls,
            key=lambda call: (
                self.delivery_by_call[call.call_id],
                call.received_s,
                call.call_id,
            ),
        )
        with _runtime_root(self.runtime_root) as root:
            services = self._services(root)
            for call in ordered_calls:
                self._process(call, services.runtime)
            return self._result(services)


def run_delta_small(
    scenario: GeneratedScenario,
    predictor: ActionPrefixPredictor,
    policy_path: Path,
    *,
    runtime_root: Path | None = None,
    visual_features: dict[str, PredictorVisualFeatureRef] | None = None,
) -> DeltaRunResult:
    """Stable public facade for the modular mission runner."""

    return DeltaMissionRunner(
        scenario,
        predictor,
        policy_path,
        runtime_root=runtime_root,
        visual_features=visual_features,
    ).run()
