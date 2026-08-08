from __future__ import annotations

import hashlib
from datetime import timedelta

from trace_jepa.scenario.delta.domain import (
    CallLineage,
    CallQuality,
    CallRecord,
    DeltaScenarioConfig,
    GroundTruth,
    IncidentTruth,
    ObservationArtifact,
    ReportedCall,
)
from trace_jepa.scenario.delta.observations_v7 import (
    OTHER_CALL_TYPES,
    _location,
    channel_probabilities_v7,
    location_error_scale_v7,
    location_method_mixture_v7,
)
from trace_jepa.scenario.delta.randomness import KeyedRandom

BASE_REPORTING_BY_HOUR_V2 = (
    0.9356040016332904,
    0.8959743662049926,
    0.7300318469335856,
    0.9658560734345135,
    0.9672777283889277,
    0.9587251126791287,
)
FALSE_REPORT_HOUR_WEIGHTS_V1 = (
    0.016463195968243055,
    0.027438659947071762,
    0.03841412392590047,
    0.38898941361133155,
    0.18246222191270053,
    0.3462323846347526,
)

DESCRIPTOR_VOCABULARY_V1 = {
    "C-STR": (
        "water-at-door",
        "water-on-floor",
        "occupants-upstairs",
        "house-access-blocked",
    ),
    "C-VEH": (
        "vehicle-stalled",
        "road-water-rising",
        "occupants-in-vehicle",
        "vehicle-near-crossing",
    ),
    "C-LEV": (
        "wet-levee-face",
        "possible-seepage",
        "ponding-near-levee",
        "soil-discoloration",
    ),
    "C-MED": (
        "medication-access",
        "oxygen-support",
        "mobility-assistance",
        "medical-access-blocked",
    ),
    "C-WEL": (
        "unable-to-contact",
        "mobility-concern",
        "relative-requested-check",
        "known-medical-need",
    ),
    "C-MIS": (
        "last-seen-away",
        "return-overdue",
        "location-unknown",
        "family-search-request",
    ),
}


def channel_probabilities_v8(iota: float) -> dict[str, float]:
    return channel_probabilities_v7(iota)


def reporting_probability_v8(
    iota: float,
    hour: int,
    baseline: tuple[float, float, float, float, float, float] = BASE_REPORTING_BY_HOUR_V2,
) -> float:
    improvement = 0.60 * (iota - 0.9)
    return min(0.995, max(0.35, baseline[hour] + improvement))


def _report_id(incident_id: str, relationship: str, ordinal: int) -> str:
    digest = hashlib.sha256(f"{incident_id}|{relationship}|{ordinal}".encode()).hexdigest()[:16]
    return f"C8-{digest}"


def _descriptor(
    keyed: KeyedRandom,
    call_id: str,
    call_type: str,
    incident_descriptor: str | None,
    relationship: str,
) -> str:
    vocabulary = DESCRIPTOR_VOCABULARY_V1[call_type]
    share_probability = 0.75 if relationship != "conflicting_report" else 0.40
    if (
        incident_descriptor is not None
        and incident_descriptor in vocabulary
        and keyed.bernoulli(share_probability, "call", call_id, "shared-descriptor")
    ):
        return incident_descriptor
    return vocabulary[keyed.choice_index(len(vocabulary), "call", call_id, "descriptor")]


def generate_observations_v8(
    config: DeltaScenarioConfig,
    truth: GroundTruth,
    keyed: KeyedRandom,
    *,
    reporting_by_hour: tuple[float, float, float, float, float, float] | None = None,
    false_report_hour_weights: tuple[float, float, float, float, float, float] | None = None,
) -> ObservationArtifact:
    """Generate a keyed, lossy zero/one/many channel from v8 truth."""

    probabilities = channel_probabilities_v8(config.axes.iota)
    structures = {item.structure_id: item for item in truth.structures}
    people = {item.person_id: item for item in truth.people}
    calls: list[CallRecord] = []
    lineage: list[CallLineage] = []

    def append_call(
        incident: IncidentTruth | None,
        incident_id: str | None,
        incident_type: str,
        incident_structure_id: str | None,
        incident_person_ids: list[str],
        incident_descriptor: str | None,
        relationship: str,
        ordinal: int,
        channel: str,
        received_s: int,
        callback_group: str,
        *,
        revision_of_call_id: str | None = None,
    ) -> str:
        incident_key = incident_id if incident_id is not None else callback_group
        call_id = _report_id(incident_key, relationship, ordinal)
        if incident_id is None:
            structure = truth.structures[
                keyed.choice_index(len(truth.structures), "call", call_id, "false-structure")
            ]
            person_ids: list[str] = []
            call_type = "C-LEV"
            occupants = 0
            medical: list[str] = []
        else:
            if incident_structure_id is None:
                raise RuntimeError("truth incident is missing its structure")
            structure = structures[incident_structure_id]
            person_ids = incident_person_ids
            call_type = incident_type
            occupants = len(person_ids)
            medical = sorted(
                {
                    people[person_id].medical_dependency
                    for person_id in person_ids
                    if people[person_id].medical_dependency != "none"
                }
            )
        is_conflict = relationship == "conflicting_report"
        disagreement = -1
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
                language=people[person_ids[0]].preferred_language if person_ids else "en",
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
                    description_token=_descriptor(
                        keyed,
                        call_id,
                        call_type,
                        incident_descriptor if call_type == incident_type else None,
                        relationship,
                    ),
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
                truth_incident_id=incident_id,
                truth_person_ids=person_ids,
                relationship=relationship,
            )
        )
        return call_id

    for incident in truth.incidents:
        hour = min(5, incident.onset_s // 3_600)
        if not keyed.bernoulli(
            reporting_probability_v8(
                config.axes.iota,
                hour,
                reporting_by_hour or BASE_REPORTING_BY_HOUR_V2,
            ),
            "incident",
            incident.incident_id,
            "reported",
        ):
            continue
        hour_end = (hour + 1) * 3_600 - 1
        callback_group = hashlib.sha256(incident.incident_id.encode("utf-8")).hexdigest()[:12]
        vocabulary = DESCRIPTOR_VOCABULARY_V1[incident.incident_type]
        incident_descriptor = vocabulary[
            keyed.choice_index(
                len(vocabulary), "incident", incident.incident_id, "descriptor-family"
            )
        ]
        base_relationship = (
            "welfare_check" if incident.incident_type in {"C-WEL", "C-MIS"} else "first_report"
        )
        base_call = append_call(
            incident,
            incident.incident_id,
            incident.incident_type,
            incident.structure_id,
            incident.person_ids,
            incident_descriptor,
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
            report_specs, start=1
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
                incident.incident_id,
                incident.incident_type,
                incident.structure_id,
                incident.person_ids,
                incident_descriptor,
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
                revision_of_call_id=base_call if relationship == "revision" else None,
            )

    false_count = keyed.poisson(probabilities["false_report_mean"], "false-report-count")
    false_weights = false_report_hour_weights or FALSE_REPORT_HOUR_WEIGHTS_V1
    if abs(sum(false_weights) - 1.0) > 1e-12 or any(value < 0.0 for value in false_weights):
        raise ValueError("false-report hourly weights must be nonnegative and sum to one")
    for false_index in range(false_count):
        false_group = f"FALSE-{false_index + 1:04d}"
        draw = keyed.uniform("false-report", false_index, "hour")
        cumulative = 0.0
        false_hour = 5
        for hour, weight in enumerate(false_weights):
            cumulative += weight
            if draw < cumulative:
                false_hour = hour
                break
        append_call(
            None,
            None,
            "C-LEV",
            None,
            [],
            None,
            "false_report",
            false_index,
            "non-emergency-transfer",
            false_hour * 3_600
            + keyed.randint(
                0,
                3_599,
                "false-report",
                false_index,
                "received",
            ),
            false_group,
        )

    mixture = location_method_mixture_v7(config.axes.iota)
    return ObservationArtifact(
        schema_version="delta-observations-v5",
        calls=sorted(calls, key=lambda item: (item.received_s, item.call_id)),
        lineage=sorted(lineage, key=lambda item: item.call_id),
        expected_calls_total=config.call_process.expected_calls_total,
        peak_expected_calls_per_hour=config.call_process.peak_expected_calls_per_hour,
        coefficients_version="delta-observation-coefficients-v2",
        location_method_target_milli={key: round(1_000 * value) for key, value in mixture.items()},
        location_error_scale_milli=round(1_000 * location_error_scale_v7(config.axes.iota)),
    )
