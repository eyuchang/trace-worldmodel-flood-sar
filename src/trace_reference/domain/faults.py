"""Development-only semantic fault schedule for Reference integration testing."""

from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import Field, model_validator

from trace_jepa.scenario.delta.domain.base import DeltaModel

ReferenceFaultFamily: TypeAlias = Literal[
    "reordered-evidence-delivery",
    "duplicated-delivery-retry",
    "authenticated-false-report",
    "identity-dispute-visible-revision",
    "controller-crash-restart",
    "silent-provider-success-after-timeout",
    "partial-service-outcome",
    "contradictory-outcome-evidence",
    "failed-compensation",
    "stale-acknowledgement-key-rotation",
    "completion-after-scenario-censoring",
]

ReferenceFaultSelector: TypeAlias = Literal[
    "first-public-report-delivery-after-anchor",
    "fixed-overlay-report-at-anchor",
    "first-callback-report-after-anchor",
    "runtime-boundary-at-anchor",
    "first-acquisition-after-anchor",
    "first-reversible-commitment-after-anchor",
    "compensation-caused-by-fault",
    "first-coordination-delivery-after-anchor",
    "active-commitment-at-censoring",
]

_REQUIRED_FAMILIES: frozenset[str] = frozenset(
    {
        "reordered-evidence-delivery",
        "duplicated-delivery-retry",
        "authenticated-false-report",
        "identity-dispute-visible-revision",
        "controller-crash-restart",
        "silent-provider-success-after-timeout",
        "partial-service-outcome",
        "contradictory-outcome-evidence",
        "failed-compensation",
        "stale-acknowledgement-key-rotation",
        "completion-after-scenario-censoring",
    }
)


class ReferenceFaultTrigger(DeltaModel):
    """One phase-anchored trigger that cannot name an inspected runtime object."""

    fault_id: str = Field(pattern=r"^reference-fault-[a-z0-9-]+-v1$")
    family: ReferenceFaultFamily
    selector: ReferenceFaultSelector
    anchor_s: int = Field(ge=0, le=345_600)
    ordinal: int = Field(default=1, ge=1, le=10)
    delivery_offset_s: int = Field(default=0, ge=0, le=7_200)
    prerequisite_fault_id: str | None = Field(
        default=None,
        pattern=r"^reference-fault-[a-z0-9-]+-v1$",
    )
    rationale: str = Field(min_length=20, max_length=500)

    @model_validator(mode="after")
    def validate_dependency(self) -> ReferenceFaultTrigger:
        dependent = self.selector == "compensation-caused-by-fault"
        if dependent != (self.prerequisite_fault_id is not None):
            raise ValueError("Reference dependent fault requires exactly one prerequisite")
        if self.prerequisite_fault_id == self.fault_id:
            raise ValueError("Reference fault cannot depend on itself")
        return self


class ReferenceFaultSchedule(DeltaModel):
    """Complete registered fault-family surface; no holdout authority is implied."""

    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    schema_version: Literal["delta-reference-fault-schedule-v1"]
    profile_id: Literal["reference-faulted-v1"]
    scientific_status: Literal["development-integration-rules-not-validation-frozen"]
    target_selection_semantics: Literal[
        "phase-anchored-first-eligible-with-canonical-digest-tie-break"
    ]
    exogenous_invariance: Literal[
        "geography-physical-exposure-truth-raw-observations-resources-byte-identical"
    ]
    triggers: tuple[ReferenceFaultTrigger, ...] = Field(min_length=11, max_length=11)
    schedule_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_complete_schedule(self) -> ReferenceFaultSchedule:
        if self.triggers != tuple(sorted(self.triggers, key=lambda item: item.fault_id)):
            raise ValueError("Reference fault triggers must use canonical fault-ID order")
        families = [item.family for item in self.triggers]
        if len(set(families)) != len(families) or set(families) != _REQUIRED_FAMILIES:
            raise ValueError("Reference fault schedule must cover every required family once")
        identifiers = {item.fault_id for item in self.triggers}
        if any(
            item.prerequisite_fault_id not in identifiers
            for item in self.triggers
            if item.prerequisite_fault_id is not None
        ):
            raise ValueError("Reference fault prerequisite is absent from the schedule")
        return self
