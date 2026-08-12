"""Typed, fail-closed companion contracts for WF-DFLD-01-REFERENCE."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Literal

from pydantic import Field, model_validator

from trace_jepa.scenario.delta.domain.base import DeltaModel

REFERENCE_GENERATION_ORDER = (
    "geography",
    "meteorology",
    "hydrology_breach_access",
    "exposure_truth_incidents",
    "public_observations",
    "resources_and_telemetry",
    "coordination_delivery",
    "predictor_prior",
    "fault_overlay",
    "trace_execution_recovery",
    "offline_evaluation",
)


class ReferenceTimelineConfig(DeltaModel):
    """Half-open burn-in and evaluation windows for the canonical design draft."""

    evaluation_start_iso8601: datetime
    timezone: Literal["America/Los_Angeles"]
    onset_clock: Literal["predawn_weekend"]
    burn_in_start_s: int
    evaluation_start_s: int
    evaluation_end_s: int
    output_tick_s: int = Field(gt=0)
    decision_tick_s: int = Field(gt=0)
    capacity_evaluation_tick_s: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_canonical_windows(self) -> ReferenceTimelineConfig:
        expected = (-172_800, 0, 345_600)
        actual = (self.burn_in_start_s, self.evaluation_start_s, self.evaluation_end_s)
        if actual != expected:
            raise ValueError("Reference requires a 48-hour burn-in and 96-hour evaluation")
        if self.evaluation_start_iso8601.utcoffset() != timedelta(hours=-8):
            raise ValueError("Reference T0 must retain its declared UTC-08:00 synthetic anchor")
        if (self.output_tick_s, self.decision_tick_s, self.capacity_evaluation_tick_s) != (
            300,
            60,
            900,
        ):
            raise ValueError("Reference design-draft grids disagree with the protocol")
        burn_in_duration = self.evaluation_start_s - self.burn_in_start_s
        evaluation_duration = self.evaluation_end_s - self.evaluation_start_s
        if burn_in_duration % self.output_tick_s or evaluation_duration % self.output_tick_s:
            raise ValueError("physical output grid must divide both declared windows")
        if evaluation_duration % self.decision_tick_s:
            raise ValueError("decision grid must divide the evaluation window")
        if evaluation_duration % self.capacity_evaluation_tick_s:
            raise ValueError("capacity grid must divide the evaluation window")
        return self


class ReferenceAxisConfig(DeltaModel):
    sigma: float = Field(ge=0.2, le=2.0)
    kappa: float = Field(ge=0.25, le=2.0)
    mu: float = Field(ge=0.5, le=3.0)
    iota: float = Field(ge=0.3, le=1.0)
    phi: int = Field(ge=1, le=9)
    pi: float = Field(ge=0.3, le=1.0)
    epsilon_profile: Literal["reference-exposure-v1"]
    delta: float = Field(ge=0.0, le=0.6)


class ReferenceExtentConfig(DeltaModel):
    islands: tuple[str, ...]
    communities: tuple[str, ...]
    crossings: tuple[str, ...]
    synthetic_people: int = Field(gt=0)
    scripted_breaches: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_reference_extent(self) -> ReferenceExtentConfig:
        expected = {
            "islands": tuple(f"ISL-{index:02d}" for index in range(1, 9)),
            "communities": tuple(f"TWN-{index:02d}" for index in range(1, 5)),
            "crossings": tuple(f"XNG-{index:02d}" for index in range(1, 11)),
            "synthetic_people": 1_400,
            "scripted_breaches": 1,
        }
        actual = {
            "islands": self.islands,
            "communities": self.communities,
            "crossings": self.crossings,
            "synthetic_people": self.synthetic_people,
            "scripted_breaches": self.scripted_breaches,
        }
        mismatches = [name for name, value in expected.items() if actual[name] != value]
        if mismatches:
            raise ValueError(f"Reference extent mismatch: {', '.join(mismatches)}")
        return self


class ReferenceProcessTargets(DeltaModel):
    expected_public_reports_evaluation: int = Field(gt=0)
    breach_phase_public_report_intensity_per_hour: int = Field(gt=0)
    breach_phase_start_s: int = Field(gt=0)
    breach_phase_end_s: int = Field(gt=0)
    breach_time_s: int = Field(gt=0)
    inherited_load_reference: Literal["approximately_4_to_1_protocol_history_report_only"]

    @model_validator(mode="after")
    def validate_process_design_targets(self) -> ReferenceProcessTargets:
        if self.expected_public_reports_evaluation != 2_900:
            raise ValueError("Reference report-volume target must remain 2,900 in expectation")
        if self.breach_phase_public_report_intensity_per_hour != 95:
            raise ValueError("Reference breach-phase report intensity must remain 95/hour")
        if (self.breach_phase_start_s, self.breach_phase_end_s) != (187_200, 230_400):
            raise ValueError("Reference breach phase must remain [T+52h,T+64h)")
        if self.breach_time_s != 187_200:
            raise ValueError("Reference canonical breach must remain at T+52 hours")
        return self


class ReferencePredictorConfig(DeltaModel):
    implementation: Literal["toy"]
    qualification: Literal["exact_teaching_fixture_only"]


class ReferenceFaultProfiles(DeltaModel):
    baseline: Literal["reference-nominal-v1"]
    integration_acceptance: Literal["reference-faulted-v1"]


class ReferenceStudyNamespace(DeltaModel):
    namespace: str = Field(
        pattern=r"^WF-DFLD-01-REFERENCE\|(development|selection|validation)-v1\|index$"
    )
    materialized: Literal[False]


class ReferenceStudyNamespaces(DeltaModel):
    development: ReferenceStudyNamespace
    selection: ReferenceStudyNamespace
    validation: ReferenceStudyNamespace

    @model_validator(mode="after")
    def validate_distinct_namespaces(self) -> ReferenceStudyNamespaces:
        namespaces = {
            self.development.namespace,
            self.selection.namespace,
            self.validation.namespace,
        }
        if len(namespaces) != 3:
            raise ValueError("Reference study namespaces must be distinct")
        return self


class ReferenceRegisteredSensitivity(DeltaModel):
    """Approved, report-only development sensitivity with no execution authority."""

    study_id: Literal["reference-kappa-0p5-scarcity-v1"]
    changed_axis: Literal["kappa"]
    value: float = Field(ge=0.5, le=0.5)
    pairing: Literal["same-seed-byte-identical-nonresource-exogenous"]
    primary_metric: Literal["strict-concurrent-load-report-only"]
    numerical_gate: Literal[False]
    status: Literal["registered-design-not-executed"]


class ReferenceScenarioConfig(DeltaModel):
    """Canonical development configuration; no confirmatory surface is accepted."""

    status: Literal["approved-decisions-development-only"]
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    scenario_schema_version: Literal["trace-delta-reference-scenario-v1"]
    generator_version: Literal["delta-reference-generator-v1"]
    randomness_namespace_version: Literal["delta-reference-randomness-v1"]
    protocol_document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    protocol_amendment_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    approved_decision_set: Literal["reference-scientific-decisions-v1"]
    small_baseline_registry: str = Field(pattern=r"^[a-zA-Z0-9_./-]+\.json$")
    timeline: ReferenceTimelineConfig
    axes: ReferenceAxisConfig
    extent: ReferenceExtentConfig
    process_targets: ReferenceProcessTargets
    canonical_predictor: ReferencePredictorConfig
    fault_profiles: ReferenceFaultProfiles
    generation_order: tuple[str, ...]
    study_namespaces: ReferenceStudyNamespaces
    registered_sensitivities: tuple[ReferenceRegisteredSensitivity, ...] = Field(
        min_length=1, max_length=1
    )
    exclusions: tuple[str, ...]

    @model_validator(mode="after")
    def validate_protocol_bindings(self) -> ReferenceScenarioConfig:
        if self.protocol_document_sha256 != (
            "03c407ceb1b87041e36f0c58c352840e94bab6cec73a1f69eacd80173e77a552"
        ):
            raise ValueError("Reference configuration does not bind the reviewed draft")
        if self.protocol_amendment_sha256 != (
            "6be6e4a6b4766fb9e66bf7de31924e545503df9202c929587471089076867cca"
        ):
            raise ValueError("Reference configuration does not bind the approved amendment")
        if self.axes.kappa != 1.0:
            raise ValueError("canonical Reference must retain kappa=1.0")
        if tuple(item.study_id for item in self.registered_sensitivities) != (
            "reference-kappa-0p5-scarcity-v1",
        ):
            raise ValueError("approved scarcity sensitivity is absent")
        if self.generation_order != REFERENCE_GENERATION_ORDER:
            raise ValueError("declared Reference generation order disagrees with execution design")
        expected_namespaces = {
            "development": "WF-DFLD-01-REFERENCE|development-v1|index",
            "selection": "WF-DFLD-01-REFERENCE|selection-v1|index",
            "validation": "WF-DFLD-01-REFERENCE|validation-v1|index",
        }
        for role, expected in expected_namespaces.items():
            actual = getattr(self.study_namespaces, role).namespace
            if actual != expected:
                raise ValueError(f"Reference {role} namespace disagrees with the protocol")
        return self


class ReferenceAuthority(DeltaModel):
    authority_id: str = Field(pattern=r"^AUTH-[0-9]{2}$")
    role_name: str = Field(min_length=3)
    status: Literal["provisional-simulation-role"]
    source_entities: tuple[str, ...] = Field(min_length=1)
    evidence_scope: tuple[str, ...] = Field(min_length=1)


class ReferenceGovernanceRegistry(DeltaModel):
    registry_version: Literal["delta-reference-governance-v1"]
    scientific_status: Literal["design-draft-not-legal-command-model"]
    authorities: tuple[ReferenceAuthority, ...] = Field(min_length=4, max_length=4)
    limitation: str = Field(min_length=20)

    @model_validator(mode="after")
    def validate_four_authorities(self) -> ReferenceGovernanceRegistry:
        identifiers = tuple(item.authority_id for item in self.authorities)
        if identifiers != ("AUTH-01", "AUTH-02", "AUTH-03", "AUTH-04"):
            raise ValueError("Reference governance must declare AUTH-01 through AUTH-04 in order")
        return self


class ReferenceSourceRequirement(DeltaModel):
    source_id: str = Field(pattern=r"^REF-SRC-[0-9]{2}$")
    source_class: str = Field(min_length=3)
    preferred_authority: str = Field(min_length=3)
    required_fields: tuple[str, ...] = Field(min_length=1)
    retrieval_status: Literal["not-retrieved"]
    license_status: Literal["not-assessed"]


class ReferenceSourceRequirements(DeltaModel):
    registry_version: Literal["delta-reference-source-requirements-v1"]
    runtime_network_access: Literal["forbidden"]
    requirements: tuple[ReferenceSourceRequirement, ...] = Field(min_length=9, max_length=9)

    @model_validator(mode="after")
    def validate_source_requirements(self) -> ReferenceSourceRequirements:
        identifiers = [item.source_id for item in self.requirements]
        if identifiers != [f"REF-SRC-{index:02d}" for index in range(1, 10)]:
            raise ValueError("Reference source requirements must be complete and ordered")
        if len({item.source_class for item in self.requirements}) != 9:
            raise ValueError("Reference source classes must be distinct")
        return self


class ReferenceSourceCandidate(DeltaModel):
    """One researched locator; it is not yet an approved runtime data input."""

    source_id: str = Field(pattern=r"^REF-SRC-[0-9]{2}$")
    research_status: Literal["verified-official-locator", "unresolved"]
    agency: str = Field(min_length=3)
    dataset_title: str = Field(min_length=3)
    landing_page_url: str | None = Field(default=None, pattern=r"^https://")
    machine_readable_url: str | None = Field(default=None, pattern=r"^https://")
    verified_date: date | None = None
    redistribution_status: Literal[
        "not-assessed",
        "united-states-public-domain",
        "public-use-no-restrictions",
        "clipped-government-snapshot-with-attribution",
    ]
    runtime_inclusion: Literal["none"]
    limitations: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_research_status(self) -> ReferenceSourceCandidate:
        if self.research_status == "verified-official-locator" and (
            self.landing_page_url is None or self.verified_date is None
        ):
            raise ValueError("verified source candidates require a landing page and date")
        if self.redistribution_status != "not-assessed" and self.research_status != (
            "verified-official-locator"
        ):
            raise ValueError("redistribution status cannot be inferred for unresolved sources")
        return self


class ReferenceSourceResearchRegistry(DeltaModel):
    """Development research ledger kept separate from the frozen source registry."""

    registry_version: Literal["delta-reference-source-research-v1"]
    scientific_status: Literal["research-draft-no-runtime-inputs"]
    candidates: tuple[ReferenceSourceCandidate, ...] = Field(min_length=9, max_length=9)

    @model_validator(mode="after")
    def validate_complete_order(self) -> ReferenceSourceResearchRegistry:
        identifiers = [candidate.source_id for candidate in self.candidates]
        if identifiers != [f"REF-SRC-{index:02d}" for index in range(1, 10)]:
            raise ValueError("Reference source research must cover all requirements in order")
        if any(candidate.runtime_inclusion != "none" for candidate in self.candidates):
            raise ValueError("research candidates cannot become implicit runtime inputs")
        return self


class ReferenceGaugeIdentity(DeltaModel):
    """One official CDEC identity check; never an operative threshold by itself."""

    station_id: str = Field(pattern=r"^[A-Z0-9]{3}$")
    official_name: str = Field(min_length=3)
    latitude_e6: int = Field(ge=-90_000_000, le=90_000_000)
    longitude_e6: int = Field(ge=-180_000_000, le=180_000_000)
    station_elevation_ft: int
    metadata_url: str = Field(pattern=r"^https://cdec\.water\.ca\.gov/")
    identity_status: Literal["matches-specification", "corrects-specification"]
    specification_name: str = Field(min_length=3)
    threshold_status: Literal["unavailable-non-operative"]
    runtime_inclusion: Literal["none"]
    notes: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_identity_disposition(self) -> ReferenceGaugeIdentity:
        names_match = self.official_name.casefold() == self.specification_name.casefold()
        if names_match != (self.identity_status == "matches-specification"):
            raise ValueError("gauge identity disposition disagrees with compared names")
        return self


class ReferenceGaugeResearchRegistry(DeltaModel):
    """Field-level CDEC identity research kept outside runtime inputs."""

    registry_version: Literal["delta-reference-gauge-identity-research-v1"]
    scientific_status: Literal["research-draft-no-runtime-inputs"]
    verified_date: date
    gauges: tuple[ReferenceGaugeIdentity, ...] = Field(min_length=7, max_length=7)

    @model_validator(mode="after")
    def validate_reference_gauge_set(self) -> ReferenceGaugeResearchRegistry:
        expected = ("FPT", "RVB", "SJJ", "ANH", "MRU", "OLD", "MSD")
        actual = tuple(gauge.station_id for gauge in self.gauges)
        if actual != expected:
            raise ValueError("Reference gauge research must retain the specified order")
        if any(gauge.runtime_inclusion != "none" for gauge in self.gauges):
            raise ValueError("gauge research cannot become an implicit runtime input")
        if any(gauge.threshold_status != "unavailable-non-operative" for gauge in self.gauges):
            raise ValueError("metadata identity checks cannot silently activate thresholds")
        return self


class ReferenceTopologyEntity(DeltaModel):
    """One specification identity awaiting authoritative geometry and graph binding."""

    entity_id: str = Field(pattern=r"^(ISL|TWN|XNG)-[0-9]{2}$")
    entity_type: Literal["island", "community", "crossing"]
    design_name: str = Field(min_length=3)
    source_requirement_ids: tuple[str, ...] = Field(min_length=1)
    geometry_status: Literal["unbound"]
    graph_status: Literal["unbound"]
    runtime_inclusion: Literal["none"]
    notes: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_identifier_type(self) -> ReferenceTopologyEntity:
        expected_prefix = {"island": "ISL", "community": "TWN", "crossing": "XNG"}[self.entity_type]
        if not self.entity_id.startswith(f"{expected_prefix}-"):
            raise ValueError("topology entity type disagrees with its identifier")
        if any(not source_id.startswith("REF-SRC-") for source_id in self.source_requirement_ids):
            raise ValueError("topology source references must use Reference source identifiers")
        return self


class ReferenceTopologyDesignRegistry(DeltaModel):
    """Design inventory only; no coordinates, geometries, or routes are approved."""

    registry_version: Literal["delta-reference-topology-design-v1"]
    scientific_status: Literal["design-inventory-no-runtime-geometry"]
    entities: tuple[ReferenceTopologyEntity, ...] = Field(min_length=22, max_length=22)

    @model_validator(mode="after")
    def validate_complete_design_inventory(self) -> ReferenceTopologyDesignRegistry:
        expected = (
            *(f"ISL-{index:02d}" for index in range(1, 9)),
            *(f"TWN-{index:02d}" for index in range(1, 5)),
            *(f"XNG-{index:02d}" for index in range(1, 11)),
        )
        actual = tuple(entity.entity_id for entity in self.entities)
        if actual != expected:
            raise ValueError("Reference topology design inventory is incomplete or unordered")
        if any(entity.runtime_inclusion != "none" for entity in self.entities):
            raise ValueError("unbound topology cannot become an implicit runtime input")
        return self


class SmallBaselineFile(DeltaModel):
    relative_path: str = Field(pattern=r"^[a-zA-Z0-9_./-]+$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    maximum_bytes: int = Field(gt=0)


class ReferenceSmallBaselineRegistry(DeltaModel):
    registry_version: Literal["delta-reference-small-baseline-v1"]
    source_branch: Literal["demo-delta-scenario"]
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    files: tuple[SmallBaselineFile, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_baseline(self) -> ReferenceSmallBaselineRegistry:
        if self.source_commit != "3f912bdf3fbacb679063da9ed2ce15a2330b91ab":
            raise ValueError("Reference must remain based on the delivered Small commit")
        paths = [item.relative_path for item in self.files]
        if len(paths) != len(set(paths)):
            raise ValueError("Small baseline registry contains duplicate paths")
        return self
