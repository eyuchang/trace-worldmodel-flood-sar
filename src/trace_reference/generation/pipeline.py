"""One deterministic, offline assembly path for Reference development worlds."""

from __future__ import annotations

from pathlib import Path

from trace_reference import (
    load_reference_activation_parameters,
    load_reference_config,
    load_reference_exposure_parameters,
    load_reference_gauge_context,
    load_reference_governance,
    load_reference_physical_parameters,
    load_reference_resource_parameters,
)
from trace_reference.calibration.loading import (
    load_reference_observation_coefficients,
    load_reference_truth_coefficients,
)
from trace_reference.domain.scenario import (
    ReferencePriorProfile,
    ReferenceScenarioArtifacts,
)
from trace_reference.geography import load_reference_geography
from trace_reference.models import ReferenceScenarioConfig

from .coordination import generate_reference_coordination
from .exposure import generate_reference_exposure
from .observation_parameters import ReferenceObservationGenerationCoefficients
from .observations import generate_reference_observations
from .physical import generate_reference_physical_scenario
from .resources import generate_reference_resources
from .truth import generate_reference_truth

_CONFIG = Path("configs/scenarios/wf_dfld_01_reference_development.yaml")
_GOVERNANCE = Path("configs/governance/wf_dfld_01_reference_governance_v1.yaml")
_PHYSICAL = Path("data/scenario/delta/reference/physical/reference_physical_parameters_v1.yaml")
_GAUGE_CONTEXT = Path("data/scenario/delta/reference/physical/reference_gauge_context_v1.yaml")
_EXPOSURE = Path("data/scenario/delta/reference/exposure/reference_exposure_parameters_v1.yaml")
_RESOURCES = Path("data/scenario/delta/reference/resources/reference_resource_parameters_v1.yaml")
_ACTIVATIONS = Path(
    "data/scenario/delta/reference/resources/reference_activation_parameters_v1.yaml"
)
_GEOGRAPHY = Path("data/scenario/delta/reference/geography")
_TRUTH_COEFFICIENTS = Path(
    "data/scenario/delta/reference/calibration/reference_truth_coefficients_v2.json"
)
_OBSERVATION_COEFFICIENTS = Path(
    "data/scenario/delta/reference/calibration/reference_observation_coefficients_v2.json"
)


def generate_reference_scenario(
    root: Path,
    *,
    seed: int,
    config: ReferenceScenarioConfig | None = None,
) -> ReferenceScenarioArtifacts:
    """Generate all exogenous stages in the approved causal order without network access."""

    resolved = config or load_reference_config(root, _CONFIG)
    geography = load_reference_geography(geography_root=root / _GEOGRAPHY)
    governance = load_reference_governance(root, _GOVERNANCE)
    physical_parameters = load_reference_physical_parameters(root, _PHYSICAL)
    gauge_context = load_reference_gauge_context(root, _GAUGE_CONTEXT)
    exposure_parameters = load_reference_exposure_parameters(root, _EXPOSURE)
    resource_parameters = load_reference_resource_parameters(root, _RESOURCES)
    activation_parameters = load_reference_activation_parameters(root, _ACTIVATIONS)
    truth_coefficients = load_reference_truth_coefficients(root, _TRUTH_COEFFICIENTS)
    observation_coefficients = load_reference_observation_coefficients(
        root, _OBSERVATION_COEFFICIENTS
    )
    physical = generate_reference_physical_scenario(
        physical_parameters,
        sigma=resolved.axes.sigma,
    )
    exposure = generate_reference_exposure(
        exposure_parameters,
        geography,
        seed=seed,
    )
    truth = generate_reference_truth(
        physical,
        exposure,
        seed=seed,
        coefficient_intercepts={
            item.incident_type: item.intercept_micros for item in truth_coefficients.selected
        },
        coefficient_digest=truth_coefficients.coefficient_digest,
    )
    observations = generate_reference_observations(
        truth,
        exposure,
        seed=seed,
        iota=resolved.axes.iota,
        coefficients=ReferenceObservationGenerationCoefficients(
            coefficient_version=observation_coefficients.coefficient_version,
            coefficient_digest=observation_coefficients.coefficient_digest,
            randomness_namespace=observation_coefficients.randomness_namespace,
            initial_report_probability_micros=(
                observation_coefficients.initial_report_probability_micros
            ),
            supplemental_witness_slots_per_incident=(
                observation_coefficients.supplemental_witness_slots_per_incident
            ),
            hourly_witness_probability_micros=tuple(
                item.witness_probability_micros for item in observation_coefficients.hourly
            ),
        ),
    )
    resources = generate_reference_resources(
        resource_parameters,
        seed=seed,
        kappa=resolved.axes.kappa,
        mu=resolved.axes.mu,
        iota=resolved.axes.iota,
        delta=resolved.axes.delta,
    )
    coordination = generate_reference_coordination(
        observations.delivery,
        resources,
        governance,
        activation_parameters,
        seed=seed,
        phi=resolved.axes.phi,
    )
    prior = ReferencePriorProfile(
        schema_version="delta-reference-prior-profile-v1",
        profile_id="reference-prior-pi-v1",
        calibration_version="toy-calibration-v1",
        prior_accuracy_milli=round(resolved.axes.pi * 1_000),
        pi_micros=round(resolved.axes.pi * 1_000_000),
    )
    return ReferenceScenarioArtifacts(
        config=resolved,
        geography=geography,
        governance=governance,
        physical=physical,
        gauge_context=gauge_context,
        exposure=exposure,
        truth=truth,
        observations=observations,
        resources=resources,
        coordination=coordination,
        prior=prior,
    )
