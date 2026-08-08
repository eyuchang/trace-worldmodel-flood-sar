from __future__ import annotations

import hashlib
from pathlib import Path

from trace_jepa.contracts import PlanPrediction
from trace_jepa.experimental.profile import AdequacyStatus
from trace_jepa.predictor.protocol import PredictorProvenance, PredictorRequest
from trace_jepa.predictor.qualification import (
    QualificationBinding,
    load_qualification_artifact,
    verify_qualification_binding,
)


class ToyActionPrefixPredictor:
    """Transparent fixture used before a learned flood-domain predictor.

    The outputs are deliberately deterministic so students can test the
    accountability path. They are not experimental results. Unlike the first
    version, behavior is keyed to the grounded action and observed route state,
    not to opaque plan identifiers.
    """

    predictor_version = "toy-action-prefix-v2"
    calibration_version = "toy-calibration-v1"
    training_snapshot = "synthetic-flood-v1"
    model_hash = hashlib.sha256(b"toy-action-prefix-v2-reviewed-source-fixture").hexdigest()
    calibration_hash = hashlib.sha256(b"toy-calibration-v1-reviewed-teaching-fixture").hexdigest()
    supported_action_types = (
        "dispatch_rescue_boat",
        "deploy_ground_team",
        "perform_welfare_check",
        "inspect_levee",
    )
    feature_schema_version = "action-prefix-features-v2"
    action_schema_version = "delta-response-actions-v2"

    def __init__(
        self,
        qualification_path: Path | None = None,
        *,
        qualification_root: Path | None = None,
    ) -> None:
        path = qualification_path or Path(__file__).with_name("toy_qualification_v1.json")
        root = qualification_root or Path(__file__).parent
        if qualification_path is not None and qualification_root is None:
            raise ValueError("qualification_root is required for a custom Toy qualification")
        qualification = load_qualification_artifact(path, trusted_root=root)
        self.qualified_action_types = verify_qualification_binding(
            qualification,
            QualificationBinding(
                predictor_version=self.predictor_version,
                model_hash=self.model_hash,
                calibration_version=self.calibration_version,
                calibration_hash=self.calibration_hash,
                encoder_version=None,
                encoder_checkpoint_hash=None,
                feature_schema_version=self.feature_schema_version,
                action_schema_version=self.action_schema_version,
                supported_action_types=self.supported_action_types,
            ),
        )
        self.adequacy_status = AdequacyStatus.QUALIFIED
        self.qualification_artifact_sha256 = qualification.artifact_sha256

    @property
    def version(self) -> str:
        return self.predictor_version

    def provenance(self) -> PredictorProvenance:
        return PredictorProvenance(
            predictor_version=self.predictor_version,
            calibration_version=self.calibration_version,
            training_snapshot=self.training_snapshot,
            model_hash=self.model_hash,
            calibration_hash=self.calibration_hash,
            adequacy_status=self.adequacy_status,
            qualification_artifact_sha256=self.qualification_artifact_sha256,
            feature_schema_version=self.feature_schema_version,
            action_schema_version=self.action_schema_version,
            supported_action_types=self.supported_action_types,
            qualified_action_types=self.qualified_action_types,
        )

    def predict(self, request: PredictorRequest) -> PlanPrediction:
        plan = request.plan
        action = plan.first_action
        route = request.observation.route(action.route_id) if action.route_id is not None else None

        if action.action_type == "verify_route":
            return PlanPrediction(
                plan_id=plan.plan_id,
                success_probability=0.98,
                arrival_time_s=180.0,
                hazard_score=0.08,
                resource_margin=0.74,
                model_support=0.97,
                out_of_distribution_score=0.04,
                uncertainty=0.04,
                rollout_horizon=2,
                assumptions=("weather_below_drone_limit",),
            )

        if action.action_type not in self.supported_action_types or route is None:
            raise KeyError(plan.plan_id)

        report = route.report
        nominal_travel_s = route.nominal_travel_s

        if report == "unknown":
            # Teaching case: a high numerical success estimate produced outside
            # the predictor's declared support. TRACE must hold the dispatch.
            return PlanPrediction(
                plan_id=plan.plan_id,
                success_probability=0.92,
                arrival_time_s=nominal_travel_s,
                hazard_score=0.12,
                resource_margin=0.35,
                model_support=0.28,
                out_of_distribution_score=0.82,
                uncertainty=0.08,
                rollout_horizon=6,
                assumptions=("map_is_current", "debris_distribution_matches_training"),
            )

        if report == "blocked":
            return PlanPrediction(
                plan_id=plan.plan_id,
                success_probability=0.03,
                arrival_time_s=max(nominal_travel_s, 1800.0),
                hazard_score=0.95,
                resource_margin=-0.20,
                model_support=0.95,
                out_of_distribution_score=0.05,
                uncertainty=0.05,
                rollout_horizon=6,
                assumptions=("verified_route_status",),
            )

        if report == "open":
            prior_adjustment = (
                request.observation.context.prior_profile.prior_accuracy_milli - 900
            ) / 5000.0
            return PlanPrediction(
                plan_id=plan.plan_id,
                success_probability=max(0.0, min(1.0, 0.82 + prior_adjustment)),
                arrival_time_s=nominal_travel_s,
                hazard_score=0.18,
                resource_margin=0.20,
                model_support=0.93,
                out_of_distribution_score=0.08,
                uncertainty=0.14,
                rollout_horizon=7,
                assumptions=("route_report_is_fresh",),
            )

        raise ValueError(f"unsupported route report: {report}")
