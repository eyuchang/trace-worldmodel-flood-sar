"""Versioned declarative truth, observation, and resource parameter tables."""

from __future__ import annotations

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
        from trace_jepa.scenario.delta.generation.observation_channel import (
            BASE_REPORTING_BY_HOUR_V2,
            DESCRIPTOR_VOCABULARY_V1,
            FALSE_REPORT_HOUR_WEIGHTS_V1,
            channel_probabilities_v8,
        )
        from trace_jepa.scenario.delta.generation.observation_primitives import (
            BASE_LOCATION_METHOD_MILLI,
            BASE_PRECISION_RANGES_M,
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
