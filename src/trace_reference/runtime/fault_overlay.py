"""Deterministic delivery-only effects from the registered Reference fault plan."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal

from trace_reference.decision.canonical import decision_digest
from trace_reference.domain import (
    ReferenceCoordinationDelivery,
    ReferenceCoordinationFaultAttempt,
    ReferenceFaultApplication,
    ReferenceFaultSchedule,
    ReferenceFaultTrigger,
    ReferenceScenarioArtifacts,
)


@dataclass(frozen=True)
class ReferenceCoordinationOverlay:
    """Materialized transport attempts and fault reachability for one scenario."""

    attempts: tuple[ReferenceCoordinationFaultAttempt, ...]
    selected_targets: tuple[tuple[str, str], ...]
    unreachable_fault_ids: tuple[str, ...]


def _id(*parts: object) -> str:
    digest = hashlib.sha256("|".join(str(item) for item in parts).encode()).hexdigest()
    return f"reference-fault-attempt-{digest[:20]}"


def _trigger(schedule: ReferenceFaultSchedule, family: str) -> ReferenceFaultTrigger:
    return next(item for item in schedule.triggers if item.family == family)


def _candidate(
    deliveries: tuple[ReferenceCoordinationDelivery, ...],
    trigger: ReferenceFaultTrigger,
    *,
    reports_only: bool,
) -> ReferenceCoordinationDelivery | None:
    eligible = tuple(
        item
        for item in deliveries
        if item.delivered_at_s >= trigger.anchor_s
        and (not reports_only or item.evidence_kind == "public-report-envelope")
    )
    index = trigger.ordinal - 1
    return eligible[index] if index < len(eligible) else None


def build_reference_coordination_overlay(
    scenario: ReferenceScenarioArtifacts,
    schedule: ReferenceFaultSchedule | None,
) -> ReferenceCoordinationOverlay:
    """Apply only transport faults; all source evidence objects remain untouched."""

    deliveries = scenario.coordination.public.deliveries
    if schedule is None:
        nominal_attempts = tuple(
            ReferenceCoordinationFaultAttempt(
                attempt_id=_id("nominal", item.delivery_id),
                at_s=item.delivered_at_s,
                delivery=item,
                behavior="deliver",
            )
            for item in deliveries
        )
        return ReferenceCoordinationOverlay(nominal_attempts, (), ())

    replacements: dict[str, ReferenceCoordinationFaultAttempt] = {}
    extras: list[ReferenceCoordinationFaultAttempt] = []
    selected: list[tuple[str, str]] = []
    unreachable: list[str] = []

    reorder = _trigger(schedule, "reordered-evidence-delivery")
    reorder_target = _candidate(deliveries, reorder, reports_only=True)
    if reorder_target is None:
        unreachable.append(reorder.fault_id)
    else:
        effective_at_s = reorder_target.delivered_at_s + reorder.delivery_offset_s
        effective = reorder_target.model_copy(update={"delivered_at_s": effective_at_s})
        replacements[reorder_target.delivery_id] = ReferenceCoordinationFaultAttempt(
            attempt_id=_id(reorder.fault_id, reorder_target.delivery_id),
            at_s=effective_at_s,
            delivery=effective,
            fault_id=reorder.fault_id,
            behavior="reordered-delivery",
        )
        selected.append((reorder.fault_id, reorder_target.delivery_id))

    duplicate = _trigger(schedule, "duplicated-delivery-retry")
    duplicate_target = _candidate(deliveries, duplicate, reports_only=True)
    if duplicate_target is None:
        unreachable.append(duplicate.fault_id)
    else:
        extras.append(
            ReferenceCoordinationFaultAttempt(
                attempt_id=_id(duplicate.fault_id, duplicate_target.delivery_id),
                at_s=duplicate_target.delivered_at_s + duplicate.delivery_offset_s,
                delivery=duplicate_target,
                fault_id=duplicate.fault_id,
                behavior="duplicate-retry",
            )
        )
        selected.append((duplicate.fault_id, duplicate_target.delivery_id))

    stale = _trigger(schedule, "stale-acknowledgement-key-rotation")
    stale_target = _candidate(deliveries, stale, reports_only=False)
    if stale_target is None:
        unreachable.append(stale.fault_id)
    else:
        replacements[stale_target.delivery_id] = ReferenceCoordinationFaultAttempt(
            attempt_id=_id(stale.fault_id, stale_target.delivery_id),
            at_s=stale_target.delivered_at_s,
            delivery=stale_target,
            fault_id=stale.fault_id,
            behavior="stale-key-reject",
        )
        selected.append((stale.fault_id, stale_target.delivery_id))

    attempts = [
        replacements.get(
            item.delivery_id,
            ReferenceCoordinationFaultAttempt(
                attempt_id=_id("nominal", item.delivery_id),
                at_s=item.delivered_at_s,
                delivery=item,
                behavior="deliver",
            ),
        )
        for item in deliveries
    ]
    attempts.extend(extras)
    attempts.sort(key=lambda item: (item.at_s, item.attempt_id))
    return ReferenceCoordinationOverlay(
        attempts=tuple(attempts),
        selected_targets=tuple(sorted(selected)),
        unreachable_fault_ids=tuple(sorted(unreachable)),
    )


def build_reference_fault_application(
    schedule: ReferenceFaultSchedule,
    attempt: ReferenceCoordinationFaultAttempt,
    *,
    disposition: Literal["applied", "duplicate-effect-suppressed", "stale-key-rejected"],
    reason: str,
) -> ReferenceFaultApplication:
    """Bind one realized transport effect to the exact registered trigger."""

    if attempt.fault_id is None:
        raise ValueError("Reference nominal attempt cannot produce a fault application")
    return build_reference_target_fault_application(
        schedule,
        fault_id=attempt.fault_id,
        target_public_id=attempt.delivery.delivery_id,
        applied_at_s=attempt.at_s,
        disposition=disposition,
        reason=reason,
    )


def build_reference_target_fault_application(
    schedule: ReferenceFaultSchedule,
    *,
    fault_id: str,
    target_public_id: str,
    applied_at_s: int,
    disposition: Literal["applied", "duplicate-effect-suppressed", "stale-key-rejected"],
    reason: str,
) -> ReferenceFaultApplication:
    """Bind any realized public runtime target to one exact registered trigger."""

    trigger = next(item for item in schedule.triggers if item.fault_id == fault_id)
    application_key = f"{fault_id}|{target_public_id}|{applied_at_s}|{disposition}"
    body = {
        "schema_version": "delta-reference-fault-application-v1",
        "application_id": (
            "reference-fault-application-"
            + hashlib.sha256(application_key.encode()).hexdigest()[:20]
        ),
        "fault_id": fault_id,
        "family": trigger.family,
        "target_public_id": target_public_id,
        "applied_at_s": applied_at_s,
        "disposition": disposition,
        "reason": reason,
    }
    return ReferenceFaultApplication(
        **body,
        application_digest=decision_digest(body),
    )
