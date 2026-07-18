from __future__ import annotations

import math

from trace_jepa.workbench.models import (
    AssetState,
    EventType,
    EventVisibility,
    GroupState,
    PathSegment,
    Position,
    ReasoningCycle,
    ReasoningStep,
    RouteBelief,
    SimulationEvent,
    WorkbenchState,
)
from trace_jepa.workbench.beliefs import (
    OBSERVED_DEPTH_TOLERANCE_M,
    project_controller_route_depth,
)
from trace_jepa.workbench.randomness import keyed_standard_normal, keyed_uniform


def _hashed_uniform(*key_parts: object) -> float:
    """Compatibility wrapper for the supplied WP-E patch's test API."""

    if not key_parts:
        raise ValueError("at least one RNG key part is required")
    return keyed_uniform(str(key_parts[0]), *key_parts[1:])


def _hashed_gauss(*key_parts: object) -> float:
    """Compatibility wrapper for the supplied WP-E patch's test API."""

    if not key_parts:
        raise ValueError("at least one RNG key part is required")
    return keyed_standard_normal(str(key_parts[0]), *key_parts[1:])


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _pending_people(state: WorkbenchState) -> int:
    return sum(
        int(group.people_waiting or 0)
        for group in state.truth.groups.values()
        if not group.rescued and not group.cancelled
    )


def _onboard_people(state: WorkbenchState) -> int:
    return sum(asset.passenger_count for asset in state.truth.assets.values())


def _sync_asset(state: WorkbenchState, asset_id: str) -> None:
    if asset_id in state.truth.assets and asset_id in state.controller.known_assets:
        state.controller.known_assets[asset_id] = state.truth.assets[asset_id].model_copy(
            deep=True
        )


def _sync_group(state: WorkbenchState, group_id: str) -> None:
    if group_id in state.truth.groups and group_id in state.controller.known_groups:
        state.controller.known_groups[group_id] = state.truth.groups[group_id].model_copy(
            deep=True
        )


def _refresh_route_edges(state: WorkbenchState) -> None:
    """Update edge-level traversability from water and fixed debris."""

    for route in state.truth.routes.values():
        count = max(0, len(route.waypoints) - 1)
        if route.water_depth >= state.config.s2.route_closure_depth:
            route.edge_open = [False] * count
        else:
            route.edge_open = [True] * count
            if route.debris_blocked and route.blocked_segment_index is not None:
                if 0 <= route.blocked_segment_index < count:
                    route.edge_open[route.blocked_segment_index] = False
        route.open = bool(route.edge_open) and all(route.edge_open)


def apply_event(state: WorkbenchState, event: SimulationEvent) -> None:
    """Apply one immutable event to the mutable workbench state."""

    state.metrics.events += 1
    payload = event.payload

    if event.event_type == EventType.RUN_STARTED:
        state.running = True
        return
    if event.event_type == EventType.RUN_PAUSED:
        state.running = False
        return

    if event.event_type == EventType.TICK:
        dt = float(payload.get("dt", 1.0))
        if not math.isfinite(dt) or dt <= 0.0:
            raise ValueError("TICK dt must be finite and strictly positive")
        state.truth.simulation_time += dt
        state.controller.simulation_time = state.truth.simulation_time

        s2 = state.config.s2
        forcing = 0.25 + 0.75 * s2.rain_intensity + 0.85 * s2.upstream_inflow
        if s2.forcing_noise_std == 0.0:
            # This branch intentionally preserves the pre-WP-E arithmetic and
            # event payloads exactly for the zero-noise compatibility oracle.
            state.truth.global_water_level += dt * s2.water_rise_rate * forcing
            for route in state.truth.routes.values():
                route.water_depth += (
                    dt * s2.water_rise_rate * forcing * route.susceptibility
                )
        else:
            # One common regional forcing innovation is shared across routes.
            # Euler--Maruyama requires sqrt(dt), so increment variance is
            # sigma^2 * dt rather than sigma^2 * dt^2.
            innovation = float(payload["forcing_noise_z"])
            if not math.isfinite(innovation):
                raise ValueError("forcing_noise_z must be finite")
            stochastic_increment = (
                s2.water_rise_rate
                * s2.forcing_noise_std
                * math.sqrt(dt)
                * innovation
            )
            state.truth.global_water_level = max(
                0.0,
                state.truth.global_water_level
                + dt * s2.water_rise_rate * forcing
                + stochastic_increment,
            )
            for route in state.truth.routes.values():
                route.water_depth = max(
                    0.0,
                    route.water_depth
                    + dt
                    * s2.water_rise_rate
                    * forcing
                    * route.susceptibility
                    + stochastic_increment * route.susceptibility,
                )
        state.truth.environment_tick_index += 1
        _refresh_route_edges(state)

        for group in state.truth.groups.values():
            if group.rescued or group.cancelled or group.rescue_phase in {
                "onboard",
                "delivered",
                "cancelled",
            }:
                continue
            deterioration = dt * (0.00002 + state.truth.global_water_level * 0.000035)
            group.severity = _clamp(group.severity + deterioration, 0.0, 1.0)
            if group.severity >= 0.85:
                group.condition = "critical"
            elif group.severity >= 0.65:
                group.condition = "deteriorating"

        state.metrics.max_water_depth = max(
            [route.water_depth for route in state.truth.routes.values()] + [0.0]
        )
        state.metrics.pending_people = _pending_people(state)
        state.metrics.onboard_people = _onboard_people(state)
        return

    if event.event_type == EventType.SET_S1_PARAMETERS:
        state.config.s1 = state.config.s1.model_copy(update=payload)
        return
    if event.event_type == EventType.SET_S2_PARAMETERS:
        state.config.s2 = state.config.s2.model_copy(update=payload)
        _refresh_route_edges(state)
        return
    if event.event_type == EventType.SET_S3_PARAMETERS:
        state.config.s3 = state.config.s3.model_copy(update=payload)
        return
    if event.event_type == EventType.SET_S5_PARAMETERS:
        state.config.s5 = state.config.s5.model_copy(update=payload)
        return

    if event.event_type == EventType.REQUEST_SURVEY:
        route_id = str(payload["route_id"])
        if route_id not in state.controller.requested_surveys:
            state.controller.requested_surveys.append(route_id)
        request_id = payload.get("evidence_request_id")
        if request_id is not None and not any(
            item.get("evidence_request_id") == request_id
            for item in state.controller.pending_evidence
        ):
            state.controller.pending_evidence.append(
                {
                    "evidence_request_id": str(request_id),
                    "refresh_decision_id": payload.get("refresh_decision_id"),
                    "channel": "drone_survey",
                    "route_id": route_id,
                    "requested_at": state.truth.simulation_time,
                }
            )
        return

    if event.event_type == EventType.GAUGE_POLL:
        request_id = str(payload["evidence_request_id"])
        if not any(
            item.get("evidence_request_id") == request_id
            for item in state.controller.pending_evidence
        ):
            # Never expose the sampled truth value before its declared delivery.
            state.controller.pending_evidence.append(
                {
                    "evidence_request_id": request_id,
                    "channel": "gauge_poll",
                    "route_id": str(payload["route_id"]),
                    "requested_at": float(payload["requested_at"]),
                    "deliver_at": float(payload["deliver_at"]),
                }
            )
        return

    if event.event_type == EventType.EVIDENCE_ACQUIRED:
        request_id = payload.get("evidence_request_id")
        if request_id is not None:
            state.controller.pending_evidence = [
                item
                for item in state.controller.pending_evidence
                if item.get("evidence_request_id") != request_id
            ]
        route_id = payload.get("route_id")
        if route_id is not None:
            state.controller.last_refresh_acquired_at[str(route_id)] = (
                state.truth.simulation_time
            )
        return

    if event.event_type in {
        EventType.REFRESH_TRIGGERED,
        EventType.AUTH_WITHDRAWN,
    }:
        return

    if event.event_type == EventType.COMMANDER_AUTHORITY:
        state.config.commander_authority_present = bool(payload.get("present", True))
        return

    if event.event_type == EventType.EMERGENCY_CALL:
        group_id = str(payload.get("group_id", "group_emergency"))
        position = Position.model_validate(
            payload.get("position", {"x": 88.0, "y": 66.0})
        )
        people = int(payload.get("people", 1))
        safe_location_id = str(
            payload.get("safe_location_id", state.config.rescue.safe_location_id)
        )

        if group_id in state.truth.groups:
            group = state.truth.groups[group_id]
            # The call form reports the current number still waiting. A repeat
            # call updates the active incident instead of adding another marker.
            # If a boat is already assigned, preserve that assignment and let the
            # next plan cycle decide whether its capacity still suffices.
            previous_phase = group.rescue_phase
            previous_assignment = group.assigned_asset_id
            group.label = str(payload.get("location_label", group.label))
            group.position = position
            group.people = people
            group.people_waiting = people
            group.people_onboard = 0
            group.people_delivered = 0
            group.severity = float(payload.get("severity", group.severity))
            group.deadline_s = float(payload.get("deadline_s", group.deadline_s))
            group.rescued = False
            group.cancelled = False
            group.condition = (
                "critical"
                if group.severity >= 0.85
                else "deteriorating" if group.severity >= 0.65 else "stable"
            )
            group.rescue_phase = (
                "assigned" if previous_phase == "assigned" else "waiting"
            )
            group.safe_location_id = safe_location_id
            group.assigned_asset_id = (
                previous_assignment if previous_phase == "assigned" else None
            )
            group.alert_count += 1
            group.last_alert_at = state.truth.simulation_time
            group.source_call_id = str(payload.get("call_id", event.event_id))
            _sync_group(state, group_id)
        else:
            group = GroupState(
                group_id=group_id,
                label=str(payload.get("location_label", "Emergency location")),
                position=position,
                people=people,
                people_waiting=people,
                severity=float(payload.get("severity", 0.55)),
                deadline_s=float(payload.get("deadline_s", 1200.0)),
                discovered=True,
                safe_location_id=safe_location_id,
                last_alert_at=state.truth.simulation_time,
                source_call_id=str(payload.get("call_id", event.event_id)),
            )
            state.truth.groups[group_id] = group
            state.controller.known_groups[group_id] = group.model_copy(deep=True)

        state.metrics.pending_people = _pending_people(state)
        return

    if event.event_type == EventType.INCIDENT_MERGED:
        group_id = str(payload["group_id"])
        if group_id not in state.truth.groups:
            raise KeyError(f"cannot merge alert into unknown incident {group_id}")
        group = state.truth.groups[group_id]
        added = int(payload.get("people_added", payload.get("people", 0)))
        group.people += added
        group.people_waiting = int(group.people_waiting or 0) + added
        group.alert_count += 1
        group.last_alert_at = state.truth.simulation_time
        group.severity = max(group.severity, float(payload.get("severity", group.severity)))
        group.deadline_s = min(group.deadline_s, float(payload.get("deadline_s", group.deadline_s)))
        group.label = str(payload.get("location_label", group.label))
        if group.cancelled or group.rescued:
            group.cancelled = False
            group.rescued = False
            group.condition = "stable"
            group.rescue_phase = "waiting"
        _sync_group(state, group_id)
        state.metrics.pending_people = _pending_people(state)
        return

    if event.event_type == EventType.ADD_GROUP:
        group = GroupState.model_validate(payload)
        state.truth.groups[group.group_id] = group
        if event.visibility in {EventVisibility.BOTH, EventVisibility.CONTROLLER}:
            state.controller.known_groups[group.group_id] = group.model_copy(deep=True)
        state.metrics.pending_people = _pending_people(state)
        return

    if event.event_type == EventType.UPDATE_GROUP:
        group_id = str(payload["group_id"])
        updates = dict(payload.get("updates", {}))
        if group_id in state.truth.groups:
            state.truth.groups[group_id] = state.truth.groups[group_id].model_copy(
                update=updates
            )
        if (
            event.visibility in {EventVisibility.BOTH, EventVisibility.CONTROLLER}
            and group_id in state.controller.known_groups
        ):
            state.controller.known_groups[group_id] = state.controller.known_groups[
                group_id
            ].model_copy(update=updates)
        state.metrics.pending_people = _pending_people(state)
        return

    if event.event_type == EventType.INCIDENT_CANCELLED:
        group_id = str(payload["group_id"])
        if group_id in state.truth.groups:
            group = state.truth.groups[group_id]
            group.cancelled = True
            group.condition = "cancelled"
            group.rescue_phase = "cancelled"
            group.people_waiting = 0
            group.assigned_asset_id = None
            _sync_group(state, group_id)
        state.metrics.pending_people = _pending_people(state)
        return

    if event.event_type == EventType.ADD_ASSET:
        asset = AssetState.model_validate(payload)
        if asset.home_position is None:
            asset.home_position = asset.position
        if asset.safe_position is None:
            asset.safe_position = asset.home_position
        state.truth.assets[asset.asset_id] = asset
        if event.visibility in {EventVisibility.BOTH, EventVisibility.CONTROLLER}:
            state.controller.known_assets[asset.asset_id] = asset.model_copy(deep=True)
        return

    if event.event_type == EventType.UPDATE_ASSET:
        asset_id = str(payload["asset_id"])
        updates = dict(payload.get("updates", {}))
        if asset_id in state.truth.assets:
            state.truth.assets[asset_id] = state.truth.assets[asset_id].model_copy(
                update=updates
            )
        if asset_id in state.controller.known_assets:
            state.controller.known_assets[asset_id] = state.controller.known_assets[
                asset_id
            ].model_copy(update=updates)
        return

    if event.event_type == EventType.INJECT_SHOCK:
        shock = str(payload.get("shock_type", "unknown"))
        severity = _clamp(float(payload.get("severity", 0.5)), 0.0, 1.0)
        target = payload.get("target")
        state.truth.last_shock = shock

        if shock == "communication_loss":
            state.truth.communications_available = False
        elif shock == "communication_restore":
            state.truth.communications_available = True
        elif shock == "sensor_degradation":
            state.config.s1.drone_report_accuracy = _clamp(
                state.config.s1.drone_report_accuracy - 0.45 * severity,
                0.05,
                1.0,
            )
            state.config.s1.sensor_noise = _clamp(
                state.config.s1.sensor_noise + 0.45 * severity,
                0.0,
                1.0,
            )
        elif shock == "levee_breach":
            state.truth.global_water_level += 0.30 * severity
            for route in state.truth.routes.values():
                route.water_depth += 0.45 * severity * route.susceptibility
            _refresh_route_edges(state)
        elif shock == "road_submergence":
            route_id = str(target or "south_detour")
            if route_id in state.truth.routes:
                state.truth.routes[route_id].water_depth = max(
                    state.truth.routes[route_id].water_depth,
                    state.config.s2.route_closure_depth + 0.05 + 0.25 * severity,
                )
                _refresh_route_edges(state)
        elif shock == "wind_shift":
            state.truth.weather_severity = _clamp(
                state.truth.weather_severity + 0.55 * severity,
                0.0,
                1.0,
            )
        elif shock == "group_deterioration":
            group_id = str(target or next(iter(state.truth.groups), ""))
            if group_id in state.truth.groups:
                group = state.truth.groups[group_id]
                group.severity = _clamp(group.severity + 0.50 * severity, 0.0, 1.0)
                group.condition = (
                    "critical" if group.severity >= 0.85 else "deteriorating"
                )
        elif shock == "asset_grounded":
            asset_id = str(target or "survey_drone_1")
            if asset_id in state.truth.assets:
                state.truth.assets[asset_id].status = "grounded"
                _sync_asset(state, asset_id)
        elif shock == "fuel_limit":
            asset_id = str(target or "rescue_boat_1")
            if asset_id in state.truth.assets:
                state.truth.assets[asset_id].resource = min(
                    state.truth.assets[asset_id].resource,
                    max(0.05, 0.40 * (1.0 - severity)),
                )
                _sync_asset(state, asset_id)
        return

    if event.event_type == EventType.OBSERVATION:
        kind = str(payload.get("kind", "route"))
        if kind == "route":
            route_id = str(payload["route_id"])
            status = str(payload["reported_status"])
            confidence = float(payload.get("confidence", 0.8))
            observed_at = float(payload.get("observed_at", state.truth.simulation_time))
            known_route = (
                route_id in state.truth.routes
                and route_id in state.controller.route_beliefs
            )
            projected_depth = (
                project_controller_route_depth(state, route_id, observed_at)
                if known_route
                else None
            )
            projected_status = (
                "open"
                if projected_depth is not None
                and projected_depth < state.config.s2.route_closure_depth
                else "blocked"
            )
            categorical_innovation = (
                float(status != projected_status)
                if known_route and status in {"open", "blocked"}
                else None
            )
            representative_depth = projected_depth
            if status == "open" and projected_depth is not None:
                representative_depth = min(
                    projected_depth,
                    state.config.s2.route_closure_depth - 1e-9,
                )
            elif status == "blocked" and projected_depth is not None:
                representative_depth = max(
                    projected_depth,
                    state.config.s2.route_closure_depth,
                )
            state.controller.route_beliefs[route_id] = RouteBelief(
                route_id=route_id,
                status=status if status in {"open", "blocked", "unknown"} else "unknown",
                confidence=_clamp(confidence, 0.0, 1.0),
                observed_at=observed_at,
                source=str(payload.get("source", "sensor")),
                clearance_valid_until=(
                    observed_at + state.config.s2.clearance_horizon_s
                    if status == "open"
                    else None
                ),
                report_id=event.event_id,
                blocked_segment_index=payload.get("blocked_segment_index"),
                water_depth=representative_depth,
                depth_observed_at=observed_at,
                observed_innovation=categorical_innovation,
                innovation_tolerance=(
                    0.5 if categorical_innovation is not None else None
                ),
                innovation_received_at=state.truth.simulation_time,
            )
        elif kind == "route_depth":
            route_id = str(payload["route_id"])
            depth = max(0.0, float(payload["water_depth"]))
            observed_at = float(payload["observed_at"])
            expected_depth = project_controller_route_depth(
                state, route_id, observed_at
            )
            status = (
                "open"
                if depth < state.config.s2.route_closure_depth
                else "blocked"
            )
            state.controller.route_beliefs[route_id] = RouteBelief(
                route_id=route_id,
                status=status,
                confidence=1.0,
                observed_at=observed_at,
                source=str(payload.get("source", "gauge_poll")),
                clearance_valid_until=(
                    observed_at + state.config.s2.clearance_horizon_s
                    if status == "open"
                    else None
                ),
                report_id=event.event_id,
                blocked_segment_index=(
                    state.controller.route_beliefs[route_id].blocked_segment_index
                    if route_id in state.controller.route_beliefs
                    else None
                ),
                water_depth=depth,
                depth_observed_at=observed_at,
                observed_innovation=depth - expected_depth,
                innovation_tolerance=OBSERVED_DEPTH_TOLERANCE_M,
                innovation_received_at=state.truth.simulation_time,
            )
        elif kind == "group":
            group = GroupState.model_validate(payload["group"])
            state.controller.known_groups[group.group_id] = group
        return

    if event.event_type == EventType.BELIEF_UPDATE:
        route_id = payload.get("route_id")
        if route_id and route_id in state.controller.route_beliefs:
            state.controller.route_beliefs[str(route_id)] = state.controller.route_beliefs[
                str(route_id)
            ].model_copy(update=payload.get("updates", {}))
        return

    if event.event_type == EventType.ACTION_STARTED:
        asset_id = str(payload["asset_id"])
        asset = state.truth.assets[asset_id]
        asset.status = "moving"
        asset.action_type = str(payload["action_type"])
        asset.mission_phase = {
            "verify_route": "surveying",
            "dispatch_rescue_boat": "outbound",
            "evacuate_to_safety": "evacuating",
            "return_to_base": "returning",
        }.get(asset.action_type, "outbound")
        asset.assigned_group_id = payload.get("group_id")
        asset.assigned_route_id = payload.get("route_id")
        asset.path = [Position.model_validate(item) for item in payload.get("path", [])]
        asset.path_segments = [
            PathSegment.model_validate(item) for item in payload.get("path_segments", [])
        ]
        asset.path_index = 0
        asset.target = Position.model_validate(payload["target"])
        asset.action_started_at = state.truth.simulation_time
        asset.authorization_record_id = payload.get("record_id")
        asset.authorization_record_version = payload.get("record_version")
        asset.interruption_reason = None
        _sync_asset(state, asset_id)

        state.metrics.commitments += 1
        state.controller.active_commitments.append(dict(payload))
        if asset.action_type == "verify_route":
            state.metrics.reconnaissance_sorties += 1
            if asset.assigned_route_id in state.controller.requested_surveys:
                state.controller.requested_surveys.remove(asset.assigned_route_id)

        group_id = asset.assigned_group_id
        if group_id and group_id in state.truth.groups:
            group = state.truth.groups[group_id]
            if group.assigned_asset_id not in {None, asset_id}:
                state.metrics.double_commitment_violations += 1
            group.assigned_asset_id = asset_id
            if group.rescue_phase == "waiting":
                group.rescue_phase = "assigned"
            _sync_group(state, group_id)
        return

    if event.event_type == EventType.ASSET_MOVED:
        asset_id = str(payload["asset_id"])
        if asset_id not in state.truth.assets:
            return
        asset = state.truth.assets[asset_id]
        previous = asset.position
        asset.position = Position.model_validate(payload["position"])
        dx = asset.position.x - previous.x
        dy = asset.position.y - previous.y
        if abs(dx) + abs(dy) > 1e-9:
            asset.heading_degrees = math.degrees(math.atan2(dy, dx))
        asset.resource = _clamp(
            float(payload.get("resource", asset.resource)),
            0.0,
            1.0,
        )
        asset.path_index = int(payload.get("path_index", asset.path_index))
        if asset.resource <= 0.001:
            asset.status = "depleted"

        # Do not move the incident marker with the boat. The group position is
        # the pickup location recorded by the call; people in transit are
        # represented by the boat's passenger manifest and onboard badge.
        # Keeping those concepts separate also makes partial pickup legible:
        # remaining people stay visible at the incident while boarded people
        # move with the asset.
        _sync_asset(state, asset_id)
        return

    if event.event_type == EventType.BOARDING_STARTED:
        asset_id = str(payload["asset_id"])
        group_id = str(payload["group_id"])
        if asset_id in state.truth.assets:
            asset = state.truth.assets[asset_id]
            asset.status = "loading"
            asset.mission_phase = "loading"
            asset.path = []
            asset.path_segments = []
            asset.path_index = 0
            asset.target = None
            _sync_asset(state, asset_id)
        if group_id in state.truth.groups:
            group = state.truth.groups[group_id]
            group.rescue_phase = "boarding"
            # If capacity forced a partial pickup, release the incident so a
            # second asset may be allocated to the people still waiting. The
            # onboard cohort remains attributable through the boat manifest.
            group.assigned_asset_id = (
                asset_id if int(group.people_waiting or 0) == 0 else None
            )
            _sync_group(state, group_id)
        return

    if event.event_type == EventType.PEOPLE_PICKED_UP:
        asset_id = str(payload["asset_id"])
        group_id = str(payload["group_id"])
        requested = int(payload.get("people", 0))
        if asset_id in state.truth.assets and group_id in state.truth.groups:
            asset = state.truth.assets[asset_id]
            group = state.truth.groups[group_id]
            boarded = min(
                requested,
                int(group.people_waiting or 0),
                max(0, asset.capacity - asset.passenger_count),
            )
            group.people_waiting = max(0, int(group.people_waiting or 0) - boarded)
            group.people_onboard += boarded
            group.rescue_phase = (
                "onboard" if group.people_waiting == 0 else "partially_rescued"
            )
            group.assigned_asset_id = asset_id
            asset.passenger_count += boarded
            if group_id not in asset.passenger_group_ids:
                asset.passenger_group_ids.append(group_id)
            asset.safe_location_id = (
                group.safe_location_id or state.config.rescue.safe_location_id
            )
            asset.status = "awaiting_clearance"
            asset.mission_phase = "awaiting_evacuation"
            asset.action_type = None
            asset.assigned_route_id = None
            asset.path = []
            asset.path_segments = []
            asset.path_index = 0
            asset.target = None
            _sync_asset(state, asset_id)
            _sync_group(state, group_id)
        state.metrics.pending_people = _pending_people(state)
        state.metrics.onboard_people = _onboard_people(state)
        return

    if event.event_type == EventType.UNLOADING_STARTED:
        asset_id = str(payload["asset_id"])
        if asset_id in state.truth.assets:
            asset = state.truth.assets[asset_id]
            asset.status = "unloading"
            asset.mission_phase = "unloading"
            asset.path = []
            asset.path_segments = []
            asset.path_index = 0
            asset.target = None
            _sync_asset(state, asset_id)
        return

    if event.event_type == EventType.PEOPLE_DELIVERED:
        asset_id = str(payload["asset_id"])
        delivered = 0
        if asset_id in state.truth.assets:
            asset = state.truth.assets[asset_id]
            for group_id in list(asset.passenger_group_ids):
                if group_id not in state.truth.groups:
                    continue
                group = state.truth.groups[group_id]
                count = group.people_onboard
                delivered += count
                group.people_onboard = 0
                group.people_delivered += count
                group.rescued = group.people_delivered == group.people
                group.condition = "rescued" if group.rescued else group.condition
                group.rescue_phase = "delivered" if group.rescued else "waiting"
                group.assigned_asset_id = None
                group.safe_location_id = (
                    asset.safe_location_id or state.config.rescue.safe_location_id
                )
                _sync_group(state, group_id)

            asset.passenger_count = 0
            asset.passenger_group_ids = []
            asset.assigned_group_id = None
            asset.assigned_route_id = None
            asset.action_type = None
            asset.path = []
            asset.path_segments = []
            asset.path_index = 0
            asset.target = None
            asset.status = (
                "standby"
                if state.config.rescue.post_rescue_policy
                == "standby_at_safe_location"
                else "available"
            )
            asset.mission_phase = "standby" if asset.status == "standby" else "idle"
            _sync_asset(state, asset_id)

        state.metrics.rescued_people += delivered
        state.metrics.pending_people = _pending_people(state)
        state.metrics.onboard_people = _onboard_people(state)
        return

    if event.event_type == EventType.ASSET_STANDBY:
        asset_id = str(payload["asset_id"])
        if asset_id in state.truth.assets:
            state.truth.assets[asset_id].status = "standby"
            state.truth.assets[asset_id].mission_phase = "standby"
            _sync_asset(state, asset_id)
        return

    if event.event_type == EventType.ACTION_INTERRUPTED:
        asset_id = str(payload["asset_id"])
        if asset_id in state.truth.assets:
            asset = state.truth.assets[asset_id]
            if payload.get("position") is not None:
                asset.position = Position.model_validate(payload["position"])
            asset.status = (
                "awaiting_clearance"
                if asset.passenger_count > 0 and asset.resource > 0.001
                else "available" if asset.resource > 0.001 else "depleted"
            )
            asset.mission_phase = (
                "awaiting_evacuation" if asset.passenger_count > 0 else "idle"
            )
            asset.interruption_reason = str(
                payload.get("reason", "path_unavailable")
            )
            group_id = asset.assigned_group_id
            asset.action_type = None
            asset.assigned_route_id = None
            if asset.passenger_count == 0:
                asset.assigned_group_id = None
            asset.path = []
            asset.path_segments = []
            asset.path_index = 0
            asset.target = None
            if group_id and group_id in state.truth.groups and asset.passenger_count == 0:
                state.truth.groups[group_id].assigned_asset_id = None
                state.truth.groups[group_id].rescue_phase = "waiting"
                _sync_group(state, group_id)
            _sync_asset(state, asset_id)
        state.metrics.route_interruptions += 1
        return

    if event.event_type == EventType.ACTION_COMPLETED:
        asset_id = str(payload["asset_id"])
        state.controller.active_commitments = [
            item
            for item in state.controller.active_commitments
            if item.get("asset_id") != asset_id
        ]
        if asset_id in state.truth.assets:
            asset = state.truth.assets[asset_id]
            asset.status = (
                "awaiting_clearance"
                if asset.passenger_count > 0 and asset.resource > 0.001
                else "available" if asset.resource > 0.001 else "depleted"
            )
            asset.mission_phase = (
                "awaiting_evacuation" if asset.passenger_count > 0 else "idle"
            )
            asset.action_type = None
            asset.assigned_route_id = None
            if asset.passenger_count == 0:
                asset.assigned_group_id = None
            asset.path = []
            asset.path_segments = []
            asset.path_index = 0
            asset.target = None
            asset.interruption_reason = None
            _sync_asset(state, asset_id)
        return

    if event.event_type == EventType.PLAN_CYCLE:
        state.controller.last_plan_cycle_at = state.truth.simulation_time
        return
    if event.event_type == EventType.PLAN_PROPOSED:
        return
    if event.event_type == EventType.PLAN_SELECTED:
        state.controller.last_selected_plan = dict(payload)
        return

    if event.event_type == EventType.TRACE_WRITTEN:
        state.metrics.trace_records += 1
        state.metrics.last_model_support = payload.get("model_support")
        state.metrics.last_ood_score = payload.get("ood_score")
        state.metrics.last_uncertainty = payload.get("uncertainty")
        state.controller.pending_claims.append(dict(payload))
        state.controller.pending_claims = state.controller.pending_claims[-30:]
        return

    if event.event_type == EventType.COMMITMENT_DECISION:
        decision = str(payload.get("decision", "hold"))
        if decision == "clear":
            state.metrics.clears += 1
        elif decision == "qualify":
            state.metrics.qualifies += 1
        elif decision == "hold":
            state.metrics.holds += 1
        elif decision == "block":
            state.metrics.blocks += 1
        elif decision == "escalate":
            state.metrics.escalations += 1
        if payload.get("false_clear"):
            state.metrics.false_clears += 1
        if payload.get("false_hold"):
            state.metrics.false_holds += 1
        if payload.get("stale_clearance"):
            state.metrics.stale_clearance_actions += 1
        return

    if event.event_type == EventType.REVISION:
        state.metrics.revisions += 1
        if payload.get("reason") != "parameter_or_state_change":
            state.controller.contradiction_count += 1
        if payload.get("reason") == "parameter_or_state_change":
            state.metrics.parameter_revisions += 1
        return

    if event.event_type == EventType.LOCAL_REPAIR:
        state.metrics.local_repairs += 1
        return

    if event.event_type == EventType.OUTCOME:
        if not bool(payload.get("metrics_already_applied", False)):
            state.metrics.rescued_people += int(payload.get("rescued_people", 0))
        state.metrics.pending_people = _pending_people(state)
        state.metrics.onboard_people = _onboard_people(state)
        return

    if event.event_type == EventType.METRIC_UPDATE:
        for key, value in payload.items():
            if hasattr(state.metrics, key):
                setattr(state.metrics, key, value)
        return

    if event.event_type == EventType.REASONING_STARTED:
        state.controller.latest_reasoning = ReasoningCycle.model_validate(payload["cycle"])
        return

    if event.event_type == EventType.REASONING_STEP:
        if state.controller.latest_reasoning is None:
            return
        state.controller.latest_reasoning.steps.append(
            ReasoningStep.model_validate(payload["step"])
        )
        return

    if event.event_type == EventType.REASONING_COMPLETED:
        if state.controller.latest_reasoning is None:
            return
        cycle = state.controller.latest_reasoning
        cycle.completed = True
        cycle.affected_record_ids = list(payload.get("affected_record_ids", []))
        cycle.selected_plan_id = payload.get("selected_plan_id")
        cycle.selected_plan_name = payload.get("selected_plan_name")
        cycle.decision_change = payload.get("decision_change")
        state.controller.reasoning_history.append(cycle.model_copy(deep=True))
        state.controller.reasoning_history = state.controller.reasoning_history[-30:]
        return

    # ROUTE_STATUS_CHANGED and audit-only notes do not mutate additional
    # state; their causal mutations are represented by the event that preceded
    # them. INCIDENT_MERGED is handled above because it changes waiting counts.
