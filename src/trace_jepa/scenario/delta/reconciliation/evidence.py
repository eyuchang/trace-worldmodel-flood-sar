"""Pure scoring of controller-visible reconciliation evidence."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable

from trace_jepa.scenario.delta.domain import CallRecord


def link_id(
    algorithm_id: str,
    source_call_id: str,
    target_call_id: str,
    status: str,
    evidence_families: Iterable[str],
) -> str:
    payload = "|".join((algorithm_id, source_call_id, target_call_id, status, *evidence_families))
    return "RL-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def distance_m(left: CallRecord, right: CallRecord) -> float:
    return (
        math.hypot(
            left.location.easting_mm - right.location.easting_mm,
            left.location.northing_mm - right.location.northing_mm,
        )
        / 1_000.0
    )


def callback_is_available(call: CallRecord) -> bool:
    return not call.quality.callback_failed and not call.callback_token.startswith(
        "SYNTH-CB-UNAVAILABLE-"
    )


def medical_contradiction(left: CallRecord, right: CallRecord) -> bool:
    left_medical = set(left.reported.medical)
    right_medical = set(right.reported.medical)
    return bool(left_medical and right_medical and left_medical != right_medical)


def visible_contradiction(left: CallRecord, right: CallRecord) -> bool:
    return (
        left.reported.call_type != right.reported.call_type
        or abs(left.reported.occupants - right.reported.occupants) > 1
        or medical_contradiction(left, right)
    )


def soft_evidence(
    current: CallRecord,
    previous: CallRecord,
    spatial_multiplier: float,
) -> tuple[bool, tuple[str, ...], bool]:
    temporal = abs(current.received_s - previous.received_s) <= 1_500
    spatial_limit = spatial_multiplier * math.sqrt(
        current.location.precision_m**2 + previous.location.precision_m**2
    )
    spatial = distance_m(current, previous) <= spatial_limit
    taxonomy = current.reported.call_type == previous.reported.call_type
    descriptor = current.reported.description_token == previous.reported.description_token
    occupant_medical = abs(
        current.reported.occupants - previous.reported.occupants
    ) <= 1 and not medical_contradiction(current, previous)
    evidence = tuple(
        name
        for name, present in (
            ("temporal_compatibility", temporal),
            ("spatial_uncertainty_compatibility", spatial),
            ("exact_taxonomy_agreement", taxonomy),
            ("shared_nonunique_descriptor", descriptor),
            ("occupant_medical_agreement", occupant_medical),
        )
        if present
    )
    return (
        temporal and spatial and taxonomy and (descriptor or occupant_medical),
        evidence,
        (temporal and spatial),
    )
