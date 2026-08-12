"""Public report, delivery-envelope, and hidden-lineage Reference contracts."""

from __future__ import annotations

from enum import Enum
from typing import Literal, TypeAlias

from pydantic import Field, model_validator

from trace_jepa.scenario.delta.domain.base import DeltaModel

ReferenceChannel: TypeAlias = Literal["911", "311", "radio-relay", "social-relay", "walk-in"]
ReferenceMedicalDescriptor: TypeAlias = Literal["oxygen", "dialysis", "insulin", "mobility"]
ReferenceAuthorityId: TypeAlias = Literal["AUTH-01", "AUTH-02", "AUTH-03", "AUTH-04"]
ReferenceLineageRelationship: TypeAlias = Literal[
    "initial",
    "duplicate",
    "multi-channel",
    "conflict",
    "revision",
    "third-party-welfare",
    "independent-witness",
    "false-benign-levee",
]


class ReferencePublicTaxonomy(str, Enum):
    C_STR = "C-STR"
    C_VEH = "C-VEH"
    C_LEV = "C-LEV"
    C_MED = "C-MED"
    C_WEL = "C-WEL"
    C_MIS = "C-MIS"
    C_ANI = "C-ANI"
    C_INF = "C-INF"
    C_HAZ = "C-HAZ"


class ReferencePublicLocation(DeltaModel):
    easting_mm_epsg26910: int
    northing_mm_epsg26910: int
    precision_m: int = Field(ge=15, le=4_500)
    method: Literal["gps", "address-intersection", "landmark", "cell-sector"]
    stated_descriptor: str = Field(min_length=3, max_length=80)


class ReferenceRawReport(DeltaModel):
    """Controller-visible report content without delivery or hidden-truth state."""

    call_id: str = Field(pattern=r"^RC-[0-9a-f]{16}$")
    observed_at_s: int = Field(ge=-172_800, le=345_300)
    channel: ReferenceChannel
    callback_token: str | None = Field(default=None, pattern=r"^SYN-CB-[0-9a-f]{16}$")
    callback_failed: bool
    call_dropped: bool
    third_party: bool
    language_access: Literal["english", "spanish", "tagalog", "chinese"]
    location: ReferencePublicLocation
    taxonomy: ReferencePublicTaxonomy
    reported_occupants: int | None = Field(default=None, ge=0, le=24)
    medical_descriptors: tuple[ReferenceMedicalDescriptor, ...]
    descriptor_tokens: tuple[str, ...] = Field(min_length=1, max_length=4)
    revision_of_call_id: str | None = Field(default=None, pattern=r"^RC-[0-9a-f]{16}$")

    @model_validator(mode="after")
    def validate_revision(self) -> ReferenceRawReport:
        if self.revision_of_call_id == self.call_id:
            raise ValueError("Reference report cannot revise itself")
        return self


class ReferenceRawObservationScenario(DeltaModel):
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    schema_version: Literal["delta-reference-observations-v1", "delta-reference-observations-v2"]
    coefficient_version: Literal[
        "delta-reference-observation-development-coefficients-v1",
        "delta-reference-observation-development-coefficients-v2",
    ]
    scientific_status: Literal[
        "development-coefficients-not-frozen-for-validation",
        "frozen-spent-development-fit-not-validation-evidence",
    ]
    seed: int = Field(ge=0)
    iota_micros: int = Field(ge=300_000, le=1_000_000)
    reports: tuple[ReferenceRawReport, ...]
    raw_reports_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_public_order_and_ids(self) -> ReferenceRawObservationScenario:
        ordered = tuple(sorted(self.reports, key=lambda item: (item.observed_at_s, item.call_id)))
        if self.reports != ordered:
            raise ValueError("Reference raw reports must use canonical observation/ID order")
        ids = tuple(item.call_id for item in self.reports)
        id_set = set(ids)
        if len(id_set) != len(ids):
            raise ValueError("Reference public report identifiers must be unique")
        if any(
            item.revision_of_call_id is not None and item.revision_of_call_id not in id_set
            for item in self.reports
        ):
            raise ValueError("Reference report revision points to an absent public call")
        return self


class ReferenceReportEnvelope(DeltaModel):
    """One signed, authority-specific delivery of a raw report."""

    envelope_id: str = Field(pattern=r"^RE-[0-9a-f]{16}$")
    call_id: str = Field(pattern=r"^RC-[0-9a-f]{16}$")
    delivered_at_s: int = Field(ge=-172_800, le=352_800)
    initial_authority_id: ReferenceAuthorityId
    authentication_status: Literal["fixture-valid", "fixture-invalid"]
    key_version: Literal["reference-test-key-v1"]
    integrity_token: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReferenceDeliveryEnvelopeScenario(DeltaModel):
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    schema_version: Literal["delta-reference-delivery-envelopes-v1"]
    seed: int = Field(ge=0)
    envelopes: tuple[ReferenceReportEnvelope, ...]
    delivery_envelopes_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_envelope_order_and_ids(self) -> ReferenceDeliveryEnvelopeScenario:
        ordered = tuple(
            sorted(self.envelopes, key=lambda item: (item.delivered_at_s, item.envelope_id))
        )
        if self.envelopes != ordered:
            raise ValueError("Reference delivery envelopes must use canonical delivery/ID order")
        ids = tuple(item.envelope_id for item in self.envelopes)
        if len(set(ids)) != len(ids):
            raise ValueError("Reference delivery envelope identifiers must be unique")
        return self


class ReferenceHiddenReportLineage(DeltaModel):
    call_id: str = Field(pattern=r"^RC-[0-9a-f]{16}$")
    truth_incident_id: str | None = Field(default=None, pattern=r"^RI-[0-9a-f]{16}$")
    relationship: ReferenceLineageRelationship
    truth_person_ids: tuple[str, ...]
    true_location_error_m: int = Field(ge=0)
    taxonomy_truthful: bool
    occupant_report_truthful: bool | None


class ReferenceHiddenObservationLineage(DeltaModel):
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    schema_version: Literal["delta-reference-hidden-lineage-v1"]
    entries: tuple[ReferenceHiddenReportLineage, ...]
    hidden_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_lineage_ids(self) -> ReferenceHiddenObservationLineage:
        ids = tuple(item.call_id for item in self.entries)
        if len(set(ids)) != len(ids):
            raise ValueError("Reference hidden lineage call identifiers must be unique")
        return self


class ReferenceObservationArtifacts(DeltaModel):
    raw: ReferenceRawObservationScenario
    delivery: ReferenceDeliveryEnvelopeScenario
    hidden: ReferenceHiddenObservationLineage

    @model_validator(mode="after")
    def validate_artifact_joins(self) -> ReferenceObservationArtifacts:
        report_ids = {item.call_id for item in self.raw.reports}
        if report_ids != {item.call_id for item in self.hidden.entries}:
            raise ValueError("Reference raw reports and hidden lineage do not join exactly")
        if report_ids != {item.call_id for item in self.delivery.envelopes}:
            raise ValueError("Reference raw reports and delivery envelopes do not join exactly")
        observed_by_call = {item.call_id: item.observed_at_s for item in self.raw.reports}
        if any(
            envelope.delivered_at_s < observed_by_call[envelope.call_id]
            for envelope in self.delivery.envelopes
        ):
            raise ValueError("Reference report delivery cannot precede observation")
        return self
