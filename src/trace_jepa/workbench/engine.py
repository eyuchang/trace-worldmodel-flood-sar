from __future__ import annotations

import asyncio
import json
import math
import random
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from trace_jepa.refresh import RefreshDecision, RefreshMode, RefreshPolicy
from trace_jepa.runtime import (
    CommitmentLog,
    EvidenceLedger,
    PolicyConfig,
    PolicyEngine,
    TraceRepository,
    TraceRuntime,
)
from trace_jepa.util import new_id
from trace_jepa.workbench.controller import DynamicMissionController
from trace_jepa.workbench.navigation import (
    NavigationError,
    plan_route_constrained_action,
    truth_edge_open,
)
from trace_jepa.workbench.models import (
    EventType,
    EventVisibility,
    Position,
    ReasoningCycle,
    ReasoningStep,
    ScenarioLevel,
    SimulationEvent,
    WorkbenchSnapshot,
    WorkbenchState,
)
from trace_jepa.workbench.reducer import apply_event
from trace_jepa.workbench.randomness import (
    RNG_SCHEMA_VERSION,
    SEED_NAMESPACE,
    keyed_standard_normal,
    keyed_uniform,
)
from trace_jepa.workbench.scenario import load_initial_state
from trace_jepa.workbench.store import EventStore

if TYPE_CHECKING:
    from trace_jepa.worldmodels.contracts import RouteWorldModel
    from trace_jepa.worldmodels.live_support import LiveSupportingInferenceBridge
    from trace_jepa.worldmodels.simulator_observations import (
        SimulatorVisualObservationStore,
    )
    from trace_jepa.worldmodels.versioning import ModelRegistry


Subscriber = Callable[[WorkbenchSnapshot], Awaitable[None]]


def _distance(a: Position, b: Position) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def _move_toward(a: Position, b: Position, distance: float) -> Position:
    total = _distance(a, b)
    if total <= distance or total <= 1e-9:
        return b
    ratio = distance / total
    return Position(x=a.x + (b.x - a.x) * ratio, y=a.y + (b.y - a.y) * ratio)


class DynamicRun:
    """Event-sourced dynamic Flood-SAR simulation with TRACE gating.

    D0.2 Step 2 is deliberately transparent: the world model is a computed surrogate,
    while the API, UI event path, state separation, TRACE repository, replay,
    S1-S5 controls, and visualization contracts are already operational.
    """

    def __init__(
        self,
        *,
        run_id: str | None = None,
        scenario_path: str | Path,
        artifact_root: str | Path,
        refresh_scheduler: RefreshPolicy | None = None,
        epsilon_c: float = 1.0,
        route_world_model: RouteWorldModel | None = None,
        supporting_world_model: LiveSupportingInferenceBridge | None = None,
        wait_for_supporting_inference: bool = False,
        supporting_inference_timeout_s: float = 120.0,
        model_registry: ModelRegistry | None = None,
        visual_observation_store: SimulatorVisualObservationStore | None = None,
        observation_episode_id: str | None = None,
        observation_study_partition: str = "development",
        test_authorization_manifest: str | Path | None = None,
    ) -> None:
        self.run_id = run_id or new_id("run")
        self.scenario_path = Path(scenario_path)
        self.artifact_root = Path(artifact_root) / self.run_id
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self.event_store = EventStore(self.artifact_root / "events" / "simulation.jsonl")
        self._initial_state = load_initial_state(self.run_id, self.scenario_path)
        self.state = self._initial_state.model_copy(deep=True)
        self.recent_events: deque[SimulationEvent] = deque(maxlen=100)
        self._subscribers: list[Subscriber] = []
        self._scheduled: list[dict[str, Any]] = []
        self._refresh_request_context: dict[str, dict[str, Any]] = {}
        self._rng = random.Random(self.state.config.s1.seed)
        self._lock = asyncio.Lock()
        self._plan_requested = True
        self.visual_observation_store = visual_observation_store
        self.observation_episode_id = observation_episode_id or self.run_id
        if observation_study_partition not in {"development", "test"}:
            raise ValueError("observation_study_partition must be development or test")
        if observation_study_partition == "test":
            from trace_jepa.worldmodels.simulator_observations import (
                validate_test_authorization,
            )

            validate_test_authorization(
                Path(test_authorization_manifest)
                if test_authorization_manifest is not None
                else None
            )
        self.observation_study_partition = observation_study_partition

        policy = PolicyEngine(
            PolicyConfig.from_yaml(
                Path(__file__).resolve().parents[3] / "configs" / "policies" / "trace_v1.yaml"
            )
        )
        self.runtime = TraceRuntime(
            repository=TraceRepository(self.artifact_root / "records" / "trace.jsonl"),
            ledger=EvidenceLedger(self.artifact_root / "evidence"),
            commitments=CommitmentLog(self.artifact_root / "commitments" / "commitments.jsonl"),
            policy=policy,
        )
        self.controller = DynamicMissionController(
            self.runtime,
            refresh_scheduler=refresh_scheduler,
            epsilon_c=epsilon_c,
            route_world_model=route_world_model,
            supporting_world_model=supporting_world_model,
            wait_for_supporting_inference=wait_for_supporting_inference,
            supporting_inference_timeout_s=supporting_inference_timeout_s,
            model_registry=model_registry,
        )
        self.emit(
            EventType.RUN_CREATED,
            source="workbench",
            payload={
                "scenario_path": str(self.scenario_path),
                "version": "D0.2-step03",
            },
        )

    @property
    def sequence(self) -> int:
        return len(self.event_store.all())

    def subscribe(self, callback: Subscriber) -> None:
        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Subscriber) -> None:
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    async def _broadcast(self) -> None:
        if not self._subscribers:
            return
        snapshot = self.snapshot()
        stale: list[Subscriber] = []
        for callback in list(self._subscribers):
            try:
                await callback(snapshot)
            except Exception:
                stale.append(callback)
        for callback in stale:
            self.unsubscribe(callback)

    def emit(
        self,
        event_type: EventType | str,
        *,
        source: str,
        payload: dict[str, Any] | None = None,
        scenario_level: ScenarioLevel | str = ScenarioLevel.CORE,
        visibility: EventVisibility | str = EventVisibility.BOTH,
    ) -> SimulationEvent:
        event = SimulationEvent(
            run_id=self.run_id,
            sequence=self.sequence + 1,
            simulation_time=self.state.truth.simulation_time,
            source=source,
            scenario_level=ScenarioLevel(scenario_level),
            event_type=EventType(event_type),
            visibility=EventVisibility(visibility),
            payload=payload or {},
        )
        self.event_store.append(event)
        apply_event(self.state, event)
        self.recent_events.append(event)
        return event

    async def emit_and_broadcast(self, *args: Any, **kwargs: Any) -> SimulationEvent:
        async with self._lock:
            event = self.emit(*args, **kwargs)
            await self._broadcast()
            return event

    async def start(self) -> None:
        async with self._lock:
            if not self.state.running:
                self.emit(EventType.RUN_STARTED, source="operator_ui")
                self._plan_requested = True
            await self._broadcast()

    async def pause(self) -> None:
        async with self._lock:
            if self.state.running:
                self.emit(EventType.RUN_PAUSED, source="operator_ui")
            await self._broadcast()

    async def reset(self) -> None:
        async with self._lock:
            self.state = self._initial_state.model_copy(deep=True)
            self.recent_events.clear()
            self._scheduled.clear()
            self._refresh_request_context.clear()
            self._rng = random.Random(self.state.config.s1.seed)
            self._plan_requested = True
            self.controller.reset_supporting_inference()
            self.event_store.clear()
            self.runtime.repository.path.write_text("", encoding="utf-8")
            self.runtime.commitments.path.write_text("", encoding="utf-8")
            for path in self.runtime.ledger.root.glob("*.json"):
                path.unlink()
            self.emit(EventType.RUN_RESET, source="operator_ui")
            await self._broadcast()

    async def plan_now(self) -> None:
        async with self._lock:
            self._run_plan_cycle()
            self._plan_requested = False
            await self._broadcast()

    async def set_speed(self, speed: float) -> None:
        async with self._lock:
            self.state.config.simulation_speed = max(0.1, min(50.0, float(speed)))
            await self._broadcast()

    def _config_for_level(self, level: ScenarioLevel) -> dict[str, Any]:
        if level == ScenarioLevel.S1:
            return self.state.config.s1.model_dump(mode="json")
        if level == ScenarioLevel.S2:
            return self.state.config.s2.model_dump(mode="json")
        if level == ScenarioLevel.S3:
            return self.state.config.s3.model_dump(mode="json")
        if level == ScenarioLevel.S5:
            return self.state.config.s5.model_dump(mode="json")
        return {
            "commander_authority_present": self.state.config.commander_authority_present
        }

    @staticmethod
    def _change_list(
        before: dict[str, Any], after: dict[str, Any], payload: dict[str, Any]
    ) -> list[dict[str, Any]]:
        changes: list[dict[str, Any]] = []
        for key in payload:
            old = before.get(key)
            new = after.get(key, payload.get(key))
            if old != new:
                changes.append({"field": key, "before": old, "after": new})
        if not changes and payload:
            changes.append({"field": "event_payload", "before": None, "after": payload})
        return changes

    @staticmethod
    def _reasoning_label(
        event_type: EventType, level: ScenarioLevel, visibility: EventVisibility
    ) -> str:
        labels = {
            ScenarioLevel.S1: "Sensor uncertainty changed",
            ScenarioLevel.S2: "Flood dynamics or clearance policy changed",
            ScenarioLevel.S3: "Mission priorities, groups, or assets changed",
            ScenarioLevel.S4: "Operational shock injected",
            ScenarioLevel.S5: "Reconnaissance policy or request changed",
            ScenarioLevel.CORE: "Authority or mission state changed",
        }
        label = labels[level]
        if event_type == EventType.COMMANDER_AUTHORITY:
            label = "Incident Commander authority changed"
        if event_type == EventType.REQUEST_SURVEY:
            label = "New decision-critical survey requested"
        if event_type == EventType.INJECT_SHOCK and visibility == EventVisibility.TRUTH:
            label += " (hidden from Mission Controller)"
        return label

    def _begin_reasoning(
        self,
        *,
        trigger: SimulationEvent,
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> ReasoningCycle:
        cycle = ReasoningCycle(
            trigger_event_id=trigger.event_id,
            scenario_level=trigger.scenario_level,
            trigger_label=self._reasoning_label(
                trigger.event_type, trigger.scenario_level, trigger.visibility
            ),
            simulation_time=self.state.truth.simulation_time,
            changes=self._change_list(before, after, trigger.payload),
        )
        self.emit(
            EventType.REASONING_STARTED,
            source="mission_controller",
            scenario_level=trigger.scenario_level,
            visibility=EventVisibility.AUDIT,
            payload={"cycle": cycle.model_dump(mode="json")},
        )
        self.emit(
            EventType.REASONING_STEP,
            source="mission_controller",
            scenario_level=trigger.scenario_level,
            visibility=EventVisibility.AUDIT,
            payload={
                "step": ReasoningStep(
                    stage="trigger",
                    title="1. Change received",
                    summary=cycle.trigger_label,
                    details={
                        "trigger_event_id": trigger.event_id,
                        "changes": cycle.changes,
                        "visibility": trigger.visibility.value,
                    },
                ).model_dump(mode="json")
            },
        )
        return cycle

    def _reasoning_step(
        self,
        cycle: ReasoningCycle,
        *,
        stage: str,
        title: str,
        summary: str,
        details: dict[str, Any] | None = None,
        status: str = "complete",
    ) -> None:
        self.emit(
            EventType.REASONING_STEP,
            source="mission_controller",
            scenario_level=cycle.scenario_level,
            visibility=EventVisibility.AUDIT,
            payload={
                "step": ReasoningStep(
                    stage=stage,
                    title=title,
                    summary=summary,
                    details=details or {},
                    status=status,
                ).model_dump(mode="json")
            },
        )

    def _complete_reasoning(
        self,
        cycle: ReasoningCycle,
        *,
        affected_record_ids: list[str] | None = None,
        selected_plan_id: str | None = None,
        selected_plan_name: str | None = None,
        decision_change: str | None = None,
    ) -> None:
        self.emit(
            EventType.REASONING_COMPLETED,
            source="mission_controller",
            scenario_level=cycle.scenario_level,
            visibility=EventVisibility.AUDIT,
            payload={
                "cycle_id": cycle.cycle_id,
                "affected_record_ids": affected_record_ids or [],
                "selected_plan_id": selected_plan_id,
                "selected_plan_name": selected_plan_name,
                "decision_change": decision_change,
            },
        )

    async def inject_event(
        self,
        *,
        event_type: EventType | str,
        payload: dict[str, Any],
        scenario_level: ScenarioLevel | str,
        visibility: EventVisibility | str = EventVisibility.BOTH,
        source: str = "operator_ui",
    ) -> SimulationEvent:
        async with self._lock:
            level = ScenarioLevel(scenario_level)
            event_kind = EventType(event_type)
            event_visibility = EventVisibility(visibility)
            before = self._config_for_level(level)
            event = self.emit(
                event_kind,
                source=source,
                payload=payload,
                scenario_level=level,
                visibility=event_visibility,
            )
            after = self._config_for_level(level)
            if event.event_type == EventType.SET_S1_PARAMETERS and "seed" in payload:
                self._rng = random.Random(int(payload["seed"]))

            reasoning_events = {
                EventType.SET_S1_PARAMETERS,
                EventType.SET_S2_PARAMETERS,
                EventType.SET_S3_PARAMETERS,
                EventType.SET_S5_PARAMETERS,
                EventType.ADD_GROUP,
                EventType.ADD_ASSET,
                EventType.UPDATE_GROUP,
                EventType.UPDATE_ASSET,
                EventType.INJECT_SHOCK,
                EventType.COMMANDER_AUTHORITY,
                EventType.REQUEST_SURVEY,
                EventType.EMERGENCY_CALL,
                EventType.INCIDENT_MERGED,
                EventType.INCIDENT_CANCELLED,
            }
            if event.event_type in reasoning_events:
                cycle = self._begin_reasoning(trigger=event, before=before, after=after)

                if event.event_type == EventType.INJECT_SHOCK and event.visibility == EventVisibility.TRUTH:
                    self._reasoning_step(
                        cycle,
                        stage="state",
                        title="2. Knowledge boundary checked",
                        summary=(
                            "Simulation truth changed, but the Mission Controller has no "
                            "new observation. No TRACE claim is revised yet."
                        ),
                        details={
                            "trace_update": "none_until_observed",
                            "controller_replan": False,
                        },
                        status="warning",
                    )
                    self._complete_reasoning(
                        cycle, decision_change="No operational decision changed"
                    )
                else:
                    self._reasoning_step(
                        cycle,
                        stage="state",
                        title="2. Mission state and affected assumptions updated",
                        summary=self._impact_summary(level, event.event_type),
                        details={"payload": payload},
                    )
                    self._plan_requested = True
                    self._run_plan_cycle(
                        trigger_event_id=event.event_id, reasoning_cycle=cycle
                    )
                    self._plan_requested = False

            await self._broadcast()
            return event

    @staticmethod
    def _impact_summary(level: ScenarioLevel, event_type: EventType) -> str:
        if level == ScenarioLevel.S1:
            return "Sensor reliability changed; support, OOD, uncertainty, and observation delivery are recomputed."
        if level == ScenarioLevel.S2:
            return "Water forecasts, observation age, and clearance validity are recomputed."
        if level == ScenarioLevel.S3:
            return "Feasible allocations and practical trade-offs are recomputed; predictive route facts are retained unless their inputs changed."
        if level == ScenarioLevel.S4:
            return "The observed disruption updates dependent beliefs and may invalidate only the commitments that rely on them."
        if level == ScenarioLevel.S5:
            return "Reconnaissance value, safety, and the priority of pending evidence requests are recomputed."
        if event_type == EventType.COMMANDER_AUTHORITY:
            return "Technical TRACE verdicts are unchanged; consumer authorization is re-evaluated."
        return "Mission demand changed; candidate plans and their licensing claims are rebuilt."

    def _route_open_map(self) -> dict[str, bool]:
        return {route_id: route.open for route_id, route in self.state.truth.routes.items()}

    async def step(self, dt: float = 1.0) -> None:
        async with self._lock:
            before_routes = self._route_open_map()
            tick_dt = float(dt)
            tick_payload: dict[str, Any] = {"dt": tick_dt}
            if self.state.config.s2.forcing_noise_std > 0.0:
                tick_index = self.state.truth.environment_tick_index
                tick_payload.update(
                    {
                        "forcing_noise_z": keyed_standard_normal(
                            "env.forcing",
                            SEED_NAMESPACE,
                            self.state.config.s1.seed,
                            tick_index,
                        ),
                        "forcing_rng_schema": RNG_SCHEMA_VERSION,
                        "forcing_seed_namespace": SEED_NAMESPACE,
                        "forcing_tick_index": tick_index,
                        "forcing_spatial_model": "common_forcing_v1",
                    }
                )
            self.emit(
                EventType.TICK,
                source="simulation_clock",
                payload=tick_payload,
            )

            for route_id, now_open in self._route_open_map().items():
                if before_routes.get(route_id) != now_open:
                    self.emit(
                        EventType.ROUTE_STATUS_CHANGED,
                        source="flood_environment",
                        scenario_level=ScenarioLevel.S2,
                        visibility=EventVisibility.TRUTH,
                        payload={
                            "route_id": route_id,
                            "open": now_open,
                            "water_depth": self.state.truth.routes[route_id].water_depth,
                            "reason": "water_threshold_or_debris",
                        },
                    )
                    self._plan_requested = True

            self._move_assets(float(dt))
            self._deliver_scheduled()
            # Completion may append supporting evidence to its originating
            # record, but it never schedules an additional operational plan
            # cycle. The next ordinary trigger can observe the attachment.
            self.controller.poll_supporting_inference(self.state)

            if self.controller.refresh_experiment_mode:
                active_demand = any(
                    not group.rescued
                    and not group.cancelled
                    and int(group.people_waiting or 0) > 0
                    for group in self.state.controller.known_groups.values()
                ) or any(
                    asset.passenger_count > 0
                    for asset in self.state.controller.known_assets.values()
                )
                if active_demand:
                    self._plan_requested = True

            if self.state.config.auto_plan:
                elapsed = self.state.truth.simulation_time - self.state.controller.last_plan_cycle_at
                if self._plan_requested and elapsed >= self.state.config.planning_interval_s:
                    self._run_plan_cycle()
                    self._plan_requested = False

            await self._broadcast()

    def _move_assets(self, dt: float) -> None:
        moving_ids = [
            asset_id
            for asset_id, asset in self.state.truth.assets.items()
            if asset.status == "moving" and asset.target is not None
        ]
        for asset_id in moving_ids:
            asset = self.state.truth.assets[asset_id]
            if asset.target is None:
                continue
            remaining = asset.speed * dt
            position = asset.position
            path_index = asset.path_index
            path = asset.path or [asset.target]
            interrupted = False

            while remaining > 0 and path_index < len(path):
                segment = (
                    asset.path_segments[path_index]
                    if path_index < len(asset.path_segments)
                    else None
                )
                if segment and segment.route_id is not None and segment.edge_index is not None:
                    route = self.state.truth.routes[segment.route_id]
                    if not truth_edge_open(route, segment.edge_index):
                        self.emit(
                            EventType.ACTION_INTERRUPTED,
                            source="flood_environment",
                            scenario_level=ScenarioLevel.S2,
                            payload={
                                "asset_id": asset_id,
                                "action_type": asset.action_type,
                                "route_id": segment.route_id,
                                "edge_index": segment.edge_index,
                                "position": position.model_dump(),
                                "reason": "declared_waterway_segment_blocked",
                                "group_id": asset.assigned_group_id,
                            },
                        )
                        self.emit(
                            EventType.OUTCOME,
                            source="flood_environment",
                            payload={
                                "action_type": asset.action_type,
                                "asset_id": asset_id,
                                "route_id": segment.route_id,
                                "group_id": asset.assigned_group_id,
                                "success": False,
                                "reason": "route_segment_blocked_during_execution",
                                "rescued_people": 0,
                            },
                        )
                        self._schedule_route_observation(
                            segment.route_id,
                            asset_id,
                            truth_only=False,
                            blocked_segment_index=segment.edge_index,
                        )
                        self._plan_requested = True
                        interrupted = True
                        break

                waypoint = path[path_index]
                segment_distance = _distance(position, waypoint)
                if segment_distance <= remaining:
                    position = waypoint
                    remaining -= segment_distance
                    path_index += 1
                else:
                    position = _move_toward(position, waypoint, remaining)
                    remaining = 0

            if interrupted:
                continue

            resource_cost = dt * {
                "survey_drone": 0.0009,
                "rescue_boat": 0.00035,
                "helicopter": 0.0016,
                "ground_team": 0.00018,
            }.get(asset.asset_type, 0.0004)
            new_resource = max(0.0, asset.resource - resource_cost)
            self.emit(
                EventType.ASSET_MOVED,
                source="flood_environment",
                payload={
                    "asset_id": asset_id,
                    "position": position.model_dump(),
                    "resource": new_resource,
                    "path_index": path_index,
                },
            )

            if path_index >= len(path) or _distance(position, asset.target) <= 0.01:
                self._complete_action(asset_id)

    def _complete_action(self, asset_id: str) -> None:
        """Complete the currently executed action without collapsing pickup into rescue.

        A boat that reaches a stranded group has completed only the outbound leg.
        Boarding, evacuation to a declared safe location, and unloading are separate
        state transitions. Each later macro-action is replanned and TRACE-gated.
        """

        asset = self.state.truth.assets[asset_id]
        action_type = asset.action_type
        route_id = asset.assigned_route_id
        group_id = asset.assigned_group_id

        if action_type == "verify_route" and route_id:
            refresh_context = self._refresh_request_context.pop(route_id, {})
            truth_status = "open" if self.state.truth.routes[route_id].open else "blocked"
            observed_at = self.state.truth.simulation_time
            observation_key = (
                SEED_NAMESPACE,
                self.state.config.s1.seed,
                "drone_survey",
                asset_id,
                route_id,
                self.state.truth.environment_tick_index,
                observed_at,
            )
            delivered = (
                keyed_uniform("obs.drone.delivery", *observation_key)
                >= self.state.config.s1.packet_loss
            )
            accurate = (
                keyed_uniform("obs.drone.accuracy", *observation_key)
                <= self.state.config.s1.drone_report_accuracy
            )
            reported_status = (
                truth_status
                if accurate
                else ("blocked" if truth_status == "open" else "open")
            )
            visual_observation = None
            if self.visual_observation_store is not None:
                from trace_jepa.worldmodels.simulator_observations import (
                    SENSOR_MODEL_VERSION,
                    SimulatorSensorSnapshot,
                )

                route_truth = self.state.truth.routes[route_id]
                visual_observation = self.visual_observation_store.capture(
                    SimulatorSensorSnapshot(
                        run_id=self.run_id,
                        episode_id=self.observation_episode_id,
                        study_partition=self.observation_study_partition,
                        route_id=route_id,
                        asset_id=asset_id,
                        observed_at=observed_at,
                        environment_tick_index=self.state.truth.environment_tick_index,
                        sensor_seed=self.state.config.s1.seed,
                        water_depth_m=route_truth.water_depth,
                        route_closure_depth_m=self.state.config.s2.route_closure_depth,
                        debris_blocked=route_truth.debris_blocked,
                        rain_intensity=self.state.config.s2.rain_intensity,
                        upstream_inflow=self.state.config.s2.upstream_inflow,
                        weather_severity=self.state.truth.weather_severity,
                        sensor_noise=self.state.config.s1.sensor_noise,
                        sensor_quality=self.state.config.s5.sensor_quality,
                        packet_delivered=delivered,
                        categorical_report_accurate=accurate,
                        sensor_model_version=SENSOR_MODEL_VERSION,
                    )
                )
            self.emit(
                EventType.ACTION_COMPLETED,
                source="flood_environment",
                payload={
                    "asset_id": asset_id,
                    "action_type": action_type,
                    "route_id": route_id,
                },
            )
            flight_duration = max(
                0.0,
                self.state.truth.simulation_time
                - float(
                    asset.action_started_at
                    if asset.action_started_at is not None
                    else self.state.truth.simulation_time
                ),
            )
            if delivered:
                self._scheduled.append(
                    {
                        # WP3 defines drone latency as flight time. The report
                        # therefore reaches the controller at flight completion,
                        # with no unmodelled post-flight delivery gap.
                        "deliver_at": self.state.truth.simulation_time,
                        "kind": "route_observation",
                        "payload": {
                            "kind": "route",
                            "route_id": route_id,
                            "reported_status": reported_status,
                            "truth_status": truth_status,
                            "confidence": max(
                                0.05,
                                self.state.config.s1.drone_report_accuracy
                                * self.state.config.s5.sensor_quality,
                            ),
                            "source": asset_id,
                            "observed_at": observed_at,
                            "accurate": accurate,
                            "blocked_segment_index": (
                                self.state.truth.routes[route_id].blocked_segment_index
                                if truth_status == "blocked"
                                else None
                            ),
                            "refresh_decision_id": refresh_context.get(
                                "refresh_decision_id"
                            ),
                            "evidence_request_id": refresh_context.get(
                                "evidence_request_id"
                            ),
                            "claim_id": refresh_context.get("claim_id"),
                            "commitment_id": refresh_context.get(
                                "commitment_id"
                            ),
                            "latency_s": flight_duration,
                            "cost": 5.0 + flight_duration * 0.0009,
                            **(
                                {
                                    "visual_observation_id": visual_observation.observation_id,
                                    "visual_observation_hash": visual_observation.observation_hash,
                                    "visual_observed_at": observed_at,
                                    "visual_sensor_version": SENSOR_MODEL_VERSION,
                                }
                                if visual_observation is not None
                                else {}
                            ),
                        },
                    }
                )
            else:
                self.emit(
                    EventType.EVIDENCE_ACQUIRED,
                    source="drone_survey",
                    scenario_level=ScenarioLevel.S5,
                    visibility=EventVisibility.AUDIT,
                    payload={
                        "refresh_decision_id": refresh_context.get(
                            "refresh_decision_id"
                        ),
                        "evidence_request_id": refresh_context.get(
                            "evidence_request_id"
                        ),
                        "channel": "drone_survey",
                        "route_id": route_id,
                        "asset_id": asset_id,
                        "observed_at": observed_at,
                        "latency_s": flight_duration,
                        "cost": 5.0 + flight_duration * 0.0009,
                        "usable": False,
                        "accurate": accurate,
                        "claim_id": refresh_context.get("claim_id"),
                        "commitment_id": refresh_context.get("commitment_id"),
                        **(
                            {
                                "visual_observation_id": visual_observation.observation_id,
                                "visual_observation_hash": visual_observation.observation_hash,
                                "visual_controller_usable": False,
                            }
                            if visual_observation is not None
                            else {}
                        ),
                    },
                )
                self.emit(
                    EventType.OUTCOME,
                    source="communications",
                    scenario_level=ScenarioLevel.S1,
                    payload={
                        "action_type": action_type,
                        "route_id": route_id,
                        "success": False,
                        "reason": "observation_packet_lost",
                        "rescued_people": 0,
                    },
                )
                self._plan_requested = True
            return

        if action_type == "dispatch_rescue_boat":
            if not group_id or group_id not in self.state.truth.groups:
                self.emit(
                    EventType.ACTION_INTERRUPTED,
                    source="flood_environment",
                    payload={
                        "asset_id": asset_id,
                        "action_type": action_type,
                        "route_id": route_id,
                        "reason": "pickup_group_missing",
                        "position": asset.position.model_dump(),
                    },
                )
                self._plan_requested = True
                return

            group = self.state.truth.groups[group_id]
            people_to_board = min(
                int(group.people_waiting or 0),
                max(0, asset.capacity - asset.passenger_count),
            )
            if people_to_board <= 0:
                self.emit(
                    EventType.ACTION_COMPLETED,
                    source="flood_environment",
                    payload={
                        "asset_id": asset_id,
                        "action_type": action_type,
                        "route_id": route_id,
                        "group_id": group_id,
                    },
                )
                self.emit(
                    EventType.OUTCOME,
                    source="flood_environment",
                    payload={
                        "action_type": action_type,
                        "asset_id": asset_id,
                        "route_id": route_id,
                        "group_id": group_id,
                        "success": False,
                        "reason": "no_people_available_for_pickup",
                        "rescued_people": 0,
                    },
                )
                self._plan_requested = True
                return

            # Successful traversal is itself a current, attributable route
            # observation. Record it before boarding so the return-to-safety
            # plan is evaluated against a fresh clearance rather than the old
            # report that licensed the outbound trip. This does not bypass
            # TRACE: it only updates evidence; evacuation remains a separate
            # candidate, claim, record, authority check, and commitment.
            if route_id:
                self._schedule_route_observation(
                    route_id,
                    source=asset_id,
                    truth_only=False,
                )

            self.emit(
                EventType.BOARDING_STARTED,
                source="flood_environment",
                payload={
                    "asset_id": asset_id,
                    "group_id": group_id,
                    "route_id": route_id,
                    "people": people_to_board,
                },
            )
            pickup_duration = (
                self.state.config.rescue.pickup_base_s
                + people_to_board * self.state.config.rescue.pickup_per_person_s
            )
            self._scheduled.append(
                {
                    "deliver_at": self.state.truth.simulation_time + pickup_duration,
                    "kind": "pickup_complete",
                    "payload": {
                        "asset_id": asset_id,
                        "group_id": group_id,
                        "route_id": route_id,
                        "people": people_to_board,
                    },
                }
            )
            return

        if action_type == "evacuate_to_safety":
            if asset.passenger_count <= 0:
                self.emit(
                    EventType.ACTION_COMPLETED,
                    source="flood_environment",
                    payload={
                        "asset_id": asset_id,
                        "action_type": action_type,
                        "route_id": route_id,
                    },
                )
                self._plan_requested = True
                return

            self.emit(
                EventType.UNLOADING_STARTED,
                source="flood_environment",
                payload={
                    "asset_id": asset_id,
                    "route_id": route_id,
                    "safe_location_id": (
                        asset.safe_location_id
                        or self.state.config.rescue.safe_location_id
                    ),
                    "people": asset.passenger_count,
                    "group_ids": list(asset.passenger_group_ids),
                },
            )
            unload_duration = (
                self.state.config.rescue.unload_base_s
                + asset.passenger_count * self.state.config.rescue.unload_per_person_s
            )
            self._scheduled.append(
                {
                    "deliver_at": self.state.truth.simulation_time + unload_duration,
                    "kind": "unload_complete",
                    "payload": {
                        "asset_id": asset_id,
                        "route_id": route_id,
                        "people": asset.passenger_count,
                        "group_ids": list(asset.passenger_group_ids),
                        "safe_location_id": (
                            asset.safe_location_id
                            or self.state.config.rescue.safe_location_id
                        ),
                    },
                }
            )
            return

        # Helicopter and ground-team actions remain direct teaching abstractions
        # in D0.2 Step 2. The complete pickup/transport/handoff lifecycle is now
        # enforced for rescue boats, which are the route-constrained case.
        if action_type in {"dispatch_helicopter", "deploy_ground_team"}:
            success = True
            reason = "rescue_completed"
            if action_type == "dispatch_helicopter":
                success = self.state.truth.weather_severity <= asset.weather_tolerance
                reason = (
                    "rescue_completed"
                    if success
                    else "weather_exceeded_aircraft_tolerance"
                )
            elif action_type == "deploy_ground_team":
                success = (
                    self.state.truth.global_water_level
                    < self.state.config.s2.route_closure_depth * 0.75
                )
                reason = (
                    "rescue_completed"
                    if success
                    else "flood_depth_blocked_ground_team"
                )

            rescued_people = 0
            if group_id and group_id in self.state.truth.groups:
                group = self.state.truth.groups[group_id]
                if success:
                    rescued_people = int(group.people_waiting or 0)
                    self.emit(
                        EventType.UPDATE_GROUP,
                        source="flood_environment",
                        payload={
                            "group_id": group_id,
                            "updates": {
                                "people_waiting": 0,
                                "people_delivered": group.people,
                                "rescued": True,
                                "condition": "rescued",
                                "rescue_phase": "delivered",
                                "assigned_asset_id": None,
                            },
                        },
                        visibility=EventVisibility.BOTH,
                    )
                else:
                    self.emit(
                        EventType.UPDATE_GROUP,
                        source="flood_environment",
                        payload={
                            "group_id": group_id,
                            "updates": {"assigned_asset_id": None},
                        },
                        visibility=EventVisibility.BOTH,
                    )

            self.emit(
                EventType.ACTION_COMPLETED,
                source="flood_environment",
                payload={
                    "asset_id": asset_id,
                    "action_type": action_type,
                    "route_id": route_id,
                    "group_id": group_id,
                },
            )
            self.emit(
                EventType.OUTCOME,
                source="flood_environment",
                payload={
                    "action_type": action_type,
                    "asset_id": asset_id,
                    "route_id": route_id,
                    "group_id": group_id,
                    "success": success,
                    "reason": reason,
                    "rescued_people": rescued_people,
                },
            )
            self._plan_requested = True
            return

        self.emit(
            EventType.ACTION_COMPLETED,
            source="flood_environment",
            payload={"asset_id": asset_id, "action_type": action_type},
        )

    def _schedule_route_observation(
        self,
        route_id: str,
        source: str,
        truth_only: bool = False,
        blocked_segment_index: int | None = None,
    ) -> None:
        truth_status = "open" if self.state.truth.routes[route_id].open else "blocked"
        if blocked_segment_index is None and truth_status == "blocked":
            blocked_segment_index = self.state.truth.routes[route_id].blocked_segment_index
        self._scheduled.append(
            {
                "deliver_at": self.state.truth.simulation_time,
                "kind": "route_observation",
                "payload": {
                    "kind": "route",
                    "route_id": route_id,
                    "reported_status": truth_status,
                    "truth_status": truth_status,
                    "confidence": 1.0 if truth_only else 0.95,
                    "source": source,
                    "observed_at": self.state.truth.simulation_time,
                    "accurate": True,
                    "blocked_segment_index": blocked_segment_index,
                },
            }
        )

    def _request_gauge_poll(
        self,
        *,
        route_id: str,
        decision: RefreshDecision,
        refresh_decision_id: str,
        evidence_request_id: str,
    ) -> str:
        requested_at = self.state.truth.simulation_time
        deliver_at = requested_at + 5.0
        sampled_depth = self.state.truth.routes[route_id].water_depth
        self.emit(
            EventType.GAUGE_POLL,
            source="gauge_poll",
            scenario_level=ScenarioLevel.S5,
            visibility=EventVisibility.AUDIT,
            payload={
                "refresh_decision_id": refresh_decision_id,
                "evidence_request_id": evidence_request_id,
                "route_id": route_id,
                "requested_at": requested_at,
                "sampled_at": requested_at,
                "deliver_at": deliver_at,
                "sampled_water_depth": sampled_depth,
                "cost": 0.2,
                "latency_s": 5.0,
                "policy": decision.policy,
                "claim_id": decision.claim_id,
                "commitment_id": decision.commitment_id,
            },
        )
        self._scheduled.append(
            {
                "deliver_at": deliver_at,
                "kind": "gauge_observation",
                "payload": {
                    "refresh_decision_id": refresh_decision_id,
                    "evidence_request_id": evidence_request_id,
                    "kind": "route_depth",
                    "route_id": route_id,
                    "water_depth": sampled_depth,
                    "source": "gauge_poll",
                    "observed_at": requested_at,
                    "cost": 0.2,
                    "latency_s": 5.0,
                    "claim_id": decision.claim_id,
                    "commitment_id": decision.commitment_id,
                },
            }
        )
        return evidence_request_id

    def _deliver_scheduled(self) -> None:
        due = [
            item
            for item in self._scheduled
            if item["deliver_at"] <= self.state.truth.simulation_time
        ]
        self._scheduled = [item for item in self._scheduled if item not in due]
        for item in due:
            kind = item["kind"]
            payload = item["payload"]

            if kind == "gauge_observation":
                event = self.emit(
                    EventType.OBSERVATION,
                    source="gauge_poll",
                    scenario_level=ScenarioLevel.S1,
                    visibility=EventVisibility.CONTROLLER,
                    payload={
                        key: value
                        for key, value in payload.items()
                        if key
                        not in {"cost", "latency_s", "claim_id", "commitment_id"}
                    },
                )
                self.emit(
                    EventType.EVIDENCE_ACQUIRED,
                    source="gauge_poll",
                    scenario_level=ScenarioLevel.S5,
                    visibility=EventVisibility.AUDIT,
                    payload={
                        "evidence_request_id": payload["evidence_request_id"],
                        "refresh_decision_id": payload["refresh_decision_id"],
                        "channel": "gauge_poll",
                        "route_id": payload["route_id"],
                        "observation_event_id": event.event_id,
                        "observed_at": payload["observed_at"],
                        "delivered_at": self.state.truth.simulation_time,
                        "latency_s": payload["latency_s"],
                        "cost": payload["cost"],
                        "usable": True,
                        "claim_id": payload["claim_id"],
                        "commitment_id": payload["commitment_id"],
                    },
                )
                self._plan_requested = True
                continue

            if kind == "route_observation":
                observation_payload = {
                    key: value
                    for key, value in payload.items()
                    if key
                    not in {
                        "refresh_decision_id",
                        "evidence_request_id",
                        "claim_id",
                        "commitment_id",
                        "latency_s",
                        "cost",
                    }
                }
                event = self.emit(
                    EventType.OBSERVATION,
                    source=str(payload.get("source", "sensor")),
                    scenario_level=ScenarioLevel.S1,
                    visibility=EventVisibility.CONTROLLER,
                    payload=observation_payload,
                )
                if "cost" in payload:
                    self.emit(
                        EventType.EVIDENCE_ACQUIRED,
                        source="drone_survey",
                        scenario_level=ScenarioLevel.S5,
                        visibility=EventVisibility.AUDIT,
                        payload={
                            "refresh_decision_id": payload.get(
                                "refresh_decision_id"
                            ),
                            "evidence_request_id": payload["evidence_request_id"],
                            "channel": "drone_survey",
                            "route_id": payload["route_id"],
                            "observation_event_id": event.event_id,
                            "observed_at": payload["observed_at"],
                            "delivered_at": self.state.truth.simulation_time,
                            "latency_s": payload["latency_s"],
                            "cost": payload["cost"],
                            "usable": True,
                            "accurate": payload["accurate"],
                            "claim_id": payload.get("claim_id"),
                            "commitment_id": payload.get("commitment_id"),
                            **(
                                {
                                    "visual_observation_id": payload[
                                        "visual_observation_id"
                                    ],
                                    "visual_observation_hash": payload[
                                        "visual_observation_hash"
                                    ],
                                    "visual_controller_usable": True,
                                }
                                if payload.get("visual_observation_id") is not None
                                else {}
                            ),
                        },
                    )
                self.emit(
                    EventType.BELIEF_UPDATE,
                    source="mission_controller",
                    payload={
                        "route_id": payload["route_id"],
                        "updates": {
                            "status": payload["reported_status"],
                            "confidence": payload["confidence"],
                            "observed_at": payload["observed_at"],
                            "source": payload["source"],
                            "blocked_segment_index": payload.get(
                                "blocked_segment_index"
                            ),
                        },
                    },
                )
                revised = self.controller.revise_route_records(
                    self.state,
                    route_id=str(payload["route_id"]),
                    reported_status=str(payload["reported_status"]),
                    truth_status=str(payload["truth_status"]),
                    observation_event_id=event.event_id,
                )
                for record in revised:
                    self.emit(
                        EventType.REVISION,
                        source="trace_runtime",
                        payload={
                            "record_id": record.record_id,
                            "record_version": record.record_version,
                            "route_id": payload["route_id"],
                            "new_status": record.final_status.value,
                        },
                    )
                if revised:
                    self.emit(
                        EventType.LOCAL_REPAIR,
                        source="candidate_planner",
                        payload={
                            "route_id": payload["route_id"],
                            "invalidated_records": [
                                record.record_id for record in revised
                            ],
                            "scope": "route-dependent branches only",
                        },
                    )
                self._plan_requested = True
                continue

            if kind == "pickup_complete":
                asset_id = str(payload["asset_id"])
                group_id = str(payload["group_id"])
                before = 0
                if group_id in self.state.truth.groups:
                    before = self.state.truth.groups[group_id].people_onboard
                self.emit(
                    EventType.PEOPLE_PICKED_UP,
                    source="flood_environment",
                    payload=payload,
                )
                after = before
                if group_id in self.state.truth.groups:
                    after = self.state.truth.groups[group_id].people_onboard
                boarded = max(0, after - before)
                self.emit(
                    EventType.ACTION_COMPLETED,
                    source="flood_environment",
                    payload={
                        "asset_id": asset_id,
                        "action_type": "dispatch_rescue_boat",
                        "route_id": payload.get("route_id"),
                        "group_id": group_id,
                        "phase": "pickup_complete",
                    },
                )
                self.emit(
                    EventType.OUTCOME,
                    source="flood_environment",
                    payload={
                        "action_type": "dispatch_rescue_boat",
                        "asset_id": asset_id,
                        "route_id": payload.get("route_id"),
                        "group_id": group_id,
                        "success": boarded > 0,
                        "reason": "pickup_completed",
                        "people_picked_up": boarded,
                        "rescued_people": 0,
                    },
                )
                self._plan_requested = True
                continue

            if kind == "unload_complete":
                asset_id = str(payload["asset_id"])
                delivered = (
                    self.state.truth.assets[asset_id].passenger_count
                    if asset_id in self.state.truth.assets
                    else 0
                )
                # Close the authorized evacuation action first; the handoff event
                # then establishes the post-rescue standby state.
                self.emit(
                    EventType.ACTION_COMPLETED,
                    source="flood_environment",
                    payload={
                        "asset_id": asset_id,
                        "action_type": "evacuate_to_safety",
                        "route_id": payload.get("route_id"),
                        "phase": "arrival_at_safe_location",
                    },
                )
                self.emit(
                    EventType.PEOPLE_DELIVERED,
                    source="safe_transfer_dock",
                    payload=payload,
                )
                self.emit(
                    EventType.ASSET_STANDBY,
                    source="safe_transfer_dock",
                    payload={
                        "asset_id": asset_id,
                        "safe_location_id": payload.get(
                            "safe_location_id",
                            self.state.config.rescue.safe_location_id,
                        ),
                        "reason": "rescue_handoff_complete",
                    },
                )
                self.emit(
                    EventType.OUTCOME,
                    source="safe_transfer_dock",
                    payload={
                        "action_type": "evacuate_to_safety",
                        "asset_id": asset_id,
                        "route_id": payload.get("route_id"),
                        "group_ids": payload.get("group_ids", []),
                        "success": delivered > 0,
                        "reason": "people_delivered_to_safe_transfer_dock",
                        "rescued_people": delivered,
                        "metrics_already_applied": True,
                    },
                )
                self._plan_requested = True
                continue

    @staticmethod
    def _record_decision(record: Any) -> str:
        actions = getattr(record, "consumer_actions", ())
        if actions:
            return actions[-1].decision.value
        return record.final_status.value

    def _run_plan_cycle(
        self,
        *,
        trigger_event_id: str | None = None,
        reasoning_cycle: ReasoningCycle | None = None,
    ) -> None:
        active_waiting = any(
            not group.rescued
            and not group.cancelled
            and int(group.people_waiting or 0) > 0
            for group in self.state.controller.known_groups.values()
        )
        onboard = any(
            asset.passenger_count > 0
            for asset in self.state.controller.known_assets.values()
        )
        if not active_waiting and not onboard:
            if reasoning_cycle is not None:
                self._reasoning_step(
                    reasoning_cycle,
                    stage="plan",
                    title="6. Plan selection",
                    summary=(
                        "No waiting or onboard people remain; no new rescue "
                        "commitment is required."
                    ),
                )
                self._complete_reasoning(
                    reasoning_cycle, decision_change="No active rescue demand"
                )
            return

        self.emit(
            EventType.PLAN_CYCLE,
            source="mission_controller",
            payload={"trigger_event_id": trigger_event_id},
        )
        assessed = self.controller.assess(
            self.state, trigger_event_id=trigger_event_id
        )

        if reasoning_cycle is not None:
            self._reasoning_step(
                reasoning_cycle,
                stage="prediction",
                title="3. Candidate futures recomputed",
                summary=f"{len(assessed)} candidate plans were predicted under the updated state.",
                details={
                    "plans": [
                        {
                            "plan_id": item.plan.plan_id,
                            "success": item.prediction.success_probability,
                            "support": item.prediction.model_support,
                            "ood": item.prediction.out_of_distribution_score,
                            "uncertainty": item.prediction.uncertainty,
                        }
                        for item in assessed
                    ]
                },
            )
            self._reasoning_step(
                reasoning_cycle,
                stage="claim",
                title="4. Licensing claims rebuilt",
                summary=(
                    "Each candidate produced a grounded predictive or practical claim; "
                    "unchanged claim identities remain in the same TRACE lineage."
                ),
                details={"claim_count": len(assessed)},
            )

        affected_records: list[str] = []
        decision_changes: list[str] = []
        revision_count = 0

        for item in assessed:
            semantic_revision = item.record.metadata.get("semantic_revision_of")
            previous_decision = None
            if semantic_revision:
                try:
                    previous_record = self.runtime.repository.get(
                        semantic_revision["record_id"],
                        int(semantic_revision["record_version"]),
                    )
                    previous_decision = self._record_decision(previous_record)
                except (KeyError, TypeError, ValueError):
                    previous_decision = None

            self.emit(
                EventType.PLAN_PROPOSED,
                source="candidate_planner",
                payload={
                    "plan_id": item.plan.plan_id,
                    "name": item.plan.name,
                    "utility": item.plan.utility,
                    "record_id": item.record.record_id,
                    "record_version": item.record.record_version,
                    "action": item.plan.first_action.model_dump(mode="json"),
                    "trigger_event_id": trigger_event_id,
                },
            )
            self.emit(
                EventType.TRACE_WRITTEN,
                source="trace_runtime",
                payload={
                    "plan_id": item.plan.plan_id,
                    "plan_name": item.plan.name,
                    "record_id": item.record.record_id,
                    "record_version": item.record.record_version,
                    "trace_status": item.status,
                    "decision": item.decision,
                    "model_support": item.prediction.model_support,
                    "ood_score": item.prediction.out_of_distribution_score,
                    "uncertainty": item.prediction.uncertainty,
                    "success_probability": item.prediction.success_probability,
                    "failed_gates": list(item.record.failed_gates),
                    "missing_items": list(item.record.missing_items),
                    "repair": item.record.repair,
                    "claim": item.record.claim.text,
                    "action": item.plan.first_action.model_dump(mode="json"),
                    "trigger_event_id": trigger_event_id,
                    "semantic_revision_of": semantic_revision,
                    "previous_decision": previous_decision,
                },
            )
            self.emit(
                EventType.COMMITMENT_DECISION,
                source="trace_gate",
                payload={
                    "plan_id": item.plan.plan_id,
                    "plan_name": item.plan.name,
                    "record_id": item.record.record_id,
                    "record_version": item.record.record_version,
                    "decision": item.decision,
                    "trace_status": item.status,
                    "reason": item.reason,
                    "utility": item.plan.utility,
                    "false_clear": item.false_clear,
                    "false_hold": item.false_hold,
                    "stale_clearance": item.stale_clearance,
                    "trigger_event_id": trigger_event_id,
                },
            )
            affected_records.append(item.record.record_id)
            if semantic_revision:
                revision_count += 1
                self.emit(
                    EventType.REVISION,
                    source="trace_runtime",
                    scenario_level=(
                        reasoning_cycle.scenario_level
                        if reasoning_cycle is not None
                        else ScenarioLevel.CORE
                    ),
                    visibility=EventVisibility.AUDIT,
                    payload={
                        "record_id": item.record.record_id,
                        "record_version": item.record.record_version,
                        "reason": "parameter_or_state_change",
                        "trigger_event_id": trigger_event_id,
                        "previous_decision": previous_decision,
                        "new_decision": item.decision,
                    },
                )
            if previous_decision and previous_decision != item.decision:
                decision_changes.append(
                    f"{item.plan.name}: {previous_decision.upper()} -> {item.decision.upper()}"
                )

        if reasoning_cycle is not None:
            self._reasoning_step(
                reasoning_cycle,
                stage="trace",
                title="5. TRACE records evaluated",
                summary=(
                    f"{len(affected_records)} record lineages were evaluated; "
                    f"{revision_count} received a new semantic version."
                ),
                details={
                    "affected_record_ids": affected_records,
                    "decision_changes": decision_changes,
                },
                status="warning" if decision_changes else "complete",
            )

        refresh_target, refresh_decision = self.controller.decide_refresh(
            self.state, assessed
        )
        assessed_for_selection = self._apply_refresh_decision(
            assessed,
            target=refresh_target,
            decision=refresh_decision,
        )
        chosen = self.controller.select(self.state, assessed_for_selection)
        if chosen is None:
            self.emit(
                EventType.PLAN_SELECTED,
                source="mission_controller",
                payload={
                    "plan_id": None,
                    "plan_name": "No admissible plan",
                    "decision": "hold",
                    "reason": "All candidate commitments failed, were unavailable, or exceeded policy.",
                    "trigger_event_id": trigger_event_id,
                },
            )
            if reasoning_cycle is not None:
                self._reasoning_step(
                    reasoning_cycle,
                    stage="plan",
                    title="6. Plan selection",
                    summary="No admissible plan is currently available; the mission remains on hold.",
                    status="blocked",
                )
                self._complete_reasoning(
                    reasoning_cycle,
                    affected_record_ids=affected_records,
                    decision_change="; ".join(decision_changes) or "No admissible plan",
                )
            return

        self.emit(
            EventType.PLAN_SELECTED,
            source="mission_controller",
            payload={
                "plan_id": chosen.plan.plan_id,
                "plan_name": chosen.plan.name,
                "decision": chosen.decision,
                "reason": chosen.reason,
                "record_id": chosen.record.record_id,
                "record_version": chosen.record.record_version,
                "utility": chosen.plan.utility,
                "trigger_event_id": trigger_event_id,
            },
        )

        if reasoning_cycle is not None:
            self._reasoning_step(
                reasoning_cycle,
                stage="plan",
                title="6. Highest-utility admissible plan selected",
                summary=f"Selected {chosen.plan.name} ({chosen.decision.upper()}).",
                details={
                    "plan_id": chosen.plan.plan_id,
                    "utility": chosen.plan.utility,
                    "record_id": chosen.record.record_id,
                    "record_version": chosen.record.record_version,
                },
            )

        action = chosen.plan.first_action
        try:
            navigation = plan_route_constrained_action(
                self.state, action, view="controller"
            )
        except NavigationError as exc:
            if reasoning_cycle is not None:
                self._reasoning_step(
                    reasoning_cycle,
                    stage="commitment",
                    title="7. Dispatcher structural check",
                    summary=f"Action was not dispatched: {exc}",
                    status="blocked",
                )
                self._complete_reasoning(
                    reasoning_cycle,
                    affected_record_ids=affected_records,
                    selected_plan_id=chosen.plan.plan_id,
                    selected_plan_name=chosen.plan.name,
                    decision_change="Structural path check blocked dispatch",
                )
            return

        commitment = self.runtime.commit(record=chosen.record, action=action)
        truth_safe_at_execution = True
        authorization_outside_tolerance = False
        if action.route_id and action.route_id in self.state.truth.routes:
            truth_safe_at_execution = self.state.truth.routes[action.route_id].open
            belief = self.state.controller.route_beliefs[action.route_id]
            authorization_outside_tolerance = bool(
                belief.clearance_valid_until is not None
                and self.state.truth.simulation_time > belief.clearance_valid_until
            )
        elif action.action_type == "dispatch_helicopter":
            asset = self.state.truth.assets[action.actor_id]
            truth_safe_at_execution = (
                self.state.truth.weather_severity <= asset.weather_tolerance
            )
        self.emit(
            EventType.ACTION_STARTED,
            source="action_dispatcher",
            payload={
                "commitment_id": commitment.commitment_id,
                "asset_id": action.actor_id,
                "action_type": action.action_type,
                "route_id": action.route_id,
                "group_id": action.parameters.get("group_id"),
                "path": [point.model_dump() for point in navigation.points],
                "path_segments": [
                    segment.model_dump(mode="json") for segment in navigation.segments
                ],
                "target": navigation.target.model_dump(),
                "navigation_summary": navigation.summary,
                "navigation_distance": navigation.total_distance,
                "record_id": chosen.record.record_id,
                "record_version": chosen.record.record_version,
                "plan_id": chosen.plan.plan_id,
                "truth_safe_at_execution": truth_safe_at_execution,
                "authorization_outside_tolerance": (
                    authorization_outside_tolerance
                ),
                "executed_stale": (
                    not truth_safe_at_execution
                ),
            },
        )

        if reasoning_cycle is not None:
            self._reasoning_step(
                reasoning_cycle,
                stage="commitment",
                title="7. Authorized action dispatched",
                summary=(
                    f"{action.actor_id} follows a declared {navigation.summary}; "
                    "no straight-line shortcut is permitted."
                ),
                details={
                    "commitment_id": commitment.commitment_id,
                    "path_segments": len(navigation.segments),
                    "distance": navigation.total_distance,
                },
            )
            self._complete_reasoning(
                reasoning_cycle,
                affected_record_ids=affected_records,
                selected_plan_id=chosen.plan.plan_id,
                selected_plan_name=chosen.plan.name,
                decision_change="; ".join(decision_changes) or "Plan re-evaluated; decision unchanged",
            )

    def _apply_refresh_decision(
        self,
        assessed: list[Any],
        *,
        target: Any | None,
        decision: RefreshDecision,
    ) -> list[Any]:
        if target is None or decision.mode == RefreshMode.CONTINUE:
            return assessed

        target_action = target.plan.first_action
        refresh_decision_id = new_id("refresh-decision")
        evidence_request_id = (
            new_id("evidence-request")
            if decision.mode == RefreshMode.ACQUIRE
            else None
        )
        voi_table = [
            channel.model_dump(mode="json") for channel in decision.voi_table
        ]
        for family in decision.triggered_families:
            self.emit(
                EventType.REFRESH_TRIGGERED,
                source="refresh_scheduler",
                scenario_level=ScenarioLevel.S5,
                visibility=EventVisibility.AUDIT,
                payload={
                    "policy": decision.policy,
                    "refresh_decision_id": refresh_decision_id,
                    "evidence_request_id": evidence_request_id,
                    "claim_id": decision.claim_id,
                    "commitment_id": decision.commitment_id,
                    "record_id": target.record.record_id,
                    "record_version": target.record.record_version,
                    "plan_id": target.plan.plan_id,
                    "route_id": target_action.route_id,
                    "family": family.value,
                    "q": decision.q,
                    "d_or_margin": decision.d_or_margin,
                    "voi_table": voi_table,
                    "selected_channel": decision.selected_channel,
                    "rationale": decision.rationale,
                },
            )

        if decision.mode == RefreshMode.ACQUIRE:
            if target_action.route_id is None:
                raise ValueError("route evidence requires a grounded route_id")
            if decision.selected_channel == "gauge_poll":
                self._request_gauge_poll(
                    route_id=target_action.route_id,
                    decision=decision,
                    refresh_decision_id=refresh_decision_id,
                    evidence_request_id=str(evidence_request_id),
                )
            elif decision.selected_channel == "drone_survey":
                self._refresh_request_context[target_action.route_id] = {
                    "evidence_request_id": evidence_request_id,
                    "refresh_decision_id": refresh_decision_id,
                    "claim_id": decision.claim_id,
                    "commitment_id": decision.commitment_id,
                }
                self.emit(
                    EventType.REQUEST_SURVEY,
                    source="refresh_scheduler",
                    scenario_level=ScenarioLevel.S5,
                    payload={
                        "route_id": target_action.route_id,
                        "requested_by": decision.policy,
                        "claim_id": decision.claim_id,
                        "commitment_id": decision.commitment_id,
                        "evidence_request_id": evidence_request_id,
                        "refresh_decision_id": refresh_decision_id,
                    },
                )
            else:
                raise ValueError(
                    f"unsupported refresh channel: {decision.selected_channel}"
                )
            withdrawal = RefreshMode.HOLD
        else:
            withdrawal = decision.mode

        self.emit(
            EventType.AUTH_WITHDRAWN,
            source="refresh_scheduler",
            scenario_level=ScenarioLevel.S5,
            visibility=EventVisibility.AUDIT,
            payload={
                "policy": decision.policy,
                "refresh_decision_id": refresh_decision_id,
                "evidence_request_id": evidence_request_id,
                "claim_id": decision.claim_id,
                "commitment_id": decision.commitment_id,
                "plan_id": target.plan.plan_id,
                "route_id": target_action.route_id,
                "mode": withdrawal.value,
                "rationale": decision.rationale,
            },
        )

        if withdrawal == RefreshMode.SAFE_ALTERNATIVE:
            return [
                item
                for item in assessed
                if item.plan.plan_id == decision.safe_alternative_plan_id
            ]
        if self.state.controller.requested_surveys:
            return [
                item
                for item in assessed
                if item.plan.first_action.action_type == "verify_route"
                and item.plan.first_action.route_id
                in self.state.controller.requested_surveys
            ]
        return []

    def snapshot(self) -> WorkbenchSnapshot:
        records = self.runtime.repository.all()
        return WorkbenchSnapshot(
            run_id=self.run_id,
            running=self.state.running,
            config=self.state.config.model_dump(mode="json"),
            truth=self.state.truth.model_dump(mode="json"),
            controller=self.state.controller.model_dump(mode="json"),
            metrics=self.state.metrics.model_dump(mode="json"),
            recent_events=tuple(
                event.model_dump(mode="json") for event in list(self.recent_events)[-60:]
            ),
            recent_records=tuple(
                record.model_dump(mode="json") for record in records[-30:]
            ),
            event_chain_valid=self.event_store.verify_chain(),
            trace_chain_valid=self.runtime.repository.verify_chain(),
        )

    def replay_state(self) -> WorkbenchState:
        replay = self._initial_state.model_copy(deep=True)
        for event in self.event_store.all():
            apply_event(replay, event)
        return replay

    def export_manifest(self) -> Path:
        path = self.artifact_root / "run_manifest.json"
        payload = {
            "run_id": self.run_id,
            "scenario_path": str(self.scenario_path),
            "controller_version": self.controller.version,
            "predictor_version": self.controller.predictor_version,
            "event_count": self.sequence,
            "event_chain_valid": self.event_store.verify_chain(),
            "trace_chain_valid": self.runtime.repository.verify_chain(),
            "config": self.state.config.model_dump(mode="json"),
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return path


class SimulationLoop:
    """Background real-time loop used by the FastAPI application."""

    def __init__(self, run: DynamicRun, interval_s: float = 0.25):
        self.run = run
        self.interval_s = interval_s
        self._task: asyncio.Task[None] | None = None
        self._stopping = False

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._stopping = False
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stopping = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        while not self._stopping:
            if self.run.state.running:
                dt = self.interval_s * self.run.state.config.simulation_speed
                await self.run.step(dt)
            await asyncio.sleep(self.interval_s)
