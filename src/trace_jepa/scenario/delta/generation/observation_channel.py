"""Keyed zero/one/many observation channel for canonical generator v8."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
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
    StructureTruth,
)
from trace_jepa.scenario.delta.generation.randomness import KeyedRandom

from .observation_primitives import (
    OTHER_CALL_TYPES,
    LocationRequest,
    call_location,
    channel_probabilities,
    location_error_scale,
    location_method_mixture,
)

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
    "C-STR": ("water-at-door", "water-on-floor", "occupants-upstairs", "house-access-blocked"),
    "C-VEH": (
        "vehicle-stalled",
        "road-water-rising",
        "occupants-in-vehicle",
        "vehicle-near-crossing",
    ),
    "C-LEV": ("wet-levee-face", "possible-seepage", "ponding-near-levee", "soil-discoloration"),
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
    "C-MIS": ("last-seen-away", "return-overdue", "location-unknown", "family-search-request"),
}


@dataclass(frozen=True)
class ReportDraft:
    """Typed description of one report before channel distortion is applied."""

    incident: IncidentTruth | None
    relationship: str
    ordinal: int
    channel: str
    received_s: int
    callback_group: str
    descriptor_family: str | None = None
    revision_of_call_id: str | None = None


def reporting_probability(
    iota: float,
    hour: int,
    baseline: tuple[float, float, float, float, float, float] = BASE_REPORTING_BY_HOUR_V2,
) -> float:
    improvement = 0.60 * (iota - 0.9)
    return min(0.995, max(0.35, baseline[hour] + improvement))


class ObservationChannel:
    """Generate calls from hidden incidents using controller-safe visible fields."""

    def __init__(
        self,
        config: DeltaScenarioConfig,
        truth: GroundTruth,
        keyed: KeyedRandom,
        *,
        reporting_by_hour: tuple[float, float, float, float, float, float] | None = None,
        false_report_hour_weights: tuple[float, float, float, float, float, float] | None = None,
    ) -> None:
        self.config = config
        self.truth = truth
        self.keyed = keyed
        self.reporting_by_hour = reporting_by_hour or BASE_REPORTING_BY_HOUR_V2
        self.false_report_hour_weights = false_report_hour_weights or FALSE_REPORT_HOUR_WEIGHTS_V1
        self.probabilities = channel_probabilities(config.axes.iota)
        self.structures = {item.structure_id: item for item in truth.structures}
        self.people = {item.person_id: item for item in truth.people}
        self.calls: list[CallRecord] = []
        self.lineage: list[CallLineage] = []

    @staticmethod
    def _report_id(incident_key: str, relationship: str, ordinal: int) -> str:
        digest = hashlib.sha256(f"{incident_key}|{relationship}|{ordinal}".encode()).hexdigest()[
            :16
        ]
        return f"C8-{digest}"

    def _descriptor(
        self,
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
            and self.keyed.bernoulli(share_probability, "call", call_id, "shared-descriptor")
        ):
            return incident_descriptor
        return vocabulary[self.keyed.choice_index(len(vocabulary), "call", call_id, "descriptor")]

    def _visible_fields(
        self, draft: ReportDraft, call_id: str
    ) -> tuple[StructureTruth, list[str], str, int, list[str]]:
        incident = draft.incident
        if incident is None:
            structure = self.truth.structures[
                self.keyed.choice_index(
                    len(self.truth.structures), "call", call_id, "false-structure"
                )
            ]
            return structure, [], "C-LEV", 0, []
        structure = self.structures[incident.structure_id]
        person_ids = list(incident.person_ids)
        medical = sorted(
            {
                self.people[person_id].medical_dependency
                for person_id in person_ids
                if self.people[person_id].medical_dependency != "none"
            }
        )
        return structure, person_ids, incident.incident_type, len(person_ids), medical

    def _apply_conflict(
        self,
        draft: ReportDraft,
        call_id: str,
        call_type: str,
        occupants: int,
        medical: list[str],
    ) -> tuple[str, int, list[str], int]:
        if draft.relationship != "conflicting_report":
            return call_type, occupants, medical, -1
        alternatives = [item for item in OTHER_CALL_TYPES if item != call_type]
        disagreement = self.keyed.choice_index(4, "call", call_id, "conflict-field")
        if disagreement == 0:
            call_type = alternatives[
                self.keyed.choice_index(len(alternatives), "call", call_id, "conflict-taxonomy")
            ]
        elif disagreement == 1:
            occupants = max(
                0,
                occupants + (-1 if self.keyed.bernoulli(0.5, "call", call_id, "count-sign") else 1),
            )
        elif disagreement == 2:
            medical = ["unverified-medical-description"]
        return call_type, occupants, medical, disagreement

    def append(self, draft: ReportDraft) -> str:
        incident_id = draft.incident.incident_id if draft.incident is not None else None
        incident_key = incident_id if incident_id is not None else draft.callback_group
        call_id = self._report_id(incident_key, draft.relationship, draft.ordinal)
        structure, person_ids, call_type, occupants, medical = self._visible_fields(draft, call_id)
        call_type, occupants, medical, disagreement = self._apply_conflict(
            draft, call_id, call_type, occupants, medical
        )
        if draft.relationship == "revision":
            occupants = len(person_ids)
        callback_failed = self.keyed.bernoulli(
            self.probabilities["callback_failure"], "call", call_id, "callback-failure"
        )
        callback_token = (
            f"SYNTH-CB-UNAVAILABLE-{call_id}"
            if callback_failed
            else f"SYNTH-CB-{draft.callback_group}"
        )
        bounded_received_s = min(self.config.timeline.duration_s - 1, max(0, draft.received_s))
        incident_type = draft.incident.incident_type if draft.incident is not None else "C-LEV"
        self.calls.append(
            CallRecord(
                call_id=call_id,
                received_s=bounded_received_s,
                received_ts=self.config.timeline.epoch_utc + timedelta(seconds=bounded_received_s),
                psap="Sacramento County",
                channel=draft.channel,
                callback_token=callback_token,
                on_scene=draft.relationship not in {"welfare_check", "false_report"},
                third_party=draft.relationship in {"welfare_check", "false_report"},
                language=self.people[person_ids[0]].preferred_language if person_ids else "en",
                location=call_location(
                    self.keyed,
                    LocationRequest(
                        call_id=call_id,
                        easting_mm=structure.easting_mm,
                        northing_mm=structure.northing_mm,
                        structure_number=int(structure.structure_id[-3:]),
                        iota=self.config.axes.iota,
                        conflict=(draft.relationship == "conflicting_report" and disagreement == 3),
                    ),
                ),
                reported=ReportedCall(
                    call_type=call_type,
                    occupants=occupants,
                    occupants_confidence=(
                        "revised" if draft.relationship == "revision" else "estimated"
                    ),
                    medical=medical,
                    description_token=self._descriptor(
                        call_id,
                        call_type,
                        draft.descriptor_family if call_type == incident_type else None,
                        draft.relationship,
                    ),
                ),
                quality=CallQuality(
                    call_dropped=self.keyed.bernoulli(
                        self.probabilities["drop"], "call", call_id, "dropped"
                    ),
                    callback_failed=callback_failed,
                    revision_of_call_id=draft.revision_of_call_id,
                ),
            )
        )
        self.lineage.append(
            CallLineage(
                call_id=call_id,
                truth_incident_id=incident_id,
                truth_person_ids=person_ids,
                relationship=draft.relationship,
            )
        )
        return call_id

    def _incident_reports(self, incident: IncidentTruth) -> None:
        hour = min(5, incident.onset_s // 3_600)
        if not self.keyed.bernoulli(
            reporting_probability(self.config.axes.iota, hour, self.reporting_by_hour),
            "incident",
            incident.incident_id,
            "reported",
        ):
            return
        hour_end = (hour + 1) * 3_600 - 1
        callback_group = hashlib.sha256(incident.incident_id.encode("utf-8")).hexdigest()[:12]
        vocabulary = DESCRIPTOR_VOCABULARY_V1[incident.incident_type]
        descriptor = vocabulary[
            self.keyed.choice_index(
                len(vocabulary), "incident", incident.incident_id, "descriptor-family"
            )
        ]
        relationship = (
            "welfare_check" if incident.incident_type in {"C-WEL", "C-MIS"} else "first_report"
        )
        base_call = self.append(
            ReportDraft(
                incident=incident,
                relationship=relationship,
                ordinal=0,
                channel="911",
                received_s=min(
                    hour_end,
                    incident.onset_s
                    + self.keyed.randint(15, 419, incident.incident_id, "base-delay"),
                ),
                callback_group=callback_group,
                descriptor_family=descriptor,
            )
        )
        specs = (
            ("duplicate", "911", 120, 899),
            ("multi_channel", "text-to-911", 60, 719),
            ("conflict", "911-transfer", 180, 1_099),
            ("revision", "911-callback", 300, 1_499),
        )
        for ordinal, (probability_name, channel, minimum, maximum) in enumerate(specs, start=1):
            if not self.keyed.bernoulli(
                self.probabilities[probability_name],
                "incident",
                incident.incident_id,
                probability_name,
            ):
                continue
            report_relationship = (
                "conflicting_report" if probability_name == "conflict" else probability_name
            )
            self.append(
                ReportDraft(
                    incident=incident,
                    relationship=report_relationship,
                    ordinal=ordinal,
                    channel=channel,
                    received_s=min(
                        hour_end,
                        incident.onset_s
                        + self.keyed.randint(
                            minimum,
                            maximum,
                            incident.incident_id,
                            probability_name,
                            "delay",
                        ),
                    ),
                    callback_group=callback_group,
                    descriptor_family=descriptor,
                    revision_of_call_id=(base_call if report_relationship == "revision" else None),
                )
            )

    def _false_reports(self) -> None:
        weights = self.false_report_hour_weights
        if abs(sum(weights) - 1.0) > 1e-12 or any(value < 0.0 for value in weights):
            raise ValueError("false-report hourly weights must be nonnegative and sum to one")
        count = self.keyed.poisson(self.probabilities["false_report_mean"], "false-report-count")
        for false_index in range(count):
            draw = self.keyed.uniform("false-report", false_index, "hour")
            cumulative = 0.0
            selected_hour = 5
            for hour, weight in enumerate(weights):
                cumulative += weight
                if draw < cumulative:
                    selected_hour = hour
                    break
            self.append(
                ReportDraft(
                    incident=None,
                    relationship="false_report",
                    ordinal=false_index,
                    channel="non-emergency-transfer",
                    received_s=selected_hour * 3_600
                    + self.keyed.randint(0, 3_599, "false-report", false_index, "received"),
                    callback_group=f"FALSE-{false_index + 1:04d}",
                )
            )

    def generate(self) -> ObservationArtifact:
        for incident in self.truth.incidents:
            self._incident_reports(incident)
        self._false_reports()
        mixture = location_method_mixture(self.config.axes.iota)
        return ObservationArtifact(
            schema_version="delta-observations-v5",
            calls=sorted(self.calls, key=lambda item: (item.received_s, item.call_id)),
            lineage=sorted(self.lineage, key=lambda item: item.call_id),
            expected_calls_total=self.config.call_process.expected_calls_total,
            peak_expected_calls_per_hour=self.config.call_process.peak_expected_calls_per_hour,
            coefficients_version="delta-observation-coefficients-v2",
            location_method_target_milli={
                key: round(1_000 * value) for key, value in mixture.items()
            },
            location_error_scale_milli=round(1_000 * location_error_scale(self.config.axes.iota)),
        )


def generate_observations_v8(
    config: DeltaScenarioConfig,
    truth: GroundTruth,
    keyed: KeyedRandom,
    *,
    reporting_by_hour: tuple[float, float, float, float, float, float] | None = None,
    false_report_hour_weights: tuple[float, float, float, float, float, float] | None = None,
) -> ObservationArtifact:
    """Public canonical observation-stage facade."""

    return ObservationChannel(
        config,
        truth,
        keyed,
        reporting_by_hour=reporting_by_hour,
        false_report_hour_weights=false_report_hour_weights,
    ).generate()


# One-release names retained for historical calibration scripts.
channel_probabilities_v8 = channel_probabilities
reporting_probability_v8 = reporting_probability
