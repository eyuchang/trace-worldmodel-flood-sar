"""Campaign protocol registration with freeze discipline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from trace_jepa.util import sha256_value, write_json


class ProtocolFreeze(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    requires_registration_before_held_out: bool = True
    shared_with: tuple[str, ...] = ()
    discipline_note: str = (
        "Held-out execution is blocked until this protocol is registered "
        "under the same freeze discipline as RQ1–RQ4."
    )


class ProtocolScenario(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str
    description: str
    predictor_change: bool = False


class ProtocolArm(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    arm_id: str
    description: str
    revalidation_guard_enabled: bool


class ProtocolMeasure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    measure_id: str
    description: str
    unit: str = "count"


class ProtocolInvariant(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    invariant_id: str
    statement: str
    applies_when_guard_enabled: bool = True


class RQ5Protocol(BaseModel):
    """Pre-registered RQ5: revalidation-guard stress test."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    protocol_id: str = "RQ5"
    title: str = "Revalidation-guard stress test"
    section_ref: str = "Section 5.5"
    freeze: ProtocolFreeze
    scenarios: tuple[ProtocolScenario, ...]
    arms: tuple[ProtocolArm, ...]
    measures: tuple[ProtocolMeasure, ...]
    invariant: ProtocolInvariant
    paired_seed_required: bool = True
    content_hash: str | None = None

    @field_validator("scenarios")
    @classmethod
    def _two_scenarios(cls, value: tuple[ProtocolScenario, ...]) -> tuple[ProtocolScenario, ...]:
        ids = {item.scenario_id for item in value}
        required = {"control", "mid_mission_replacement"}
        if not required.issubset(ids):
            raise ValueError(
                "RQ5 must declare scenarios 'control' and 'mid_mission_replacement'"
            )
        return value

    @field_validator("arms")
    @classmethod
    def _two_arms(cls, value: tuple[ProtocolArm, ...]) -> tuple[ProtocolArm, ...]:
        guard_flags = {item.revalidation_guard_enabled for item in value}
        if guard_flags != {True, False}:
            raise ValueError(
                "RQ5 must declare one arm with the guard and one arm without it"
            )
        return value

    def with_content_hash(self) -> "RQ5Protocol":
        payload = self.model_dump(mode="json", exclude={"content_hash"})
        return self.model_copy(update={"content_hash": sha256_value(payload)})


def default_rq5_protocol() -> RQ5Protocol:
    protocol = RQ5Protocol(
        freeze=ProtocolFreeze(
            requires_registration_before_held_out=True,
            shared_with=("RQ1", "RQ2", "RQ3", "RQ4"),
        ),
        scenarios=(
            ProtocolScenario(
                scenario_id="control",
                description="No predictor change during the mission.",
                predictor_change=False,
            ),
            ProtocolScenario(
                scenario_id="mid_mission_replacement",
                description=(
                    "Predictor version is replaced explicitly mid-mission, recorded "
                    "as a structural event with old and new model hashes; the "
                    "replacement version's calibration status is initially "
                    "unqualified for high-consequence classes."
                ),
                predictor_change=True,
            ),
        ),
        arms=(
            ProtocolArm(
                arm_id="gate_without_guard",
                description="Current gate without the revalidation guard.",
                revalidation_guard_enabled=False,
            ),
            ProtocolArm(
                arm_id="gate_with_guard",
                description="Gate with the revalidation guard enabled.",
                revalidation_guard_enabled=True,
            ),
        ),
        measures=(
            ProtocolMeasure(
                measure_id="high_consequence_clear_on_bad_version",
                description=(
                    "Count of high-consequence CLEAR decisions issued on a "
                    "superseded or unqualified predictor version."
                ),
            ),
            ProtocolMeasure(
                measure_id="held_or_escalated_pending_revalidation",
                description=(
                    "Commitments held or escalated pending revalidation."
                ),
            ),
            ProtocolMeasure(
                measure_id="time_replacement_to_restored_operation",
                description="Time from replacement to restored ordinary operation.",
                unit="seconds",
            ),
            ProtocolMeasure(
                measure_id="additional_verification_cost",
                description="Additional verification cost induced by the guard.",
                unit="cost",
            ),
            ProtocolMeasure(
                measure_id="mission_completion",
                description="Mission completion indicator.",
                unit="boolean",
            ),
            ProtocolMeasure(
                measure_id="rescued_people",
                description="People rescued by mission end.",
            ),
            ProtocolMeasure(
                measure_id="exact_replayability",
                description=(
                    "Exact replayability of every model-version and gate "
                    "transition from the store."
                ),
                unit="boolean",
            ),
        ),
        invariant=ProtocolInvariant(
            invariant_id="no_clear_on_superseded_or_unqualified",
            statement=(
                "Under the guard, no high-consequence commitment is cleared on a "
                "superseded or unqualified model version; the control scenario "
                "bounds the guard's overhead when no replacement occurs."
            ),
            applies_when_guard_enabled=True,
        ),
    )
    return protocol.with_content_hash()


def load_rq5_protocol(path: Path | None = None) -> RQ5Protocol:
    if path is None:
        return default_rq5_protocol()
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return RQ5Protocol.model_validate(payload).with_content_hash()


class ProtocolRegistry:
    """Registers campaign protocols before any held-out run may proceed."""

    def __init__(self, *, store_path: Path | None = None) -> None:
        self.store_path = store_path
        self._protocols: dict[str, dict[str, Any]] = {}

    def register(self, protocol: RQ5Protocol | BaseModel) -> str:
        payload = protocol.model_dump(mode="json")
        protocol_id = payload["protocol_id"]
        digest = payload.get("content_hash") or sha256_value(
            {k: v for k, v in payload.items() if k != "content_hash"}
        )
        payload["content_hash"] = digest
        self._protocols[protocol_id] = payload
        if self.store_path is not None:
            target = self.store_path / f"{protocol_id}.json"
            write_json(target, payload)
        return digest

    def is_registered(self, protocol_id: str) -> bool:
        if protocol_id in self._protocols:
            return True
        if self.store_path is not None:
            path = self.store_path / f"{protocol_id}.json"
            return path.exists()
        return False

    def get(self, protocol_id: str) -> dict[str, Any]:
        if protocol_id in self._protocols:
            return self._protocols[protocol_id]
        if self.store_path is not None:
            path = self.store_path / f"{protocol_id}.json"
            if path.exists():
                import json

                return json.loads(path.read_text(encoding="utf-8"))
        raise KeyError(f"protocol {protocol_id} is not registered")

    def registered_ids(self) -> tuple[str, ...]:
        ids = set(self._protocols)
        if self.store_path is not None and self.store_path.exists():
            ids.update(path.stem for path in self.store_path.glob("*.json"))
        return tuple(sorted(ids))


class HeldOutGateError(RuntimeError):
    """Raised when a held-out run is attempted before protocol registration."""


def require_protocol_before_held_out(
    registry: ProtocolRegistry,
    protocol_id: str,
    *,
    held_out: bool,
) -> None:
    if not held_out:
        return
    if not registry.is_registered(protocol_id):
        raise HeldOutGateError(
            f"Held-out run blocked: protocol {protocol_id} must be registered "
            "before any held-out execution under the campaign freeze discipline."
        )
