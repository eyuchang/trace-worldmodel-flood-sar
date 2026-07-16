from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from trace_jepa.util import new_id, utc_now


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ScenarioLevel(str, Enum):
    S1 = "S1"
    S2 = "S2"
    S3 = "S3"
    S4 = "S4"
    S5 = "S5"
    CORE = "CORE"


class EventVisibility(str, Enum):
    TRUTH = "truth"
    CONTROLLER = "controller"
    BOTH = "both"
    AUDIT = "audit"


class EventType(str, Enum):
    RUN_CREATED = "RUN_CREATED"
    RUN_STARTED = "RUN_STARTED"
    RUN_PAUSED = "RUN_PAUSED"
    RUN_RESET = "RUN_RESET"
    TICK = "TICK"
    EMERGENCY_CALL = "EMERGENCY_CALL"
    SET_S1_PARAMETERS = "SET_S1_PARAMETERS"
    SET_S2_PARAMETERS = "SET_S2_PARAMETERS"
    SET_S3_PARAMETERS = "SET_S3_PARAMETERS"
    ADD_GROUP = "ADD_GROUP"
    UPDATE_GROUP = "UPDATE_GROUP"
    ADD_ASSET = "ADD_ASSET"
    UPDATE_ASSET = "UPDATE_ASSET"
    INJECT_SHOCK = "INJECT_SHOCK"
    SET_S5_PARAMETERS = "SET_S5_PARAMETERS"
    REQUEST_SURVEY = "REQUEST_SURVEY"
    COMMANDER_AUTHORITY = "COMMANDER_AUTHORITY"
    ROUTE_STATUS_CHANGED = "ROUTE_STATUS_CHANGED"
    OBSERVATION = "OBSERVATION"
    BELIEF_UPDATE = "BELIEF_UPDATE"
    PLAN_CYCLE = "PLAN_CYCLE"
    PLAN_PROPOSED = "PLAN_PROPOSED"
    PLAN_SELECTED = "PLAN_SELECTED"
    TRACE_WRITTEN = "TRACE_WRITTEN"
    COMMITMENT_DECISION = "COMMITMENT_DECISION"
    ACTION_STARTED = "ACTION_STARTED"
    ASSET_MOVED = "ASSET_MOVED"
    ACTION_INTERRUPTED = "ACTION_INTERRUPTED"
    ACTION_COMPLETED = "ACTION_COMPLETED"
    BOARDING_STARTED = "BOARDING_STARTED"
    PEOPLE_PICKED_UP = "PEOPLE_PICKED_UP"
    UNLOADING_STARTED = "UNLOADING_STARTED"
    PEOPLE_DELIVERED = "PEOPLE_DELIVERED"
    ASSET_STANDBY = "ASSET_STANDBY"
    INCIDENT_MERGED = "INCIDENT_MERGED"
    INCIDENT_CANCELLED = "INCIDENT_CANCELLED"
    REVISION = "REVISION"
    LOCAL_REPAIR = "LOCAL_REPAIR"
    OUTCOME = "OUTCOME"
    METRIC_UPDATE = "METRIC_UPDATE"
    REASONING_STARTED = "REASONING_STARTED"
    REASONING_STEP = "REASONING_STEP"
    REASONING_COMPLETED = "REASONING_COMPLETED"


class Position(FrozenModel):
    x: float
    y: float


class PathSegment(FrozenModel):
    """One traversable segment of an authorized route-constrained path.

    `to_position` is the next point the asset may move to. A segment carries the
    underlying route and edge index so the simulator can stop at a newly blocked
    edge rather than allowing a straight-line shortcut across the map.
    """

    route_id: str | None = None
    edge_index: int | None = None
    direction: Literal["forward", "reverse", "direct"] = "direct"
    from_position: Position
    to_position: Position
    mode: Literal["water", "road", "air", "foot", "direct"] = "direct"
    segment_id: str = Field(default_factory=lambda: new_id("segment"))


class SimulationEvent(FrozenModel):
    event_id: str = Field(default_factory=lambda: new_id("event"))
    run_id: str
    sequence: int = Field(ge=1)
    simulation_time: float = Field(ge=0.0)
    source: str
    scenario_level: ScenarioLevel = ScenarioLevel.CORE
    event_type: EventType
    visibility: EventVisibility = EventVisibility.BOTH
    payload: dict[str, Any] = Field(default_factory=dict)
    schema_version: str = "simulation-event-v1.1"
    created_at: datetime = Field(default_factory=utc_now)


class S1Parameters(Model):
    drone_report_accuracy: float = Field(default=0.92, ge=0.0, le=1.0)
    sensor_noise: float = Field(default=0.12, ge=0.0, le=1.0)
    observation_latency_s: float = Field(default=2.0, ge=0.0, le=600.0)
    packet_loss: float = Field(default=0.02, ge=0.0, le=1.0)
    ood_severity: float = Field(default=0.25, ge=0.0, le=1.0)
    seed: int = 7


class S2Parameters(Model):
    rain_intensity: float = Field(default=0.25, ge=0.0, le=1.0)
    upstream_inflow: float = Field(default=0.20, ge=0.0, le=1.0)
    water_rise_rate: float = Field(default=0.00015, ge=0.0, le=0.1)
    route_closure_depth: float = Field(default=0.72, ge=0.05, le=2.0)
    clearance_horizon_s: float = Field(default=180.0, ge=5.0, le=3600.0)
    observation_freshness_s: float = Field(default=120.0, ge=1.0, le=3600.0)


class S3Parameters(Model):
    mission_budget: float = Field(default=1000.0, ge=0.0)
    severity_weight: float = Field(default=1.0, ge=0.0, le=10.0)
    deadline_weight: float = Field(default=1.0, ge=0.0, le=10.0)
    risk_weight: float = Field(default=1.0, ge=0.0, le=10.0)
    conflict_policy: Literal["serialize", "escalate"] = "serialize"


class S5Parameters(Model):
    default_drone_endurance: float = Field(default=0.82, ge=0.0, le=1.0)
    sensor_quality: float = Field(default=0.90, ge=0.0, le=1.0)
    sector_weather: float = Field(default=0.25, ge=0.0, le=1.0)
    value_of_information_weight: float = Field(default=0.70, ge=0.0, le=5.0)
    max_pending_surveys: int = Field(default=3, ge=1, le=20)


class RescueParameters(Model):
    """Timings and disposition for a complete rescue cycle.

    Arrival at the incident is only pickup. A group is counted as rescued after
    delivery to a declared safe location. By default the boat remains available
    at the safe transfer dock, where the global controller may retask it.
    """

    safe_location_id: str = "safe_transfer_dock"
    pickup_base_s: float = Field(default=6.0, ge=0.0, le=600.0)
    pickup_per_person_s: float = Field(default=1.5, ge=0.0, le=120.0)
    unload_base_s: float = Field(default=5.0, ge=0.0, le=600.0)
    unload_per_person_s: float = Field(default=1.0, ge=0.0, le=120.0)
    merge_alert_radius: float = Field(default=2.0, ge=0.0, le=25.0)
    post_rescue_policy: Literal["standby_at_safe_location", "return_home"] = (
        "standby_at_safe_location"
    )


class WorkbenchConfig(Model):
    s1: S1Parameters = Field(default_factory=S1Parameters)
    s2: S2Parameters = Field(default_factory=S2Parameters)
    s3: S3Parameters = Field(default_factory=S3Parameters)
    s5: S5Parameters = Field(default_factory=S5Parameters)
    rescue: RescueParameters = Field(default_factory=RescueParameters)
    commander_authority_present: bool = True
    auto_plan: bool = True
    planning_interval_s: float = Field(default=5.0, ge=0.5, le=300.0)
    simulation_speed: float = Field(default=1.0, ge=0.1, le=50.0)


class RouteTruth(Model):
    route_id: str
    label: str
    waypoints: list[Position]
    mode: Literal["water", "road", "air", "foot"] = "water"
    start_location_id: str | None = None
    end_location_id: str | None = None
    water_depth: float = Field(default=0.20, ge=0.0)
    debris_blocked: bool = False
    blockage_position: Position | None = None
    blocked_segment_index: int | None = None
    edge_open: list[bool] = Field(default_factory=list)
    open: bool = True
    susceptibility: float = Field(default=1.0, ge=0.0)
    nominal_travel_s: float = Field(default=600.0, ge=1.0)
    last_changed_at: float = 0.0


class RouteBelief(Model):
    route_id: str
    status: Literal["unknown", "open", "blocked"] = "unknown"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    observed_at: float | None = None
    source: str | None = None
    clearance_valid_until: float | None = None
    report_id: str | None = None
    blocked_segment_index: int | None = None


class AssetState(Model):
    asset_id: str
    asset_type: Literal["survey_drone", "rescue_boat", "helicopter", "ground_team"]
    position: Position
    home_position: Position | None = None
    safe_position: Position | None = None
    capacity: int = Field(default=0, ge=0)
    speed: float = Field(default=4.0, gt=0.0)
    resource: float = Field(default=1.0, ge=0.0, le=1.0)
    operating_cost: float = Field(default=1.0, ge=0.0)
    weather_tolerance: float = Field(default=0.7, ge=0.0, le=1.0)
    status: Literal[
        "available",
        "assigned",
        "moving",
        "loading",
        "unloading",
        "awaiting_clearance",
        "standby",
        "grounded",
        "depleted",
        "stranded",
    ] = "available"
    mission_phase: Literal[
        "idle",
        "surveying",
        "outbound",
        "loading",
        "awaiting_evacuation",
        "evacuating",
        "unloading",
        "standby",
        "returning",
    ] = "idle"
    assigned_group_id: str | None = None
    assigned_route_id: str | None = None
    action_type: str | None = None
    path: list[Position] = Field(default_factory=list)
    path_segments: list[PathSegment] = Field(default_factory=list)
    path_index: int = 0
    target: Position | None = None
    action_started_at: float | None = None
    authorization_record_id: str | None = None
    authorization_record_version: int | None = None
    interruption_reason: str | None = None
    passenger_count: int = Field(default=0, ge=0)
    passenger_group_ids: list[str] = Field(default_factory=list)
    heading_degrees: float = 0.0
    safe_location_id: str | None = None


class GroupState(Model):
    group_id: str
    label: str
    position: Position
    people: int = Field(ge=1)
    people_waiting: int | None = Field(default=None, ge=0)
    people_onboard: int = Field(default=0, ge=0)
    people_delivered: int = Field(default=0, ge=0)
    severity: float = Field(default=0.5, ge=0.0, le=1.0)
    deadline_s: float = Field(default=1200.0, ge=1.0)
    discovered: bool = True
    rescued: bool = False
    cancelled: bool = False
    assigned_asset_id: str | None = None
    condition: Literal["stable", "deteriorating", "critical", "rescued", "cancelled"] = "stable"
    rescue_phase: Literal[
        "waiting",
        "assigned",
        "boarding",
        "onboard",
        "partially_rescued",
        "delivered",
        "cancelled",
    ] = "waiting"
    safe_location_id: str | None = None
    alert_count: int = Field(default=1, ge=1)
    last_alert_at: float = Field(default=0.0, ge=0.0)
    source_call_id: str | None = None

    @model_validator(mode="after")
    def normalize_people_counts(self) -> "GroupState":
        if self.people_waiting is None:
            self.people_waiting = max(
                0,
                self.people - self.people_onboard - self.people_delivered,
            )
        total = self.people_waiting + self.people_onboard + self.people_delivered
        if total != self.people:
            raise ValueError(
                "group people counts must sum to people: "
                f"waiting={self.people_waiting}, onboard={self.people_onboard}, "
                f"delivered={self.people_delivered}, people={self.people}"
            )
        if self.people_delivered == self.people:
            self.rescued = True
            self.rescue_phase = "delivered"
            self.condition = "rescued"
        return self


class TruthState(Model):
    simulation_time: float = 0.0
    routes: dict[str, RouteTruth]
    assets: dict[str, AssetState]
    groups: dict[str, GroupState]
    weather_severity: float = Field(default=0.25, ge=0.0, le=1.0)
    communications_available: bool = True
    global_water_level: float = Field(default=0.20, ge=0.0)
    last_shock: str | None = None


class ReasoningStep(Model):
    stage: Literal[
        "trigger",
        "state",
        "prediction",
        "claim",
        "trace",
        "plan",
        "commitment",
    ]
    title: str
    summary: str
    status: Literal["pending", "complete", "warning", "blocked"] = "complete"
    details: dict[str, Any] = Field(default_factory=dict)


class ReasoningCycle(Model):
    cycle_id: str = Field(default_factory=lambda: new_id("reasoning"))
    trigger_event_id: str
    scenario_level: ScenarioLevel
    trigger_label: str
    simulation_time: float
    changes: list[dict[str, Any]] = Field(default_factory=list)
    steps: list[ReasoningStep] = Field(default_factory=list)
    affected_record_ids: list[str] = Field(default_factory=list)
    selected_plan_id: str | None = None
    selected_plan_name: str | None = None
    decision_change: str | None = None
    completed: bool = False


class ControllerState(Model):
    simulation_time: float = 0.0
    route_beliefs: dict[str, RouteBelief]
    known_assets: dict[str, AssetState]
    known_groups: dict[str, GroupState]
    pending_claims: list[dict[str, Any]] = Field(default_factory=list)
    requested_surveys: list[str] = Field(default_factory=list)
    active_commitments: list[dict[str, Any]] = Field(default_factory=list)
    last_plan_cycle_at: float = -1.0
    last_selected_plan: dict[str, Any] | None = None
    contradiction_count: int = 0
    latest_reasoning: ReasoningCycle | None = None
    reasoning_history: list[ReasoningCycle] = Field(default_factory=list)


class RunMetrics(Model):
    events: int = 0
    trace_records: int = 0
    commitments: int = 0
    clears: int = 0
    qualifies: int = 0
    holds: int = 0
    blocks: int = 0
    escalations: int = 0
    revisions: int = 0
    parameter_revisions: int = 0
    local_repairs: int = 0
    route_interruptions: int = 0
    rescued_people: int = 0
    onboard_people: int = 0
    pending_people: int = 0
    false_clears: int = 0
    false_holds: int = 0
    stale_clearance_actions: int = 0
    reconnaissance_sorties: int = 0
    wasted_reconnaissance: int = 0
    double_commitment_violations: int = 0
    last_model_support: float | None = None
    last_ood_score: float | None = None
    last_uncertainty: float | None = None
    max_water_depth: float = 0.0


class WorkbenchState(Model):
    run_id: str
    running: bool = False
    config: WorkbenchConfig = Field(default_factory=WorkbenchConfig)
    truth: TruthState
    controller: ControllerState
    metrics: RunMetrics = Field(default_factory=RunMetrics)


class WorkbenchSnapshot(FrozenModel):
    run_id: str
    running: bool
    config: dict[str, Any]
    truth: dict[str, Any]
    controller: dict[str, Any]
    metrics: dict[str, Any]
    recent_events: tuple[dict[str, Any], ...]
    recent_records: tuple[dict[str, Any], ...]
    event_chain_valid: bool
    trace_chain_valid: bool
    generated_at: datetime = Field(default_factory=utc_now)
