from __future__ import annotations

import math
import tempfile
from collections import defaultdict
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

from pydantic import Field, model_validator

from trace_jepa.contracts import (
    ActionInstance,
    Claim,
    ClaimLayer,
    Commitment,
    CommitmentDecision,
    PlanCandidate,
    TraceRecord,
    WorldModelEvidence,
)
from trace_jepa.experimental import build_experimental_profile
from trace_jepa.experimental.revalidation import RevalidationGuard
from trace_jepa.predictor import (
    ActionPrefixPredictor,
    PredictorContext,
    PredictorObservation,
    PredictorPriorProfile,
    PredictorRequest,
    PredictorRouteObservation,
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
from trace_jepa.scenario.delta.artifacts import canonical_json_bytes, sha256_bytes
from trace_jepa.scenario.delta.models import (
    CallRecord,
    CrossingState,
    DeltaModel,
    GeneratedScenario,
    IncidentTruth,
    ResourceUnit,
    WeatherSample,
)

CALL_ACTION = {
    "C-STR": ("dispatch_rescue_boat", "water_rescue"),
    "C-VEH": ("deploy_ground_team", "road_rescue"),
    "C-LEV": ("inspect_levee", "levee_inspection"),
    "C-MED": ("deploy_ground_team", "medical_first_response"),
    "C-WEL": ("perform_welfare_check", "welfare_check"),
    "C-MIS": ("perform_welfare_check", "missing_person_search"),
}


class DeltaDecisionEvent(DeltaModel):
    sequence: int = Field(gt=0)
    call_id: str
    simulation_time_s: int = Field(ge=0)
    event_type: str
    resource_id: str
    reason: str
    visible_evidence_basis: tuple[str, ...] = ()
    belief_cluster_id: str
    trace_decision: str
    trace_record_id: str
    trace_record_version: int = Field(gt=0)
    commitment_id: str | None = None
    service_complete_s: int | None = Field(default=None, ge=0)


class DemandWindow(DeltaModel):
    window_start_s: int = Field(ge=0)
    active_demand_service_units: int = Field(ge=0)
    gross_compatible_capacity_units: int = Field(ge=0)
    gross_load_ratio_milli: int | None = Field(default=None, ge=0)
    gross_unserviceable: bool
    commitment_covered_demand_units: int = Field(ge=0)
    residual_unassigned_demand_units: int = Field(ge=0)
    free_compatible_capacity_units: int = Field(ge=0)
    residual_pressure_ratio_milli: int | None = Field(default=None, ge=0)
    residual_unserviceable: bool

    @model_validator(mode="after")
    def validate_capacity_accounting(self) -> DemandWindow:
        if (
            self.commitment_covered_demand_units + self.residual_unassigned_demand_units
            != self.active_demand_service_units
        ):
            raise ValueError("covered plus residual demand must equal active demand")
        if self.gross_unserviceable != (
            self.active_demand_service_units > 0 and self.gross_compatible_capacity_units == 0
        ):
            raise ValueError("gross unserviceable status disagrees with demand and capacity")
        if self.residual_unserviceable != (
            self.residual_unassigned_demand_units > 0 and self.free_compatible_capacity_units == 0
        ):
            raise ValueError("residual unserviceable status disagrees with demand and capacity")
        return self


class DeltaResourceOutcome(DeltaModel):
    outcome_id: str
    call_id: str
    resource_id: str
    status: str
    completed_s: int = Field(ge=0)
    authorizing_commitment_id: str


class DeltaRunResult(DeltaModel):
    schema_version: str
    scenario_id: str
    predictor_version: str
    calibration_version: str
    decisions: list[DeltaDecisionEvent]
    demand_windows: list[DemandWindow]
    trace_records: list[TraceRecord]
    evidence: list[WorldModelEvidence]
    commitments: list[Commitment]
    outcomes: list[DeltaResourceOutcome]
    trace_chain_verified: bool
    peak_gross_load_ratio_milli: int = Field(ge=0)
    gross_unserviceable_windows: int = Field(ge=0)
    peak_finite_residual_pressure_ratio_milli: int = Field(ge=0)
    residual_unserviceable_windows: int = Field(ge=0)
    allocated: int = Field(ge=0)
    refused: int = Field(ge=0)
    repaired: int = Field(ge=0)

    @property
    def peak_demand_capacity_ratio_milli(self) -> int:
        """Deprecated source-compatibility alias; v2 means gross scenario load."""
        return self.peak_gross_load_ratio_milli

    @property
    def unserviceable_windows(self) -> int:
        """Deprecated source-compatibility alias for residual pressure."""
        return self.residual_unserviceable_windows


def _nearest_tick(scenario: GeneratedScenario, simulation_time_s: int) -> int:
    return min(
        scenario.config.timeline.duration_s,
        simulation_time_s // scenario.config.timeline.tick_s * scenario.config.timeline.tick_s,
    )


def _route_for_call(scenario: GeneratedScenario, call: CallRecord) -> str:
    centroids = {island.island_id: island.centroid for island in scenario.geography.islands}
    distance_by_island = {
        island_id: (call.location.easting_mm - coordinate.easting_mm) ** 2
        + (call.location.northing_mm - coordinate.northing_mm) ** 2
        for island_id, coordinate in centroids.items()
    }
    nearest_island = min(distance_by_island, key=distance_by_island.__getitem__)
    return "XNG-03" if nearest_island == "ISL-02" else "XNG-04"


def _crossing_state(
    scenario: GeneratedScenario,
    route_id: str,
    simulation_time_s: int,
) -> CrossingState:
    tick = _nearest_tick(scenario, simulation_time_s)
    return next(
        item
        for item in scenario.crossing_states
        if item.crossing_id == route_id and item.simulation_time_s == tick
    )


def _weather(scenario: GeneratedScenario, simulation_time_s: int) -> WeatherSample:
    tick = _nearest_tick(scenario, simulation_time_s)
    return next(item for item in scenario.weather if item.simulation_time_s == tick)


def _routed_travel_s(
    scenario: GeneratedScenario,
    unit: ResourceUnit,
    simulation_time_s: int,
    route_id: str | None = None,
) -> int | None:
    selected_route = route_id or unit.route_id
    state = _crossing_state(scenario, selected_route, simulation_time_s)
    if state.status != "open":
        return None
    friction = state.travel_time_s / next(
        crossing.nominal_travel_s
        for crossing in scenario.geography.crossings
        if crossing.crossing_id == selected_route
    )
    return round(unit.nominal_travel_time_s * friction)


def _candidate_resource(
    scenario: GeneratedScenario,
    capability: str,
    simulation_time_s: int,
    route_id: str,
    busy_until: dict[str, int],
) -> tuple[ResourceUnit, int] | None:
    for unit in sorted(scenario.resources.units, key=lambda item: item.resource_id):
        if capability not in unit.capabilities:
            continue
        if not unit.is_available or unit.available_from_s > simulation_time_s:
            continue
        if busy_until[unit.resource_id] > simulation_time_s:
            continue
        travel_s = _routed_travel_s(scenario, unit, simulation_time_s, route_id)
        if travel_s is not None:
            return unit, travel_s
    return None


def _visible_relationship(
    call: CallRecord,
    earlier_calls: list[CallRecord],
    cluster_by_call: dict[str, str],
) -> tuple[str, tuple[str, ...]]:
    if call.quality.revision_of_call_id is not None:
        source = call.quality.revision_of_call_id
        return cluster_by_call.get(source, source), ("explicit_report_revision", source)
    for previous in reversed(earlier_calls):
        if call.callback_token == previous.callback_token:
            return cluster_by_call[previous.call_id], (
                "shared_synthetic_callback_token",
                previous.call_id,
            )
    for previous in reversed(earlier_calls):
        if call.received_s - previous.received_s > 600:
            break
        if call.reported.call_type != previous.reported.call_type:
            continue
        distance_m = (
            math.hypot(
                call.location.easting_mm - previous.location.easting_mm,
                call.location.northing_mm - previous.location.northing_mm,
            )
            / 1000.0
        )
        tolerance_m = call.location.precision_m + previous.location.precision_m
        if distance_m <= tolerance_m:
            return cluster_by_call[previous.call_id], (
                "spatiotemporal_taxonomy_similarity",
                previous.call_id,
            )
    return call.call_id, ()


def _prediction_evidence(
    scenario: GeneratedScenario,
    predictor: ActionPrefixPredictor,
    call: CallRecord,
    action: ActionInstance,
    available_units: int,
    visual_feature: PredictorVisualFeatureRef | None = None,
) -> WorldModelEvidence:
    route_id = action.route_id
    if route_id is None:
        raise ValueError("Delta actions require an explicit route")
    route_state = _crossing_state(scenario, route_id, call.received_s)
    weather = _weather(scenario, call.received_s)
    plan = PlanCandidate(
        plan_id=f"plan-{call.call_id}",
        name=f"Respond to {call.call_id}",
        actions=(action,),
        utility=1.0,
        reversible_first_action=False,
        requires_authority=True,
        metadata={"call_type": call.reported.call_type},
    )
    prediction = predictor.predict(
        PredictorRequest(
            plan=plan,
            observation=PredictorObservation(
                routes=[
                    PredictorRouteObservation(
                        route_id=route_id,
                        report=("unknown" if call.quality.call_dropped else route_state.status),
                        nominal_travel_s=float(route_state.travel_time_s),
                        confidence=route_state.confidence_milli / 1000.0,
                        observation_age_s=0.0,
                    )
                ],
                context=PredictorContext(
                    simulation_time_s=call.received_s,
                    rain_milli_inches_per_hour=weather.rain_milli_inches_per_hour,
                    wind_milli_knots=weather.wind_milli_knots,
                    available_resource_units=available_units,
                    prior_profile=PredictorPriorProfile(
                        profile_id=scenario.prior_profile.profile_id,
                        calibration_version=scenario.prior_profile.calibration_version,
                        prior_accuracy_milli=scenario.prior_profile.prior_accuracy_milli,
                    ),
                    visual_feature=visual_feature,
                ),
            ),
        )
    )
    stamp = scenario.config.timeline.epoch_utc + timedelta(seconds=call.received_s)
    provenance = predictor.provenance()
    profile = build_experimental_profile(
        predictor_version=provenance.predictor_version,
        calibration_version=provenance.calibration_version,
        claim_family=action.action_type,
        adequacy_status=provenance.adequacy_status,
        prediction_timestamp=stamp,
        model_hash=provenance.model_hash,
        calibration_hash=provenance.calibration_hash,
        notes=(f"prior_profile={scenario.prior_profile.profile_id}",),
    ).model_copy(update={"profile_id": f"profile-{call.call_id}"})
    return WorldModelEvidence(
        evidence_id=f"evidence-{call.call_id}",
        rollout_id=f"rollout-{call.call_id}",
        encoder_version=provenance.encoder_version or "delta-symbolic-observation-v2",
        fusion_version="delta-small-controller-context-v2",
        predictor_version=provenance.predictor_version,
        semantic_probe_versions=("delta-route-and-resource-probe-v2",),
        training_snapshot=provenance.training_snapshot,
        observation_window_hash=sha256_bytes(canonical_json_bytes(call.model_dump(mode="json"))),
        fleet_state_hash=sha256_bytes(
            canonical_json_bytes(
                {
                    "available_compatible_units": available_units,
                    "resource_schema": scenario.resources.schema_version,
                }
            )
        ),
        candidate_plan_id=plan.plan_id,
        action_schema_version=provenance.action_schema_version,
        rollout_horizon=prediction.rollout_horizon,
        predicted_claims=(
            f"{route_id} and compatible local capacity support the proposed response",
        ),
        uncertainty=prediction.uncertainty,
        model_support=prediction.model_support,
        out_of_distribution_score=prediction.out_of_distribution_score,
        rollout_consistency=1.0 - prediction.uncertainty,
        reachability_evidence={
            "arrival_time_s": prediction.arrival_time_s,
            "hazard_score": prediction.hazard_score,
            "route_status": route_state.status,
            "route_confidence_milli": route_state.confidence_milli,
        },
        calibration_version=provenance.calibration_version,
        assumptions=prediction.assumptions,
        observation_age_s=0.0,
        created_at=stamp,
        experimental_profile=profile,
    )


def evaluate_capacity_windows(
    scenario: GeneratedScenario,
    decisions: list[DeltaDecisionEvent],
) -> list[DemandWindow]:
    """Evaluate intrinsic load and post-controller residual pressure.

    The gross metric is a property of truth plus the registered resource
    schedule. It deliberately ignores commitments. The residual metric is an
    offline evaluation: it uses hidden lineage only after TRACE execution to
    determine which truth demand an authorized commitment covered. No truth
    identifier is emitted in the aggregate window artifact.
    """
    window_s = scenario.config.demand_capacity.window_s
    lineage_by_call = {
        item.call_id: item.truth_incident_id
        for item in scenario.observations.lineage
        if item.truth_incident_id is not None
    }
    allocation_events = [
        event
        for event in decisions
        if event.event_type == "allocation"
        and event.call_id in lineage_by_call
        and event.service_complete_s is not None
    ]
    busy_intervals = [
        (event.resource_id, event.simulation_time_s, event.service_complete_s)
        for event in decisions
        if event.event_type == "allocation" and event.service_complete_s is not None
    ]
    windows: list[DemandWindow] = []
    for start in range(0, scenario.config.timeline.duration_s, window_s):
        active = [
            incident
            for incident in scenario.truth.incidents
            if incident.onset_s <= start < incident.onset_s + incident.service_duration_s
        ]
        active_demand = sum(incident.service_units for incident in active)
        gross_capacity = _maximum_coverable_service_units(scenario, active, start, ())

        covered_ids = {
            lineage_by_call[event.call_id]
            for event in allocation_events
            if event.service_complete_s is not None
            and event.simulation_time_s <= start < event.service_complete_s
        }
        residual_incidents = [
            incident for incident in active if incident.incident_id not in covered_ids
        ]
        commitment_covered = active_demand - sum(
            incident.service_units for incident in residual_incidents
        )
        residual_demand = active_demand - commitment_covered
        free_capacity = _maximum_coverable_service_units(
            scenario,
            residual_incidents,
            start,
            busy_intervals,
        )
        windows.append(
            DemandWindow(
                window_start_s=start,
                active_demand_service_units=active_demand,
                gross_compatible_capacity_units=gross_capacity,
                gross_load_ratio_milli=(
                    0
                    if active_demand == 0
                    else round(1000 * active_demand / gross_capacity)
                    if gross_capacity
                    else None
                ),
                gross_unserviceable=active_demand > 0 and gross_capacity == 0,
                commitment_covered_demand_units=commitment_covered,
                residual_unassigned_demand_units=residual_demand,
                free_compatible_capacity_units=free_capacity,
                residual_pressure_ratio_milli=(
                    0
                    if residual_demand == 0
                    else round(1000 * residual_demand / free_capacity)
                    if free_capacity
                    else None
                ),
                residual_unserviceable=residual_demand > 0 and free_capacity == 0,
            )
        )
    return windows


def _maximum_coverable_service_units(
    scenario: GeneratedScenario,
    active: list[IncidentTruth],
    simulation_time_s: int,
    busy_intervals: Sequence[tuple[str, int, int | None]],
) -> int:
    """Return a deterministic maximum compatibility match without double counting.

    Each resource can be assigned to at most one capability/route demand bucket.
    Capacity is capped at the service units it can actually cover in those active
    buckets, so surplus engine units cannot dilute water-rescue demand.
    """
    demand_by_key: dict[tuple[str, str], int] = defaultdict(int)
    for incident in active:
        structure = next(
            item for item in scenario.truth.structures if item.structure_id == incident.structure_id
        )
        route_id = "XNG-03" if structure.island_id == "ISL-02" else "XNG-04"
        demand_by_key[(incident.required_capability, route_id)] += incident.service_units
    keys = sorted(demand_by_key)
    if not keys:
        return 0

    states: set[tuple[int, ...]] = {(0,) * len(keys)}
    for unit in sorted(scenario.resources.units, key=lambda item: item.resource_id):
        committed = any(
            resource_id == unit.resource_id
            and interval_start <= simulation_time_s < int(interval_end)
            for resource_id, interval_start, interval_end in busy_intervals
            if interval_end is not None
        )
        if not unit.is_available or unit.available_from_s > simulation_time_s or committed:
            continue
        compatible_indexes = [
            index
            for index, (capability, route_id) in enumerate(keys)
            if capability in unit.capabilities
            and _routed_travel_s(scenario, unit, simulation_time_s, route_id) is not None
        ]
        next_states = set(states)
        for state in states:
            for index in compatible_indexes:
                updated = list(state)
                updated[index] = min(
                    demand_by_key[keys[index]],
                    updated[index] + unit.service_units,
                )
                next_states.add(tuple(updated))
        states = next_states
    return max((sum(state) for state in states), default=0)


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
        provenance.supported_action_types if provenance.adequacy_status.value == "qualified" else ()
    )
    guard = RevalidationGuard.bootstrap(
        predictor_version=provenance.predictor_version,
        calibration_version=provenance.calibration_version,
        model_hash=provenance.model_hash,
        qualified_families=qualified_families,
    )
    policy_config = PolicyConfig.from_yaml(policy_path)
    if not policy_config.enable_revalidation_guard:
        raise ValueError("Delta Small requires enable_revalidation_guard=true")
    policy = PolicyEngine(policy_config, revalidation=guard)
    decisions: list[DeltaDecisionEvent] = []
    evidence_items: list[WorldModelEvidence] = []
    outcomes: list[DeltaResourceOutcome] = []
    busy_until = {unit.resource_id: unit.available_from_s for unit in scenario.resources.units}
    earlier_calls: list[CallRecord] = []
    cluster_by_call: dict[str, str] = {}

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
        for call in scenario.observations.calls:
            cluster_id, evidence_basis = _visible_relationship(call, earlier_calls, cluster_by_call)
            cluster_by_call[call.call_id] = cluster_id
            earlier_calls.append(call)
            action_name, capability = CALL_ACTION[call.reported.call_type]
            route_id = _route_for_call(scenario, call)
            candidate = _candidate_resource(
                scenario, capability, call.received_s, route_id, busy_until
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
            available_units = sum(
                unit.service_units
                for unit in scenario.resources.units
                if capability in unit.capabilities
                and unit.is_available
                and unit.available_from_s <= call.received_s
                and busy_until[unit.resource_id] <= call.received_s
                and _routed_travel_s(scenario, unit, call.received_s, route_id) is not None
            )
            evidence = _prediction_evidence(
                scenario,
                predictor,
                call,
                action,
                available_units,
                (visual_features or {}).get(call.call_id),
            )
            evidence_items.append(evidence)
            claim = Claim(
                claim_id=f"claim-{call.call_id}",
                layer=ClaimLayer.PREDICTIVE,
                text="A compatible local resource can reach the reported location.",
                grounding={"call_id": call.call_id, "action_type": action_name},
                confidence=0.82,
                confidence_semantics="predictor action-prefix probability support",
                created_at=call.received_ts,
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
                created_at=call.received_ts,
            )
            consumed = runtime.consume(
                record,
                evaluation,
                consumer="delta-mission-controller",
                consumer_action_id=f"consumer-{call.call_id}",
                created_at=call.received_ts,
            )
            if evidence_basis:
                decisions.append(
                    DeltaDecisionEvent(
                        sequence=len(decisions) + 1,
                        call_id=call.call_id,
                        simulation_time_s=call.received_s,
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
                complete_s = min(
                    scenario.config.timeline.duration_s,
                    call.received_s + travel_s + unit.service_duration_s,
                )
                busy_until[unit.resource_id] = complete_s
                commitment = runtime.commit(
                    record=consumed,
                    action=action,
                    commitment_id=f"commitment-{call.call_id}",
                    created_at=call.received_ts,
                )
                event_type = "allocation"
                reason = "TRACE cleared and compatible reachable capacity was assigned"
                resource_id = unit.resource_id
                outcomes.append(
                    DeltaResourceOutcome(
                        outcome_id=f"outcome-{call.call_id}",
                        call_id=call.call_id,
                        resource_id=unit.resource_id,
                        status="service_completed_by_declared_duration",
                        completed_s=complete_s,
                        authorizing_commitment_id=commitment.commitment_id,
                    )
                )
                commitment_id = commitment.commitment_id
            else:
                event_type = "refusal"
                resource_id = ""
                complete_s = None
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
                    simulation_time_s=call.received_s,
                    event_type=event_type,
                    resource_id=resource_id,
                    reason=reason,
                    belief_cluster_id=cluster_id,
                    trace_decision=evaluation.decision.value,
                    trace_record_id=consumed.record_id,
                    trace_record_version=consumed.record_version,
                    commitment_id=commitment_id,
                    service_complete_s=complete_s,
                )
            )
        trace_records = repository.all()
        commitments = commitment_log.all()
        chain_verified = repository.verify_chain()

    windows = evaluate_capacity_windows(scenario, decisions)
    gross_ratios = [
        item.gross_load_ratio_milli for item in windows if item.gross_load_ratio_milli is not None
    ]
    residual_ratios = [
        item.residual_pressure_ratio_milli
        for item in windows
        if item.residual_pressure_ratio_milli is not None
    ]
    return DeltaRunResult(
        schema_version="delta-small-run-result-v3",
        scenario_id=scenario.config.scenario_id,
        predictor_version=provenance.predictor_version,
        calibration_version=provenance.calibration_version,
        decisions=decisions,
        demand_windows=windows,
        trace_records=trace_records,
        evidence=evidence_items,
        commitments=commitments,
        outcomes=outcomes,
        trace_chain_verified=chain_verified,
        peak_gross_load_ratio_milli=max(gross_ratios, default=0),
        gross_unserviceable_windows=sum(item.gross_unserviceable for item in windows),
        peak_finite_residual_pressure_ratio_milli=max(residual_ratios, default=0),
        residual_unserviceable_windows=sum(item.residual_unserviceable for item in windows),
        allocated=sum(event.event_type == "allocation" for event in decisions),
        refused=sum(event.event_type == "refusal" for event in decisions),
        repaired=sum(event.event_type == "repair" for event in decisions),
    )
