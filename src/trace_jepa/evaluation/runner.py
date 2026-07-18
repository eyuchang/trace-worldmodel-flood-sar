from __future__ import annotations

import asyncio
import importlib.metadata
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from trace_jepa.evaluation.adjudication import (
    RunDiagnostics,
    adjudicate_execution_truth,
    classify_failure,
)
from trace_jepa.evaluation.cached_storage import (
    CachedEventStore,
    CachedTraceRepository,
)
from trace_jepa.evaluation.workloads import (
    WORKLOAD_EVENT_ORDER,
    WORKLOAD_SCHEDULER_VERSION,
    CommonGaugeObservation,
    EvaluationWorkload,
    ScheduledIncident,
    load_evaluation_workload,
)
from trace_jepa.evaluation.ledger import (
    CommitmentLedgerRow,
    CommitmentUnitLedgerRow,
    RefreshLedgerRow,
    derive_commitment_ledger,
    derive_commitment_unit_ledger,
    derive_refresh_ledger,
    read_hashed_ledger,
    verify_hashed_ledger,
    write_hashed_ledger,
)
from trace_jepa.evaluation.metrics import (
    CommitmentMetrics,
    RefreshMetrics,
    compute_commitment_metrics,
    compute_proposal_record_metrics,
    compute_refresh_metrics,
    eligible_proposal_record_count,
)
from trace_jepa.refresh import (
    AdaptiveRefreshPolicy,
    FixedIntervalRefreshPolicy,
    NoRefreshPolicy,
    RefreshPolicy,
    ValidityClockRefreshPolicy,
)
from trace_jepa.runtime import PolicyConfig, TraceRepository
from trace_jepa.util import canonical_json, sha256_file, sha256_value
from trace_jepa.workbench.engine import DynamicRun
from trace_jepa.workbench.models import (
    EventType,
    EventVisibility,
    ScenarioLevel,
    SimulationEvent,
)
from trace_jepa.workbench.randomness import RNG_SCHEMA_VERSION, SEED_NAMESPACE
from trace_jepa.workbench.reducer import apply_event
from trace_jepa.workbench.scenario import load_initial_state
from trace_jepa.workbench.shocks import ShockRegistry, load_shock_registry
from trace_jepa.workbench.store import EventStore


RUN_SCHEMA_VERSION = "trace-evaluation-run-v1"
COMPLETION_SCHEMA_VERSION = "trace-run-completion-v1"
DAY1_ORIGINAL_DEVELOPMENT_SEEDS = frozenset(range(1, 21))
# Seeds 21--40 are reserved for amended-harness QA; seeds 41--60 are the
# untouched amended G2 pilot. Both remain development-only and are barred from
# confirmatory inference.
DAY1_AMENDMENT_DEVELOPMENT_SEEDS = frozenset(range(21, 61))
WP_E_SOURCE_ARCHIVE_SHA256 = (
    "dfcbdd5f08d65490358f21bda55f2345014c1d0aac45b0ddcd4d8e6470993bc6"
)


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RunRequest(FrozenModel):
    """One Day-1 development cell; validation and test partitions are blocked."""

    regime: Literal["R-B"] = "R-B"
    policy: str
    seed: int = Field(ge=1, le=60)
    scenario_path: Path
    shock_registry_root: Path
    protocol_path: Path
    output_root: Path
    evaluation_workload_path: Path | None = None
    protocol_amendment_id: str | None = Field(
        default=None, pattern=r"^[a-z0-9][a-z0-9._-]{0,95}$"
    )
    forcing_noise_std: float = Field(default=0.35, ge=0.0, le=2.0)
    duration_s: float = Field(default=7200.0, gt=0.0, le=86_400.0)
    tick_s: float = Field(default=1.0, gt=0.0, le=1.0)
    requested_speed: float = Field(default=50.0, gt=0.0, le=50.0)
    resume: bool = True

    @model_validator(mode="after")
    def validate_finite_grid(self) -> "RunRequest":
        numeric = (
            self.forcing_noise_std,
            self.duration_s,
            self.tick_s,
            self.requested_speed,
        )
        if not all(math.isfinite(value) for value in numeric):
            raise ValueError("numeric run parameters must be finite")
        if not math.isclose(self.tick_s, 1.0, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("the Day-1 E6 protocol requires tick_s exactly 1.0")
        steps = self.duration_s / self.tick_s
        if not math.isclose(steps, round(steps), rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("duration_s must be an integer multiple of tick_s")
        if (self.evaluation_workload_path is None) != (
            self.protocol_amendment_id is None
        ):
            raise ValueError(
                "evaluation_workload_path and protocol_amendment_id must be set together"
            )
        allowed_seeds = (
            DAY1_AMENDMENT_DEVELOPMENT_SEEDS
            if self.evaluation_workload_path is not None
            else DAY1_ORIGINAL_DEVELOPMENT_SEEDS
        )
        if self.seed not in allowed_seeds:
            raise ValueError(
                "seed is outside the development partition for this protocol"
            )
        return self


class ResolvedPolicy(FrozenModel):
    spec: str
    family: Literal["none", "fixed_k", "validity_clock", "adaptive"]
    parameter_name: str | None = None
    parameter_value: float | None = None
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,95}$")


class CommonBaselineEvidenceMetrics(FrozenModel):
    acquisitions: int = Field(default=0, ge=0)
    usable_acquisitions: int = Field(default=0, ge=0)
    total_cost: float = Field(default=0.0, ge=0.0)


class VerificationCostMetrics(FrozenModel):
    discretionary_acquisitions: int = Field(ge=0)
    common_baseline_acquisitions: int = Field(ge=0)
    total_acquisitions: int = Field(ge=0)
    discretionary_cost: float = Field(ge=0.0)
    common_baseline_cost: float = Field(ge=0.0)
    total_cost: float = Field(ge=0.0)

    @model_validator(mode="after")
    def validate_totals(self) -> "VerificationCostMetrics":
        if self.total_acquisitions != (
            self.discretionary_acquisitions + self.common_baseline_acquisitions
        ):
            raise ValueError("verification acquisition counts do not conserve")
        if not math.isclose(
            self.total_cost,
            self.discretionary_cost + self.common_baseline_cost,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("verification costs do not conserve")
        return self


class RunMetricsArtifact(FrozenModel):
    schema_version: Literal["trace-run-metrics-v1", "trace-run-metrics-v2"] = (
        "trace-run-metrics-v2"
    )
    run_id: str
    regime: Literal["R-B"]
    policy: str
    seed: int
    completed: bool
    terminal_simulation_time: float = Field(ge=0.0)
    event_count: int = Field(ge=0)
    commitment: CommitmentMetrics
    refresh: RefreshMetrics
    common_baseline_evidence: CommonBaselineEvidenceMetrics = Field(
        default_factory=CommonBaselineEvidenceMetrics
    )
    verification_cost: VerificationCostMetrics | None = None
    mission: dict[str, Any]

    @model_validator(mode="after")
    def validate_schema_contract(self) -> "RunMetricsArtifact":
        if self.schema_version == "trace-run-metrics-v2":
            if self.commitment.proposal_records is None:
                raise ValueError("v2 metrics require raw proposal-record count")
            if self.verification_cost is None:
                raise ValueError("v2 metrics require complete verification cost")
        return self


class CompletionMarker(FrozenModel):
    schema_version: Literal["trace-run-completion-v1"] = COMPLETION_SCHEMA_VERSION
    run_schema_version: Literal["trace-evaluation-run-v1"] = RUN_SCHEMA_VERSION
    run_id: str
    run_fingerprint: str
    artifact_sha256: dict[str, str]
    completion_hash: str

    @model_validator(mode="after")
    def validate_completion_hash(self) -> "CompletionMarker":
        expected = sha256_value(
            {
                "schema_version": self.schema_version,
                "run_schema_version": self.run_schema_version,
                "run_id": self.run_id,
                "run_fingerprint": self.run_fingerprint,
                "artifact_sha256": self.artifact_sha256,
            }
        )
        if self.completion_hash != expected:
            raise ValueError("completion marker hash is invalid")
        return self


class FailedRunArtifact(FrozenModel):
    schema_version: Literal["trace-failed-run-v1"] = "trace-failed-run-v1"
    run_id: str
    run_fingerprint: str
    failed_at_utc: str
    phase: str
    exception_type: str
    exception_message: str
    diagnostics: dict[str, Any]
    classification: dict[str, Any]
    partial_artifact_sha256: dict[str, str]


def _strict_float(text: str, *, name: str) -> float:
    try:
        value = float(text)
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def _float_slug(value: float) -> str:
    rendered = format(value, ".12g")
    return rendered.replace("-", "m").replace(".", "p").replace("+", "")


def resolve_policy(spec: str) -> tuple[ResolvedPolicy, RefreshPolicy]:
    """Parse a closed policy grammar so a spec can never become a path."""

    if spec == "none":
        return (
            ResolvedPolicy(spec=spec, family="none", slug="none"),
            NoRefreshPolicy(),
        )
    if spec.startswith("fixed-k:"):
        value = _strict_float(spec.removeprefix("fixed-k:"), name="fixed-k interval")
        if not 0.0 < value <= 7200.0:
            raise ValueError("fixed-k interval must lie in (0, 7200]")
        return (
            ResolvedPolicy(
                spec=spec,
                family="fixed_k",
                parameter_name="interval_s",
                parameter_value=value,
                slug=f"fixed-k-{_float_slug(value)}",
            ),
            FixedIntervalRefreshPolicy(value),
        )
    if spec.startswith("clock:"):
        value = _strict_float(spec.removeprefix("clock:"), name="clock alpha")
        if not 0.0 <= value <= 1.0:
            raise ValueError("clock alpha must lie in [0, 1]")
        return (
            ResolvedPolicy(
                spec=spec,
                family="validity_clock",
                parameter_name="alpha",
                parameter_value=value,
                slug=f"clock-{_float_slug(value)}",
            ),
            ValidityClockRefreshPolicy(value),
        )
    if spec.startswith("adaptive:"):
        value = _strict_float(spec.removeprefix("adaptive:"), name="adaptive epsilon_c")
        if not 0.0 < value < 7.5:
            raise ValueError("adaptive epsilon_c must lie in (0, 7.5)")
        return (
            ResolvedPolicy(
                spec=spec,
                family="adaptive",
                parameter_name="epsilon_c",
                parameter_value=value,
                slug=f"adaptive-eps-{_float_slug(value)}",
            ),
            AdaptiveRefreshPolicy(),
        )
    raise ValueError(
        "policy must be one of none, fixed-k:<seconds>, clock:<alpha>, "
        "adaptive:<epsilon_c>"
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _atomic_write_json(path: Path, payload: Any) -> None:
    _atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _confined_file(path: Path, root: Path, *, label: str) -> Path:
    resolved_root = root.resolve(strict=True)
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"{label} must be contained by the project root") from exc
    if not resolved.is_file():
        raise ValueError(f"{label} must be a regular file")
    return resolved


def _git_output(repository_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return completed.stdout.strip()


def _source_inventory(repository_root: Path) -> list[dict[str, str]]:
    roots = [repository_root / "src", repository_root / "scripts"]
    files: set[Path] = {repository_root / "pyproject.toml"}
    for root in roots:
        files.update(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)
    files.update((repository_root / "configs" / "policies").glob("*.yaml"))
    files.update((repository_root / "configs" / "scenarios").glob("*.yaml"))
    files.update((repository_root / "configs" / "shocks").rglob("*.yaml"))
    files.update((repository_root / "configs" / "workloads").rglob("*.yaml"))
    return [
        {
            "path": path.relative_to(repository_root).as_posix(),
            "sha256": sha256_file(path),
        }
        for path in sorted(files)
        if path.is_file()
    ]


def scientific_source_tree_hash(repository_root: str | Path) -> str:
    """Return the exact source/configuration hash used in run identities."""

    return sha256_value(_source_inventory(Path(repository_root).resolve(strict=True)))


def _environment_inventory() -> dict[str, Any]:
    packages = sorted(
        (
            {"name": distribution.metadata["Name"], "version": distribution.version}
            for distribution in importlib.metadata.distributions()
            if distribution.metadata["Name"]
        ),
        key=lambda item: item["name"].lower(),
    )
    return {
        "python": sys.version,
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "packages": packages,
    }


def _seed_incident(run: DynamicRun) -> None:
    run.emit(
        EventType.EMERGENCY_CALL,
        source="evaluation_harness",
        scenario_level=ScenarioLevel.S3,
        payload={
            "group_id": "group_riverside",
            "location_label": "Riverside Apartments",
            "position": {"x": 88.0, "y": 66.0},
            "people": 4,
            "severity": 0.55,
            "deadline_s": 1200.0,
            "safe_location_id": "safe_transfer_dock",
        },
    )


def _validate_shock_grid(registry: ShockRegistry, tick_s: float) -> None:
    for entry in registry.entries:
        grid_index = entry.scheduled_at / tick_s
        if not math.isclose(grid_index, round(grid_index), rel_tol=0.0, abs_tol=1e-9):
            raise ValueError(
                f"shock {entry.shock_id} at {entry.scheduled_at} is not aligned "
                f"to tick_s={tick_s}"
            )


def _validate_evaluation_workload(
    workload: EvaluationWorkload,
    *,
    tick_s: float,
    duration_s: float,
    scenario_path: Path,
) -> None:
    state = load_initial_state("incident-schedule-validation", scenario_path)
    terminal_route_positions = {
        (route.waypoints[-1].x, route.waypoints[-1].y)
        for route in state.truth.routes.values()
        if route.waypoints
    }
    for observation in workload.common_gauge_observations:
        for timestamp in (observation.sampled_at, observation.delivered_at):
            grid_index = timestamp / tick_s
            if not math.isclose(
                grid_index, round(grid_index), rel_tol=0.0, abs_tol=1e-9
            ):
                raise ValueError(
                    f"gauge {observation.observation_id} at {timestamp} is not "
                    f"aligned to tick_s={tick_s}"
                )
            if timestamp >= duration_s:
                raise ValueError(
                    f"gauge {observation.observation_id} lies outside the horizon"
                )
        if observation.route_id not in state.truth.routes:
            raise ValueError(
                f"gauge {observation.observation_id} references an unknown route"
            )
    for entry in workload.incidents:
        grid_index = entry.scheduled_at / tick_s
        if not math.isclose(grid_index, round(grid_index), rel_tol=0.0, abs_tol=1e-9):
            raise ValueError(
                f"incident {entry.incident_id} at {entry.scheduled_at} is not "
                f"aligned to tick_s={tick_s}"
            )
        if entry.scheduled_at >= duration_s:
            raise ValueError(
                f"incident {entry.incident_id} lies outside the mission horizon"
            )
        if entry.safe_location_id != state.config.rescue.safe_location_id:
            raise ValueError(
                f"incident {entry.incident_id} references an undeclared safe location"
            )
        position = (entry.position.x, entry.position.y)
        if position not in terminal_route_positions:
            raise ValueError(
                f"incident {entry.incident_id} is not located at a declared route terminal"
            )


def _scheduled_incident_payload(
    workload: EvaluationWorkload, entry: ScheduledIncident
) -> dict[str, Any]:
    return {
        "workload_id": workload.workload_id,
        "workload_hash": workload.workload_hash,
        "amendment_id": workload.amendment_id,
        "incident_id": entry.incident_id,
        "scheduled_at": entry.scheduled_at,
        "group_id": entry.group_id,
        "location_label": entry.location_label,
        "position": entry.position.model_dump(mode="json"),
        "people": entry.people,
        "severity": entry.severity,
        "deadline_s": entry.deadline_s,
        "safe_location_id": entry.safe_location_id,
    }


def _common_gauge_request_payload(
    workload: EvaluationWorkload,
    observation: CommonGaugeObservation,
    *,
    sampled_water_depth: float,
) -> dict[str, Any]:
    return {
        "workload_id": workload.workload_id,
        "workload_hash": workload.workload_hash,
        "amendment_id": workload.amendment_id,
        "observation_id": observation.observation_id,
        "refresh_decision_id": f"common-baseline:{observation.observation_id}",
        "evidence_request_id": f"common-baseline:{observation.observation_id}",
        "route_id": observation.route_id,
        "requested_at": observation.sampled_at,
        "sampled_at": observation.sampled_at,
        "deliver_at": observation.delivered_at,
        "sampled_water_depth": sampled_water_depth,
        "cost": observation.cost,
        "latency_s": observation.delivered_at - observation.sampled_at,
        "policy": "common_baseline",
        "claim_id": None,
        "commitment_id": None,
    }


async def _simulate(
    run: DynamicRun,
    request: RunRequest,
    registry: ShockRegistry,
    workload: EvaluationWorkload | None,
) -> None:
    run.emit(
        EventType.SET_S1_PARAMETERS,
        source="evaluation_harness",
        scenario_level=ScenarioLevel.S1,
        payload={"seed": request.seed},
    )
    run.emit(
        EventType.SET_S2_PARAMETERS,
        source="evaluation_harness",
        scenario_level=ScenarioLevel.S2,
        payload={"forcing_noise_std": request.forcing_noise_std},
    )
    if workload is None:
        _seed_incident(run)
    await run.start()
    await run.plan_now()

    shock_index = 0
    gauge_sample_index = 0
    gauge_delivery_index = 0
    incident_index = 0
    sampled_gauges: dict[str, dict[str, Any]] = {}
    while run.state.truth.simulation_time < request.duration_s:
        now = run.state.truth.simulation_time
        while (
            shock_index < len(registry.entries)
            and registry.entries[shock_index].scheduled_at <= now + 1e-9
        ):
            entry = registry.entries[shock_index]
            await run.inject_event(
                event_type=EventType.INJECT_SHOCK,
                scenario_level=ScenarioLevel.S4,
                visibility=EventVisibility.TRUTH,
                source="registered_shock_scheduler",
                payload={
                    "shock_id": entry.shock_id,
                    "scheduled_at": entry.scheduled_at,
                    "shock_type": entry.shock_type,
                    "severity": entry.severity,
                    "target": entry.target,
                    "registry_hash": registry.registry_hash,
                },
            )
            shock_index += 1
        while (
            workload is not None
            and gauge_sample_index < len(workload.common_gauge_observations)
            and workload.common_gauge_observations[gauge_sample_index].sampled_at
            <= now + 1e-9
        ):
            observation = workload.common_gauge_observations[gauge_sample_index]
            sampled_water_depth = run.state.truth.routes[
                observation.route_id
            ].water_depth
            request_payload = _common_gauge_request_payload(
                workload,
                observation,
                sampled_water_depth=sampled_water_depth,
            )
            run.emit(
                EventType.GAUGE_POLL,
                source="common_baseline_gauge",
                scenario_level=ScenarioLevel.S5,
                visibility=EventVisibility.AUDIT,
                payload=request_payload,
            )
            sampled_gauges[observation.observation_id] = request_payload
            gauge_sample_index += 1
        while (
            workload is not None
            and gauge_delivery_index < len(workload.common_gauge_observations)
            and workload.common_gauge_observations[
                gauge_delivery_index
            ].delivered_at
            <= now + 1e-9
        ):
            observation = workload.common_gauge_observations[
                gauge_delivery_index
            ]
            request_payload = sampled_gauges.get(observation.observation_id)
            if request_payload is None:
                raise RuntimeError(
                    f"gauge {observation.observation_id} delivered before sampling"
                )
            observation_event = run.emit(
                EventType.OBSERVATION,
                source="common_baseline_gauge",
                scenario_level=ScenarioLevel.S1,
                visibility=EventVisibility.CONTROLLER,
                payload={
                    "kind": "route_depth",
                    "route_id": observation.route_id,
                    "water_depth": request_payload["sampled_water_depth"],
                    "source": "common_baseline_gauge",
                    "observed_at": observation.sampled_at,
                    "observation_id": observation.observation_id,
                    "evidence_request_id": request_payload[
                        "evidence_request_id"
                    ],
                    "workload_id": workload.workload_id,
                    "workload_hash": workload.workload_hash,
                },
            )
            run.emit(
                EventType.EVIDENCE_ACQUIRED,
                source="common_baseline_gauge",
                scenario_level=ScenarioLevel.S5,
                visibility=EventVisibility.AUDIT,
                payload={
                    "refresh_decision_id": request_payload[
                        "refresh_decision_id"
                    ],
                    "evidence_request_id": request_payload[
                        "evidence_request_id"
                    ],
                    "channel": "gauge_poll",
                    "route_id": observation.route_id,
                    "observation_id": observation.observation_id,
                    "observation_event_id": observation_event.event_id,
                    "observed_at": observation.sampled_at,
                    "delivered_at": observation.delivered_at,
                    "latency_s": observation.delivered_at
                    - observation.sampled_at,
                    "cost": observation.cost,
                    "usable": True,
                    "policy": "common_baseline",
                    "claim_id": None,
                    "commitment_id": None,
                    "workload_id": workload.workload_id,
                    "workload_hash": workload.workload_hash,
                },
            )
            gauge_delivery_index += 1
        while (
            workload is not None
            and incident_index < len(workload.incidents)
            and workload.incidents[incident_index].scheduled_at
            <= now + 1e-9
        ):
            entry = workload.incidents[incident_index]
            await run.inject_event(
                event_type=EventType.EMERGENCY_CALL,
                scenario_level=ScenarioLevel.S3,
                visibility=EventVisibility.BOTH,
                source="registered_workload_scheduler",
                payload=_scheduled_incident_payload(workload, entry),
            )
            incident_index += 1
        await run.step(request.tick_s)

    if shock_index != len(registry.entries):
        unobserved = [entry.shock_id for entry in registry.entries[shock_index:]]
        raise ValueError(f"registered shocks lie outside the mission horizon: {unobserved}")
    if workload is not None and gauge_sample_index != len(
        workload.common_gauge_observations
    ):
        raise ValueError("registered gauge samples lie outside the mission horizon")
    if workload is not None and gauge_delivery_index != len(
        workload.common_gauge_observations
    ):
        raise ValueError("registered gauge deliveries lie outside the mission horizon")
    if workload is not None and incident_index != len(workload.incidents):
        unobserved = [
            entry.incident_id for entry in workload.incidents[incident_index:]
        ]
        raise ValueError(
            f"registered incidents lie outside the mission horizon: {unobserved}"
        )
    await run.pause()


def _exogenous_projection(
    initial_state: Any,
    events: list[SimulationEvent],
) -> list[dict[str, Any]]:
    """Replay only declared environment inputs, independent of policy actions."""

    replay = initial_state.model_copy(deep=True)
    rows: list[dict[str, Any]] = []
    for event in events:
        if event.event_type in {EventType.SET_S1_PARAMETERS, EventType.SET_S2_PARAMETERS}:
            apply_event(replay, event)
        elif event.event_type == EventType.TICK:
            apply_event(replay, event)
            rows.append(
                {
                    "kind": "environment_tick",
                    "simulation_time": replay.truth.simulation_time,
                    "environment_tick_index": replay.truth.environment_tick_index,
                    "forcing_noise_z": event.payload.get("forcing_noise_z"),
                    "global_water_level": replay.truth.global_water_level,
                    "route_water_depths": {
                        route_id: route.water_depth
                        for route_id, route in sorted(replay.truth.routes.items())
                    },
                }
            )
        elif event.event_type == EventType.INJECT_SHOCK:
            apply_event(replay, event)
            rows.append(
                {
                    "kind": "registered_shock",
                    "simulation_time": event.simulation_time,
                    "payload": event.payload,
                }
            )
        elif (
            event.event_type == EventType.EMERGENCY_CALL
            and event.source == "registered_workload_scheduler"
        ):
            rows.append(
                {
                    "kind": "registered_incident",
                    "simulation_time": event.simulation_time,
                    "payload": event.payload,
                }
            )
        elif event.source == "common_baseline_gauge" and event.event_type in {
            EventType.GAUGE_POLL,
            EventType.OBSERVATION,
            EventType.EVIDENCE_ACQUIRED,
        }:
            rows.append(
                {
                    "kind": "common_baseline_gauge",
                    "event_type": event.event_type.value,
                    "simulation_time": event.simulation_time,
                    "payload": {
                        key: value
                        for key, value in event.payload.items()
                        if key != "observation_event_id"
                    },
                }
            )
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    content = "".join(canonical_json(row) + "\n" for row in rows)
    _atomic_write_text(path, content)


def _mission_summary(run: DynamicRun) -> dict[str, Any]:
    # Preserve the simulator's full versioned metric vocabulary instead of
    # silently inventing a second outcome schema in the experiment harness.
    return run.state.metrics.model_dump(mode="json")


def _common_baseline_metrics(
    events: list[SimulationEvent],
) -> CommonBaselineEvidenceMetrics:
    acquisitions = [
        event
        for event in events
        if event.event_type == EventType.EVIDENCE_ACQUIRED
        and event.source == "common_baseline_gauge"
    ]
    return CommonBaselineEvidenceMetrics(
        acquisitions=len(acquisitions),
        usable_acquisitions=sum(
            event.payload.get("usable") is True for event in acquisitions
        ),
        total_cost=sum(float(event.payload.get("cost", 0.0)) for event in acquisitions),
    )


def _verification_cost_metrics(
    *,
    refresh: RefreshMetrics,
    common_baseline: CommonBaselineEvidenceMetrics,
) -> VerificationCostMetrics:
    return VerificationCostMetrics(
        discretionary_acquisitions=refresh.evidence_acquisitions,
        common_baseline_acquisitions=common_baseline.acquisitions,
        total_acquisitions=(
            refresh.evidence_acquisitions + common_baseline.acquisitions
        ),
        discretionary_cost=refresh.total_cost,
        common_baseline_cost=common_baseline.total_cost,
        total_cost=refresh.total_cost + common_baseline.total_cost,
    )


def _artifact_hashes(directory: Path) -> dict[str, str]:
    return {
        path.relative_to(directory).as_posix(): sha256_file(path)
        for path in sorted(directory.rglob("*"))
        if path.is_file() and path.name != "COMPLETED.json"
    }


def _scientific_identity(
    *,
    request: RunRequest,
    resolved_policy: ResolvedPolicy,
    repository_root: Path,
    scenario_path: Path,
    registry_path: Path,
    registry: ShockRegistry,
    evaluation_workload_path: Path | None,
    evaluation_workload: EvaluationWorkload | None,
    protocol_path: Path,
    source_inventory: list[dict[str, str]],
    environment: dict[str, Any],
) -> dict[str, Any]:
    gate_policy_path = repository_root / "configs/policies/trace_v1.yaml"
    gate_policy = PolicyConfig.from_yaml(gate_policy_path)
    git_status = _git_output(repository_root, "status", "--porcelain=v1")
    return {
        "schema_version": RUN_SCHEMA_VERSION,
        "partition": "development",
        "request": {
            "regime": request.regime,
            "policy": request.policy,
            "seed": request.seed,
            "forcing_noise_std": request.forcing_noise_std,
            "duration_s": request.duration_s,
            "tick_s": request.tick_s,
            "requested_speed": request.requested_speed,
            "execution_mode": "accelerated_discrete_no_wall_sleep",
            "protocol_amendment_id": request.protocol_amendment_id,
        },
        "resolved_policy": resolved_policy.model_dump(mode="json"),
        "rng": {
            "schema_version": RNG_SCHEMA_VERSION,
            "seed_namespace": SEED_NAMESPACE,
        },
        "scenario": {
            "path": scenario_path.relative_to(repository_root).as_posix(),
            "sha256": sha256_file(scenario_path),
        },
        "shock_registry": {
            "path": registry_path.relative_to(repository_root).as_posix(),
            "sha256": sha256_file(registry_path),
            "semantic_hash": registry.registry_hash,
            "entry_count": len(registry.entries),
        },
        "evaluation_workload": (
            {
                "enabled": True,
                "path": evaluation_workload_path.relative_to(
                    repository_root
                ).as_posix(),
                "sha256": sha256_file(evaluation_workload_path),
                "semantic_hash": evaluation_workload.workload_hash,
                "workload_id": evaluation_workload.workload_id,
                "amendment_id": evaluation_workload.amendment_id,
                "incident_count": len(evaluation_workload.incidents),
                "common_gauge_count": len(
                    evaluation_workload.common_gauge_observations
                ),
                "common_gauge_cost": sum(
                    observation.cost
                    for observation in evaluation_workload.common_gauge_observations
                ),
                "scheduler_version": WORKLOAD_SCHEDULER_VERSION,
                "event_order": WORKLOAD_EVENT_ORDER,
            }
            if evaluation_workload_path is not None
            and evaluation_workload is not None
            else {"enabled": False}
        ),
        "protocol": {
            "path": protocol_path.relative_to(repository_root.parent).as_posix(),
            "sha256": sha256_file(protocol_path),
        },
        "effective_gate_policy": {
            "path": gate_policy_path.relative_to(repository_root).as_posix(),
            "sha256": sha256_file(gate_policy_path),
            "resolved": gate_policy.model_dump(mode="json"),
            "note": "trace_exp_v1.yaml is provisional and inactive before E11/G3",
        },
        "patch_provenance": {
            "wp_e_source_archive_sha256": WP_E_SOURCE_ARCHIVE_SHA256,
            "integration_note": "docs/ACTIVE_REFRESH_IMPLEMENTATION_NOTES.md",
        },
        "code": {
            "git_commit": _git_output(repository_root, "rev-parse", "HEAD"),
            "git_dirty": bool(git_status),
            "git_status": git_status.splitlines(),
            "source_tree_hash": sha256_value(source_inventory),
        },
        "environment_hash": sha256_value(environment),
    }


def _run_fingerprint(identity: dict[str, Any]) -> str:
    return sha256_value(identity)


def _assert_execution_labels(
    events: list[SimulationEvent],
    labels: dict[int, Any],
) -> None:
    for event in events:
        label = labels.get(event.sequence)
        if label is None:
            continue
        if event.payload.get("truth_safe_at_execution") is not label.truth_safe:
            raise ValueError(
                f"execution {event.sequence} truth label disagrees with replay oracle"
            )
        if bool(event.payload.get("executed_stale", False)) != label.executed_stale:
            raise ValueError(
                f"execution {event.sequence} stale label disagrees with replay oracle"
            )


def _quarantine_path(path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    candidate = path.with_name(f".{path.name}.quarantine-{stamp}")
    counter = 1
    while candidate.exists():
        candidate = path.with_name(f".{path.name}.quarantine-{stamp}-{counter}")
        counter += 1
    return candidate


def _quarantine(path: Path) -> Path:
    destination = _quarantine_path(path)
    os.replace(path, destination)
    return destination


def _copy_if_exists(source: Path, destination: Path) -> None:
    if source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def _read_events(path: Path) -> list[SimulationEvent]:
    return EventStore(path).all()


def _assert_event_time_and_scheduler_order(events: list[SimulationEvent]) -> None:
    previous_time = -math.inf
    ranks_by_time: dict[float, list[int]] = {}
    for event in events:
        if event.simulation_time < previous_time:
            raise ValueError("event simulation times are not nondecreasing")
        previous_time = event.simulation_time
        rank: int | None = None
        if event.source == "registered_shock_scheduler":
            rank = 0
        elif (
            event.source == "common_baseline_gauge"
            and event.event_type == EventType.GAUGE_POLL
        ):
            rank = 1
        elif event.source == "common_baseline_gauge":
            rank = 2
        elif event.source == "registered_workload_scheduler":
            rank = 3
        elif event.event_type == EventType.TICK:
            rank = 4
        if rank is not None:
            ranks_by_time.setdefault(event.simulation_time, []).append(rank)
    if any(ranks != sorted(ranks) for ranks in ranks_by_time.values()):
        raise ValueError("registered scheduler events violate declared event order")


def _assert_shock_registry_events(
    *, identity: dict[str, Any], events: list[SimulationEvent], repository_root: Path
) -> None:
    shock_root = repository_root / "configs" / "shocks"
    registry_identity = identity["shock_registry"]
    registry_path = _confined_file(
        repository_root / str(registry_identity["path"]),
        shock_root,
        label="manifest shock registry",
    )
    if sha256_file(registry_path) != registry_identity["sha256"]:
        raise ValueError("shock registry bytes no longer match run identity")
    registry = load_shock_registry(
        registry_path,
        registry_root=shock_root,
        expected_seed=int(identity["request"]["seed"]),
        expected_regime=str(identity["request"]["regime"]),
    )
    if registry.registry_hash != registry_identity["semantic_hash"]:
        raise ValueError("shock registry semantic hash is invalid")
    if len(registry.entries) != registry_identity["entry_count"]:
        raise ValueError("shock registry entry count is invalid")

    expected = {entry.shock_id: entry for entry in registry.entries}
    observed: dict[str, SimulationEvent] = {}
    for event in events:
        if event.event_type != EventType.INJECT_SHOCK:
            continue
        if event.source != "registered_shock_scheduler":
            raise ValueError("event log contains an unregistered shock source")
        shock_id = str(event.payload.get("shock_id", ""))
        entry = expected.get(shock_id)
        if entry is None:
            raise ValueError("event log contains a shock absent from its registry")
        if shock_id in observed:
            raise ValueError("event log contains a duplicate registered shock")
        expected_payload = {
            "shock_id": entry.shock_id,
            "scheduled_at": entry.scheduled_at,
            "shock_type": entry.shock_type,
            "severity": entry.severity,
            "target": entry.target,
            "registry_hash": registry.registry_hash,
        }
        if event.payload != expected_payload:
            raise ValueError("registered shock payload does not match its registry")
        if event.simulation_time != entry.scheduled_at:
            raise ValueError("registered shock occurred at the wrong time")
        if (
            event.scenario_level != ScenarioLevel.S4
            or event.visibility != EventVisibility.TRUTH
        ):
            raise ValueError("registered shock has invalid visibility or level")
        observed[shock_id] = event
    if set(observed) != set(expected):
        raise ValueError("registered shock event inventory is incomplete")


def _assert_evaluation_workload_events(
    *,
    identity: dict[str, Any],
    initial_state: Any,
    events: list[SimulationEvent],
    repository_root: Path,
) -> None:
    workload_identity = identity.get("evaluation_workload", {"enabled": False})
    registered_sources = {
        "common_baseline_gauge",
        "registered_workload_scheduler",
    }
    if not workload_identity.get("enabled", False):
        if any(event.source in registered_sources for event in events):
            raise ValueError("legacy run contains unregistered amended-workload events")
        emergency_calls = [
            event for event in events if event.event_type == EventType.EMERGENCY_CALL
        ]
        if len(emergency_calls) != 1:
            raise ValueError("legacy evaluation demand inventory is invalid")
        emergency = emergency_calls[0]
        if (
            emergency.source != "evaluation_harness"
            or emergency.simulation_time != 0.0
            or emergency.scenario_level != ScenarioLevel.S3
            or emergency.visibility != EventVisibility.BOTH
            or emergency.payload
            != {
                "group_id": "group_riverside",
                "location_label": "Riverside Apartments",
                "position": {"x": 88.0, "y": 66.0},
                "people": 4,
                "severity": 0.55,
                "deadline_s": 1200.0,
                "safe_location_id": "safe_transfer_dock",
            }
        ):
            raise ValueError("legacy evaluation demand event is invalid")
        return

    workload_root = repository_root / "configs" / "workloads"
    workload_path = _confined_file(
        repository_root / str(workload_identity["path"]),
        workload_root,
        label="manifest evaluation workload",
    )
    if sha256_file(workload_path) != workload_identity["sha256"]:
        raise ValueError("evaluation workload bytes no longer match run identity")
    workload = load_evaluation_workload(
        workload_path,
        workload_root=workload_root,
        expected_amendment_id=identity["request"]["protocol_amendment_id"],
        expected_regime=identity["request"]["regime"],
    )
    if workload.workload_hash != workload_identity["semantic_hash"]:
        raise ValueError("evaluation workload semantic hash is invalid")

    expected_gauges = {
        observation.observation_id: observation
        for observation in workload.common_gauge_observations
    }
    expected_incidents = {
        incident.incident_id: incident for incident in workload.incidents
    }
    gauge_requests: dict[str, SimulationEvent] = {}
    gauge_observations: dict[str, SimulationEvent] = {}
    gauge_acquisitions: dict[str, SimulationEvent] = {}
    incident_events: dict[str, SimulationEvent] = {}
    replay = initial_state.model_copy(deep=True)

    for event in events:
        if event.source == "common_baseline_gauge":
            observation_id = str(event.payload.get("observation_id", ""))
            observation = expected_gauges.get(observation_id)
            if observation is None:
                raise ValueError("unregistered common gauge observation")
            if event.event_type == EventType.GAUGE_POLL:
                if observation_id in gauge_requests:
                    raise ValueError("duplicate common gauge request")
                expected_payload = _common_gauge_request_payload(
                    workload,
                    observation,
                    sampled_water_depth=replay.truth.routes[
                        observation.route_id
                    ].water_depth,
                )
                if event.simulation_time != observation.sampled_at:
                    raise ValueError("common gauge sampled at the wrong time")
                if event.payload != expected_payload:
                    raise ValueError("common gauge request payload is invalid")
                if (
                    event.scenario_level != ScenarioLevel.S5
                    or event.visibility != EventVisibility.AUDIT
                ):
                    raise ValueError("common gauge request has invalid visibility")
                gauge_requests[observation_id] = event
            elif event.event_type == EventType.OBSERVATION:
                request_event = gauge_requests.get(observation_id)
                if request_event is None:
                    raise ValueError("common gauge delivered before its request")
                expected_payload = {
                    "kind": "route_depth",
                    "route_id": observation.route_id,
                    "water_depth": request_event.payload["sampled_water_depth"],
                    "source": "common_baseline_gauge",
                    "observed_at": observation.sampled_at,
                    "observation_id": observation.observation_id,
                    "evidence_request_id": request_event.payload[
                        "evidence_request_id"
                    ],
                    "workload_id": workload.workload_id,
                    "workload_hash": workload.workload_hash,
                }
                if event.simulation_time != observation.delivered_at:
                    raise ValueError("common gauge delivered at the wrong time")
                if event.payload != expected_payload:
                    raise ValueError("common gauge observation payload is invalid")
                if (
                    event.scenario_level != ScenarioLevel.S1
                    or event.visibility != EventVisibility.CONTROLLER
                ):
                    raise ValueError("common gauge observation has invalid visibility")
                if observation_id in gauge_observations:
                    raise ValueError("duplicate common gauge observation")
                gauge_observations[observation_id] = event
            elif event.event_type == EventType.EVIDENCE_ACQUIRED:
                observation_event = gauge_observations.get(observation_id)
                request_event = gauge_requests.get(observation_id)
                if observation_event is None or request_event is None:
                    raise ValueError("common gauge acquisition is causally unlinked")
                expected_payload = {
                    "refresh_decision_id": request_event.payload[
                        "refresh_decision_id"
                    ],
                    "evidence_request_id": request_event.payload[
                        "evidence_request_id"
                    ],
                    "channel": "gauge_poll",
                    "route_id": observation.route_id,
                    "observation_id": observation.observation_id,
                    "observation_event_id": observation_event.event_id,
                    "observed_at": observation.sampled_at,
                    "delivered_at": observation.delivered_at,
                    "latency_s": observation.delivered_at
                    - observation.sampled_at,
                    "cost": observation.cost,
                    "usable": True,
                    "policy": "common_baseline",
                    "claim_id": None,
                    "commitment_id": None,
                    "workload_id": workload.workload_id,
                    "workload_hash": workload.workload_hash,
                }
                if event.payload != expected_payload:
                    raise ValueError("common gauge acquisition payload is invalid")
                if (
                    event.scenario_level != ScenarioLevel.S5
                    or event.visibility != EventVisibility.AUDIT
                ):
                    raise ValueError("common gauge acquisition has invalid visibility")
                if observation_id in gauge_acquisitions:
                    raise ValueError("duplicate common gauge acquisition")
                gauge_acquisitions[observation_id] = event
            else:
                raise ValueError("common gauge source emitted an unsupported event")
        elif event.source == "registered_workload_scheduler":
            if event.event_type != EventType.EMERGENCY_CALL:
                raise ValueError("workload scheduler emitted an unsupported event")
            incident_id = str(event.payload.get("incident_id", ""))
            incident = expected_incidents.get(incident_id)
            if incident is None:
                raise ValueError("unregistered workload incident")
            if event.simulation_time != incident.scheduled_at:
                raise ValueError("workload incident occurred at the wrong time")
            if event.payload != _scheduled_incident_payload(workload, incident):
                raise ValueError("workload incident payload is invalid")
            if (
                event.scenario_level != ScenarioLevel.S3
                or event.visibility != EventVisibility.BOTH
            ):
                raise ValueError("workload incident has invalid visibility or level")
            if incident_id in incident_events:
                raise ValueError("duplicate workload incident")
            incident_events[incident_id] = event
        elif event.event_type == EventType.EMERGENCY_CALL:
            raise ValueError("amended workload contains unregistered demand")
        apply_event(replay, event)

    expected_gauge_ids = set(expected_gauges)
    if set(gauge_requests) != expected_gauge_ids:
        raise ValueError("common gauge request inventory is incomplete")
    if set(gauge_observations) != expected_gauge_ids:
        raise ValueError("common gauge observation inventory is incomplete")
    if set(gauge_acquisitions) != expected_gauge_ids:
        raise ValueError("common gauge acquisition inventory is incomplete")
    if set(incident_events) != set(expected_incidents):
        raise ValueError("workload incident inventory is incomplete")


def validate_run_directory(directory: str | Path) -> tuple[bool, tuple[str, ...]]:
    """Verify integrity, schemas, accounting, identity, and deterministic metrics."""

    run_dir = Path(directory)
    errors: list[str] = []
    required = {
        "COMPLETED.json",
        "manifest.json",
        "environment.json",
        "events.jsonl",
        "commitment_ledger.jsonl",
        "refresh_ledger.jsonl",
        "exogenous.jsonl",
        "metrics.json",
    }
    missing = sorted(name for name in required if not (run_dir / name).is_file())
    if missing:
        return False, tuple(f"missing required artifact: {name}" for name in missing)

    try:
        marker = CompletionMarker.model_validate_json(
            (run_dir / "COMPLETED.json").read_text(encoding="utf-8")
        )
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("schema_version") != RUN_SCHEMA_VERSION:
            raise ValueError("manifest schema_version is invalid")
        identity = manifest["scientific_identity"]
        if manifest.get("run_fingerprint") != _run_fingerprint(identity):
            raise ValueError("manifest run fingerprint is invalid")
        if marker.run_fingerprint != manifest["run_fingerprint"]:
            raise ValueError("completion and manifest fingerprints differ")
        environment = json.loads(
            (run_dir / "environment.json").read_text(encoding="utf-8")
        )
        if identity["environment_hash"] != sha256_value(environment):
            raise ValueError("environment artifact does not match run identity")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return False, (f"invalid completion or manifest: {exc}",)

    actual_hashes = _artifact_hashes(run_dir)
    if marker.artifact_sha256 != actual_hashes:
        errors.append("artifact hash inventory does not match completion marker")

    event_store = EventStore(run_dir / "events.jsonl")
    try:
        event_chain_valid = event_store.verify_chain()
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        event_chain_valid = False
    if not event_chain_valid:
        errors.append("event hash chain failed verification")
    if not verify_hashed_ledger(run_dir / "commitment_ledger.jsonl"):
        errors.append("commitment ledger hash chain failed verification")
    if not verify_hashed_ledger(run_dir / "refresh_ledger.jsonl"):
        errors.append("refresh ledger hash chain failed verification")

    try:
        metrics = RunMetricsArtifact.model_validate_json(
            (run_dir / "metrics.json").read_text(encoding="utf-8")
        )
        commitment_rows = read_hashed_ledger(
            run_dir / "commitment_ledger.jsonl", CommitmentLedgerRow
        )
        commitment_unit_rows: list[CommitmentUnitLedgerRow] | None = None
        if metrics.schema_version == "trace-run-metrics-v2":
            unit_ledger_path = run_dir / "commitment_unit_ledger.jsonl"
            if not unit_ledger_path.is_file():
                raise ValueError("v2 run is missing commitment-unit ledger")
            if not verify_hashed_ledger(unit_ledger_path):
                raise ValueError("commitment-unit ledger hash chain failed verification")
            commitment_unit_rows = read_hashed_ledger(
                unit_ledger_path, CommitmentUnitLedgerRow
            )
        refresh_rows = read_hashed_ledger(
            run_dir / "refresh_ledger.jsonl", RefreshLedgerRow
        )
        events = event_store.all()
        _assert_event_time_and_scheduler_order(events)
        repository_root = Path(__file__).resolve().parents[3]
        scenario_path = repository_root / identity["scenario"]["path"]
        if sha256_file(scenario_path) != identity["scenario"]["sha256"]:
            raise ValueError("scenario bytes no longer match the run identity")
        initial_state = load_initial_state(metrics.run_id, scenario_path)
        _assert_shock_registry_events(
            identity=identity,
            events=events,
            repository_root=repository_root,
        )
        _assert_evaluation_workload_events(
            identity=identity,
            initial_state=initial_state,
            events=events,
            repository_root=repository_root,
        )
        execution_truth = adjudicate_execution_truth(initial_state, events)
        _assert_execution_labels(events, execution_truth)
        derived_commitments = derive_commitment_ledger(
            events, execution_truth=execution_truth
        )
        derived_refresh = derive_refresh_ledger(events)
        if derived_commitments != commitment_rows:
            errors.append("commitment ledger does not match event-log derivation")
        derived_commitment_units = derive_commitment_unit_ledger(
            derived_commitments
        )
        if (
            commitment_unit_rows is not None
            and derived_commitment_units != commitment_unit_rows
        ):
            errors.append(
                "commitment-unit ledger does not match proposal-ledger derivation"
            )
        if derived_refresh != refresh_rows:
            errors.append("refresh ledger does not match event-log derivation")
        expected_exogenous = "".join(
            canonical_json(row) + "\n"
            for row in _exogenous_projection(initial_state, events)
        )
        if (run_dir / "exogenous.jsonl").read_text(
            encoding="utf-8"
        ) != expected_exogenous:
            errors.append("exogenous projection does not match event-log replay")
        trace_path = run_dir / "trace_records.jsonl"
        if trace_path.exists() and not TraceRepository(trace_path).verify_chain():
            errors.append("TRACE record hash chain failed verification")
        if metrics.schema_version == "trace-run-metrics-v2":
            assert commitment_unit_rows is not None
            recomputed = compute_commitment_metrics(
                commitment_unit_rows,
                proposal_records=eligible_proposal_record_count(commitment_rows),
            )
        else:
            recomputed = compute_proposal_record_metrics(commitment_rows)
        recomputed_refresh = compute_refresh_metrics(refresh_rows)
        if recomputed != metrics.commitment:
            errors.append("stored commitment metrics do not match ledger recomputation")
        if recomputed_refresh != metrics.refresh:
            errors.append("stored refresh metrics do not match ledger recomputation")
        common_baseline_metrics = _common_baseline_metrics(events)
        if common_baseline_metrics != metrics.common_baseline_evidence:
            errors.append("stored common-baseline metrics do not match events")
        if metrics.schema_version == "trace-run-metrics-v2" and (
            metrics.verification_cost
            != _verification_cost_metrics(
                refresh=recomputed_refresh,
                common_baseline=common_baseline_metrics,
            )
        ):
            errors.append("stored total verification cost does not match components")
        if len(events) != metrics.event_count:
            errors.append("stored event count does not match event log")
        if not events or events[-1].event_type != EventType.RUN_PAUSED:
            errors.append("event log does not terminate with RUN_PAUSED")
        if events and not math.isclose(
            events[-1].simulation_time,
            metrics.terminal_simulation_time,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            errors.append("terminal simulation time is inconsistent")
        if marker.run_id != metrics.run_id:
            errors.append("run identity differs between completion and metrics")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(f"artifact schema or recomputation failed: {exc}")
    return not errors, tuple(errors)


async def run_one(request: RunRequest) -> Path:
    repository_root = Path(__file__).resolve().parents[3]
    scenario_path = _confined_file(
        request.scenario_path, repository_root, label="scenario_path"
    )
    protocol_path = _confined_file(
        request.protocol_path, repository_root.parent, label="protocol_path"
    )
    shock_root = request.shock_registry_root.resolve(strict=True)
    try:
        shock_root.relative_to(repository_root.resolve(strict=True))
    except ValueError as exc:
        raise ValueError("shock_registry_root must be contained by the project root") from exc

    resolved_policy, policy = resolve_policy(request.policy)
    epsilon_c = (
        resolved_policy.parameter_value
        if resolved_policy.family == "adaptive"
        else 1.0
    )
    assert epsilon_c is not None
    registry_path = shock_root / "S2" / f"seed_{request.seed}.yaml"
    registry = load_shock_registry(
        registry_path,
        registry_root=shock_root,
        expected_seed=request.seed,
        expected_regime=request.regime,
    )
    _validate_shock_grid(registry, request.tick_s)
    outside_horizon = [
        entry.shock_id
        for entry in registry.entries
        if entry.scheduled_at >= request.duration_s
    ]
    if outside_horizon:
        raise ValueError(
            "shock times must satisfy scheduled_at < duration_s; outside: "
            f"{outside_horizon}"
        )

    evaluation_workload_path: Path | None = None
    evaluation_workload: EvaluationWorkload | None = None
    if request.evaluation_workload_path is not None:
        workload_root = repository_root / "configs" / "workloads"
        evaluation_workload_path = _confined_file(
            request.evaluation_workload_path,
            workload_root,
            label="evaluation_workload_path",
        )
        evaluation_workload = load_evaluation_workload(
            evaluation_workload_path,
            workload_root=workload_root,
            expected_amendment_id=request.protocol_amendment_id,
            expected_regime=request.regime,
        )
        _validate_evaluation_workload(
            evaluation_workload,
            tick_s=request.tick_s,
            duration_s=request.duration_s,
            scenario_path=scenario_path,
        )

    source_inventory_before = _source_inventory(repository_root)
    environment_before = _environment_inventory()
    identity_before = _scientific_identity(
        request=request,
        resolved_policy=resolved_policy,
        repository_root=repository_root,
        scenario_path=scenario_path,
        registry_path=registry_path,
        registry=registry,
        evaluation_workload_path=evaluation_workload_path,
        evaluation_workload=evaluation_workload,
        protocol_path=protocol_path,
        source_inventory=source_inventory_before,
        environment=environment_before,
    )
    run_fingerprint = _run_fingerprint(identity_before)

    final_directory = (
        request.output_root.resolve()
        / request.regime
        / resolved_policy.slug
        / str(request.seed)
    )
    final_directory.parent.mkdir(parents=True, exist_ok=True)
    if final_directory.exists():
        valid, _ = validate_run_directory(final_directory)
        if request.resume and valid:
            try:
                existing_manifest = json.loads(
                    (final_directory / "manifest.json").read_text(encoding="utf-8")
                )
            except (OSError, ValueError):
                existing_manifest = {}
            if existing_manifest.get("run_fingerprint") == run_fingerprint:
                return final_directory
        _quarantine(final_directory)

    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{request.seed}.staging-", dir=final_directory.parent
        )
    )
    workload_slug = (
        f"-{evaluation_workload.workload_id}"
        if evaluation_workload is not None
        else ""
    )
    run_id = (
        f"{request.regime.lower()}-{resolved_policy.slug}{workload_slug}"
        f"-seed-{request.seed}"
    )
    started_at = _utc_now()
    phase = "construct_run"
    try:
        run = DynamicRun(
            run_id=run_id,
            scenario_path=scenario_path,
            artifact_root=staging / "_engine",
            refresh_scheduler=policy,
            epsilon_c=epsilon_c,
        )
        run.event_store = CachedEventStore(run.event_store.path)
        run.runtime.repository = CachedTraceRepository(run.runtime.repository.path)
        phase = "simulate"
        await _simulate(run, request, registry, evaluation_workload)
        phase = "derive_artifacts"
        events = run.event_store.all()
        execution_truth = adjudicate_execution_truth(run._initial_state, events)
        _assert_execution_labels(events, execution_truth)
        commitment_rows = derive_commitment_ledger(
            events, execution_truth=execution_truth
        )
        commitment_unit_rows = derive_commitment_unit_ledger(commitment_rows)
        refresh_rows = derive_refresh_ledger(events)
        commitment_metrics = compute_commitment_metrics(
            commitment_unit_rows,
            proposal_records=eligible_proposal_record_count(commitment_rows),
        )
        refresh_metrics = compute_refresh_metrics(refresh_rows)
        common_baseline_metrics = _common_baseline_metrics(events)

        shutil.copy2(run.event_store.path, staging / "events.jsonl")
        _copy_if_exists(
            run.runtime.repository.path,
            staging / "trace_records.jsonl",
        )
        _copy_if_exists(
            run.runtime.commitments.path,
            staging / "runtime_commitments.jsonl",
        )
        if run.runtime.ledger.root.is_dir():
            shutil.copytree(run.runtime.ledger.root, staging / "evidence")

        write_hashed_ledger(staging / "commitment_ledger.jsonl", commitment_rows)
        write_hashed_ledger(
            staging / "commitment_unit_ledger.jsonl", commitment_unit_rows
        )
        write_hashed_ledger(staging / "refresh_ledger.jsonl", refresh_rows)
        _write_jsonl(
            staging / "exogenous.jsonl",
            _exogenous_projection(run._initial_state, events),
        )

        source_inventory_after = _source_inventory(repository_root)
        environment_after = _environment_inventory()
        identity_after = _scientific_identity(
            request=request,
            resolved_policy=resolved_policy,
            repository_root=repository_root,
            scenario_path=scenario_path,
            registry_path=registry_path,
            registry=registry,
            evaluation_workload_path=evaluation_workload_path,
            evaluation_workload=evaluation_workload,
            protocol_path=protocol_path,
            source_inventory=source_inventory_after,
            environment=environment_after,
        )
        if identity_after != identity_before:
            raise RuntimeError(
                "source, input, protocol, git, or environment identity changed during run"
            )
        manifest = {
            "schema_version": RUN_SCHEMA_VERSION,
            "run_id": run_id,
            "run_fingerprint": run_fingerprint,
            "started_at_utc": started_at,
            "finished_at_utc": _utc_now(),
            "scientific_identity": identity_before,
            "source_inventory": source_inventory_before,
        }
        _atomic_write_json(staging / "manifest.json", manifest)
        _atomic_write_json(staging / "environment.json", environment_before)

        metrics = RunMetricsArtifact(
            run_id=run_id,
            regime=request.regime,
            policy=request.policy,
            seed=request.seed,
            completed=True,
            terminal_simulation_time=run.state.truth.simulation_time,
            event_count=len(events),
            commitment=commitment_metrics,
            refresh=refresh_metrics,
            common_baseline_evidence=common_baseline_metrics,
            verification_cost=_verification_cost_metrics(
                refresh=refresh_metrics,
                common_baseline=common_baseline_metrics,
            ),
            mission=_mission_summary(run),
        )
        _atomic_write_json(staging / "metrics.json", metrics.model_dump(mode="json"))
        shutil.rmtree(staging / "_engine")

        artifact_hashes = _artifact_hashes(staging)
        completion_body = {
            "schema_version": COMPLETION_SCHEMA_VERSION,
            "run_schema_version": RUN_SCHEMA_VERSION,
            "run_id": run_id,
            "run_fingerprint": run_fingerprint,
            "artifact_sha256": artifact_hashes,
        }
        marker = CompletionMarker(
            **completion_body,
            completion_hash=sha256_value(completion_body),
        )
        _atomic_write_json(
            staging / "COMPLETED.json", marker.model_dump(mode="json")
        )
        phase = "validate_staging"
        valid, errors = validate_run_directory(staging)
        if not valid:
            raise RuntimeError(
                "staged run failed independent validation: " + "; ".join(errors)
            )
        phase = "publish"
        os.replace(staging, final_directory)

        valid, errors = validate_run_directory(final_directory)
        if not valid:
            quarantined = _quarantine(final_directory)
            raise RuntimeError(
                f"published run failed validation and was quarantined at {quarantined}: "
                + "; ".join(errors)
            )
        return final_directory
    except BaseException as exc:
        if staging.exists():
            diagnostics = RunDiagnostics(
                storage_chain_valid=phase not in {"validate_staging", "publish"},
                schema_contract_valid=(
                    "identity changed during run" not in str(exc)
                ),
                harness_exception=True,
            )
            classification = classify_failure(diagnostics)
            assert classification is not None
            failure = FailedRunArtifact(
                run_id=run_id,
                run_fingerprint=run_fingerprint,
                failed_at_utc=_utc_now(),
                phase=phase,
                exception_type=type(exc).__name__,
                exception_message=str(exc)[:2000],
                diagnostics=diagnostics.model_dump(mode="json"),
                classification=classification.model_dump(mode="json"),
                partial_artifact_sha256=_artifact_hashes(staging),
            )
            _atomic_write_json(
                staging / "FAILED.json", failure.model_dump(mode="json")
            )
            _quarantine(staging)
        raise


def run_one_sync(request: RunRequest) -> Path:
    return asyncio.run(run_one(request))
