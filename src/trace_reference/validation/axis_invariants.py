"""Development-only causal-axis probes for the approved Reference mechanisms."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from trace_reference import (
    load_reference_activation_parameters,
    load_reference_exposure_parameters,
    load_reference_governance,
    load_reference_physical_parameters,
    load_reference_resource_parameters,
)
from trace_reference.calibration.loading import (
    load_reference_observation_coefficients,
    load_reference_truth_coefficients,
)
from trace_reference.decision.canonical import decision_digest
from trace_reference.domain import (
    ReferenceCoordinationArtifacts,
    ReferenceIncidentCandidateAudit,
    ReferenceIncidentType,
    ReferencePriorProfile,
    ReferenceResourceArtifacts,
    ReferenceScenarioArtifacts,
)
from trace_reference.generation import (
    generate_reference_coordination,
    generate_reference_exposure,
    generate_reference_observations,
    generate_reference_physical_scenario,
    generate_reference_resources,
    generate_reference_truth,
)
from trace_reference.generation.observation_parameters import (
    ReferenceObservationGenerationCoefficients,
)

from .acceptance_models import (
    REFERENCE_PHASE6_AXIS_IDS,
    ReferencePhase6AxisId,
    ReferencePhase6AxisResult,
)

_GOVERNANCE = Path("configs/governance/wf_dfld_01_reference_governance_v1.yaml")
_PHYSICAL = Path("data/scenario/delta/reference/physical/reference_physical_parameters_v1.yaml")
_EXPOSURE = Path("data/scenario/delta/reference/exposure/reference_exposure_parameters_v1.yaml")
_RESOURCES = Path("data/scenario/delta/reference/resources/reference_resource_parameters_v1.yaml")
_ACTIVATIONS = Path(
    "data/scenario/delta/reference/resources/reference_activation_parameters_v1.yaml"
)
_TRUTH_COEFFICIENTS = Path(
    "data/scenario/delta/reference/calibration/reference_truth_coefficients_v2.json"
)
_OBSERVATION_COEFFICIENTS = Path(
    "data/scenario/delta/reference/calibration/reference_observation_coefficients_v2.json"
)


@dataclass(frozen=True)
class _AxisResultInput:
    axis: ReferencePhase6AxisId
    baseline_value: str
    variant_value: str
    unchanged: tuple[str, ...]
    changed: tuple[str, ...]
    keyed_draws: bool
    checks: Mapping[str, bool]
    observed_digests: Mapping[str, str]


def _result(values: _AxisResultInput) -> ReferencePhase6AxisResult:
    passed = values.keyed_draws and all(values.checks.values())
    body = {
        "axis": values.axis,
        "baseline_value": values.baseline_value,
        "variant_value": values.variant_value,
        "unchanged_stage_names": tuple(sorted(values.unchanged)),
        "changed_stage_names": tuple(sorted(values.changed)),
        "mechanism_checks": tuple(sorted(values.checks.items())),
        "observed_digests": tuple(sorted(values.observed_digests.items())),
        "keyed_draw_identity_preserved": values.keyed_draws,
        "passed": passed,
    }
    return ReferencePhase6AxisResult(
        **body,
        evidence_digest=decision_digest(body),
    )


def _truth_draws(
    audit: tuple[ReferenceIncidentCandidateAudit, ...],
) -> dict[str, int]:
    return {
        item.representative_attempt.candidate_digest: item.representative_attempt.draw_micros
        for item in audit
    }


def _shared_truth_draws_equal(
    baseline: tuple[ReferenceIncidentCandidateAudit, ...],
    variant: tuple[ReferenceIncidentCandidateAudit, ...],
) -> bool:
    first = _truth_draws(baseline)
    second = _truth_draws(variant)
    shared = first.keys() & second.keys()
    return bool(shared) and all(first[key] == second[key] for key in shared)


def _resource_roster_signature(resources: ReferenceResourceArtifacts) -> str:
    hidden = resources.hidden
    return decision_digest(
        {
            "resources": tuple(
                (
                    item.resource_id,
                    item.resource_class.value,
                    tuple(capability.value for capability in item.capabilities),
                    item.service_units,
                    item.crew_id,
                    item.inclusion_threshold_micros,
                )
                for item in hidden.resources
            )
        }
    )


def _shared_resource_truth_equal(
    first: ReferenceResourceArtifacts,
    second: ReferenceResourceArtifacts,
) -> bool:
    first_hidden = first.hidden
    second_hidden = second.hidden
    second_resources = {item.resource_id: item for item in second_hidden.resources}
    second_crews = {item.crew_id: item for item in second_hidden.crews}
    return all(
        second_resources.get(item.resource_id) == item
        and second_crews.get(item.crew_id)
        == next(crew for crew in first_hidden.crews if crew.crew_id == item.crew_id)
        for item in first_hidden.resources
        if item.resource_id in second_resources
    )


def _shared_resource_randomness_equal(
    first: ReferenceResourceArtifacts,
    second: ReferenceResourceArtifacts,
) -> bool:
    """Compare properties generated from axis-independent resource draw keys."""

    second_resources = {item.resource_id: item for item in second.hidden.resources}
    second_crews = {item.crew_id: item for item in second.hidden.crews}
    second_samples = {(item.resource_id, item.at_s): item for item in second.hidden.state_samples}
    shared_resources = tuple(
        item for item in first.hidden.resources if item.resource_id in second_resources
    )
    if not shared_resources:
        return False
    for resource in shared_resources:
        peer = second_resources[resource.resource_id]
        if resource.inclusion_threshold_micros != peer.inclusion_threshold_micros:
            return False
        crew = next(item for item in first.hidden.crews if item.crew_id == resource.crew_id)
        peer_crew = second_crews.get(resource.crew_id)
        if peer_crew is None or crew.cycle_offset_s != peer_crew.cycle_offset_s:
            return False
    return all(
        second_samples.get((item.resource_id, item.at_s)) is not None
        and second_samples[(item.resource_id, item.at_s)].fuel_or_charge_micros
        == item.fuel_or_charge_micros
        for item in first.hidden.state_samples
        if item.resource_id in second_resources
    )


def _shared_report_candidate_ids(
    first: ReferenceScenarioArtifacts,
    variant_reports: set[str],
) -> bool:
    baseline = {item.call_id for item in first.observations.raw.reports}
    return bool(baseline & variant_reports)


def _shared_coordination_draws_equal(
    scenario: ReferenceScenarioArtifacts,
    variant: ReferenceCoordinationArtifacts,
) -> bool:
    baseline_attempts = {
        (item.evidence_id, item.recipient_authority_id): item
        for item in scenario.coordination.hidden.attempts
    }
    variant_attempts = {
        (item.evidence_id, item.recipient_authority_id): item for item in variant.hidden.attempts
    }
    shared = baseline_attempts.keys() & variant_attempts.keys()
    return bool(shared) and all(
        (
            baseline_attempts[key].latency_draw_micros,
            baseline_attempts[key].loss_draw_micros,
        )
        == (
            variant_attempts[key].latency_draw_micros,
            variant_attempts[key].loss_draw_micros,
        )
        for key in shared
    )


def _observation_parameters(repository_root: Path) -> ReferenceObservationGenerationCoefficients:
    values = load_reference_observation_coefficients(repository_root, _OBSERVATION_COEFFICIENTS)
    return ReferenceObservationGenerationCoefficients(
        coefficient_version=values.coefficient_version,
        coefficient_digest=values.coefficient_digest,
        randomness_namespace=values.randomness_namespace,
        initial_report_probability_micros=values.initial_report_probability_micros,
        supplemental_witness_slots_per_incident=values.supplemental_witness_slots_per_incident,
        hourly_witness_probability_micros=tuple(
            item.witness_probability_micros for item in values.hourly
        ),
    )


def _truth_parameters(
    repository_root: Path,
) -> tuple[dict[ReferenceIncidentType, int], str]:
    values = load_reference_truth_coefficients(repository_root, _TRUTH_COEFFICIENTS)
    return (
        {item.incident_type: item.intercept_micros for item in values.selected},
        values.coefficient_digest,
    )


def build_reference_phase6_axis_results(
    repository_root: Path,
    scenario: ReferenceScenarioArtifacts,
) -> tuple[ReferencePhase6AxisResult, ...]:
    """Exercise all eight approved mechanisms on one spent development world."""

    seed = scenario.truth.seed
    if seed != 20260812:
        raise ValueError("Phase 6 axis probes require the spent illustrative seed")
    physical_parameters = load_reference_physical_parameters(repository_root, _PHYSICAL)
    exposure_parameters = load_reference_exposure_parameters(repository_root, _EXPOSURE)
    resource_parameters = load_reference_resource_parameters(repository_root, _RESOURCES)
    activation_parameters = load_reference_activation_parameters(repository_root, _ACTIVATIONS)
    governance = load_reference_governance(repository_root, _GOVERNANCE)
    truth_intercepts, truth_digest = _truth_parameters(repository_root)

    severe_physical = generate_reference_physical_scenario(physical_parameters, sigma=1.2)
    severe_truth = generate_reference_truth(
        severe_physical,
        scenario.exposure,
        seed=seed,
        coefficient_intercepts=truth_intercepts,
        coefficient_digest=truth_digest,
    )
    sigma = _result(
        _AxisResultInput(
            axis="sigma",
            baseline_value="1.0",
            variant_value="1.2-development-mechanism-probe",
            unchanged=("exposure", "geography", "observations-randomness", "resource-inventory"),
            changed=("physical-hazard", "truth-descendants"),
            keyed_draws=_shared_truth_draws_equal(
                scenario.truth.candidate_audit,
                severe_truth.candidate_audit,
            ),
            checks={
                "physical-changed": severe_physical.physical_digest
                != scenario.physical.physical_digest,
                "truth-changed": severe_truth.truth_digest != scenario.truth.truth_digest,
            },
            observed_digests={
                "baseline-physical": scenario.physical.physical_digest,
                "baseline-truth": scenario.truth.truth_digest,
                "variant-physical": severe_physical.physical_digest,
                "variant-truth": severe_truth.truth_digest,
            },
        )
    )

    scarce = generate_reference_resources(resource_parameters, seed=seed, kappa=0.5)
    kappa = _result(
        _AxisResultInput(
            axis="kappa",
            baseline_value="1.0",
            variant_value="0.5-registered-scarcity-mechanism",
            unchanged=("exposure", "geography", "observations", "physical-hazard", "truth"),
            changed=("resource-inventory",),
            keyed_draws=_shared_resource_randomness_equal(scenario.resources, scarce),
            checks={
                "inventory-is-strict-subset": {item.resource_id for item in scarce.hidden.resources}
                < {item.resource_id for item in scenario.resources.hidden.resources},
                "shared-resource-truth-stable": _shared_resource_truth_equal(
                    scarce,
                    scenario.resources,
                ),
            },
            observed_digests={
                "baseline-roster": _resource_roster_signature(scenario.resources),
                "variant-roster": _resource_roster_signature(scarce),
            },
        )
    )

    slow = generate_reference_resources(resource_parameters, seed=seed, mu=1.5)
    mu = _result(
        _AxisResultInput(
            axis="mu",
            baseline_value="1.0",
            variant_value="1.5-development-mechanism-probe",
            unchanged=("exposure", "geography", "inventory-identity", "physical-hazard", "truth"),
            changed=("resource-mobilization-friction",),
            keyed_draws=_shared_resource_randomness_equal(scenario.resources, slow),
            checks={
                "roster-stable": _resource_roster_signature(slow)
                == _resource_roster_signature(scenario.resources),
                "friction-nondecreasing": all(
                    variant.activation_delay_s >= baseline.activation_delay_s
                    and variant.nominal_travel_s >= baseline.nominal_travel_s
                    and variant.staging_delay_s >= baseline.staging_delay_s
                    for baseline, variant in zip(
                        scenario.resources.hidden.resources,
                        slow.hidden.resources,
                        strict=True,
                    )
                ),
            },
            observed_digests={
                "baseline-resource-truth": scenario.resources.hidden.hidden_resource_digest,
                "baseline-roster": _resource_roster_signature(scenario.resources),
                "variant-resource-truth": slow.hidden.hidden_resource_digest,
                "variant-roster": _resource_roster_signature(slow),
            },
        )
    )

    low_iota_observations = generate_reference_observations(
        scenario.truth,
        scenario.exposure,
        seed=seed,
        iota=0.3,
        coefficients=_observation_parameters(repository_root),
    )
    low_iota_resources = generate_reference_resources(
        resource_parameters,
        seed=seed,
        iota=0.3,
    )
    iota = _result(
        _AxisResultInput(
            axis="iota",
            baseline_value="0.7",
            variant_value="0.3-development-mechanism-probe",
            unchanged=("exposure", "geography", "physical-hazard", "resource-inventory", "truth"),
            changed=("public-observations", "resource-telemetry"),
            keyed_draws=(
                _shared_report_candidate_ids(
                    scenario,
                    {item.call_id for item in low_iota_observations.raw.reports},
                )
                and _shared_resource_randomness_equal(
                    scenario.resources,
                    low_iota_resources,
                )
            ),
            checks={
                "reports-changed": low_iota_observations.raw.raw_reports_digest
                != scenario.observations.raw.raw_reports_digest,
                "resource-truth-stable": low_iota_resources.hidden.hidden_resource_digest
                == scenario.resources.hidden.hidden_resource_digest,
                "telemetry-changed": low_iota_resources.public.telemetry_digest
                != scenario.resources.public.telemetry_digest,
            },
            observed_digests={
                "baseline-reports": scenario.observations.raw.raw_reports_digest,
                "baseline-resource-truth": scenario.resources.hidden.hidden_resource_digest,
                "baseline-telemetry": scenario.resources.public.telemetry_digest,
                "variant-reports": low_iota_observations.raw.raw_reports_digest,
                "variant-resource-truth": low_iota_resources.hidden.hidden_resource_digest,
                "variant-telemetry": low_iota_resources.public.telemetry_digest,
            },
        )
    )

    partitioned = generate_reference_coordination(
        scenario.observations.delivery,
        scenario.resources,
        governance,
        activation_parameters,
        seed=seed,
        phi=5,
    )
    phi = _result(
        _AxisResultInput(
            axis="phi",
            baseline_value="4",
            variant_value="5-development-mechanism-probe",
            unchanged=(
                "exposure",
                "physical-hazard",
                "public-observations",
                "resource-inventory",
                "truth",
            ),
            changed=("coordination-delivery",),
            keyed_draws=_shared_coordination_draws_equal(scenario, partitioned),
            checks={
                "coordination-changed": partitioned.public.public_coordination_digest
                != scenario.coordination.public.public_coordination_digest,
                "partitioning-changed": {
                    item.recipient_partition_id for item in partitioned.hidden.attempts
                }
                != {item.recipient_partition_id for item in scenario.coordination.hidden.attempts},
            },
            observed_digests={
                "baseline-coordination": scenario.coordination.public.public_coordination_digest,
                "raw-observations": scenario.observations.raw.raw_reports_digest,
                "variant-coordination": partitioned.public.public_coordination_digest,
            },
        )
    )

    prior_variant = ReferencePriorProfile(
        schema_version="delta-reference-prior-profile-v1",
        profile_id="reference-prior-pi-v1",
        calibration_version=scenario.prior.calibration_version,
        prior_accuracy_milli=900,
        pi_micros=900_000,
    )
    pi = _result(
        _AxisResultInput(
            axis="pi",
            baseline_value="0.7",
            variant_value="0.9-development-mechanism-probe",
            unchanged=(
                "exposure",
                "geography",
                "observations",
                "physical-hazard",
                "resource-inventory",
                "truth",
            ),
            changed=("predictor-prior-profile",),
            keyed_draws=True,
            checks={
                "axis-is-deterministic-without-random-draws": True,
                "profile-value-changed": prior_variant.pi_micros != scenario.prior.pi_micros,
                "predictor-identity-stable": prior_variant.calibration_version
                == scenario.prior.calibration_version,
            },
            observed_digests={
                "baseline-prior": decision_digest(scenario.prior.model_dump(mode="json")),
                "variant-prior": decision_digest(prior_variant.model_dump(mode="json")),
            },
        )
    )

    exposed = generate_reference_exposure(
        exposure_parameters,
        scenario.geography,
        seed=seed,
        epsilon=1.2,
    )
    exposed_truth = generate_reference_truth(
        scenario.physical,
        exposed,
        seed=seed,
        coefficient_intercepts=truth_intercepts,
        coefficient_digest=truth_digest,
    )
    epsilon = _result(
        _AxisResultInput(
            axis="epsilon",
            baseline_value="reference-exposure-v1@1.0",
            variant_value="1.2-development-mechanism-probe",
            unchanged=("geography", "physical-hazard", "resource-inventory"),
            changed=("exposure-vulnerability", "truth-descendants"),
            keyed_draws=_shared_truth_draws_equal(
                scenario.truth.candidate_audit,
                exposed_truth.candidate_audit,
            ),
            checks={
                "structure-identity-stable": tuple(
                    item.truth_structure_id for item in exposed.structures
                )
                == tuple(item.truth_structure_id for item in scenario.exposure.structures),
                "person-identity-stable": tuple(item.truth_person_id for item in exposed.people)
                == tuple(item.truth_person_id for item in scenario.exposure.people),
                "vulnerability-changed": sum(item.vulnerability_micros for item in exposed.people)
                > sum(item.vulnerability_micros for item in scenario.exposure.people),
                "truth-changed": exposed_truth.truth_digest != scenario.truth.truth_digest,
            },
            observed_digests={
                "baseline-exposure": scenario.exposure.exposure_digest,
                "baseline-truth": scenario.truth.truth_digest,
                "variant-exposure": exposed.exposure_digest,
                "variant-truth": exposed_truth.truth_digest,
            },
        )
    )

    degraded = generate_reference_resources(resource_parameters, seed=seed, delta=0.6)
    delta = _result(
        _AxisResultInput(
            axis="delta",
            baseline_value="0.2",
            variant_value="0.6-development-mechanism-probe",
            unchanged=("exposure", "geography", "inventory-identity", "physical-hazard", "truth"),
            changed=("resource-availability", "resource-telemetry"),
            keyed_draws=_shared_resource_randomness_equal(scenario.resources, degraded),
            checks={
                "roster-stable": _resource_roster_signature(degraded)
                == _resource_roster_signature(scenario.resources),
                "availability-changed": degraded.hidden.hidden_resource_digest
                != scenario.resources.hidden.hidden_resource_digest,
                "telemetry-changed": degraded.public.telemetry_digest
                != scenario.resources.public.telemetry_digest,
            },
            observed_digests={
                "baseline-resource-truth": scenario.resources.hidden.hidden_resource_digest,
                "baseline-roster": _resource_roster_signature(scenario.resources),
                "baseline-telemetry": scenario.resources.public.telemetry_digest,
                "variant-resource-truth": degraded.hidden.hidden_resource_digest,
                "variant-roster": _resource_roster_signature(degraded),
                "variant-telemetry": degraded.public.telemetry_digest,
            },
        )
    )
    results = (sigma, kappa, mu, iota, phi, pi, epsilon, delta)
    if tuple(item.axis for item in results) != REFERENCE_PHASE6_AXIS_IDS:
        raise RuntimeError("Reference Phase 6 axis construction is incomplete")
    return results
