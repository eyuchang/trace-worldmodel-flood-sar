from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, model_validator

from trace_jepa.util import sha256_value
from trace_jepa.workbench.models import FrozenModel, Position


WORKLOAD_SCHEDULER_VERSION = "registered-evaluation-workload-v1"
WORKLOAD_EVENT_ORDER = (
    "shocks-gauge-samples-gauge-deliveries-incidents-tick-v1"
)


class CommonGaugeObservation(FrozenModel):
    observation_id: str = Field(
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"
    )
    route_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
    sampled_at: float = Field(gt=0.0, lt=86_400.0)
    delivered_at: float = Field(gt=0.0, lt=86_400.0)
    cost: float = Field(ge=0.0)

    @model_validator(mode="after")
    def validate_delivery(self) -> "CommonGaugeObservation":
        if self.delivered_at <= self.sampled_at:
            raise ValueError("gauge delivery must occur after sampling")
        return self


class ScheduledIncident(FrozenModel):
    incident_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
    group_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
    scheduled_at: float = Field(gt=0.0, lt=86_400.0)
    location_label: str = Field(min_length=1, max_length=256)
    position: Position
    people: int = Field(ge=1, le=1000)
    severity: float = Field(ge=0.0, le=1.0)
    deadline_s: float = Field(gt=0.0, le=86_400.0)
    safe_location_id: str = Field(
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"
    )

    @model_validator(mode="after")
    def validate_deadline(self) -> "ScheduledIncident":
        if self.deadline_s <= self.scheduled_at:
            raise ValueError("incident deadline must occur after the incident")
        return self


class EvaluationWorkload(FrozenModel):
    schema_version: Literal["trace-evaluation-workload-v1"] = (
        "trace-evaluation-workload-v1"
    )
    workload_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,95}$")
    amendment_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,95}$")
    partition: Literal["development", "validation"] = "development"
    regime: Literal["R-B"] = "R-B"
    design_basis: str = Field(min_length=1, max_length=512)
    scheduler_version: Literal["registered-evaluation-workload-v1"] = (
        WORKLOAD_SCHEDULER_VERSION
    )
    event_order: Literal[
        "shocks-gauge-samples-gauge-deliveries-incidents-tick-v1"
    ] = WORKLOAD_EVENT_ORDER
    common_gauge_observations: tuple[CommonGaugeObservation, ...]
    incidents: tuple[ScheduledIncident, ...]

    @model_validator(mode="after")
    def validate_order_and_identity(self) -> "EvaluationWorkload":
        observation_ids = [
            observation.observation_id
            for observation in self.common_gauge_observations
        ]
        incident_ids = [incident.incident_id for incident in self.incidents]
        group_ids = [incident.group_id for incident in self.incidents]
        if len(observation_ids) != len(set(observation_ids)):
            raise ValueError("observation_id values must be unique")
        if len(incident_ids) != len(set(incident_ids)):
            raise ValueError("incident_id values must be unique")
        if len(group_ids) != len(set(group_ids)):
            raise ValueError("group_id values must be unique")
        observation_keys = [
            (observation.sampled_at, observation.observation_id)
            for observation in self.common_gauge_observations
        ]
        if observation_keys != sorted(observation_keys):
            raise ValueError("gauge observations must be sorted")
        incident_keys = [
            (incident.scheduled_at, incident.incident_id)
            for incident in self.incidents
        ]
        if incident_keys != sorted(incident_keys):
            raise ValueError("incidents must be sorted")
        return self

    @property
    def workload_hash(self) -> str:
        return sha256_value(self.model_dump(mode="json"))


def load_evaluation_workload(
    path: str | Path,
    *,
    workload_root: str | Path,
    expected_amendment_id: str | None = None,
    expected_regime: str | None = None,
    expected_partition: str | None = None,
) -> EvaluationWorkload:
    """Load one strict, evaluation-only workload confined to its root."""

    root = Path(workload_root).resolve(strict=True)
    workload_path = Path(path)
    if not workload_path.is_absolute():
        workload_path = root / workload_path
    resolved = workload_path.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("evaluation workload path escapes its configured root") from exc
    if not resolved.is_file():
        raise ValueError("evaluation workload must be a regular file")
    if resolved.stat().st_size > 1_000_000:
        raise ValueError("evaluation workload exceeds the 1 MB safety limit")

    raw = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("evaluation workload must contain a YAML mapping")
    workload = EvaluationWorkload.model_validate(raw)
    if (
        expected_amendment_id is not None
        and workload.amendment_id != expected_amendment_id
    ):
        raise ValueError(
            f"workload amendment {workload.amendment_id} does not match "
            f"{expected_amendment_id}"
        )
    if expected_regime is not None and workload.regime != expected_regime:
        raise ValueError(
            f"workload regime {workload.regime} does not match {expected_regime}"
        )
    if expected_partition is not None and workload.partition != expected_partition:
        raise ValueError(
            f"workload partition {workload.partition} does not match "
            f"{expected_partition}"
        )
    return workload
