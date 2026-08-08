from __future__ import annotations

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
    PredictorResourceTelemetry,
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
from trace_jepa.scenario.delta.evaluation import (
    ReconciliationEvaluation,
    evaluate_reconciliation,
)
from trace_jepa.scenario.delta.models import (
    CallRecord,
    CrossingState,
    DeltaModel,
    GeneratedScenario,
    IncidentTruth,
    ResourceUnit,
    WeatherSample,
)
from trace_jepa.scenario.delta.reconciliation_selection import (
    CANONICAL_RECONCILIATION_ALGORITHM,
)
from trace_jepa.scenario.delta.reconciliation_v8 import (
    EvidenceGraphReconciler,
    ReconciliationArtifact,
    baseline_v7_visible_relationship,
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
    active_demand_units: int = Field(ge=0)
    strict_matched_capacity_units: int = Field(ge=0)
    strict_concurrent_load_ratio_milli: int | None = Field(default=None, ge=0)
    strict_unserviceable: bool
    uncapped_compatible_service_unit_capacity_units: int = Field(ge=0)
    uncapped_compatible_load_ratio_milli: int | None = Field(default=None, ge=0)
    historical_capped_coverable_capacity_units: int = Field(ge=0)
    registered_normalized_coverable_load_index_milli: int | None = Field(default=None, ge=0)
    commitment_covered_demand_units: int = Field(ge=0)
    residual_demand_units: int = Field(ge=0)
    free_strict_compatible_capacity_units: int = Field(ge=0)
    residual_strict_pressure_ratio_milli: int | None = Field(default=None, ge=0)
    residual_strict_unserviceable: bool

    @model_validator(mode="after")
    def validate_capacity_accounting(self) -> DemandWindow:
        if (
            self.commitment_covered_demand_units + self.residual_demand_units
            != self.active_demand_units
        ):
            raise ValueError("covered plus residual demand must equal active demand")
        if self.strict_unserviceable != (
            self.active_demand_units > 0 and self.strict_matched_capacity_units == 0
        ):
            raise ValueError("strict unserviceable status disagrees with demand and capacity")
        if self.residual_strict_unserviceable != (
            self.residual_demand_units > 0 and self.free_strict_compatible_capacity_units == 0
        ):
            raise ValueError("residual unserviceable status disagrees with demand and capacity")
        if self.active_demand_units == 0 and any(
            ratio != 0
            for ratio in (
                self.strict_concurrent_load_ratio_milli,
                self.uncapped_compatible_load_ratio_milli,
                self.registered_normalized_coverable_load_index_milli,
            )
        ):
            raise ValueError("all intrinsic load measures must be zero when demand is zero")
        return self

    # Read-only aliases keep downstream v6 readers source-compatible. They are
    # intentionally absent from serialized v7 artifacts, where the precise metric
    # names above are mandatory.
    @property
    def active_demand_service_units(self) -> int:
        return self.active_demand_units

    @property
    def gross_compatible_capacity_units(self) -> int:
        return self.historical_capped_coverable_capacity_units

    @property
    def gross_load_ratio_milli(self) -> int | None:
        return self.registered_normalized_coverable_load_index_milli

    @property
    def gross_unserviceable(self) -> bool:
        return self.active_demand_units > 0 and self.historical_capped_coverable_capacity_units == 0

    @property
    def residual_unassigned_demand_units(self) -> int:
        return self.residual_demand_units

    @property
    def free_compatible_capacity_units(self) -> int:
        return self.free_strict_compatible_capacity_units

    @property
    def residual_pressure_ratio_milli(self) -> int | None:
        return self.residual_strict_pressure_ratio_milli

    @property
    def residual_unserviceable(self) -> bool:
        return self.residual_strict_unserviceable


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
    predictor_requests: list[PredictorRequest] = Field(default_factory=list)
    commitments: list[Commitment]
    outcomes: list[DeltaResourceOutcome]
    reconciliation_artifact: ReconciliationArtifact | None = None
    reconciliation_evaluation: ReconciliationEvaluation
    trace_chain_verified: bool
    peak_strict_concurrent_load_ratio_milli: int = Field(ge=0)
    strict_unserviceable_windows: int = Field(ge=0)
    peak_uncapped_compatible_load_ratio_milli: int = Field(ge=0)
    uncapped_unserviceable_windows: int = Field(ge=0)
    peak_registered_normalized_coverable_load_index_milli: int = Field(ge=0)
    historical_capped_unserviceable_windows: int = Field(ge=0)
    peak_finite_residual_strict_pressure_ratio_milli: int = Field(ge=0)
    residual_strict_unserviceable_windows: int = Field(ge=0)
    allocated: int = Field(ge=0)
    refused: int = Field(ge=0)
    repaired: int = Field(ge=0)

    @property
    def peak_demand_capacity_ratio_milli(self) -> int:
        """Deprecated alias for the primary v7 strict-concurrency measure."""
        return self.peak_strict_concurrent_load_ratio_milli

    @property
    def peak_gross_load_ratio_milli(self) -> int:
        """Deprecated v6 alias for the registered historical normalized index."""
        return self.peak_registered_normalized_coverable_load_index_milli

    @property
    def gross_unserviceable_windows(self) -> int:
        """Deprecated v6 alias for historical capped-capacity zero windows."""
        return self.historical_capped_unserviceable_windows

    @property
    def peak_finite_residual_pressure_ratio_milli(self) -> int:
        """Deprecated v6 alias for strict residual operational pressure."""
        return self.peak_finite_residual_strict_pressure_ratio_milli

    @property
    def residual_unserviceable_windows(self) -> int:
        """Deprecated v6 alias for strict residual unserviceable windows."""
        return self.residual_strict_unserviceable_windows

    @property
    def unserviceable_windows(self) -> int:
        """Deprecated source-compatibility alias for residual pressure."""
        return self.residual_strict_unserviceable_windows


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


def _prediction_evidence(
    scenario: GeneratedScenario,
    predictor: ActionPrefixPredictor,
    call: CallRecord,
    action: ActionInstance,
    busy_until: dict[str, int],
    controller_time_s: int,
    visual_feature: PredictorVisualFeatureRef | None = None,
) -> tuple[WorldModelEvidence, PredictorRequest]:
    route_id = action.route_id
    if route_id is None:
        raise ValueError("Delta actions require an explicit route")
    route_state = _crossing_state(scenario, route_id, controller_time_s)
    weather = _weather(scenario, controller_time_s)
    tick = _nearest_tick(scenario, controller_time_s)
    crossing = next(item for item in scenario.geography.crossings if item.crossing_id == route_id)
    nearest_gauge = min(
        scenario.geography.gauges,
        key=lambda gauge: (
            (gauge.location.easting_mm - crossing.location.easting_mm) ** 2
            + (gauge.location.northing_mm - crossing.location.northing_mm) ** 2,
            gauge.gauge_id,
        ),
    )
    gauge_sample = next(
        item
        for item in scenario.gauges
        if item.gauge_id == nearest_gauge.gauge_id and item.simulation_time_s == tick
    )
    call_age_s = float(controller_time_s - call.received_s)
    crossing_age_s = float(controller_time_s - route_state.simulation_time_s)
    gauge_age_s = float(controller_time_s - gauge_sample.simulation_time_s)
    observation_age_s = max(call_age_s, crossing_age_s, gauge_age_s)
    capability = str(action.parameters["required_capability"])
    compatible_resources: list[PredictorResourceTelemetry] = []
    for unit in sorted(scenario.resources.units, key=lambda item: item.resource_id):
        if capability not in unit.capabilities:
            continue
        routed_travel_s = _routed_travel_s(scenario, unit, controller_time_s, route_id)
        compatible_resources.append(
            PredictorResourceTelemetry(
                resource_id=unit.resource_id,
                resource_class=unit.resource_class,
                capabilities=unit.capabilities,
                service_units=unit.service_units,
                availability_mode=unit.availability_mode,
                origin_base_id=unit.origin_base_id,
                staged_base_id=unit.base_id,
                route_id=route_id,
                scheduled_available_s=unit.available_from_s,
                busy_until_s=busy_until[unit.resource_id],
                currently_available=(
                    unit.is_available
                    and unit.available_from_s <= controller_time_s
                    and busy_until[unit.resource_id] <= controller_time_s
                    and routed_travel_s is not None
                ),
                route_reachable=routed_travel_s is not None,
                routed_travel_s=routed_travel_s,
            )
        )
    available_units = sum(
        item.service_units for item in compatible_resources if item.currently_available
    )
    plan = PlanCandidate(
        plan_id=f"plan-{call.call_id}",
        name=f"Respond to {call.call_id}",
        actions=(action,),
        utility=1.0,
        reversible_first_action=False,
        requires_authority=True,
        metadata={"call_type": call.reported.call_type},
    )
    request = PredictorRequest(
        plan=plan,
        observation=PredictorObservation(
            routes=[
                PredictorRouteObservation(
                    route_id=route_id,
                    report=("unknown" if call.quality.call_dropped else route_state.status),
                    nominal_travel_s=float(route_state.travel_time_s),
                    confidence=route_state.confidence_milli / 1000.0,
                    observation_age_s=crossing_age_s,
                    stage_millifeet=gauge_sample.stage_millifeet,
                    crossing_sample_time_s=route_state.simulation_time_s,
                    gauge_id=nearest_gauge.gauge_id,
                    gauge_sample_time_s=gauge_sample.simulation_time_s,
                    gauge_threshold_status=nearest_gauge.threshold_status,
                ),
            ],
            context=PredictorContext(
                simulation_time_s=controller_time_s,
                rain_milli_inches_per_hour=weather.rain_milli_inches_per_hour,
                wind_milli_knots=weather.wind_milli_knots,
                available_resource_units=available_units,
                call_observation_age_s=call_age_s,
                coordination_latency_s=call_age_s,
                compatible_resources=tuple(compatible_resources),
                source_call_sha256=sha256_bytes(canonical_json_bytes(call.model_dump(mode="json"))),
                prior_profile=PredictorPriorProfile(
                    profile_id=scenario.prior_profile.profile_id,
                    calibration_version=scenario.prior_profile.calibration_version,
                    prior_accuracy_milli=scenario.prior_profile.prior_accuracy_milli,
                ),
                visual_feature=visual_feature,
            ),
        ),
    )
    prediction = predictor.predict(request)
    stamp = scenario.config.timeline.epoch_utc + timedelta(seconds=controller_time_s)
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
    evidence = WorldModelEvidence(
        evidence_id=f"evidence-{call.call_id}",
        rollout_id=f"rollout-{call.call_id}",
        encoder_version=provenance.encoder_version or "delta-symbolic-observation-v2",
        fusion_version=(
            "delta-small-controller-context-v4"
            if scenario.config.generator_version == "delta-small-generator-v8"
            else (
                "delta-small-controller-context-v3"
                if scenario.config.generator_version == "delta-small-generator-v7"
                else "delta-small-controller-context-v2"
            )
        ),
        predictor_version=provenance.predictor_version,
        semantic_probe_versions=("delta-route-and-resource-probe-v2",),
        training_snapshot=provenance.training_snapshot,
        observation_window_hash=sha256_bytes(canonical_json_bytes(request.model_dump(mode="json"))),
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
            f"{route_id} and registered compatible capacity support the proposed response",
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
            "gauge_id": nearest_gauge.gauge_id,
            "gauge_stage_millifeet": gauge_sample.stage_millifeet,
            "gauge_threshold_status": nearest_gauge.threshold_status,
            "crossing_sample_time_s": route_state.simulation_time_s,
            "gauge_sample_time_s": gauge_sample.simulation_time_s,
        },
        calibration_version=provenance.calibration_version,
        assumptions=prediction.assumptions,
        observation_age_s=observation_age_s,
        created_at=stamp,
        experimental_profile=profile,
    )
    return evidence, request


def evaluate_capacity_windows(
    scenario: GeneratedScenario,
    decisions: list[DeltaDecisionEvent],
) -> list[DemandWindow]:
    """Evaluate registered intrinsic-load definitions and strict residual pressure.

    All intrinsic metrics are properties of ground truth plus the registered
    resource schedule and therefore ignore controller commitments. Strict
    concurrency is primary. The uncapped service-unit and historical capped
    index definitions are sensitivity measures. Residual pressure is an offline
    evaluation that uses hidden lineage only after TRACE execution; no truth
    identifier is emitted in the aggregate result.
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
        strict_capacity = _strict_matched_capacity_units(scenario, active, start, ())
        uncapped_capacity = _uncapped_compatible_service_unit_capacity(scenario, active, start, ())
        historical_capacity = _historical_capped_coverable_capacity_units(
            scenario, active, start, ()
        )

        covered_ids = _truth_incidents_covered_by_commitments(
            scenario,
            active,
            start,
            allocation_events,
            lineage_by_call,
        )
        residual_incidents = [
            incident for incident in active if incident.incident_id not in covered_ids
        ]
        commitment_covered = active_demand - sum(
            incident.service_units for incident in residual_incidents
        )
        residual_demand = active_demand - commitment_covered
        free_strict_capacity = _strict_matched_capacity_units(
            scenario,
            residual_incidents,
            start,
            busy_intervals,
        )
        windows.append(
            DemandWindow(
                window_start_s=start,
                active_demand_units=active_demand,
                strict_matched_capacity_units=strict_capacity,
                strict_concurrent_load_ratio_milli=_ratio_milli(active_demand, strict_capacity),
                strict_unserviceable=active_demand > 0 and strict_capacity == 0,
                uncapped_compatible_service_unit_capacity_units=uncapped_capacity,
                uncapped_compatible_load_ratio_milli=_ratio_milli(active_demand, uncapped_capacity),
                historical_capped_coverable_capacity_units=historical_capacity,
                registered_normalized_coverable_load_index_milli=_ratio_milli(
                    active_demand, historical_capacity
                ),
                commitment_covered_demand_units=commitment_covered,
                residual_demand_units=residual_demand,
                free_strict_compatible_capacity_units=free_strict_capacity,
                residual_strict_pressure_ratio_milli=_ratio_milli(
                    residual_demand, free_strict_capacity
                ),
                residual_strict_unserviceable=(residual_demand > 0 and free_strict_capacity == 0),
            )
        )
    return windows


def _ratio_milli(demand: int, capacity: int) -> int | None:
    if demand == 0:
        return 0
    if capacity == 0:
        return None
    return round(1000 * demand / capacity)


def _incident_route(scenario: GeneratedScenario, incident: IncidentTruth) -> str:
    structure = next(
        item for item in scenario.truth.structures if item.structure_id == incident.structure_id
    )
    return "XNG-03" if structure.island_id == "ISL-02" else "XNG-04"


def _unit_is_eligible(
    scenario: GeneratedScenario,
    unit: ResourceUnit,
    simulation_time_s: int,
    route_id: str,
    busy_intervals: Sequence[tuple[str, int, int | None]],
) -> bool:
    committed = any(
        resource_id == unit.resource_id and interval_start <= simulation_time_s < int(interval_end)
        for resource_id, interval_start, interval_end in busy_intervals
        if interval_end is not None
    )
    return (
        unit.is_available
        and unit.available_from_s <= simulation_time_s
        and not committed
        and _routed_travel_s(scenario, unit, simulation_time_s, route_id) is not None
    )


def _strict_matched_capacity_units(
    scenario: GeneratedScenario,
    active: Sequence[IncidentTruth],
    simulation_time_s: int,
    busy_intervals: Sequence[tuple[str, int, int | None]],
) -> int:
    """Maximize incident units covered under one-resource/one-incident concurrency."""
    incidents = sorted(active, key=lambda item: item.incident_id)
    if not incidents:
        return 0
    routes = [_incident_route(scenario, incident) for incident in incidents]
    states: set[int] = {0}
    for unit in sorted(scenario.resources.units, key=lambda item: item.resource_id):
        compatible = [
            index
            for index, incident in enumerate(incidents)
            if incident.required_capability in unit.capabilities
            and unit.service_units >= incident.service_units
            and _unit_is_eligible(
                scenario,
                unit,
                simulation_time_s,
                routes[index],
                busy_intervals,
            )
        ]
        next_states = set(states)
        for state in states:
            for index in compatible:
                bit = 1 << index
                if state & bit == 0:
                    next_states.add(state | bit)
        states = next_states
    return max(
        (
            sum(
                incident.service_units
                for index, incident in enumerate(incidents)
                if state & (1 << index)
            )
            for state in states
        ),
        default=0,
    )


def _uncapped_compatible_service_unit_capacity(
    scenario: GeneratedScenario,
    active: Sequence[IncidentTruth],
    simulation_time_s: int,
    busy_intervals: Sequence[tuple[str, int, int | None]],
) -> int:
    """Sum eligible resource service units once when any active incident is compatible."""
    if not active:
        return 0
    routes = {incident.incident_id: _incident_route(scenario, incident) for incident in active}
    return sum(
        unit.service_units
        for unit in sorted(scenario.resources.units, key=lambda item: item.resource_id)
        if any(
            incident.required_capability in unit.capabilities
            and _unit_is_eligible(
                scenario,
                unit,
                simulation_time_s,
                routes[incident.incident_id],
                busy_intervals,
            )
            for incident in active
        )
    )


def _historical_capped_coverable_capacity_units(
    scenario: GeneratedScenario,
    active: Sequence[IncidentTruth],
    simulation_time_s: int,
    busy_intervals: Sequence[tuple[str, int, int | None]],
) -> int:
    """Reproduce the v6 registered normalized coverable-load denominator.

    Each resource can be assigned to at most one capability/route demand bucket.
    Capacity is capped at the service units it can actually cover in those active
    buckets, so surplus engine units cannot dilute water-rescue demand.
    """
    demand_by_key: dict[tuple[str, str], int] = defaultdict(int)
    for incident in active:
        route_id = _incident_route(scenario, incident)
        demand_by_key[(incident.required_capability, route_id)] += incident.service_units
    keys = sorted(demand_by_key)
    if not keys:
        return 0

    states: set[tuple[int, ...]] = {(0,) * len(keys)}
    for unit in sorted(scenario.resources.units, key=lambda item: item.resource_id):
        compatible_indexes = [
            index
            for index, (capability, route_id) in enumerate(keys)
            if capability in unit.capabilities
            and _unit_is_eligible(scenario, unit, simulation_time_s, route_id, busy_intervals)
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


def _truth_incidents_covered_by_commitments(
    scenario: GeneratedScenario,
    active: Sequence[IncidentTruth],
    simulation_time_s: int,
    allocation_events: Sequence[DeltaDecisionEvent],
    lineage_by_call: dict[str, str],
) -> set[str]:
    """Score authorized commitments against truth without credit for incompatibility."""
    active_by_id = {incident.incident_id: incident for incident in active}
    unit_by_id = {unit.resource_id: unit for unit in scenario.resources.units}
    covered: set[str] = set()
    for event in allocation_events:
        if (
            event.service_complete_s is None
            or not event.simulation_time_s <= simulation_time_s < event.service_complete_s
        ):
            continue
        incident_id = lineage_by_call.get(event.call_id)
        incident = active_by_id.get(incident_id or "")
        unit = unit_by_id.get(event.resource_id)
        if incident is None or unit is None:
            continue
        route_id = _incident_route(scenario, incident)
        if (
            incident.required_capability in unit.capabilities
            and unit.service_units >= incident.service_units
            and unit.is_available
            and unit.available_from_s <= event.simulation_time_s
            and _routed_travel_s(scenario, unit, event.simulation_time_s, route_id) is not None
        ):
            covered.add(incident.incident_id)
    return covered


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
            route_id = _route_for_call(scenario, call)
            candidate = _candidate_resource(
                scenario, capability, controller_time_s, route_id, busy_until
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
            evidence, predictor_request = _prediction_evidence(
                scenario,
                predictor,
                call,
                action,
                busy_until,
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
                complete_s = min(
                    scenario.config.timeline.duration_s,
                    controller_time_s + travel_s + unit.service_duration_s,
                )
                busy_until[unit.resource_id] = complete_s
                commitment = runtime.commit(
                    record=consumed,
                    action=action,
                    commitment_id=f"commitment-{call.call_id}",
                    created_at=controller_timestamp,
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
                    simulation_time_s=controller_time_s,
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
        schema_version="delta-small-run-result-v4",
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
        peak_strict_concurrent_load_ratio_milli=max(strict_ratios, default=0),
        strict_unserviceable_windows=sum(item.strict_unserviceable for item in windows),
        peak_uncapped_compatible_load_ratio_milli=max(uncapped_ratios, default=0),
        uncapped_unserviceable_windows=sum(
            item.active_demand_units > 0
            and item.uncapped_compatible_service_unit_capacity_units == 0
            for item in windows
        ),
        peak_registered_normalized_coverable_load_index_milli=max(historical_ratios, default=0),
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
