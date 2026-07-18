"""WP-E acceptance tests for diffusion and common-random-number isolation."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import statistics
from pathlib import Path

import pytest
from pydantic import ValidationError

from trace_jepa.workbench.engine import DynamicRun
from trace_jepa.workbench.models import (
    EventType,
    S2Parameters,
    ScenarioLevel,
    SimulationEvent,
)
from trace_jepa.workbench.randomness import (
    RNG_SCHEMA_VERSION,
    SEED_NAMESPACE,
    keyed_standard_normal,
    keyed_uniform,
)
from trace_jepa.workbench.reducer import apply_event
from trace_jepa.workbench.scenario import load_initial_state


SCENARIO = Path("configs/scenarios/riverside_flood_dynamic_v2.yaml")
ORIGIN_MAIN = "11c6661a9e1ab73318ff691e262a29a6c77a0658"
BASELINE_EVENT_HASHES = {
    1: "2669a328ded54767716c7dca634a6ca255dc9b9eb92f368d4c378dda5bcc07d2",
    2: "27c128a543257c4509fae3a7a589b97585487cc737f3cbfc55e6983fd9bc6dd4",
    3: "c5b5f2a6278486139b5bc8c23cee39633f09dbb00f0059d220a95fb2f5745043",
    4: "e714dd76dffe815e5f6a9adae7181cd57056177a9c3d4488db695614ff06e4de",
    5: "60c8353d0d1e8c22fe9ca129c7887842ced37624e0798a35d71cabc0acf469fc",
}
BASELINE_TRAJECTORY_HASH = (
    "e708ed89561017d2a72bbaafcb8a7bc0d12c5c0e6e48e255805d8fd92121d655"
)


def _json_hash(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _event_projection(run: DynamicRun) -> list[dict]:
    projected = []
    for event in run.event_store.all():
        row = event.model_dump(mode="json")
        row.pop("event_id")
        row.pop("created_at")
        projected.append(row)
    return projected


def _truth_row(run: DynamicRun, tick_index: int) -> dict:
    return {
        "tick_index": tick_index,
        "simulation_time": run.state.truth.simulation_time.hex(),
        "global_water_level": run.state.truth.global_water_level.hex(),
        "routes": [
            {
                "route_id": route_id,
                "water_depth": route.water_depth.hex(),
                "open": route.open,
                "edge_open": route.edge_open,
            }
            for route_id, route in sorted(run.state.truth.routes.items())
        ],
    }


async def _drive(
    tmp_path: Path,
    *,
    seed: int,
    noise: float,
    ticks: int = 12,
    dt: float = 1.0,
    extra_observations: bool = False,
) -> tuple[DynamicRun, list[dict]]:
    run_id = (
        f"wp-e-baseline-seed-{seed}"
        if noise == 0.0 and not extra_observations and dt == 1.0 and ticks == 12
        else f"wp-e-seed-{seed}-noise-{noise}-{extra_observations}"
    )
    run = DynamicRun(
        run_id=run_id,
        scenario_path=SCENARIO,
        artifact_root=tmp_path,
    )
    run.state.config.auto_plan = False
    run.emit(
        EventType.SET_S1_PARAMETERS,
        source="wp_e_oracle",
        scenario_level=ScenarioLevel.S1,
        payload={"seed": seed},
    )
    s2_payload = {
        "rain_intensity": 0.6,
        "upstream_inflow": 0.5,
        "water_rise_rate": 0.001,
    }
    if noise != 0.0:
        s2_payload["forcing_noise_std"] = noise
    run.emit(
        EventType.SET_S2_PARAMETERS,
        source="wp_e_oracle",
        scenario_level=ScenarioLevel.S2,
        payload=s2_payload,
    )

    trajectory = []
    for tick_index in range(ticks):
        if extra_observations and tick_index % 3 == 0:
            run.emit(
                EventType.OBSERVATION,
                source="synthetic_independent_schedule",
                scenario_level=ScenarioLevel.S1,
                payload={
                    "kind": "route",
                    "route_id": "channel_e12",
                    "reported_status": "open",
                    "confidence": 0.9,
                    "source": "independent_schedule",
                    "observed_at": run.state.truth.simulation_time,
                },
            )
        await run.step(dt)
        trajectory.append(_truth_row(run, tick_index))
    return run, trajectory


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_noise_zero_matches_origin_main_oracle(tmp_path: Path, seed: int) -> None:
    """Canonical events and full depth paths match clean origin/main."""

    run, trajectory = asyncio.run(_drive(tmp_path, seed=seed, noise=0.0))
    assert _json_hash(_event_projection(run)) == BASELINE_EVENT_HASHES[seed]
    assert _json_hash(trajectory) == BASELINE_TRAJECTORY_HASH

    tick_payloads = [
        event.payload
        for event in run.event_store.all()
        if event.event_type == EventType.TICK
    ]
    assert tick_payloads == [{"dt": 1.0}] * 12


def test_positive_noise_is_reproducible_and_seed_distinct(tmp_path: Path) -> None:
    _, first = asyncio.run(_drive(tmp_path / "a", seed=7, noise=0.35, ticks=40))
    _, repeat = asyncio.run(_drive(tmp_path / "b", seed=7, noise=0.35, ticks=40))
    _, other = asyncio.run(_drive(tmp_path / "c", seed=8, noise=0.35, ticks=40))
    assert first == repeat
    assert first != other


def test_environment_path_is_invariant_to_observation_schedule(tmp_path: Path) -> None:
    _, no_observations = asyncio.run(
        _drive(tmp_path / "none", seed=7, noise=0.35, ticks=40)
    )
    _, extra_observations = asyncio.run(
        _drive(
            tmp_path / "observed",
            seed=7,
            noise=0.35,
            ticks=40,
            extra_observations=True,
        )
    )
    assert no_observations == extra_observations


def _state_for_increment(seed: int, noise: float):
    state = load_initial_state(f"increment-{seed}", SCENARIO)
    state.config.s1.seed = seed
    state.config.s2.rain_intensity = 0.6
    state.config.s2.upstream_inflow = 0.5
    state.config.s2.water_rise_rate = 0.001
    state.config.s2.forcing_noise_std = noise
    return state


def _apply_tick(state, dt: float) -> float:
    tick_index = state.truth.environment_tick_index
    innovation = keyed_standard_normal(
        "env.forcing", SEED_NAMESPACE, state.config.s1.seed, tick_index
    )
    event = SimulationEvent(
        run_id=state.run_id,
        sequence=tick_index + 1,
        simulation_time=state.truth.simulation_time,
        source="wp_e_test",
        event_type=EventType.TICK,
        payload={
            "dt": dt,
            "forcing_noise_z": innovation,
            "forcing_rng_schema": RNG_SCHEMA_VERSION,
            "forcing_seed_namespace": SEED_NAMESPACE,
            "forcing_tick_index": tick_index,
            "forcing_spatial_model": "common_forcing_v1",
        },
    )
    apply_event(state, event)
    return innovation


def test_euler_maruyama_increment_and_common_forcing_are_exact() -> None:
    state = _state_for_increment(seed=17, noise=0.35)
    dt = 0.25
    global_before = state.truth.global_water_level
    route_before = {
        route_id: route.water_depth for route_id, route in state.truth.routes.items()
    }
    innovation = _apply_tick(state, dt)

    s2 = state.config.s2
    forcing = 0.25 + 0.75 * s2.rain_intensity + 0.85 * s2.upstream_inflow
    base_noise = s2.water_rise_rate * s2.forcing_noise_std * math.sqrt(dt) * innovation
    assert state.truth.global_water_level == pytest.approx(
        global_before + dt * s2.water_rise_rate * forcing + base_noise,
        abs=1e-15,
    )
    for route_id, route in state.truth.routes.items():
        expected = route_before[route_id] + route.susceptibility * (
            dt * s2.water_rise_rate * forcing + base_noise
        )
        assert route.water_depth == pytest.approx(expected, abs=1e-15)


@pytest.mark.parametrize("dt", [1.0, 0.5, 0.25])
def test_endpoint_residual_variance_is_tick_stable(dt: float) -> None:
    duration = 4.0
    residuals = []
    for seed in range(600):
        state = _state_for_increment(seed=seed, noise=0.35)
        route = state.truth.routes["north_channel"]
        initial = route.water_depth
        susceptibility = route.susceptibility
        steps = int(duration / dt)
        for _ in range(steps):
            _apply_tick(state, dt)
        forcing = (
            0.25
            + 0.75 * state.config.s2.rain_intensity
            + 0.85 * state.config.s2.upstream_inflow
        )
        drift = (
            duration
            * state.config.s2.water_rise_rate
            * forcing
            * susceptibility
        )
        residuals.append(route.water_depth - initial - drift)

    sigma = 0.001 * 0.35 * 1.3
    expected_variance = sigma**2 * duration
    assert statistics.mean(residuals) == pytest.approx(0.0, abs=8e-5)
    assert statistics.pvariance(residuals) == pytest.approx(
        expected_variance, rel=0.16
    )


def test_rng_keys_are_typed_unambiguous_and_domain_separated() -> None:
    assert keyed_uniform("test", 1) != keyed_uniform("test", "1")
    assert keyed_uniform("test", "a|b", "c") != keyed_uniform("test", "a", "b|c")
    key = (SEED_NAMESPACE, 7, "drone_survey", "channel_e12", 10, 10.0)
    assert keyed_uniform("obs.drone.delivery", *key) == keyed_uniform(
        "obs.drone.delivery", *key
    )
    assert keyed_uniform("obs.drone.delivery", *key) != keyed_uniform(
        "obs.drone.accuracy", *key
    )


def test_forcing_tick_payload_is_auditable(tmp_path: Path) -> None:
    run, _ = asyncio.run(_drive(tmp_path, seed=3, noise=0.35, ticks=2))
    ticks = [
        event.payload
        for event in run.event_store.all()
        if event.event_type == EventType.TICK
    ]
    assert [payload["forcing_tick_index"] for payload in ticks] == [0, 1]
    assert all(payload["forcing_rng_schema"] == RNG_SCHEMA_VERSION for payload in ticks)
    assert all(
        payload["forcing_spatial_model"] == "common_forcing_v1" for payload in ticks
    )


def test_invalid_noise_and_tick_inputs_are_rejected() -> None:
    with pytest.raises(ValidationError):
        S2Parameters(forcing_noise_std=-0.01)

    state = _state_for_increment(seed=1, noise=0.35)
    bad_event = SimulationEvent(
        run_id=state.run_id,
        sequence=1,
        simulation_time=0.0,
        source="wp_e_test",
        event_type=EventType.TICK,
        payload={"dt": 0.0, "forcing_noise_z": 0.0},
    )
    with pytest.raises(ValueError, match="strictly positive"):
        apply_event(state, bad_event)
