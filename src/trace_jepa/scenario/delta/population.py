from __future__ import annotations

import random
from datetime import timedelta

from trace_jepa.scenario.delta.geography_models import GeographyCatalog, LinearRing
from trace_jepa.scenario.delta.models import (
    CallLineage,
    CallLocation,
    CallQuality,
    CallRecord,
    CrossingState,
    DeltaScenarioConfig,
    GroundTruth,
    IncidentTruth,
    LeveeTruth,
    ObservationArtifact,
    PersonPosition,
    PersonTruth,
    PriorProfileArtifact,
    ReportedCall,
    ResourceArtifact,
    ResourceUnit,
    StructureState,
    StructureTruth,
    WeatherSample,
)
from trace_jepa.scenario.delta.randomness import sample_poisson

CALL_TYPE_WEIGHTS = (
    ("C-STR", 34),
    ("C-VEH", 8),
    ("C-LEV", 11),
    ("C-MED", 14),
    ("C-WEL", 20),
    ("C-MIS", 13),
)
INCIDENT_REQUIREMENTS = {
    "C-STR": ("water_rescue", 2_400),
    "C-VEH": ("road_rescue", 1_500),
    "C-LEV": ("levee_inspection", 1_200),
    "C-MED": ("medical_first_response", 1_200),
    "C-WEL": ("welfare_check", 1_200),
    "C-MIS": ("missing_person_search", 1_500),
}
LOCATION_METHODS = ("cell-sector", "landmark", "address-intersection", "gps-share")


def population_parameter_table(generator_version: str | None = None) -> dict[str, object]:
    if generator_version == "delta-small-generator-v8":
        from trace_jepa.scenario.delta.observations_v7 import (
            BASE_LOCATION_METHOD_MILLI,
            BASE_PRECISION_RANGES_M,
        )
        from trace_jepa.scenario.delta.observations_v8 import (
            BASE_REPORTING_BY_HOUR_V2,
            DESCRIPTOR_VOCABULARY_V1,
            FALSE_REPORT_HOUR_WEIGHTS_V1,
            channel_probabilities_v8,
        )
        from trace_jepa.scenario.delta.truth_v8 import TYPE_INTERCEPTS_V2

        return {
            "schema_version": "delta-truth-observation-resource-parameters-v7",
            "truth_schema_version": "delta-ground-truth-v5",
            "observation_schema_version": "delta-observations-v5",
            "coordination_schema_version": "delta-coordination-v1",
            "truth_coefficients_version": "delta-truth-intercepts-v2",
            "type_intercepts": TYPE_INTERCEPTS_V2,
            "incident_requirements": INCIDENT_REQUIREMENTS,
            "episode_thinning": "one-incident-per-continuous-eligibility-episode-v1",
            "observation_coefficients_version": "delta-observation-coefficients-v2",
            "reporting_probability_by_hour_at_iota_0_9": BASE_REPORTING_BY_HOUR_V2,
            "false_report_hour_weights_at_iota_0_9": FALSE_REPORT_HOUR_WEIGHTS_V1,
            "channel_probabilities_at_iota_0_9": channel_probabilities_v8(0.9),
            "descriptor_vocabulary": DESCRIPTOR_VOCABULARY_V1,
            "location_method_milli_at_iota_0_9": BASE_LOCATION_METHOD_MILLI,
            "location_precision_ranges_m_at_iota_0_9": BASE_PRECISION_RANGES_M,
            "location_error_scaling": "min(3, 0.9 / iota)",
            "cohort_claim_limit": "synthetic-teaching-cohort-not-demographically-representative",
            "resource_profile": "kappa-0.5-local-plus-automatic-aid-v1",
            "physical_resource_concurrency": 1,
        }
    if generator_version == "delta-small-generator-v7":
        from trace_jepa.scenario.delta.observations_v7 import (
            BASE_LOCATION_METHOD_MILLI,
            BASE_PRECISION_RANGES_M,
            BASE_REPORTING_BY_HOUR_V1,
            channel_probabilities_v7,
        )
        from trace_jepa.scenario.delta.truth_v7 import (
            INCIDENT_REQUIREMENTS_V7,
            TYPE_INTERCEPTS_V1,
        )

        return {
            "schema_version": "delta-truth-observation-resource-parameters-v6",
            "truth_schema_version": "delta-ground-truth-v4",
            "observation_schema_version": "delta-observations-v4",
            "coordination_schema_version": "delta-coordination-v1",
            "truth_coefficients_version": "delta-truth-intercepts-v1",
            "type_intercepts": TYPE_INTERCEPTS_V1,
            "incident_requirements": INCIDENT_REQUIREMENTS_V7,
            "observation_coefficients_version": "delta-observation-coefficients-v1",
            "reporting_probability_by_hour_at_iota_0_9": BASE_REPORTING_BY_HOUR_V1,
            "channel_probabilities_at_iota_0_9": channel_probabilities_v7(0.9),
            "location_method_milli_at_iota_0_9": BASE_LOCATION_METHOD_MILLI,
            "location_precision_ranges_m_at_iota_0_9": BASE_PRECISION_RANGES_M,
            "location_error_scaling": "min(3, 0.9 / iota)",
            "cohort_claim_limit": "synthetic-teaching-cohort-not-demographically-representative",
            "resource_profile": "kappa-0.5-local-plus-automatic-aid-v1",
            "physical_resource_concurrency": 1,
        }
    return {
        "schema_version": "delta-truth-observation-resource-parameters-v5",
        "call_type_weights": CALL_TYPE_WEIGHTS,
        "incident_requirements": INCIDENT_REQUIREMENTS,
        "location_methods": LOCATION_METHODS,
        "channel_probability_coefficients": {
            "nonreporting_per_information_loss": 1.0 / 3.0,
            "duplicate_per_information_loss": 1.164,
            "multi_channel_per_information_loss": 0.741,
            "revision_per_information_loss": 2.116,
            "callback_failure_per_information_loss": 1.033,
            "drop_per_information_loss": 0.40,
            "false_report_mean_per_information_loss": 46.667,
        },
        "hourly_observation_calibration": {
            "version": "hazard-conditioned-hourly-expectation-v1",
            "definition": (
                "target observed intensity minus uniform expected false reports, divided "
                "by the physical-hazard-derived latent incident rate; reporting and "
                "zero/one/many channel probabilities are then solved analytically"
            ),
            "calibration_information_quality": 0.9,
            "truth_generation_uses_target_call_profile": False,
        },
        "cohort_claim_limit": "synthetic-teaching-cohort-not-demographically-representative",
        "resource_profiles": {
            "kappa-0.5-local-plus-automatic-aid-v1": {
                "local_inventory": ["one-type-i-engine", "one-rescue-boat"],
                "automatic_aid_inventory": ["one-type-i-engine", "one-zodiac-rescue-boat"],
                "automatic_aid_arrival_s_at_mu_1": 5_400,
                "availability_semantics": "preauthorized-fixed-teaching-schedule",
                "service_unit_definition": "normalized-analytical-capability-load-unit",
                "physical_resource_concurrency": 1,
            }
        },
    }


def _weighted_call_type(rng: random.Random) -> str:
    draw = rng.randrange(sum(weight for _, weight in CALL_TYPE_WEIGHTS))
    running = 0
    for call_type, weight in CALL_TYPE_WEIGHTS:
        running += weight
        if draw < running:
            return call_type
    raise RuntimeError("call taxonomy weights did not cover the random draw")


def _point_inside_ring(easting_mm: int, northing_mm: int, ring: LinearRing) -> bool:
    inside = False
    points = ring.points
    previous = points[-1]
    for current in points:
        crosses = (current.northing_mm > northing_mm) != (previous.northing_mm > northing_mm)
        if crosses:
            intersection = current.easting_mm + (
                (northing_mm - current.northing_mm)
                * (previous.easting_mm - current.easting_mm)
                // (previous.northing_mm - current.northing_mm)
            )
            if easting_mm < intersection:
                inside = not inside
        previous = current
    return inside


def _sample_points(
    ring: LinearRing,
    count: int,
    rng: random.Random,
    *,
    minimum_separation_m: int,
    required_containment_rings: list[LinearRing] | None = None,
) -> list[tuple[int, int]]:
    eastings = [point.easting_mm for point in ring.points]
    northings = [point.northing_mm for point in ring.points]
    separation_squared = (minimum_separation_m * 1000) ** 2
    result: list[tuple[int, int]] = []
    for _attempt in range(50_000):
        candidate = (
            rng.randint(min(eastings), max(eastings)),
            rng.randint(min(northings), max(northings)),
        )
        if not _point_inside_ring(*candidate, ring):
            continue
        if required_containment_rings and not any(
            _point_inside_ring(*candidate, required_ring)
            for required_ring in required_containment_rings
        ):
            continue
        if any(
            (candidate[0] - point[0]) ** 2 + (candidate[1] - point[1]) ** 2 < separation_squared
            for point in result
        ):
            continue
        result.append(candidate)
        if len(result) == count:
            return result
    raise RuntimeError("could not place the synthetic structures within the frozen polygon")


def _structures(geography: GeographyCatalog, rng: random.Random) -> list[StructureTruth]:
    community = next(item for item in geography.communities if item.community_id == "TWN-01")
    andrus = next(item for item in geography.islands if item.island_id == "ISL-01")
    brannan = next(item for item in geography.islands if item.island_id == "ISL-02")
    andrus_points = _sample_points(
        community.geometry.polygons[0],
        12,
        rng,
        minimum_separation_m=55,
        required_containment_rings=andrus.geometry.polygons,
    )
    brannan_points = _sample_points(brannan.geometry.polygons[0], 3, rng, minimum_separation_m=200)
    return [
        StructureTruth(
            structure_id=f"STR-{index + 1:03d}",
            community_id="TWN-01" if index < 12 else "OUTSIDE-TWN-01",
            island_id="ISL-01" if index < 12 else "ISL-02",
            easting_mm=easting_mm,
            northing_mm=northing_mm,
            placement_profile="seeded-within-government-footprint-v1",
        )
        for index, (easting_mm, northing_mm) in enumerate([*andrus_points, *brannan_points])
    ]


def _hour_hazard_weights(
    weather: list[WeatherSample], crossing_states: list[CrossingState]
) -> list[float]:
    weights: list[float] = []
    for hour in range(6):
        hour_weather = [
            sample
            for sample in weather
            if hour * 3600 <= sample.simulation_time_s < (hour + 1) * 3600
        ]
        hour_crossings = [
            sample
            for sample in crossing_states
            if hour * 3600 <= sample.simulation_time_s < (hour + 1) * 3600
        ]
        rain = sum(item.rain_milli_inches_per_hour for item in hour_weather) / len(hour_weather)
        wind = sum(item.wind_milli_knots for item in hour_weather) / len(hour_weather)
        route_friction = sum(item.travel_time_s for item in hour_crossings) / len(hour_crossings)
        weights.append(0.25 + rain / 140.0 + wind / 24_000.0 + route_friction / 5_000.0)
    return weights


def _latent_hour_rates(
    config: DeltaScenarioConfig,
    weather: list[WeatherSample],
    crossing_states: list[CrossingState],
) -> list[float]:
    hazard_weights = _hour_hazard_weights(weather, crossing_states)
    normalized = sum(hazard_weights)
    severity_multiplier = (config.axes.sigma / 0.3) ** 0.8
    exposure_multiplier = 1.12 if config.axes.exposure_profile != "isleton_small_v1" else 1.0
    return [
        config.call_process.latent_expected_incidents
        * severity_multiplier
        * exposure_multiplier
        * weight
        / normalized
        for weight in hazard_weights
    ]


def generate_truth(
    config: DeltaScenarioConfig,
    geography: GeographyCatalog,
    weather: list[WeatherSample],
    crossing_states: list[CrossingState],
    rng: random.Random,
) -> GroundTruth:
    structures = _structures(geography, rng)
    high_vulnerability = config.axes.exposure_profile != "isleton_small_v1"
    andrus_people = 48 if high_vulnerability else 52
    languages = ("en", "en", "en", "en", "es", "tl")
    people: list[PersonTruth] = []
    for index in range(config.extent.roster_size):
        island_structures = structures[:12] if index < andrus_people else structures[12:]
        home = island_structures[index % len(island_structures)]
        mobility_divisor = 7 if high_vulnerability else 11
        medical_divisor = 13 if high_vulnerability else 17
        people.append(
            PersonTruth(
                person_id=f"PER-{index + 1:03d}",
                home_structure_id=home.structure_id,
                mobility="limited" if index % mobility_divisor == 0 else "ambulatory",
                medical_dependency="oxygen" if index % medical_divisor == 0 else "none",
                preferred_language=languages[index % len(languages)],
            )
        )

    positions: list[PersonPosition] = []
    for index, person in enumerate(people):
        positions.append(
            PersonPosition(
                person_id=person.person_id,
                simulation_time_s=0,
                structure_id=person.home_structure_id,
                state="at_home",
            )
        )
        if index % 5 == 0:
            positions.append(
                PersonPosition(
                    person_id=person.person_id,
                    simulation_time_s=10_800,
                    structure_id=structures[(index + 3) % len(structures)].structure_id,
                    state="visiting",
                )
            )
            positions.append(
                PersonPosition(
                    person_id=person.person_id,
                    simulation_time_s=18_000,
                    structure_id=person.home_structure_id,
                    state="returned_home",
                )
            )

    structure_states: list[StructureState] = []
    weather_by_time = {sample.simulation_time_s: sample for sample in weather}
    for structure in structures:
        vulnerability_offset = int(structure.structure_id[-3:]) % 5
        for simulation_time_s in range(0, config.timeline.duration_s + 1, config.timeline.tick_s):
            rain = weather_by_time[simulation_time_s].rain_milli_inches_per_hour
            impaired = rain + vulnerability_offset * 20 >= 190
            structure_states.append(
                StructureState(
                    structure_id=structure.structure_id,
                    simulation_time_s=simulation_time_s,
                    flood_state="shallow_ponding" if impaired else "dry",
                    access_state="impaired" if impaired else "open",
                )
            )

    incident_rates = _latent_hour_rates(config, weather, crossing_states)
    incidents: list[IncidentTruth] = []
    for hour, rate in enumerate(incident_rates):
        for _ in range(sample_poisson(rng, rate)):
            incident_index = len(incidents)
            structure = structures[rng.randrange(len(structures))]
            occupants = [
                person.person_id
                for person in people
                if person.home_structure_id == structure.structure_id
            ]
            selected_count = min(len(occupants), 1 + rng.randrange(max(len(occupants), 1)))
            incident_type = _weighted_call_type(rng)
            capability, service_duration_s = INCIDENT_REQUIREMENTS[incident_type]
            complexity_milli = round(rng.random() * 1000)
            incidents.append(
                IncidentTruth(
                    incident_id=f"INC-{incident_index + 1:04d}",
                    structure_id=structure.structure_id,
                    person_ids=occupants[:selected_count],
                    incident_type=incident_type,
                    required_capability=capability,
                    onset_s=hour * 3600 + rng.randrange(3600),
                    service_duration_s=service_duration_s,
                    service_units=1,
                    complexity_milli=complexity_milli,
                    causal_mechanism="weather-access-exposure-vulnerability-v1",
                )
            )

    levees = [
        LeveeTruth(
            segment_id=f"{district}-SMALL-01",
            island_id=island_id,
            district_id=district,
            simulation_time_s=simulation_time_s,
            condition="fair",
            seepage_state=(
                "minor_observation"
                if weather_by_time[simulation_time_s].rain_milli_inches_per_hour >= 200
                else "none"
            ),
            breach=False,
        )
        for district, island_id in (("RD-407", "ISL-01"), ("RD-2067", "ISL-02"))
        for simulation_time_s in range(0, config.timeline.duration_s + 1, config.timeline.tick_s)
    ]
    return GroundTruth(
        schema_version="delta-ground-truth-v3",
        cohort_label="synthetic-isleton-teaching-cohort-v2-not-demographic",
        structures=structures,
        structure_states=structure_states,
        people=people,
        person_positions=positions,
        levees=levees,
        incidents=sorted(incidents, key=lambda item: (item.onset_s, item.incident_id)),
    )


def _channel_probabilities(iota: float) -> dict[str, float]:
    degradation = max(0.0, 1.0 - iota)
    return {
        "nonreporting": min(0.35, degradation / 3.0),
        "duplicate": min(0.85, degradation * 1.164),
        "multi_channel": min(0.70, degradation * 0.741),
        "revision": min(0.80, degradation * 2.116),
        "callback_failure": min(0.80, degradation * 1.033),
        "drop": min(0.50, degradation * 0.40),
        "false_report_mean": 46.667 * degradation,
    }


def _allocate_extra_report_probabilities(
    desired_retained_sum: float,
    base: dict[str, float],
    retention_by_key: dict[str, float],
) -> dict[str, float]:
    """Allocate retained same-hour expectation without probabilities above one."""
    keys = ("duplicate", "multi_channel", "revision")
    weights = {key: base[key] for key in keys}
    if sum(weights.values()) == 0.0:
        weights = {"duplicate": 1.164, "multi_channel": 0.741, "revision": 2.116}
    maximum = sum(retention_by_key[key] for key in keys)
    target = min(maximum, max(0.0, desired_retained_sum))
    lower = 0.0
    upper = 1.0

    def allocation(scale: float) -> dict[str, float]:
        return {key: min(1.0, scale * weights[key]) for key in keys}

    while (
        sum(probability * retention_by_key[key] for key, probability in allocation(upper).items())
        < target
    ):
        upper *= 2.0
    for _ in range(80):
        middle = (lower + upper) / 2.0
        retained = sum(
            probability * retention_by_key[key] for key, probability in allocation(middle).items()
        )
        if retained < target:
            lower = middle
        else:
            upper = middle
    return allocation((lower + upper) / 2.0)


def _hourly_channel_probabilities(
    config: DeltaScenarioConfig,
    weather: list[WeatherSample],
    crossing_states: list[CrossingState],
) -> list[dict[str, float]]:
    """Solve the lossy channel's per-hour expectations at the frozen profile.

    The configured call profile is used only here, after latent physical incidents
    have been defined. It therefore calibrates observation intensity without
    creating truth incidents from a call schedule.
    """
    base = _channel_probabilities(config.axes.iota)
    latent_rates = _latent_hour_rates(config, weather, crossing_states)
    expected_false_per_hour = base["false_report_mean"] / 6.0
    shift_probability = {
        "first_report": 209.5 / 3600.0,
        "duplicate": 509.5 / 3600.0,
        "multi_channel": 389.5 / 3600.0,
        "revision": 899.5 / 3600.0,
    }
    result: list[dict[str, float]] = []
    incoming_from_previous_hour = 0.0
    for hour, (target, latent_rate) in enumerate(
        zip(
            config.call_process.hourly_intensity,
            latent_rates,
            strict=True,
        )
    ):
        shifts = {key: (0.0 if hour == 5 else value) for key, value in shift_probability.items()}
        desired_current_hour_per_incident = (
            max(
                0.0,
                target - expected_false_per_hour - incoming_from_previous_hour,
            )
            / latent_rate
        )
        first_retention = 1.0 - shifts["first_report"]
        reporting_cap = 1.0 - base["nonreporting"]
        reporting_probability = min(
            reporting_cap,
            desired_current_hour_per_incident / first_retention,
        )
        desired_extra_retained = (
            max(
                0.0,
                desired_current_hour_per_incident / reporting_probability - first_retention,
            )
            if reporting_probability > 0.0
            else 0.0
        )
        retention_by_key = {
            key: 1.0 - shifts[key] for key in ("duplicate", "multi_channel", "revision")
        }
        extras = _allocate_extra_report_probabilities(
            desired_extra_retained,
            base,
            retention_by_key,
        )
        incoming_from_previous_hour = (
            latent_rate
            * reporting_probability
            * (shifts["first_report"] + sum(extras[key] * shifts[key] for key in extras))
        )
        result.append(
            {
                **base,
                "reporting": reporting_probability,
                **extras,
                "analytical_expected_reports_per_incident": (
                    reporting_probability * (1.0 + sum(extras.values()))
                ),
                "analytical_expected_spill_to_next_hour": incoming_from_previous_hour,
            }
        )
    return result


def generate_observations(
    config: DeltaScenarioConfig,
    truth: GroundTruth,
    weather: list[WeatherSample],
    crossing_states: list[CrossingState],
    rng: random.Random,
) -> ObservationArtifact:
    probabilities = _channel_probabilities(config.axes.iota)
    if config.generator_version in {
        "delta-small-generator-v4",
        "delta-small-generator-v5",
        "delta-small-generator-v6",
    }:
        hourly_probabilities = _hourly_channel_probabilities(
            config,
            weather,
            crossing_states,
        )
    else:
        # Historical reconstruction for preregistered v1/v2 studies. New runs
        # must use v4; retaining this branch prevents adverse results from being
        # silently recomputed under amended mechanics.
        hourly_probabilities = [
            {**probabilities, "reporting": 1.0 - probabilities["nonreporting"]} for _ in range(6)
        ]
    structure_by_id = {item.structure_id: item for item in truth.structures}
    people_by_id = {item.person_id: item for item in truth.people}
    calls: list[CallRecord] = []
    lineage: list[CallLineage] = []
    next_id = 1

    def append_call(
        *,
        incident: IncidentTruth | None,
        relationship: str,
        channel: str,
        received_s: int,
        callback_token: str,
        revision_of_call_id: str | None = None,
    ) -> str:
        nonlocal next_id
        call_id = f"C-20260115-{next_id:05d}"
        next_id += 1
        if incident is None:
            structure = truth.structures[rng.randrange(len(truth.structures))]
            call_type = "C-LEV"
            person_ids: list[str] = []
            reported_occupants = 0
            medical: list[str] = []
        else:
            structure = structure_by_id[incident.structure_id]
            call_type = incident.incident_type
            person_ids = incident.person_ids
            reported_occupants = len(person_ids)
            if relationship == "revision":
                reported_occupants += 1 if rng.random() < 0.5 else -1
                reported_occupants = max(0, reported_occupants)
            medical = sorted(
                {
                    people_by_id[person_id].medical_dependency
                    for person_id in person_ids
                    if people_by_id[person_id].medical_dependency != "none"
                }
            )
        precision_m = rng.randint(35, 430)
        offset_east_mm = rng.randint(-precision_m * 1000, precision_m * 1000)
        offset_north_mm = rng.randint(-precision_m * 1000, precision_m * 1000)
        bounded_received_s = min(config.timeline.duration_s - 1, max(0, received_s))
        calls.append(
            CallRecord(
                call_id=call_id,
                received_s=bounded_received_s,
                received_ts=config.timeline.epoch_utc + timedelta(seconds=bounded_received_s),
                psap="Sacramento County",
                channel=channel,
                callback_token=callback_token,
                on_scene=relationship not in {"welfare_check", "false_report"},
                third_party=relationship in {"welfare_check", "false_report"},
                language=(people_by_id[person_ids[0]].preferred_language if person_ids else "en"),
                location=CallLocation(
                    stated=f"synthetic landmark {int(structure.structure_id[-3:]):02d}",
                    easting_mm=structure.easting_mm + offset_east_mm,
                    northing_mm=structure.northing_mm + offset_north_mm,
                    precision_m=precision_m,
                    method=LOCATION_METHODS[rng.randrange(len(LOCATION_METHODS))],
                    confidence_milli=max(100, 1000 - precision_m),
                ),
                reported=ReportedCall(
                    call_type=call_type,
                    occupants=reported_occupants,
                    occupants_confidence="revised" if relationship == "revision" else "estimated",
                    medical=medical,
                    description_token=f"SYNTH-DESC-{rng.randrange(16):02d}",
                ),
                quality=CallQuality(
                    call_dropped=rng.random() < probabilities["drop"],
                    callback_failed=(rng.random() < probabilities["callback_failure"]),
                    revision_of_call_id=revision_of_call_id,
                ),
            )
        )
        lineage.append(
            CallLineage(
                call_id=call_id,
                truth_incident_id=incident.incident_id if incident else None,
                truth_person_ids=person_ids,
                relationship=relationship,
            )
        )
        return call_id

    for incident in truth.incidents:
        incident_probabilities = hourly_probabilities[min(5, incident.onset_s // 3600)]
        if rng.random() >= incident_probabilities["reporting"]:
            continue
        callback_token = f"SYNTH-CB-{rng.randrange(10**8):08d}"
        base_call = append_call(
            incident=incident,
            relationship=(
                "welfare_check" if incident.incident_type in {"C-WEL", "C-MIS"} else "first_report"
            ),
            channel="911",
            received_s=incident.onset_s + rng.randrange(420),
            callback_token=callback_token,
        )
        if rng.random() < incident_probabilities["duplicate"]:
            append_call(
                incident=incident,
                relationship="duplicate",
                channel="911",
                received_s=incident.onset_s + rng.randrange(120, 900),
                callback_token=callback_token,
            )
        if rng.random() < incident_probabilities["multi_channel"]:
            append_call(
                incident=incident,
                relationship="multi_channel",
                channel="text-to-911",
                received_s=incident.onset_s + rng.randrange(60, 720),
                callback_token=callback_token,
            )
        if rng.random() < incident_probabilities["revision"]:
            append_call(
                incident=incident,
                relationship="revision",
                channel="911-callback",
                received_s=incident.onset_s + rng.randrange(300, 1_500),
                callback_token=callback_token,
                revision_of_call_id=base_call,
            )

    false_count = sample_poisson(rng, probabilities["false_report_mean"])
    for false_index in range(false_count):
        append_call(
            incident=None,
            relationship="false_report",
            channel="non-emergency-transfer",
            received_s=rng.randrange(config.timeline.duration_s),
            callback_token=f"SYNTH-FALSE-{false_index + 1:04d}",
        )

    return ObservationArtifact(
        schema_version="delta-lossy-observation-channel-v2",
        calls=sorted(calls, key=lambda item: (item.received_s, item.call_id)),
        lineage=sorted(lineage, key=lambda item: item.call_id),
        expected_calls_total=config.call_process.expected_calls_total,
        peak_expected_calls_per_hour=config.call_process.peak_expected_calls_per_hour,
    )


def generate_prior_profile(config: DeltaScenarioConfig) -> PriorProfileArtifact:
    if config.axes.pi >= 0.8:
        profile_id, accuracy = "delta-prior-high-v1", 900
    elif config.axes.pi >= 0.55:
        profile_id, accuracy = "delta-prior-medium-v1", 650
    else:
        profile_id, accuracy = "delta-prior-low-v1", 400
    return PriorProfileArtifact(
        profile_id=profile_id,
        schema_version="delta-predictor-prior-profile-v1",
        calibration_version=f"{profile_id}-calibration-v1",
        prior_accuracy_milli=accuracy,
        selected_by_pi=config.axes.pi,
    )


def generate_resources(config: DeltaScenarioConfig) -> ResourceArtifact:
    # At the frozen kappa=0.5 setting this yields the two locally documented
    # apparatus classes: one Type I engine and one 25-foot rescue boat.
    boat_count = max(1, round(2 * config.axes.kappa))
    engine_count = max(1, round(2 * config.axes.kappa))
    definitions: list[
        tuple[
            str,
            str,
            tuple[str, ...],
            str,
            int,
            int,
            int,
            int,
            int,
            int,
            int,
            str,
            str | None,
            tuple[str, ...],
        ]
    ] = []
    for index in range(boat_count):
        definitions.append(
            (
                f"RES-BOAT-{index + 1:02d}",
                "flat_bottom_rescue_boat",
                ("water_rescue", "missing_person_search"),
                "XNG-04",
                6,
                index * 240,
                0,
                180,
                900,
                2_700,
                2,
                "local-from-scenario-start",
                "FAC-FIRE-01",
                ("isleton-fire-department-2026-08-05",),
            )
        )
    for index in range(engine_count):
        definitions.append(
            (
                f"RES-ENGINE-{index + 1:02d}",
                "type_i_engine",
                (
                    "medical_first_response",
                    "road_rescue",
                    "welfare_check",
                    "levee_inspection",
                ),
                "XNG-04",
                0,
                180 + index * 180,
                0,
                120,
                720,
                2_700,
                2,
                "local-from-scenario-start",
                "FAC-FIRE-01",
                ("isleton-fire-department-2026-08-05",),
            )
        )
    if config.generator_version in {
        "delta-small-generator-v6",
        "delta-small-generator-v7",
        "delta-small-generator-v8",
    }:
        automatic_aid_count = max(0, round(2 * config.axes.kappa))
        for index in range(automatic_aid_count):
            definitions.append(
                (
                    f"RES-RV-BOAT-55-{index + 1:02d}",
                    "zodiac_rescue_boat",
                    ("water_rescue", "missing_person_search"),
                    "XNG-04",
                    6,
                    2_700 + index * 240,
                    2_100,
                    600,
                    900,
                    2_700,
                    2,
                    "preauthorized-automatic-aid-fixed-staging",
                    "FAC-RIO-VISTA-55",
                    ("rio-vista-fire-source-extract-v1",),
                )
            )
        for index in range(automatic_aid_count):
            definitions.append(
                (
                    f"RES-RV-ENGINE-55-{index + 1:02d}",
                    "type_i_engine",
                    (
                        "medical_first_response",
                        "road_rescue",
                        "welfare_check",
                        "levee_inspection",
                    ),
                    "XNG-04",
                    0,
                    2_700 + index * 180,
                    1_200,
                    1_500,
                    720,
                    2_700,
                    2,
                    "preauthorized-automatic-aid-fixed-staging",
                    "FAC-RIO-VISTA-55",
                    ("rio-vista-fire-source-extract-v1",),
                )
            )
    units = [
        ResourceUnit(
            resource_id=resource_id,
            resource_class=resource_class,
            base_id="FAC-FIRE-01",
            capabilities=capabilities,
            route_id=route_id,
            passenger_capacity=passenger_capacity,
            activation_time_s=round(activation_s * config.axes.mu),
            transit_time_s=round(transit_s * config.axes.mu),
            staging_time_s=round(staging_s * config.axes.mu),
            nominal_travel_time_s=round(travel_s * config.axes.mu),
            available_from_s=round((activation_s + transit_s + staging_s) * config.axes.mu),
            service_duration_s=service_duration_s,
            service_units=service_units,
            is_available=config.axes.delta < max(0.08, 0.56 - 0.08 * index),
            availability_mode=availability_mode,
            origin_base_id=origin_base_id,
            source_record_ids=source_record_ids,
        )
        for index, (
            resource_id,
            resource_class,
            capabilities,
            route_id,
            passenger_capacity,
            activation_s,
            transit_s,
            staging_s,
            travel_s,
            service_duration_s,
            service_units,
            availability_mode,
            origin_base_id,
            source_record_ids,
        ) in enumerate(definitions)
    ]
    return ResourceArtifact(
        schema_version=(
            "delta-resources-v3"
            if config.generator_version
            in {
                "delta-small-generator-v6",
                "delta-small-generator-v7",
                "delta-small-generator-v8",
            }
            else "delta-resources-v2"
        ),
        capability_schema_version="delta-incident-resource-capabilities-v1",
        coordination_domain=(
            "delta-small-resource-inventory-v3"
            if config.generator_version in {"delta-small-generator-v7", "delta-small-generator-v8"}
            else f"delta-small-logical-authorities-{config.axes.phi}"
        ),
        resource_profile_id=config.resource_profile_id,
        units=units,
    )
