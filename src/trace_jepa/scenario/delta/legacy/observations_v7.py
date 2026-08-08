"""Preserved v7 observation implementation for historical artifact verification."""

from __future__ import annotations

import hashlib
import math
from datetime import timedelta

from trace_jepa.scenario.delta.models import (
    CallLineage,
    CallLocation,
    CallQuality,
    CallRecord,
    DeltaScenarioConfig,
    GroundTruth,
    IncidentTruth,
    ObservationArtifact,
    ReportedCall,
)
from trace_jepa.scenario.delta.randomness import KeyedRandom

# Fitted once on the registered development seeds after truth-intercept freeze.
BASE_REPORTING_BY_HOUR_V1 = (
    0.9899046796655848,
    0.9473066625001544,
    0.6774532482591634,
    0.995,
    0.9138338895253811,
    0.9787899115866391,
)
BASE_LOCATION_METHOD_MILLI = {
    "gps-or-address-intersection": 550,
    "landmark": 270,
    "cell-sector": 180,
}
BASE_PRECISION_RANGES_M = {
    "gps-or-address-intersection": (15, 75),
    "landmark": (200, 800),
    "cell-sector": (400, 1_500),
}
OTHER_CALL_TYPES = ("C-STR", "C-VEH", "C-LEV", "C-MED", "C-WEL", "C-MIS")


def channel_probabilities_v7(iota: float) -> dict[str, float]:
    degradation_scale = max(0.0, (1.0 - iota) / 0.1)
    return {
        "duplicate": min(0.85, 0.1164 * degradation_scale),
        "multi_channel": min(0.70, 0.0741 * degradation_scale),
        "revision": min(0.80, 0.2116 * degradation_scale),
        "conflict": min(0.70, 0.10 * degradation_scale),
        "callback_failure": min(0.80, 0.1033 * degradation_scale),
        "drop": min(0.50, 0.04 * degradation_scale),
        "false_report_mean": min(18.0, 4.6667 * degradation_scale),
    }


def reporting_probability_v7(iota: float, hour: int) -> float:
    improvement = 0.60 * (iota - 0.9)
    return min(0.995, max(0.35, BASE_REPORTING_BY_HOUR_V1[hour] + improvement))


def location_method_mixture_v7(iota: float) -> dict[str, float]:
    shift = (0.9 - iota) / 0.6
    gps = min(0.65, max(0.15, 0.55 - 0.40 * shift))
    landmark = min(0.30, max(0.17, 0.27 - 0.10 * shift))
    cell = round(1.0 - gps - landmark, 12)
    return {
        "gps-or-address-intersection": gps,
        "landmark": landmark,
        "cell-sector": cell,
    }


def location_error_scale_v7(iota: float) -> float:
    return min(3.0, 0.9 / iota)


def _report_id(incident_id: str, relationship: str, ordinal: int) -> str:
    digest = hashlib.sha256(f"{incident_id}|{relationship}|{ordinal}".encode()).hexdigest()[:16]
    return f"C7-{digest}"


def _select_location_method(keyed: KeyedRandom, call_id: str, iota: float) -> str:
    mixture = location_method_mixture_v7(iota)
    draw = keyed.uniform("call", call_id, "location-method")
    cumulative = 0.0
    for method in ("gps-or-address-intersection", "landmark", "cell-sector"):
        cumulative += mixture[method]
        if draw < cumulative:
            return method
    return "cell-sector"


def _location(
    keyed: KeyedRandom,
    call_id: str,
    structure_easting_mm: int,
    structure_northing_mm: int,
    structure_number: int,
    iota: float,
    *,
    conflict: bool,
) -> CallLocation:
    method = _select_location_method(keyed, call_id, iota)
    base_lower, base_upper = BASE_PRECISION_RANGES_M[method]
    scale = location_error_scale_v7(iota)
    lower = max(1, round(base_lower * scale))
    upper = max(lower, round(base_upper * scale))
    precision_m = keyed.randint(lower, upper, "call", call_id, "precision")
    radius_m = precision_m * math.sqrt(keyed.uniform("call", call_id, "radius"))
    if conflict:
        radius_m = min(precision_m * 1.5, radius_m + 0.75 * precision_m)
    angle = 2.0 * math.pi * keyed.uniform("call", call_id, "angle")
    return CallLocation(
        stated=f"synthetic landmark {structure_number:02d}",
        easting_mm=structure_easting_mm + round(1_000 * radius_m * math.cos(angle)),
        northing_mm=structure_northing_mm + round(1_000 * radius_m * math.sin(angle)),
        precision_m=precision_m,
        method=method,
        confidence_milli=max(50, round(1_000 / (1.0 + precision_m / 100.0))),
    )


def generate_observations_v7(
    config: DeltaScenarioConfig,
    truth: GroundTruth,
    keyed: KeyedRandom,
) -> ObservationArtifact:
    probabilities = channel_probabilities_v7(config.axes.iota)
    structures = {item.structure_id: item for item in truth.structures}
    people = {item.person_id: item for item in truth.people}
    calls: list[CallRecord] = []
    lineage: list[CallLineage] = []

    def append_call(
        incident: IncidentTruth | None,
        relationship: str,
        ordinal: int,
        channel: str,
        received_s: int,
        callback_group: str,
        *,
        revision_of_call_id: str | None = None,
    ) -> str:
        incident_key = incident.incident_id if incident is not None else callback_group
        call_id = _report_id(incident_key, relationship, ordinal)
        if incident is None:
            structure = truth.structures[
                keyed.choice_index(len(truth.structures), "call", call_id, "false-structure")
            ]
            person_ids: list[str] = []
            call_type = "C-LEV"
            occupants = 0
            medical: list[str] = []
        else:
            structure = structures[incident.structure_id]
            person_ids = incident.person_ids
            call_type = incident.incident_type
            occupants = len(person_ids)
            medical = sorted(
                {
                    people[person_id].medical_dependency
                    for person_id in person_ids
                    if people[person_id].medical_dependency != "none"
                }
            )
        is_conflict = relationship == "conflicting_report"
        if is_conflict:
            alternatives = [item for item in OTHER_CALL_TYPES if item != call_type]
            disagreement = keyed.choice_index(4, "call", call_id, "conflict-field")
            if disagreement == 0:
                call_type = alternatives[
                    keyed.choice_index(len(alternatives), "call", call_id, "conflict-taxonomy")
                ]
            elif disagreement == 1:
                occupants = max(
                    0,
                    occupants + (-1 if keyed.bernoulli(0.5, "call", call_id, "count-sign") else 1),
                )
            elif disagreement == 2:
                medical = ["unverified-medical-description"]
        if relationship == "revision":
            occupants = len(person_ids)
        callback_failed = keyed.bernoulli(
            probabilities["callback_failure"], "call", call_id, "callback-failure"
        )
        callback_token = (
            f"SYNTH-CB-UNAVAILABLE-{call_id}" if callback_failed else f"SYNTH-CB-{callback_group}"
        )
        bounded_received_s = min(config.timeline.duration_s - 1, max(0, received_s))
        calls.append(
            CallRecord(
                call_id=call_id,
                received_s=bounded_received_s,
                received_ts=config.timeline.epoch_utc + timedelta(seconds=bounded_received_s),
                psap="Sacramento County",
                channel=channel,
                callback_token=callback_token,
                on_scene=relationship not in {"welfare_check", "false_report"},
                third_party=relationship in {"welfare_check", "false_report"},
                language=(people[person_ids[0]].preferred_language if person_ids else "en"),
                location=_location(
                    keyed,
                    call_id,
                    structure.easting_mm,
                    structure.northing_mm,
                    int(structure.structure_id[-3:]),
                    config.axes.iota,
                    conflict=is_conflict and disagreement == 3,
                ),
                reported=ReportedCall(
                    call_type=call_type,
                    occupants=occupants,
                    occupants_confidence=("revised" if relationship == "revision" else "estimated"),
                    medical=medical,
                    description_token=f"SYNTH-DESC-{keyed.randint(0, 31, 'call', call_id, 'description'):02d}",
                ),
                quality=CallQuality(
                    call_dropped=keyed.bernoulli(probabilities["drop"], "call", call_id, "dropped"),
                    callback_failed=callback_failed,
                    revision_of_call_id=revision_of_call_id,
                ),
            )
        )
        lineage.append(
            CallLineage(
                call_id=call_id,
                truth_incident_id=incident.incident_id if incident is not None else None,
                truth_person_ids=person_ids,
                relationship=relationship,
            )
        )
        return call_id

    for incident in truth.incidents:
        hour = min(5, incident.onset_s // 3_600)
        if not keyed.bernoulli(
            reporting_probability_v7(config.axes.iota, hour),
            "incident",
            incident.incident_id,
            "reported",
        ):
            continue
        hour_end = (hour + 1) * 3_600 - 1
        callback_group = hashlib.sha256(incident.incident_id.encode("utf-8")).hexdigest()[:12]
        base_relationship = (
            "welfare_check" if incident.incident_type in {"C-WEL", "C-MIS"} else "first_report"
        )
        base_call = append_call(
            incident,
            base_relationship,
            0,
            "911",
            min(
                hour_end,
                incident.onset_s + keyed.randint(15, 419, incident.incident_id, "base-delay"),
            ),
            callback_group,
        )
        report_specs = (
            ("duplicate", "911", 120, 899),
            ("multi_channel", "text-to-911", 60, 719),
            ("conflict", "911-transfer", 180, 1_099),
            ("revision", "911-callback", 300, 1_499),
        )
        for ordinal, (probability_name, channel, minimum_delay, maximum_delay) in enumerate(
            report_specs,
            start=1,
        ):
            if not keyed.bernoulli(
                probabilities[probability_name],
                "incident",
                incident.incident_id,
                probability_name,
            ):
                continue
            relationship = (
                "conflicting_report" if probability_name == "conflict" else probability_name
            )
            append_call(
                incident,
                relationship,
                ordinal,
                channel,
                min(
                    hour_end,
                    incident.onset_s
                    + keyed.randint(
                        minimum_delay,
                        maximum_delay,
                        incident.incident_id,
                        probability_name,
                        "delay",
                    ),
                ),
                callback_group,
                revision_of_call_id=(base_call if relationship == "revision" else None),
            )

    false_count = keyed.poisson(probabilities["false_report_mean"], "false-report-count")
    for false_index in range(false_count):
        false_group = f"FALSE-{false_index + 1:04d}"
        append_call(
            None,
            "false_report",
            false_index,
            "non-emergency-transfer",
            keyed.randint(
                0,
                config.timeline.duration_s - 1,
                "false-report",
                false_index,
                "received",
            ),
            false_group,
        )

    mixture = location_method_mixture_v7(config.axes.iota)
    return ObservationArtifact(
        schema_version="delta-observations-v4",
        calls=sorted(calls, key=lambda item: (item.received_s, item.call_id)),
        lineage=sorted(lineage, key=lambda item: item.call_id),
        expected_calls_total=config.call_process.expected_calls_total,
        peak_expected_calls_per_hour=config.call_process.peak_expected_calls_per_hour,
        coefficients_version="delta-observation-coefficients-v1",
        location_method_target_milli={key: round(1_000 * value) for key, value in mixture.items()},
        location_error_scale_milli=round(1_000 * location_error_scale_v7(config.axes.iota)),
    )
