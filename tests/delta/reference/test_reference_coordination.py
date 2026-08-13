from __future__ import annotations

from pathlib import Path

import pytest

import trace_reference.generation.coordination as coordination_module
from trace_reference import (
    load_reference_activation_parameters,
    load_reference_config,
    load_reference_exposure_parameters,
    load_reference_governance,
    load_reference_physical_parameters,
    load_reference_resource_parameters,
)
from trace_reference.domain.coordination import (
    ReferenceResourceActivationPhase,
    ReferenceResourceActivationSchedule,
)
from trace_reference.generation import (
    generate_reference_coordination,
    generate_reference_exposure,
    generate_reference_observations,
    generate_reference_physical_scenario,
    generate_reference_resources,
    generate_reference_truth,
)
from trace_reference.geography import load_reference_geography

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def coordination_inputs():
    config = load_reference_config(
        ROOT, Path("configs/scenarios/wf_dfld_01_reference_development.yaml")
    )
    governance = load_reference_governance(
        ROOT, Path("configs/governance/wf_dfld_01_reference_governance_v1.yaml")
    )
    physical_parameters = load_reference_physical_parameters(
        ROOT,
        Path("data/scenario/delta/reference/physical/reference_physical_parameters_v1.yaml"),
    )
    exposure_parameters = load_reference_exposure_parameters(
        ROOT,
        Path("data/scenario/delta/reference/exposure/reference_exposure_parameters_v1.yaml"),
    )
    resource_parameters = load_reference_resource_parameters(
        ROOT,
        Path("data/scenario/delta/reference/resources/reference_resource_parameters_v1.yaml"),
    )
    activation_parameters = load_reference_activation_parameters(
        ROOT,
        Path("data/scenario/delta/reference/resources/reference_activation_parameters_v1.yaml"),
    )
    geography = load_reference_geography(
        geography_root=ROOT / "data/scenario/delta/reference/geography"
    )
    physical = generate_reference_physical_scenario(physical_parameters)
    exposure = generate_reference_exposure(exposure_parameters, geography, seed=20260812)
    truth = generate_reference_truth(physical, exposure, seed=20260812)
    observations = generate_reference_observations(truth, exposure, seed=20260812)
    resources = generate_reference_resources(
        resource_parameters,
        seed=20260812,
        kappa=config.axes.kappa,
        mu=config.axes.mu,
        iota=config.axes.iota,
        delta=config.axes.delta,
    )
    return governance, observations, resources, activation_parameters


def test_coordination_is_deterministic_and_uses_public_inputs_only(
    coordination_inputs,
) -> None:
    governance, observations, resources, activation_parameters = coordination_inputs
    first = generate_reference_coordination(
        observations.delivery,
        resources,
        governance,
        activation_parameters,
        seed=20260812,
    )
    second = generate_reference_coordination(
        observations.delivery,
        resources,
        governance,
        activation_parameters,
        seed=20260812,
    )
    assert first.model_dump_json() == second.model_dump_json()
    public = first.public.model_dump_json()
    assert "truth_incident" not in public
    assert "truth_person" not in public
    assert "hidden" not in public
    activation_json = first.activations.model_dump_json()
    assert "truth_incident" not in activation_json
    assert "truth_person" not in activation_json
    assert governance.scientific_status == "design-draft-not-legal-command-model"


def test_activation_schedule_has_complete_ordered_role_histories(
    coordination_inputs,
) -> None:
    governance, observations, resources, activation_parameters = coordination_inputs
    coordinated = generate_reference_coordination(
        observations.delivery,
        resources,
        governance,
        activation_parameters,
        seed=20260812,
        phi=4,
    )
    assert len(coordinated.activations.events) == len(resources.hidden.resources) * 4 * 6
    assert (
        coordinated.activations.resource_catalog_digest
        == resources.public_catalog.resource_catalog_digest
    )
    grouped = {}
    for event in coordinated.activations.events:
        grouped.setdefault((event.resource_id, event.recipient_authority_id), []).append(event)
    expected_phases = tuple(ReferenceResourceActivationPhase)
    for values in grouped.values():
        ordered = tuple(sorted(values, key=lambda item: expected_phases.index(item.phase)))
        assert tuple(item.phase for item in ordered) == expected_phases
        assert tuple(item.delivered_at_s for item in ordered) == tuple(
            sorted(item.delivered_at_s for item in ordered)
        )
    local = next(item for item in resources.hidden.resources if item.tier.value == "T0-local")
    local_requests = tuple(
        item
        for item in coordinated.activations.events
        if item.resource_id == local.resource_id
        and item.phase == ReferenceResourceActivationPhase.REQUESTED
    )
    assert {item.observed_at_s for item in local_requests} == {-172_800}


def test_activation_schedule_digest_fails_closed(coordination_inputs) -> None:
    governance, observations, resources, activation_parameters = coordination_inputs
    coordinated = generate_reference_coordination(
        observations.delivery,
        resources,
        governance,
        activation_parameters,
        seed=20260812,
        phi=4,
    )
    payload = coordinated.activations.model_dump(mode="json")
    payload["schedule_digest"] = "0" * 64
    with pytest.raises(ValueError, match="schedule digest"):
        ReferenceResourceActivationSchedule.model_validate(payload)


def test_activation_parameter_loader_rejects_symlink(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    source = ROOT / (
        "data/scenario/delta/reference/resources/reference_activation_parameters_v1.yaml"
    )
    (root / "parameters.yaml").symlink_to(source)

    with pytest.raises(ValueError, match="must not be a symlink"):
        load_reference_activation_parameters(root, Path("parameters.yaml"))


def test_phi_one_collapses_delivery_to_one_immediate_logical_authority(
    coordination_inputs,
) -> None:
    governance, observations, resources, activation_parameters = coordination_inputs
    coordinated = generate_reference_coordination(
        observations.delivery,
        resources,
        governance,
        activation_parameters,
        seed=20260812,
        phi=1,
    )
    source_count = len(observations.delivery.envelopes) + len(resources.public.telemetry)
    assert len(coordinated.public.deliveries) == source_count
    assert all(
        item.recipient_authority_id == "AUTH-01"
        and item.delivered_at_s == item.source_available_at_s
        for item in coordinated.public.deliveries
    )
    assert all(item.disposition == "delivered" for item in coordinated.hidden.attempts)
    assert {item.recipient_authority_id for item in coordinated.activations.events} == {"AUTH-01"}


def test_phi_four_preserves_local_delivery_and_models_cross_role_loss(
    coordination_inputs,
) -> None:
    governance, observations, resources, activation_parameters = coordination_inputs
    coordinated = generate_reference_coordination(
        observations.delivery,
        resources,
        governance,
        activation_parameters,
        seed=20260812,
        phi=4,
    )
    source_count = len(observations.delivery.envelopes) + len(resources.public.telemetry)
    assert len(coordinated.hidden.attempts) == source_count * 4
    assert any(item.disposition == "lost-before-delivery" for item in coordinated.hidden.attempts)
    assert any(
        item.delivered_at_s > item.source_available_at_s for item in coordinated.public.deliveries
    )
    by_source = {
        (item.evidence_kind, item.evidence_id): item.source_authority_id
        for item in coordinated.public.deliveries
    }
    delivered = {
        (item.evidence_kind, item.evidence_id, item.recipient_authority_id)
        for item in coordinated.public.deliveries
    }
    assert all(
        (*source, source_authority) in delivered for source, source_authority in by_source.items()
    )
    public_ids = {item.delivery_id for item in coordinated.public.deliveries}
    assert {
        item.delivered_public_id
        for item in coordinated.hidden.attempts
        if item.delivered_public_id is not None
    } == public_ids


def test_higher_phi_adds_queue_partitions_without_new_authority_claims(
    coordination_inputs,
) -> None:
    governance, observations, resources, activation_parameters = coordination_inputs
    coordinated = generate_reference_coordination(
        observations.delivery,
        resources,
        governance,
        activation_parameters,
        seed=20260812,
        phi=9,
    )
    assert {item.recipient_authority_id for item in coordinated.public.deliveries} <= {
        "AUTH-01",
        "AUTH-02",
        "AUTH-03",
        "AUTH-04",
    }
    assert any(
        item.recipient_partition_id.endswith("P02") for item in coordinated.public.deliveries
    )


def test_phi_preserves_underlying_draws_across_partition_changes(
    coordination_inputs,
) -> None:
    governance, observations, resources, activation_parameters = coordination_inputs
    baseline = generate_reference_coordination(
        observations.delivery,
        resources,
        governance,
        activation_parameters,
        seed=20260812,
        phi=4,
    )
    variant = generate_reference_coordination(
        observations.delivery,
        resources,
        governance,
        activation_parameters,
        seed=20260812,
        phi=5,
    )
    baseline_attempts = {
        (item.evidence_id, item.recipient_authority_id): item for item in baseline.hidden.attempts
    }
    variant_attempts = {
        (item.evidence_id, item.recipient_authority_id): item for item in variant.hidden.attempts
    }
    assert baseline_attempts.keys() == variant_attempts.keys()
    assert any(
        baseline_attempts[key].recipient_partition_id
        != variant_attempts[key].recipient_partition_id
        for key in baseline_attempts
    )
    assert all(
        (
            baseline_attempts[key].latency_draw_micros,
            baseline_attempts[key].loss_draw_micros,
        )
        == (
            variant_attempts[key].latency_draw_micros,
            variant_attempts[key].loss_draw_micros,
        )
        for key in baseline_attempts
    )


def test_phi_preserves_every_coordination_and_activation_draw_key(
    coordination_inputs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    governance, observations, resources, activation_parameters = coordination_inputs
    original = coordination_module.uniform_micros
    observed: list[tuple[object, ...]] = []

    def record(seed: int, namespace: str, *parts: object) -> int:
        observed.append((seed, namespace, *parts))
        return original(seed, namespace, *parts)

    monkeypatch.setattr(coordination_module, "uniform_micros", record)
    generate_reference_coordination(
        observations.delivery,
        resources,
        governance,
        activation_parameters,
        seed=20260812,
        phi=4,
    )
    baseline_draw_keys = tuple(observed)
    observed.clear()
    generate_reference_coordination(
        observations.delivery,
        resources,
        governance,
        activation_parameters,
        seed=20260812,
        phi=5,
    )

    assert baseline_draw_keys == tuple(observed)
    assert baseline_draw_keys
    assert all("P0" not in str(part) for key in baseline_draw_keys for part in key)
