from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable

from trace_jepa.contracts import (
    ActionInstance,
    Claim,
    ClaimLayer,
    PlanCandidate,
    PlanPrediction,
    RealizedOutcome,
    TraceRecord,
    TraceStatus,
    WorldModelEvidence,
)
from trace_jepa.runtime import PolicyConfig, PolicyEngine, TraceRuntime
from trace_jepa.util import sha256_value
from trace_jepa.workbench.models import Position, WorkbenchState
from trace_jepa.workbench.navigation import NavigationError, plan_route_constrained_action


Emit = Callable[[str, dict[str, Any]], None]


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _distance(a: Position, b: Position) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def _midpoint(points: list[Position]) -> Position:
    if not points:
        return Position(x=50.0, y=40.0)
    return points[len(points) // 2]


@dataclass
class AssessedCandidate:
    plan: PlanCandidate
    prediction: PlanPrediction
    record: TraceRecord
    decision: str
    status: str
    reason: str
    false_clear: bool
    false_hold: bool
    stale_clearance: bool


class DynamicMissionController:
    """Mission Controller for the dynamic S1-S5 research workbench.

    The current predictor is a transparent surrogate with computed support,
    uncertainty, OOD, and validity horizons. Its interface is deliberately the
    same one that a later TRACE-WorldModel model service will implement.
    """

    version = "dynamic-mission-controller-d0.2-step02"
    predictor_version = "dynamic-surrogate-predictor-v1.1"
    probe_version = "dynamic-flood-probes-v1.1"

    def __init__(self, runtime: TraceRuntime):
        self.runtime = runtime

    def refresh_policy(self, state: WorkbenchState) -> None:
        current = self.runtime.policy.config
        self.runtime.policy = PolicyEngine(
            PolicyConfig(
                policy_version="trace-dynamic-v1",
                min_model_support=current.min_model_support,
                max_ood_score=current.max_ood_score,
                max_uncertainty=current.max_uncertainty,
                max_rollout_horizon=current.max_rollout_horizon,
                max_observation_age_s=state.config.s2.observation_freshness_s,
                require_authority_for=(
                    "dispatch_rescue_boat",
                    "dispatch_helicopter",
                    "deploy_ground_team",
                    "evacuate_to_safety",
                ),
                allow_qualified_reversible_probe=True,
            )
        )

    def _available_assets(self, state: WorkbenchState, asset_type: str) -> list[str]:
        return [
            asset_id
            for asset_id, asset in state.controller.known_assets.items()
            if asset.asset_type == asset_type
            and asset.status in {"available", "standby"}
            and asset.passenger_count == 0
            and asset.resource > 0.05
        ]

    def _route_age(self, state: WorkbenchState, route_id: str) -> float:
        belief = state.controller.route_beliefs[route_id]
        if belief.observed_at is None:
            return state.config.s2.observation_freshness_s * 10.0
        return max(0.0, state.truth.simulation_time - belief.observed_at)

    def _route_prediction(
        self,
        state: WorkbenchState,
        *,
        plan_id: str,
        route_id: str,
        asset_id: str,
        travel_s: float | None = None,
    ) -> PlanPrediction:
        route = state.truth.routes[route_id]
        belief = state.controller.route_beliefs[route_id]
        asset = state.controller.known_assets[asset_id]
        age = self._route_age(state, route_id)
        freshness = math.exp(-age / max(1.0, state.config.s2.observation_freshness_s))

        unknown_penalty = 0.28 if belief.status == "unknown" else 0.0
        weather_penalty = max(0.0, state.truth.weather_severity - asset.weather_tolerance) * 0.55
        ood = _clamp(
            state.config.s1.ood_severity
            + unknown_penalty
            + weather_penalty
            + 0.12 * max(0.0, route.water_depth - 0.45)
        )
        status_support = {
            "open": 0.72 + 0.22 * belief.confidence,
            "blocked": 0.78 + 0.18 * belief.confidence,
            "unknown": 0.34,
        }[belief.status]
        support = _clamp(
            status_support
            * max(0.15, freshness)
            * state.config.s5.sensor_quality
            * (1.0 - 0.45 * ood)
        )
        uncertainty = _clamp(
            state.config.s1.sensor_noise
            + 0.42 * (1.0 - support)
            + 0.20 * state.config.s1.packet_loss
        )

        base_success = {"open": 0.91, "blocked": 0.05, "unknown": 0.70}[belief.status]
        effective_travel_s = float(travel_s if travel_s is not None else route.nominal_travel_s)
        forecast_rise = (
            effective_travel_s
            * state.config.s2.water_rise_rate
            * (0.25 + state.config.s2.rain_intensity + state.config.s2.upstream_inflow)
            * route.susceptibility
        )
        predicted_depth = route.water_depth + forecast_rise
        dynamic_risk = _clamp(predicted_depth / max(0.05, state.config.s2.route_closure_depth))
        success = _clamp(
            base_success
            - 0.34 * dynamic_risk
            - 0.18 * uncertainty
            - 0.12 * state.truth.weather_severity
        )
        hazard = _clamp(
            0.15 + 0.55 * dynamic_risk + 0.25 * uncertainty + 0.20 * weather_penalty
        )
        resource_margin = asset.resource - 0.12 - 0.08 * dynamic_risk
        return PlanPrediction(
            plan_id=plan_id,
            success_probability=success,
            arrival_time_s=effective_travel_s,
            hazard_score=hazard,
            resource_margin=resource_margin,
            model_support=support,
            out_of_distribution_score=ood,
            uncertainty=uncertainty,
            rollout_horizon=max(1, int(math.ceil(effective_travel_s / 180.0))),
            assumptions=(
                "model_conditional_prediction",
                "route_geometry_is_current",
                "weather_forecast_is_stable_over_the_action_prefix",
            ),
        )

    def _verification_prediction(
        self,
        state: WorkbenchState,
        *,
        plan_id: str,
        route_id: str,
        asset_id: str,
    ) -> PlanPrediction:
        asset = state.controller.known_assets[asset_id]
        weather_excess = max(0.0, state.truth.weather_severity - asset.weather_tolerance)
        ood = _clamp(0.25 * state.config.s1.ood_severity + 0.55 * weather_excess)
        support = _clamp(
            0.72
            * state.config.s5.sensor_quality
            * state.config.s1.drone_report_accuracy
            * (1.0 - 0.35 * ood)
        )
        uncertainty = _clamp(
            state.config.s1.sensor_noise + 0.40 * (1.0 - support) + 0.25 * weather_excess
        )
        route = state.truth.routes[route_id]
        target = _midpoint(route.waypoints)
        travel = max(30.0, _distance(asset.position, target) / max(0.1, asset.speed))
        success = _clamp(
            state.config.s1.drone_report_accuracy
            * state.config.s5.sensor_quality
            * (1.0 - 0.55 * weather_excess)
        )
        return PlanPrediction(
            plan_id=plan_id,
            success_probability=success,
            arrival_time_s=travel,
            hazard_score=_clamp(0.08 + 0.60 * weather_excess + 0.20 * uncertainty),
            resource_margin=asset.resource - 0.10 - 0.20 * weather_excess,
            model_support=support,
            out_of_distribution_score=ood,
            uncertainty=uncertainty,
            rollout_horizon=max(1, int(math.ceil(travel / 60.0))),
            assumptions=(
                "model_conditional_prediction",
                "bounded_information_gathering_action",
            ),
        )

    def _air_prediction(
        self,
        state: WorkbenchState,
        *,
        plan_id: str,
        asset_id: str,
        group_id: str,
    ) -> PlanPrediction:
        asset = state.controller.known_assets[asset_id]
        group = state.controller.known_groups[group_id]
        distance = _distance(asset.position, group.position)
        travel = max(20.0, distance / max(0.1, asset.speed))
        weather_excess = max(0.0, state.truth.weather_severity - asset.weather_tolerance)
        ood = _clamp(state.config.s1.ood_severity + 0.65 * weather_excess)
        support = _clamp(0.84 * (1.0 - 0.50 * ood))
        uncertainty = _clamp(state.config.s1.sensor_noise + 0.45 * (1.0 - support))
        return PlanPrediction(
            plan_id=plan_id,
            success_probability=_clamp(0.94 - 0.65 * weather_excess - 0.15 * uncertainty),
            arrival_time_s=travel,
            hazard_score=_clamp(0.12 + 0.75 * weather_excess + 0.15 * uncertainty),
            resource_margin=asset.resource - 0.18 - 0.15 * weather_excess,
            model_support=support,
            out_of_distribution_score=ood,
            uncertainty=uncertainty,
            rollout_horizon=max(1, int(math.ceil(travel / 60.0))),
            assumptions=("model_conditional_prediction", "air_corridor_available"),
        )

    def _evacuation_candidates(
        self,
        state: WorkbenchState,
    ) -> list[tuple[PlanCandidate, PlanPrediction, Claim]]:
        """Plan transport from pickup to the declared safe transfer dock.

        Reaching a stranded group is not rescue completion. When people are
        onboard, each feasible water route back to safety becomes a fresh
        candidate with its own prediction, TRACE record, and authority check.
        """

        result: list[tuple[PlanCandidate, PlanPrediction, Claim]] = []
        for asset_id, asset in state.controller.known_assets.items():
            if asset.asset_type != "rescue_boat":
                continue
            if asset.passenger_count <= 0:
                continue
            if asset.status not in {"available", "standby", "awaiting_clearance"}:
                continue

            safe_location_id = (
                asset.safe_location_id or state.config.rescue.safe_location_id
            )
            for route_id, route in state.truth.routes.items():
                plan_id = (
                    f"evacuate:{asset_id}:{route_id}:"
                    f"{'-'.join(asset.passenger_group_ids)}"
                )
                action = ActionInstance(
                    action_type="evacuate_to_safety",
                    actor_id=asset_id,
                    origin="incident_pickup",
                    destination=safe_location_id,
                    route_id=route_id,
                    parameters={
                        "group_ids": list(asset.passenger_group_ids),
                        "people_count": asset.passenger_count,
                        "safe_location_id": safe_location_id,
                        "safe_location_label": "Safe Transfer Dock",
                    },
                )
                try:
                    navigation = plan_route_constrained_action(
                        state,
                        action,
                        view="controller",
                    )
                except NavigationError:
                    continue

                travel_s = max(
                    1.0,
                    navigation.total_distance / max(0.1, asset.speed),
                )
                prediction = self._route_prediction(
                    state,
                    plan_id=plan_id,
                    route_id=route_id,
                    asset_id=asset_id,
                    travel_s=travel_s,
                )
                cost = asset.operating_cost * prediction.arrival_time_s / 60.0
                utility = (
                    250.0 * prediction.success_probability
                    - 60.0 * prediction.hazard_score
                    - 0.02 * prediction.arrival_time_s
                    - cost
                )
                plan = PlanCandidate(
                    plan_id=plan_id,
                    name=(
                        f"Evacuate {asset.passenger_count} people to safety "
                        f"via {route.label}"
                    ),
                    actions=(action,),
                    utility=utility,
                    reversible_first_action=False,
                    requires_authority=True,
                    metadata={
                        "route_id": route_id,
                        "asset_id": asset_id,
                        "group_ids": list(asset.passenger_group_ids),
                        "kind": "evacuation",
                        "priority": 1000,
                        "cost": cost,
                        "navigation_summary": navigation.summary,
                        "navigation_distance": navigation.total_distance,
                    },
                )
                claim = Claim(
                    layer=ClaimLayer.PREDICTIVE,
                    text=(
                        f"{route.label} will remain traversable long enough "
                        f"for {asset_id} to deliver {asset.passenger_count} "
                        "onboard people to the Safe Transfer Dock."
                    ),
                    grounding={
                        "route_id": route_id,
                        "asset_id": asset_id,
                        "group_ids": list(asset.passenger_group_ids),
                        "safe_location_id": safe_location_id,
                        "arrival_time_s": prediction.arrival_time_s,
                    },
                    confidence=prediction.success_probability,
                    confidence_semantics=(
                        "model-conditional evacuation success probability"
                    ),
                )
                result.append((plan, prediction, claim))
        return result

    def candidates(self, state: WorkbenchState) -> list[tuple[PlanCandidate, PlanPrediction, Claim]]:
        candidates: list[tuple[PlanCandidate, PlanPrediction, Claim]] = []
        candidates.extend(self._evacuation_candidates(state))
        unrescued = [
            group
            for group in state.controller.known_groups.values()
            if not group.rescued
            and not group.cancelled
            and group.rescue_phase == "waiting"
            and int(group.people_waiting or 0) > 0
            and group.assigned_asset_id is None
        ]
        # S5 evidence-seeking plans for unknown, stale, or soon-expiring route beliefs.
        drones = self._available_assets(state, "survey_drone")
        if drones:
            drone_id = drones[0]
            for route_id, belief in state.controller.route_beliefs.items():
                age = self._route_age(state, route_id)
                expiring = (
                    belief.clearance_valid_until is not None
                    and belief.clearance_valid_until - state.truth.simulation_time
                    < state.config.s2.clearance_horizon_s * 0.25
                )
                requested = route_id in state.controller.requested_surveys
                if requested or belief.status == "unknown" or age > state.config.s2.observation_freshness_s or expiring:
                    plan_id = f"verify:{drone_id}:{route_id}"
                    action = ActionInstance(
                        action_type="verify_route",
                        actor_id=drone_id,
                        route_id=route_id,
                        parameters={
                            "purpose": "resolve_pending_route_claim",
                            "expected_information_yield": state.config.s5.value_of_information_weight,
                        },
                    )
                    prediction = self._verification_prediction(
                        state, plan_id=plan_id, route_id=route_id, asset_id=drone_id
                    )
                    voi = (
                        state.config.s5.value_of_information_weight
                        * (1.0 if belief.status == "unknown" else 0.55)
                        * prediction.success_probability
                    )
                    plan = PlanCandidate(
                        plan_id=plan_id,
                        name=f"Verify {state.truth.routes[route_id].label}",
                        actions=(action,),
                        utility=35.0 + 30.0 * voi - 10.0 * prediction.hazard_score,
                        reversible_first_action=True,
                        requires_authority=False,
                        metadata={"route_id": route_id, "kind": "reconnaissance", "voi": voi, "operator_requested": requested},
                    )
                    claim = Claim(
                        layer=ClaimLayer.PRACTICAL,
                        text=f"{drone_id} should verify {state.truth.routes[route_id].label} now.",
                        grounding={
                            "asset_id": drone_id,
                            "route_id": route_id,
                            "purpose": "resolve_missing_evidence",
                        },
                        confidence=prediction.success_probability,
                        confidence_semantics="predicted probability that the bounded survey completes",
                    )
                    candidates.append((plan, prediction, claim))

        if not unrescued:
            return candidates

        boats = self._available_assets(state, "rescue_boat")
        helicopters = self._available_assets(state, "helicopter")
        ground_teams = self._available_assets(state, "ground_team")

        for group in unrescued:
            urgency = (
                state.config.s3.severity_weight * group.severity
                + state.config.s3.deadline_weight
                * max(0.0, 1.0 - (group.deadline_s - state.truth.simulation_time) / max(1.0, group.deadline_s))
            )

            for boat_id in boats:
                boat = state.controller.known_assets[boat_id]
                people_to_board = min(boat.capacity, int(group.people_waiting or group.people))
                if people_to_board <= 0:
                    continue
                for route_id, route in state.truth.routes.items():
                    plan_id = f"boat:{boat_id}:{group.group_id}:{route_id}"
                    action = ActionInstance(
                        action_type="dispatch_rescue_boat",
                        actor_id=boat_id,
                        origin="rescue_base",
                        destination=group.group_id,
                        route_id=route_id,
                        parameters={
                            "people_count": people_to_board,
                            "deadline_s": group.deadline_s,
                            "group_id": group.group_id,
                        },
                    )
                    try:
                        navigation = plan_route_constrained_action(
                            state, action, view="controller"
                        )
                    except NavigationError:
                        # A plan that cannot be connected to the declared
                        # waterway graph is structurally invalid and never
                        # reaches TRACE. TRACE audits warrants, not wiring.
                        continue
                    travel_s = max(1.0, navigation.total_distance / max(0.1, boat.speed))
                    prediction = self._route_prediction(
                        state,
                        plan_id=plan_id,
                        route_id=route_id,
                        asset_id=boat_id,
                        travel_s=travel_s,
                    )
                    cost = boat.operating_cost * prediction.arrival_time_s / 60.0
                    utility = (
                        90.0 * prediction.success_probability
                        + 25.0 * urgency
                        - 32.0 * prediction.hazard_score
                        - 0.025 * prediction.arrival_time_s
                        - cost
                    )
                    plan = PlanCandidate(
                        plan_id=plan_id,
                        name=f"Boat to {group.label} via {route.label}",
                        actions=(action,),
                        utility=utility,
                        reversible_first_action=False,
                        requires_authority=True,
                        metadata={
                            "route_id": route_id,
                            "group_id": group.group_id,
                            "asset_id": boat_id,
                            "cost": cost,
                            "navigation_summary": navigation.summary,
                            "navigation_distance": navigation.total_distance,
                        },
                    )
                    claim = Claim(
                        layer=ClaimLayer.PREDICTIVE,
                        text=(
                            f"{route.label} will remain traversable long enough for {boat_id} "
                            f"to reach {group.label}."
                        ),
                        grounding={
                            "route_id": route_id,
                            "asset_id": boat_id,
                            "group_id": group.group_id,
                            "arrival_time_s": prediction.arrival_time_s,
                        },
                        confidence=prediction.success_probability,
                        confidence_semantics="model-conditional plan success probability",
                    )
                    candidates.append((plan, prediction, claim))

            for helicopter_id in helicopters:
                helicopter = state.controller.known_assets[helicopter_id]
                if helicopter.capacity < int(group.people_waiting or group.people):
                    continue
                plan_id = f"air:{helicopter_id}:{group.group_id}"
                prediction = self._air_prediction(
                    state, plan_id=plan_id, asset_id=helicopter_id, group_id=group.group_id
                )
                cost = helicopter.operating_cost * prediction.arrival_time_s / 60.0
                utility = (
                    95.0 * prediction.success_probability
                    + 28.0 * urgency
                    - 40.0 * prediction.hazard_score
                    - 0.035 * prediction.arrival_time_s
                    - cost
                )
                action = ActionInstance(
                    action_type="dispatch_helicopter",
                    actor_id=helicopter_id,
                    destination=group.group_id,
                    parameters={
                        "people_count": int(group.people_waiting or group.people),
                        "deadline_s": group.deadline_s,
                        "group_id": group.group_id,
                    },
                )
                plan = PlanCandidate(
                    plan_id=plan_id,
                    name=f"Helicopter to {group.label}",
                    actions=(action,),
                    utility=utility,
                    reversible_first_action=False,
                    requires_authority=True,
                    metadata={
                        "group_id": group.group_id,
                        "asset_id": helicopter_id,
                        "cost": cost,
                    },
                )
                claim = Claim(
                    layer=ClaimLayer.PREDICTIVE,
                    text=f"{helicopter_id} can reach {group.label} safely within the deadline.",
                    grounding={
                        "asset_id": helicopter_id,
                        "group_id": group.group_id,
                        "arrival_time_s": prediction.arrival_time_s,
                    },
                    confidence=prediction.success_probability,
                    confidence_semantics="model-conditional air-rescue success probability",
                )
                candidates.append((plan, prediction, claim))

            # Ground teams are represented but deliberately conservative in flood water.
            for team_id in ground_teams:
                team = state.controller.known_assets[team_id]
                distance = _distance(team.position, group.position)
                arrival = distance / max(0.1, team.speed)
                water_risk = _clamp(state.truth.global_water_level / state.config.s2.route_closure_depth)
                support = _clamp(0.82 * (1.0 - 0.55 * water_risk))
                uncertainty = _clamp(state.config.s1.sensor_noise + 0.45 * (1.0 - support))
                plan_id = f"ground:{team_id}:{group.group_id}"
                prediction = PlanPrediction(
                    plan_id=plan_id,
                    success_probability=_clamp(0.80 - 0.62 * water_risk - 0.15 * uncertainty),
                    arrival_time_s=arrival,
                    hazard_score=_clamp(0.25 + 0.70 * water_risk),
                    resource_margin=team.resource - 0.15,
                    model_support=support,
                    out_of_distribution_score=_clamp(state.config.s1.ood_severity + 0.35 * water_risk),
                    uncertainty=uncertainty,
                    rollout_horizon=max(1, int(math.ceil(arrival / 60.0))),
                    assumptions=("model_conditional_prediction", "ground_access_is_continuous"),
                )
                action = ActionInstance(
                    action_type="deploy_ground_team",
                    actor_id=team_id,
                    destination=group.group_id,
                    parameters={"group_id": group.group_id, "people_count": int(group.people_waiting or group.people)},
                )
                plan = PlanCandidate(
                    plan_id=plan_id,
                    name=f"Ground team to {group.label}",
                    actions=(action,),
                    utility=(
                        80.0 * prediction.success_probability
                        + 22.0 * urgency
                        - 45.0 * prediction.hazard_score
                    ),
                    reversible_first_action=False,
                    requires_authority=True,
                    metadata={"group_id": group.group_id, "asset_id": team_id},
                )
                claim = Claim(
                    layer=ClaimLayer.PREDICTIVE,
                    text=f"{team_id} can reach {group.label} through the current flood conditions.",
                    grounding={"asset_id": team_id, "group_id": group.group_id},
                    confidence=prediction.success_probability,
                    confidence_semantics="model-conditional ground-team success probability",
                )
                candidates.append((plan, prediction, claim))

        return candidates

    def _evidence(
        self,
        state: WorkbenchState,
        plan: PlanCandidate,
        prediction: PlanPrediction,
        claim: Claim,
    ) -> WorldModelEvidence:
        route_id = plan.metadata.get("route_id")
        observation_age = self._route_age(state, route_id) if route_id else 0.0
        return WorldModelEvidence(
            encoder_version="surrogate-encoder-v1",
            fusion_version="dynamic-state-fusion-v1",
            predictor_version=self.predictor_version,
            semantic_probe_versions=(self.probe_version,),
            training_snapshot="dynamic-surrogate-no-training",
            observation_window_hash=sha256_value(
                {
                    "beliefs": {
                        key: value.model_dump(mode="json")
                        for key, value in state.controller.route_beliefs.items()
                    },
                    "time": state.truth.simulation_time,
                }
            ),
            fleet_state_hash=sha256_value(
                {
                    "assets": {
                        key: value.model_dump(mode="json")
                        for key, value in state.controller.known_assets.items()
                    },
                    "groups": {
                        key: value.model_dump(mode="json")
                        for key, value in state.controller.known_groups.items()
                    },
                }
            ),
            candidate_plan_id=plan.plan_id,
            action_schema_version="flood-actions-dynamic-v1",
            rollout_horizon=prediction.rollout_horizon,
            predicted_claims=(claim.text,),
            uncertainty=prediction.uncertainty,
            model_support=prediction.model_support,
            out_of_distribution_score=prediction.out_of_distribution_score,
            rollout_consistency=_clamp(1.0 - 0.60 * prediction.uncertainty),
            reachability_evidence={
                "predicted_success_probability": prediction.success_probability,
                "arrival_time_s": prediction.arrival_time_s,
                "hazard_score": prediction.hazard_score,
                "resource_margin": prediction.resource_margin,
            },
            calibration_version="surrogate-calibration-v1",
            assumptions=prediction.assumptions,
            observation_age_s=observation_age,
            decisively_contradicted=bool(
                route_id
                and route_id in state.controller.route_beliefs
                and state.controller.route_beliefs[route_id].status == "blocked"
                and claim.layer == ClaimLayer.PREDICTIVE
            ),
        )

    def assess(
        self, state: WorkbenchState, *, trigger_event_id: str | None = None
    ) -> list[AssessedCandidate]:
        self.refresh_policy(state)
        assessed: list[AssessedCandidate] = []
        for plan, prediction, claim in self.candidates(state):
            evidence = self._evidence(state, plan, prediction, claim)
            action = plan.first_action
            repair_hint = None
            if action.action_type in {
                "dispatch_rescue_boat",
                "evacuate_to_safety",
                "dispatch_helicopter",
                "deploy_ground_team",
            }:
                if action.route_id:
                    repair_hint = f"Verify {action.route_id} or choose a supported alternative."
                else:
                    repair_hint = "Wait for safer weather or choose a supported alternative asset."
            lineage_key = "|".join(
                [
                    claim.layer.value,
                    action.action_type,
                    action.actor_id,
                    str(action.route_id or "none"),
                    str(action.parameters.get("group_id") or action.destination or "none"),
                ]
            )
            record, evaluation = self.runtime.assess(
                claim=claim,
                evidence=evidence,
                action_name=action.action_type,
                reversible=plan.reversible_first_action,
                authority_present=state.config.commander_authority_present,
                repair_hint=repair_hint,
                lineage_key=lineage_key,
                trigger_event_id=trigger_event_id,
                metadata={
                    **plan.metadata,
                    "plan_id": plan.plan_id,
                    "plan_name": plan.name,
                    "utility": plan.utility,
                    "action": action.model_dump(mode="json"),
                    "prediction": prediction.model_dump(mode="json"),
                    "controller_version": self.version,
                },
            )
            consumed = self.runtime.consume(record, evaluation)

            truth_safe = True
            if action.route_id and action.route_id in state.truth.routes:
                truth_safe = state.truth.routes[action.route_id].open
            elif action.action_type == "dispatch_helicopter":
                asset = state.truth.assets[action.actor_id]
                truth_safe = state.truth.weather_severity <= asset.weather_tolerance

            false_clear = evaluation.decision.value in {"clear", "qualify"} and not truth_safe
            false_hold = evaluation.decision.value in {"hold", "block"} and truth_safe
            stale_clearance = False
            if action.route_id:
                belief = state.controller.route_beliefs[action.route_id]
                stale_clearance = bool(
                    belief.clearance_valid_until is not None
                    and state.truth.simulation_time > belief.clearance_valid_until
                    and evaluation.decision.value in {"clear", "qualify"}
                )

            assessed.append(
                AssessedCandidate(
                    plan=plan,
                    prediction=prediction,
                    record=consumed,
                    decision=evaluation.decision.value,
                    status=evaluation.status.value,
                    reason=evaluation.reason,
                    false_clear=false_clear,
                    false_hold=false_hold,
                    stale_clearance=stale_clearance,
                )
            )
        return assessed

    def select(self, state: WorkbenchState, assessed: list[AssessedCandidate]) -> AssessedCandidate | None:
        admissible = [item for item in assessed if item.decision in {"clear", "qualify"}]
        if not admissible:
            return None

        # Avoid spending an asset twice even if a stale plan remains in the list.
        # Evacuation is the deliberate exception to the empty-asset rule: a
        # boat carrying people must remain executable while it waits for a
        # separately authorized route to the safe transfer dock.
        def executable(item: AssessedCandidate) -> bool:
            action = item.plan.first_action
            asset = state.truth.assets.get(action.actor_id)
            if asset is None or asset.resource <= 0.05:
                return False
            if action.action_type == "evacuate_to_safety":
                return (
                    asset.passenger_count > 0
                    and asset.status in {
                        "awaiting_clearance",
                        "available",
                        "standby",
                    }
                )
            return (
                asset.passenger_count == 0
                and asset.status in {"available", "standby"}
            )

        admissible = [item for item in admissible if executable(item)]
        if not admissible:
            return None

        evacuations = [
            item
            for item in admissible
            if item.plan.metadata.get("kind") == "evacuation"
        ]
        if evacuations:
            return max(evacuations, key=lambda item: item.plan.utility)

        reconnaissance = [
            item
            for item in admissible
            if item.plan.first_action.action_type == "verify_route"
            and float(item.plan.metadata.get("voi", 0.0)) >= 0.20
        ]
        operator_requested = [
            item for item in reconnaissance if bool(item.plan.metadata.get("operator_requested"))
        ]
        if operator_requested:
            return max(operator_requested, key=lambda item: item.plan.utility)
        if reconnaissance:
            return max(reconnaissance, key=lambda item: item.plan.utility)

        budget = state.config.s3.mission_budget
        within_budget = [
            item for item in admissible if float(item.plan.metadata.get("cost", 0.0)) <= budget
        ]
        if not within_budget:
            return None
        return max(within_budget, key=lambda item: item.plan.utility)

    def revise_route_records(
        self,
        state: WorkbenchState,
        *,
        route_id: str,
        reported_status: str,
        truth_status: str,
        observation_event_id: str,
    ) -> list[TraceRecord]:
        revised: list[TraceRecord] = []
        latest_by_id: dict[str, TraceRecord] = {}
        for record in self.runtime.repository.all():
            latest_by_id[record.record_id] = max(
                record,
                latest_by_id.get(record.record_id, record),
                key=lambda item: item.record_version,
            )

        for record in latest_by_id.values():
            if record.metadata.get("route_id") != route_id:
                continue
            if record.metadata.get("action", {}).get("action_type") not in {
                "dispatch_rescue_boat",
                "evacuate_to_safety",
            }:
                continue
            predicted_probability = float(
                record.metadata.get("prediction", {}).get("success_probability", 0.5)
            )
            contradicted = reported_status == "blocked"
            if not contradicted:
                continue
            original_evidence = self.runtime.ledger.get(record.evidence_refs[0])
            realized = RealizedOutcome(
                action=ActionInstance.model_validate(record.metadata["action"]),
                success=False,
                observations={
                    "route_id": route_id,
                    "reported_status": reported_status,
                    "truth_status": truth_status,
                    "observation_event_id": observation_event_id,
                },
                reason="route_observation_contradicted_prediction",
            )
            revision_evidence = original_evidence.model_copy(
                update={
                    "evidence_id": f"{original_evidence.evidence_id}-revision-{record.record_version + 1}",
                    "decisively_contradicted": True,
                    "realized_outcome": realized.model_dump(mode="json"),
                    "prediction_residual": {
                        "predicted_success_probability": predicted_probability,
                        "realized_route_open": truth_status == "open",
                    },
                }
            )
            revised_record = self.runtime.revise_with_outcome(
                record,
                revision_evidence,
                new_status=TraceStatus.REJECT,
                reason="route observation contradicted the predictive premise",
                repair="Invalidate only plans licensed by this route premise and generate alternatives.",
            )
            revised.append(revised_record)
        return revised
