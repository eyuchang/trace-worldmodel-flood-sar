"""Pure bounded one-step public-belief model; results are never evidence."""

from __future__ import annotations

from .canonical import decision_digest, verify_model_digest
from .domain import (
    ControllerVisibleSnapshot,
    CounterfactualStepRequest,
    CounterfactualStepResult,
    PublicModelState,
    ResponseBundle,
)


class ReferencePublicCounterfactualModel:
    model_id = "reference-public-one-step-model-v1"

    def fork(self, snapshot: ControllerVisibleSnapshot) -> PublicModelState:
        facts = tuple(
            sorted(
                (
                    *(
                        (f"environment:{item.belief_id}", item.value)
                        for item in snapshot.environment_beliefs
                    ),
                    *(
                        (f"resource:{item.resource_id}", item.reported_state)
                        for item in snapshot.resource_beliefs
                    ),
                )
            )
        )
        body = {
            "schema_version": "delta-reference-public-model-state-v1",
            "source_snapshot_digest": snapshot.snapshot_digest,
            "at_s": snapshot.at_s,
            "fact_values": facts,
        }
        return PublicModelState(**body, state_digest=decision_digest(body))

    def step(
        self,
        request: CounterfactualStepRequest,
        state: PublicModelState,
        bundle: ResponseBundle,
    ) -> CounterfactualStepResult:
        if request.model_version != self.model_id:
            raise ValueError("Reference counterfactual request names another model")
        if request.state_digest != state.state_digest:
            raise ValueError("Reference counterfactual request does not bind its state")
        if request.bundle_digest != bundle.bundle_digest:
            raise ValueError("Reference counterfactual request does not bind its bundle")
        if not verify_model_digest(state, digest_field="state_digest"):
            raise ValueError("Reference public model-state digest is invalid")
        if not verify_model_digest(bundle, digest_field="bundle_digest"):
            raise ValueError("Reference response-bundle digest is invalid")
        operations = len(state.fact_values) + 8
        if operations > request.maximum_primitive_operations:
            raise ValueError("Reference counterfactual compute allowance exceeded")
        predicted_at = state.at_s + request.horizon_increment_s
        facts = tuple(
            sorted((*state.fact_values, (f"modeled:{bundle.bundle_id}", "one-step-applied")))
        )
        body = {
            "schema_version": "delta-reference-counterfactual-step-v1",
            "semantic_role": "simulation_only",
            "source_state_digest": state.state_digest,
            "bundle_digest": bundle.bundle_digest,
            "predicted_at_s": predicted_at,
            "predicted_fact_values": facts,
            "success_probability_micros": 650_000,
            "censor_status": ("within-horizon" if predicted_at <= 345_600 else "scenario-censored"),
            "assumptions": ("public-belief-only", "single-bounded-transition"),
            "primitive_operations": operations,
        }
        return CounterfactualStepResult(**body, result_digest=decision_digest(body))
