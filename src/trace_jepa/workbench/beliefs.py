from __future__ import annotations

import math

from trace_jepa.workbench.models import WorkbenchState


OBSERVED_DEPTH_TOLERANCE_M = 0.15


def declared_forcing(state: WorkbenchState) -> float:
    """Return the deterministic drift factor declared by the S2 model."""

    s2 = state.config.s2
    return 0.25 + 0.75 * s2.rain_intensity + 0.85 * s2.upstream_inflow


def project_controller_route_depth(
    state: WorkbenchState,
    route_id: str,
    at_time: float,
) -> float:
    """Project depth from controller-visible evidence and public model inputs.

    Route geometry and susceptibility are declared map/model parameters. The
    current truth depth is deliberately never read. Binary reports use an
    interval representative; exact gauge observations carry their measured
    depth and sampling time.
    """

    belief = state.controller.route_beliefs[route_id]
    route_model = state.truth.routes[route_id]
    threshold = state.config.s2.route_closure_depth
    if belief.water_depth is not None:
        base_depth = belief.water_depth
        base_time = (
            belief.depth_observed_at
            if belief.depth_observed_at is not None
            else belief.observed_at
        )
    elif belief.status == "open":
        base_depth = 0.5 * threshold
        base_time = belief.observed_at
    elif belief.status == "blocked":
        base_depth = threshold + 0.05
        base_time = belief.observed_at
    else:
        base_depth = 0.75 * threshold
        base_time = belief.observed_at
    elapsed = max(0.0, at_time - float(base_time or 0.0))
    drift = (
        state.config.s2.water_rise_rate
        * declared_forcing(state)
        * route_model.susceptibility
    )
    return max(0.0, base_depth + elapsed * drift)


def route_threshold_failure_probability(
    state: WorkbenchState,
    route_id: str,
    horizon_end: float,
) -> float:
    """Model-conditional probability that route depth exceeds its threshold.

    This is an explicit Gaussian approximation for the R-B controller belief,
    not the surrogate's whole-mission success probability and not the latent
    simulator truth. Reflection at zero is negligible near the upper closure
    boundary but prevents calling this the paper theorem's exact process.
    """

    belief = state.controller.route_beliefs[route_id]
    route_model = state.truth.routes[route_id]
    mean = project_controller_route_depth(state, route_id, horizon_end)
    threshold = state.config.s2.route_closure_depth
    last_evidence_time = (
        belief.depth_observed_at
        if belief.depth_observed_at is not None
        else belief.observed_at
    )
    elapsed = max(0.0, horizon_end - float(last_evidence_time or 0.0))
    sigma = (
        state.config.s2.water_rise_rate
        * state.config.s2.forcing_noise_std
        * route_model.susceptibility
    )
    standard_deviation = sigma * math.sqrt(elapsed)
    if standard_deviation <= 0.0:
        return 1.0 if mean >= threshold else 0.0
    z = (threshold - mean) / standard_deviation
    return 0.5 * math.erfc(z / math.sqrt(2.0))
