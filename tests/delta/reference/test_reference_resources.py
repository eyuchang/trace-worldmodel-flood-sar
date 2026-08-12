from __future__ import annotations

from pathlib import Path

import pytest

from trace_reference import load_reference_resource_parameters
from trace_reference.domain.resources import (
    ReferenceResourceCapability,
    ReferenceResourceClass,
    ReferenceResourceState,
)
from trace_reference.generation import generate_reference_resources

ROOT = Path(__file__).resolve().parents[3]
RESOURCE_PARAMETERS = Path(
    "data/scenario/delta/reference/resources/reference_resource_parameters_v1.yaml"
)


@pytest.fixture(scope="module")
def parameters():
    return load_reference_resource_parameters(ROOT, RESOURCE_PARAMETERS)


@pytest.fixture(scope="module")
def resources(parameters):
    return generate_reference_resources(parameters, seed=20260812)


def test_resource_roster_is_deterministic_nested_and_explicitly_synthetic(
    parameters, resources
) -> None:
    regenerated = generate_reference_resources(parameters, seed=20260812)
    assert resources.model_dump_json() == regenerated.model_dump_json()
    assert len(resources.hidden.resources) == sum(
        item.baseline_count for item in parameters.holdings
    )
    assert all(
        item.fixture_semantics
        == "synthetic-planning-fixture-from-source-sketch-not-current-inventory-claim"
        for item in parameters.holdings
    )
    half = generate_reference_resources(parameters, seed=20260812, kappa=0.5)
    double = generate_reference_resources(parameters, seed=20260812, kappa=2.0)
    half_ids = {item.resource_id for item in half.hidden.resources}
    base_ids = {item.resource_id for item in resources.hidden.resources}
    double_ids = {item.resource_id for item in double.hidden.resources}
    assert half_ids < base_ids < double_ids


def test_inventory_has_exact_crew_join_and_capability_separation(resources) -> None:
    resource_by_id = {item.resource_id: item for item in resources.hidden.resources}
    assert {item.resource_id for item in resources.hidden.crews} == set(resource_by_id)
    engines = [
        item
        for item in resources.hidden.resources
        if item.resource_class == ReferenceResourceClass.TYPE_I_ENGINE
    ]
    assert engines
    assert all(
        ReferenceResourceCapability.WATER_RESCUE not in item.capabilities for item in engines
    )
    assert any(
        ReferenceResourceCapability.WATER_RESCUE in item.capabilities
        for item in resources.hidden.resources
    )


def test_public_roster_contains_no_hidden_operational_state(resources) -> None:
    hidden_ids = {item.resource_id for item in resources.hidden.resources}
    public_ids = {item.resource_id for item in resources.public_catalog.resources}
    assert public_ids == hidden_ids
    serialized = resources.public_catalog.model_dump_json()
    for forbidden in (
        "initial_outage_until_s",
        "fatigue",
        "crew_rest",
        "hidden_resource_digest",
        "state_samples",
    ):
        assert forbidden not in serialized


def test_kappa_mu_iota_delta_have_separate_resource_effects(parameters) -> None:
    baseline = generate_reference_resources(parameters, seed=20260812)
    slow = generate_reference_resources(parameters, seed=20260812, mu=1.5)
    degraded = generate_reference_resources(parameters, seed=20260812, delta=0.6)
    noisy = generate_reference_resources(parameters, seed=20260812, iota=0.3)

    def inventory_signature(artifacts):
        return tuple(
            (
                item.resource_id,
                item.resource_class,
                item.capabilities,
                item.service_units,
                item.home_base_id,
                item.tier,
            )
            for item in artifacts.hidden.resources
        )

    assert inventory_signature(baseline) == inventory_signature(slow)
    assert inventory_signature(baseline) == inventory_signature(degraded)
    assert baseline.hidden.hidden_resource_digest == noisy.hidden.hidden_resource_digest
    assert baseline.public.telemetry_digest != noisy.public.telemetry_digest
    assert all(
        slow_item.activation_delay_s >= base_item.activation_delay_s
        and slow_item.nominal_travel_s >= base_item.nominal_travel_s
        and slow_item.staging_delay_s >= base_item.staging_delay_s
        for base_item, slow_item in zip(
            baseline.hidden.resources, slow.hidden.resources, strict=True
        )
    )
    assert any(
        first.initial_outage_until_s != second.initial_outage_until_s
        for first, second in zip(baseline.hidden.resources, degraded.hidden.resources, strict=True)
    )


def test_hidden_state_and_public_telemetry_are_distinct(resources) -> None:
    assert resources.hidden.state_samples
    assert resources.public.telemetry
    assert "contradiction_injected" not in resources.public.model_dump_json()
    assert any(item.contradiction_injected for item in resources.hidden_telemetry_audit.entries)
    assert len(resources.public.telemetry) < len(resources.hidden.state_samples)
    hidden_status = {
        (item.resource_id, item.at_s): item.state for item in resources.hidden.state_samples
    }
    public_by_id = {item.telemetry_id: item for item in resources.public.telemetry}
    assert any(
        hidden_status[(item.resource_id, item.observed_at_s)]
        != public_by_id[item.public_telemetry_id].reported_state
        for item in resources.hidden_telemetry_audit.entries
        if item.contradiction_injected and item.public_telemetry_id is not None
    )
    assert any(
        item.state == ReferenceResourceState.AWAITING_REQUEST
        for item in resources.hidden.state_samples
    )
    assert any(
        item.state == ReferenceResourceState.CREW_REST for item in resources.hidden.state_samples
    )


def test_resource_loader_rejects_symlinked_parameter_file(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "parameters.yaml").symlink_to(ROOT / RESOURCE_PARAMETERS)
    with pytest.raises(ValueError, match="must not be a symlink"):
        load_reference_resource_parameters(root, Path("parameters.yaml"))
