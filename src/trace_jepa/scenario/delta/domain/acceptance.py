from __future__ import annotations

import hashlib
from datetime import datetime

from pydantic import Field, model_validator

from .base import DeltaModel


class AcceptanceEnsemble(DeltaModel):
    first_seed: int = Field(ge=0)
    seed_count: int = Field(gt=0)


class AcceptanceConfirmatoryEnsemble(DeltaModel):
    derivation: str
    protocol_role: str
    seeds: list[int] = Field(min_length=100, max_length=100)

    @model_validator(mode="after")
    def validate_preregistered_seeds(self) -> AcceptanceConfirmatoryEnsemble:
        prefix = "sha256-u31:WF-DFLD-01-SMALL|confirmatory-"
        if not self.derivation.startswith(prefix) or not self.derivation.endswith("|index"):
            raise ValueError("unknown confirmatory seed derivation")
        version = self.derivation.removeprefix(prefix).removesuffix("|index")
        if version not in {"v1", "v2", "v3", "v4", "v5", "v6", "v7", "v8"}:
            raise ValueError("unsupported confirmatory protocol version")
        expected = [
            int.from_bytes(
                hashlib.sha256(
                    f"WF-DFLD-01-SMALL|confirmatory-{version}|{index}".encode()
                ).digest()[:4],
                "big",
            )
            & 0x7FFFFFFF
            for index in range(100)
        ]
        if self.seeds != expected:
            raise ValueError("confirmatory seeds disagree with the preregistered derivation")
        return self


class AcceptanceCallProcess(DeltaModel):
    expected_total_mean: float = Field(gt=0.0)
    total_mean_absolute_tolerance: float = Field(gt=0.0)
    configured_peak_intensity_per_hour: float = Field(gt=0.0)


class AcceptanceObservationChannel(DeltaModel):
    small_information_quality: float = Field(ge=0.3, le=1.0)
    expected_duplicate_fraction: float = Field(ge=0.0, le=1.0)
    expected_callback_failure_fraction: float = Field(ge=0.0, le=1.0)
    expected_false_levee_fraction: float = Field(ge=0.0, le=1.0)
    expected_multi_channel_fraction: float = Field(ge=0.0, le=1.0)
    expected_nonreporting_fraction: float = Field(ge=0.0, le=1.0)
    expected_revision_fraction: float = Field(ge=0.0, le=1.0)
    fraction_absolute_tolerance: float = Field(gt=0.0, le=1.0)
    expected_point_estimates: dict[str, float] = Field(default_factory=dict)
    point_absolute_tolerances: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_v7_points(self) -> AcceptanceObservationChannel:
        if set(self.expected_point_estimates) != set(self.point_absolute_tolerances):
            raise ValueError(
                "observation point estimates and tolerances must name identical metrics"
            )
        if any(not 0.0 <= value <= 1.0 for value in self.expected_point_estimates.values()):
            raise ValueError("observation point estimates must be fractions")
        if any(not 0.0 < value <= 1.0 for value in self.point_absolute_tolerances.values()):
            raise ValueError("observation point tolerances must be positive fractions")
        return self


class AcceptanceDemandCapacity(DeltaModel):
    target_peak_ratio: float | None = Field(default=None, gt=0.0)
    book_seed_minimum: float | None = Field(default=None, gt=0.0)
    book_seed_maximum: float | None = Field(default=None, gt=0.0)
    confirmatory_median_minimum: float | None = Field(default=None, gt=0.0)
    confirmatory_median_maximum: float | None = Field(default=None, gt=0.0)
    book_allocation_share_minimum: float = Field(default=0.25, ge=0.0, le=1.0)
    book_allocation_share_maximum: float = Field(default=0.75, ge=0.0, le=1.0)
    primary_metric: str = "historical-unspecified"
    strict_numerical_gate: str | None = "legacy-ratio-band"
    historical_sensitivity_metric: str = "not-declared"


class AcceptanceInference(DeltaModel):
    schema_version: str
    seed_cluster_unit: str
    bootstrap_resamples: int = Field(ge=10_000)
    bootstrap_seed_derivation: str
    mean_and_fraction_interval: str
    median_interval: str
    call_pooling_as_independent_observations: bool


class AcceptancePerformance(DeltaModel):
    maximum_generate_run_replay_s: float = Field(gt=0.0)


class AcceptanceReconciliationComparison(DeltaModel):
    selected_algorithm_id: str
    immutable_baseline_algorithm_id: str
    primary_endpoint: str
    recall_noninferiority_margin: float = Field(ge=-0.05, le=-0.05)
    false_merge_claim_rule: str
    recall_claim_rule: str


class DeltaSmallAcceptanceConfig(DeltaModel):
    schema_version: str
    registered_utc: datetime
    book_seed: int = Field(ge=0)
    book_seed_role: str
    development_ensemble: AcceptanceEnsemble
    confirmatory_ensemble: AcceptanceConfirmatoryEnsemble | None = None
    amended_confirmatory_ensemble: AcceptanceConfirmatoryEnsemble | None = None
    final_confirmatory_registered_utc: datetime | None = None
    final_confirmatory_ensemble: AcceptanceConfirmatoryEnsemble | None = None
    spatial_confirmatory_registered_utc: datetime | None = None
    spatial_confirmatory_ensemble: AcceptanceConfirmatoryEnsemble | None = None
    balanced_confirmatory_registered_utc: datetime | None = None
    balanced_confirmatory_ensemble: AcceptanceConfirmatoryEnsemble | None = None
    v7_confirmatory_registered_utc: datetime | None = None
    v7_confirmatory_ensemble: AcceptanceConfirmatoryEnsemble | None = None
    v8_confirmatory_registered_utc: datetime | None = None
    v8_confirmatory_ensemble: AcceptanceConfirmatoryEnsemble | None = None
    artifact_reconstruction_registered_utc: datetime | None = None
    registration_erratum: str | None = None
    frozen_input_sha256: dict[str, str] = Field(default_factory=dict)
    scientific_input_manifest_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    scientific_input_manifest_path: str | None = None
    scientific_input_core_aggregate_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    reconciliation_comparison: AcceptanceReconciliationComparison | None = None
    inference: AcceptanceInference | None = None
    protocol_amendment: str
    call_process: AcceptanceCallProcess
    observation_channel: AcceptanceObservationChannel
    demand_capacity: AcceptanceDemandCapacity
    performance: AcceptancePerformance

    @model_validator(mode="after")
    def validate_protocol_generation(self) -> DeltaSmallAcceptanceConfig:
        _validate_protocol(self)
        return self


def _legacy_ratio_gates(config: DeltaSmallAcceptanceConfig) -> tuple[float | None, ...]:
    demand = config.demand_capacity
    return (
        demand.target_peak_ratio,
        demand.book_seed_minimum,
        demand.book_seed_maximum,
        demand.confirmatory_median_minimum,
        demand.confirmatory_median_maximum,
    )


def _validate_modern_common(config: DeltaSmallAcceptanceConfig, version: str) -> None:
    if config.reconciliation_comparison is None or config.inference is None:
        raise ValueError(f"acceptance {version} requires reconciliation and inference protocols")
    if config.reconciliation_comparison.selected_algorithm_id != "evidence-graph-q075":
        raise ValueError(f"acceptance {version} must bind the selected evidence graph")
    if config.inference.call_pooling_as_independent_observations:
        raise ValueError(f"acceptance {version} forbids pooling calls as independent samples")
    if config.demand_capacity.primary_metric != "strict_concurrent_load_ratio":
        raise ValueError(f"acceptance {version} requires strict concurrency as primary")
    if config.demand_capacity.strict_numerical_gate is not None:
        raise ValueError(f"acceptance {version} forbids a strict-load numerical gate")


def _validate_v9(config: DeltaSmallAcceptanceConfig) -> None:
    if config.v8_confirmatory_registered_utc is None:
        raise ValueError("acceptance v9 requires a registration timestamp")
    ensemble = config.v8_confirmatory_ensemble
    if ensemble is None or "confirmatory-v8" not in ensemble.derivation:
        raise ValueError("acceptance v9 requires untouched confirmatory-v8 seeds")
    expected_manifest = "data/scenario/delta/provenance/v8_scientific_input_manifest_v2.json"
    if config.scientific_input_manifest_path != expected_manifest:
        raise ValueError("acceptance v9 must name the canonical scientific manifest")
    if config.scientific_input_core_aggregate_sha256 is None:
        raise ValueError("acceptance v9 must bind the self-reference-free core aggregate")
    if config.scientific_input_manifest_sha256 is not None:
        raise ValueError("acceptance v9 cannot contain its enclosing manifest hash")
    _validate_modern_common(config, "v9")
    if any(value is not None for value in _legacy_ratio_gates(config)):
        raise ValueError("acceptance v9 forbids historical ratio targets")


def _validate_v10(config: DeltaSmallAcceptanceConfig) -> None:
    if config.artifact_reconstruction_registered_utc is None:
        raise ValueError("acceptance v10 requires an artifact-reconstruction timestamp")
    ensemble = config.v8_confirmatory_ensemble
    if ensemble is None or "confirmatory-v8" not in ensemble.derivation:
        raise ValueError("acceptance v10 must preserve the consumed confirmatory-v8 seeds")
    if "artifact_reconstruction_is_explicitly_not_untouched" not in ensemble.protocol_role:
        raise ValueError("acceptance v10 must label reconstruction evidence as non-untouched")
    expected_manifest = "data/scenario/delta/provenance/v8_scientific_input_manifest_v3.json"
    if config.scientific_input_manifest_path != expected_manifest:
        raise ValueError("acceptance v10 must name scientific manifest v3")
    if config.scientific_input_core_aggregate_sha256 is None:
        raise ValueError("acceptance v10 must bind the self-reference-free core aggregate")
    if config.scientific_input_manifest_sha256 is not None:
        raise ValueError("acceptance v10 cannot contain its enclosing manifest hash")
    if config.registration_erratum is None:
        raise ValueError("acceptance v10 must preserve both failed execution records")
    _validate_modern_common(config, "v10")
    if any(value is not None for value in _legacy_ratio_gates(config)):
        raise ValueError("acceptance v10 forbids historical ratio targets")


def _validate_v8(config: DeltaSmallAcceptanceConfig) -> None:
    if config.v8_confirmatory_registered_utc is None:
        raise ValueError("acceptance v8 requires a registration timestamp field")
    ensemble = config.v8_confirmatory_ensemble
    if ensemble is None or "confirmatory-v7" not in ensemble.derivation:
        raise ValueError("acceptance v8 requires untouched confirmatory-v7 seeds")
    if config.scientific_input_manifest_sha256 is None:
        raise ValueError("acceptance v8 must bind the scientific-input manifest")
    if config.registration_erratum is None:
        raise ValueError("acceptance v8 requires provenance and inference protocols")
    _validate_modern_common(config, "v8")
    if config.frozen_input_sha256:
        raise ValueError("acceptance v8 uses one complete scientific manifest")


def _validate_v7(config: DeltaSmallAcceptanceConfig) -> None:
    if config.v7_confirmatory_registered_utc is None:
        raise ValueError("acceptance v7 requires a registration timestamp field")
    ensemble = config.v7_confirmatory_ensemble
    if ensemble is None or "confirmatory-v6" not in ensemble.derivation:
        raise ValueError("acceptance v7 requires untouched confirmatory-v6 seeds")
    if config.registration_erratum is None or config.inference is None:
        raise ValueError("acceptance v7 requires provenance and inference protocols")
    if config.inference.call_pooling_as_independent_observations:
        raise ValueError("acceptance v7 forbids pooling calls as independent samples")
    if config.demand_capacity.primary_metric != "strict_concurrent_load_ratio":
        raise ValueError("acceptance v7 requires strict concurrency as primary")
    if config.demand_capacity.strict_numerical_gate is not None:
        raise ValueError("acceptance v7 forbids a strict-load numerical gate")
    if any(value is not None for value in _legacy_ratio_gates(config)):
        raise ValueError("acceptance v7 must not retain ambiguous legacy ratio gates")
    if len(config.frozen_input_sha256) < 10 or any(
        len(digest) != 64 for digest in config.frozen_input_sha256.values()
    ):
        raise ValueError("acceptance v7 requires complete SHA-256 input bindings")


def _validate_v6(config: DeltaSmallAcceptanceConfig) -> None:
    if config.balanced_confirmatory_registered_utc is None:
        raise ValueError("acceptance v6 requires a registration timestamp")
    ensemble = config.balanced_confirmatory_ensemble
    if ensemble is None or "confirmatory-v5" not in ensemble.derivation:
        raise ValueError("acceptance v6 requires untouched confirmatory-v5 seeds")


def _validate_v5(config: DeltaSmallAcceptanceConfig) -> None:
    historical = (
        config.confirmatory_ensemble,
        config.amended_confirmatory_ensemble,
        config.final_confirmatory_ensemble,
        config.spatial_confirmatory_ensemble,
    )
    if any(item is None for item in historical):
        raise ValueError("acceptance v5 requires all four historical ensembles")


def _validate_protocol(config: DeltaSmallAcceptanceConfig) -> None:
    validators = {
        "delta-small-acceptance-v10": _validate_v10,
        "delta-small-acceptance-v9": _validate_v9,
        "delta-small-acceptance-v8": _validate_v8,
        "delta-small-acceptance-v7": _validate_v7,
        "delta-small-acceptance-v6": _validate_v6,
        "delta-small-acceptance-v5": _validate_v5,
    }
    validator = validators.get(config.schema_version)
    if validator is None:
        raise ValueError("unsupported Delta Small acceptance schema")
    validator(config)
