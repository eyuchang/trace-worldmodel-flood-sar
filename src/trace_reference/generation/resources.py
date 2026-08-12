"""Generate nested resource inventories, crew truth, and lossy telemetry."""

from __future__ import annotations

import hashlib

from trace_jepa.support import canonical_json_bytes
from trace_reference.domain.resources import (
    ReferenceCrewTruth,
    ReferenceHiddenResourceScenario,
    ReferenceHiddenResourceTelemetryAudit,
    ReferencePublicResourceCatalog,
    ReferencePublicResourceDefinition,
    ReferencePublicResourceTelemetryScenario,
    ReferenceResourceArtifacts,
    ReferenceResourceParameters,
    ReferenceResourceState,
    ReferenceResourceStateSample,
    ReferenceResourceTelemetry,
    ReferenceResourceTelemetryAuditEntry,
    ReferenceResourceTruth,
)

from .randomness import keyed_digest, uniform_micros

_NAMESPACE = "reference-resources-v1"


def _identifier(prefix: str, *parts: object) -> str:
    digest = hashlib.sha256("|".join(str(item) for item in parts).encode()).hexdigest()
    return f"{prefix}-{digest[:16]}"


def _candidate_keys(parameters: ReferenceResourceParameters) -> tuple[tuple[str, int, bool], ...]:
    values: list[tuple[str, int, bool]] = []
    for holding in parameters.holdings:
        values.extend(
            (holding.holding_id, index, index < holding.baseline_count)
            for index in range(holding.maximum_count)
        )
    return tuple(values)


def _inclusion_thresholds(
    parameters: ReferenceResourceParameters,
) -> dict[tuple[str, int], int]:
    candidates = _candidate_keys(parameters)
    baseline = sorted(
        (item for item in candidates if item[2]),
        key=lambda item: keyed_digest(0, _NAMESPACE, "baseline-rank", item[0], item[1]),
    )
    surge = sorted(
        (item for item in candidates if not item[2]),
        key=lambda item: keyed_digest(0, _NAMESPACE, "surge-rank", item[0], item[1]),
    )
    thresholds: dict[tuple[str, int], int] = {}
    for rank, (holding_id, index, _) in enumerate(baseline):
        denominator = max(1, len(baseline) - 1)
        thresholds[(holding_id, index)] = 250_000 + round(rank * 750_000 / denominator)
    for rank, (holding_id, index, _) in enumerate(surge, start=1):
        thresholds[(holding_id, index)] = 1_000_000 + round(rank * 1_000_000 / len(surge))
    return thresholds


def _scaled_seconds(value: int, mu_micros: int) -> int:
    return round(value * mu_micros / 1_000_000)


def _crew_on_duty(crew: ReferenceCrewTruth, at_s: int) -> tuple[bool, int]:
    cycle = crew.duty_limit_s + crew.rest_requirement_s
    elapsed = (at_s + 172_800 + crew.cycle_offset_s) % cycle
    on_duty = elapsed < crew.duty_limit_s
    fatigue = (
        min(1_000_000, round(elapsed * 1_000_000 / crew.duty_limit_s))
        if on_duty
        else max(0, round((cycle - elapsed) * 250_000 / crew.rest_requirement_s))
    )
    return on_duty, max(fatigue, crew.initial_fatigue_micros if at_s == -172_800 else 0)


def _state_sample(
    resource: ReferenceResourceTruth,
    crew: ReferenceCrewTruth,
    *,
    seed: int,
    at_s: int,
) -> ReferenceResourceStateSample:
    on_duty, fatigue = _crew_on_duty(crew, at_s)
    if resource.initial_outage_until_s is not None and at_s < resource.initial_outage_until_s:
        state = ReferenceResourceState.INITIAL_OUTAGE
    elif not on_duty:
        state = ReferenceResourceState.CREW_REST
    elif resource.tier.value != "T0-local":
        state = ReferenceResourceState.AWAITING_REQUEST
    else:
        state = ReferenceResourceState.AVAILABLE_STAGED
    depletion = uniform_micros(seed, _NAMESPACE, resource.resource_id, at_s, "fuel") % 300_001
    return ReferenceResourceStateSample(
        resource_id=resource.resource_id,
        at_s=at_s,
        state=state,
        crew_on_duty=on_duty,
        crew_fatigue_micros=fatigue,
        fuel_or_charge_micros=1_000_000 - depletion,
    )


def _telemetry_bands(sample: ReferenceResourceStateSample) -> tuple[str, str]:
    fatigue = (
        "low"
        if sample.crew_fatigue_micros < 350_000
        else "moderate"
        if sample.crew_fatigue_micros < 700_000
        else "high"
    )
    fuel = (
        "full"
        if sample.fuel_or_charge_micros >= 800_000
        else "usable"
        if sample.fuel_or_charge_micros >= 300_000
        else "low"
    )
    return fatigue, fuel


def _telemetry(
    sample: ReferenceResourceStateSample,
    resource: ReferenceResourceTruth,
    *,
    seed: int,
    iota_micros: int,
) -> tuple[ReferenceResourceTelemetry | None, ReferenceResourceTelemetryAuditEntry]:
    key = (resource.resource_id, sample.at_s)
    audit_id = _identifier("RA", seed, resource.resource_id, sample.at_s)
    report_probability = round(850_000 * iota_micros / 700_000)
    if uniform_micros(seed, _NAMESPACE, *key, "telemetry-report") >= min(
        990_000, report_probability
    ):
        return None, ReferenceResourceTelemetryAuditEntry(
            audit_id=audit_id,
            resource_id=resource.resource_id,
            observed_at_s=sample.at_s,
            disposition="omitted-by-observation-channel",
            public_telemetry_id=None,
            contradiction_injected=False,
        )
    error_probability = min(700_000, round(100_000 * 700_000 / iota_micros))
    contradiction = uniform_micros(seed, _NAMESPACE, *key, "telemetry-error") < error_probability
    state = sample.state
    if contradiction:
        state = (
            ReferenceResourceState.AVAILABLE_STAGED
            if state != ReferenceResourceState.AVAILABLE_STAGED
            else ReferenceResourceState.INITIAL_OUTAGE
        )
    fatigue, fuel = _telemetry_bands(sample)
    if uniform_micros(seed, _NAMESPACE, *key, "telemetry-fatigue-missing") >= iota_micros:
        fatigue = "unknown"
    if uniform_micros(seed, _NAMESPACE, *key, "telemetry-fuel-missing") >= iota_micros:
        fuel = "unknown"
    delay_limit = max(60, round(3_600 * 700_000 / iota_micros))
    delay = uniform_micros(seed, _NAMESPACE, *key, "telemetry-delay") % (delay_limit + 1)
    telemetry_id = _identifier("RT", seed, resource.resource_id, sample.at_s)
    telemetry = ReferenceResourceTelemetry(
        telemetry_id=telemetry_id,
        resource_id=resource.resource_id,
        observed_at_s=sample.at_s,
        delivered_at_s=sample.at_s + delay,
        owning_authority_id=resource.owning_authority_id,
        reported_state=state,
        reported_crew_fatigue_band=fatigue,
        reported_fuel_or_charge_band=fuel,
    )
    audit = ReferenceResourceTelemetryAuditEntry(
        audit_id=audit_id,
        resource_id=resource.resource_id,
        observed_at_s=sample.at_s,
        disposition="delivered",
        public_telemetry_id=telemetry_id,
        contradiction_injected=contradiction,
    )
    return telemetry, audit


def generate_reference_resources(
    parameters: ReferenceResourceParameters,
    *,
    seed: int,
    kappa: float = 1.0,
    mu: float = 1.0,
    iota: float = 0.7,
    delta: float = 0.2,
) -> ReferenceResourceArtifacts:
    """Generate inventory and telemetry while preserving the four axis boundaries."""

    if not 0.25 <= kappa <= 2.0:
        raise ValueError("Reference kappa is outside the registered range")
    if not 0.5 <= mu <= 2.0:
        raise ValueError("Reference mu is outside the registered range")
    if not 0.3 <= iota <= 1.0:
        raise ValueError("Reference iota is outside the registered range")
    if not 0.0 <= delta <= 1.0:
        raise ValueError("Reference delta is outside the registered range")
    kappa_micros = round(kappa * 1_000_000)
    mu_micros = round(mu * 1_000_000)
    iota_micros = round(iota * 1_000_000)
    delta_micros = round(delta * 1_000_000)
    profiles = {item.resource_class: item for item in parameters.class_profiles}
    holdings = {item.holding_id: item for item in parameters.holdings}
    thresholds = _inclusion_thresholds(parameters)
    resources: list[ReferenceResourceTruth] = []
    crews: list[ReferenceCrewTruth] = []
    for holding_id, index, _ in _candidate_keys(parameters):
        threshold = thresholds[(holding_id, index)]
        if threshold > kappa_micros:
            continue
        holding = holdings[holding_id]
        profile = profiles[holding.resource_class]
        resource_id = _identifier("RR", holding_id, index)
        crew_id = _identifier("CREW", holding_id, index)
        outage = uniform_micros(seed, _NAMESPACE, resource_id, "initial-outage") < delta_micros
        outage_until = (
            -172_800
            + 7_200
            + uniform_micros(seed, _NAMESPACE, resource_id, "outage-duration") % 36_001
            if outage
            else None
        )
        activation = _scaled_seconds(parameters.tier_activation_midpoint_s[holding.tier], mu_micros)
        resource = ReferenceResourceTruth(
            resource_id=resource_id,
            holding_id=holding_id,
            resource_class=holding.resource_class,
            capabilities=profile.capabilities,
            service_units=profile.service_units,
            physical_capacity=profile.physical_capacity,
            home_base_id=holding.base_id,
            staged_node_id=holding.staging_node_id,
            owning_authority_id=holding.owning_authority_id,
            tier=holding.tier,
            crew_id=crew_id,
            inclusion_threshold_micros=threshold,
            activation_delay_s=activation,
            nominal_travel_s=_scaled_seconds(holding.nominal_travel_s, mu_micros),
            staging_delay_s=_scaled_seconds(holding.nominal_staging_s, mu_micros),
            initial_outage_until_s=outage_until,
            turn_around_s=profile.turn_around_s,
            constraints=profile.constraints,
        )
        crew = ReferenceCrewTruth(
            crew_id=crew_id,
            resource_id=resource_id,
            synthetic_people=profile.crew_size,
            qualification=profile.resource_class,
            duty_limit_s=profile.duty_limit_s,
            rest_requirement_s=profile.rest_requirement_s,
            cycle_offset_s=uniform_micros(seed, _NAMESPACE, crew_id, "cycle-offset")
            % (profile.duty_limit_s + profile.rest_requirement_s),
            initial_fatigue_micros=min(
                1_000_000,
                round(
                    delta_micros
                    * uniform_micros(seed, _NAMESPACE, crew_id, "initial-fatigue")
                    / 1_000_000
                ),
            ),
        )
        resources.append(resource)
        crews.append(crew)
    resources.sort(key=lambda item: item.resource_id)
    crews.sort(key=lambda item: item.crew_id)
    resource_by_id = {item.resource_id: item for item in resources}
    crew_by_id = {item.crew_id: item for item in crews}
    sample_times = range(-172_800, 345_600, parameters.telemetry_interval_s)
    states = sorted(
        (
            _state_sample(
                resource,
                crew_by_id[resource.crew_id],
                seed=seed,
                at_s=at_s,
            )
            for at_s in sample_times
            for resource in resources
        ),
        key=lambda item: (item.at_s, item.resource_id),
    )
    telemetry: list[ReferenceResourceTelemetry] = []
    telemetry_audit: list[ReferenceResourceTelemetryAuditEntry] = []
    for sample in states:
        public_item, audit_item = _telemetry(
            sample,
            resource_by_id[sample.resource_id],
            seed=seed,
            iota_micros=iota_micros,
        )
        telemetry_audit.append(audit_item)
        if public_item is not None:
            telemetry.append(public_item)
    telemetry.sort(key=lambda item: (item.delivered_at_s, item.telemetry_id))
    telemetry_audit.sort(key=lambda item: item.audit_id)
    hidden_body = {
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "schema_version": "delta-reference-resource-truth-v1",
        "parameter_version": parameters.parameter_version,
        "scientific_status": parameters.scientific_status,
        "seed": seed,
        "kappa_micros": kappa_micros,
        "mu_micros": mu_micros,
        "delta_micros": delta_micros,
        "resources": [item.model_dump(mode="json") for item in resources],
        "crews": [item.model_dump(mode="json") for item in crews],
        "state_samples": [item.model_dump(mode="json") for item in states],
    }
    public_body = {
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "schema_version": "delta-reference-resource-telemetry-v1",
        "seed": seed,
        "iota_micros": iota_micros,
        "telemetry": [item.model_dump(mode="json") for item in telemetry],
    }
    catalog_body = {
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "schema_version": "delta-reference-resource-catalog-v1",
        "scientific_status": "synthetic-planning-roster-not-current-inventory-claim",
        "resources": [
            ReferencePublicResourceDefinition(
                resource_id=item.resource_id,
                resource_class=item.resource_class,
                capabilities=item.capabilities,
                service_units=item.service_units,
                physical_capacity=item.physical_capacity,
                home_base_id=item.home_base_id,
                staged_node_id=item.staged_node_id,
                owning_authority_id=item.owning_authority_id,
                tier=item.tier,
                nominal_travel_s=item.nominal_travel_s,
                constraints=item.constraints,
            ).model_dump(mode="json")
            for item in resources
        ],
    }
    telemetry_audit_body = {
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "schema_version": "delta-reference-resource-telemetry-audit-v1",
        "seed": seed,
        "iota_micros": iota_micros,
        "entries": [item.model_dump(mode="json") for item in telemetry_audit],
    }
    return ReferenceResourceArtifacts(
        hidden=ReferenceHiddenResourceScenario(
            **hidden_body,
            hidden_resource_digest=hashlib.sha256(canonical_json_bytes(hidden_body)).hexdigest(),
        ),
        public_catalog=ReferencePublicResourceCatalog(
            **catalog_body,
            resource_catalog_digest=hashlib.sha256(canonical_json_bytes(catalog_body)).hexdigest(),
        ),
        public=ReferencePublicResourceTelemetryScenario(
            **public_body,
            telemetry_digest=hashlib.sha256(canonical_json_bytes(public_body)).hexdigest(),
        ),
        hidden_telemetry_audit=ReferenceHiddenResourceTelemetryAudit(
            **telemetry_audit_body,
            hidden_telemetry_audit_digest=hashlib.sha256(
                canonical_json_bytes(telemetry_audit_body)
            ).hexdigest(),
        ),
    )
