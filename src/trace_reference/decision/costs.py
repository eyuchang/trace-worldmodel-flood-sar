"""Receipt-conserving aggregation of unit-preserving Reference decision costs."""

from __future__ import annotations

from dataclasses import dataclass, field

from .canonical import decision_digest, verify_model_digest
from .domain import CostAmount, DecisionCostDelta


@dataclass
class DecisionCostLedger:
    _deltas: dict[str, DecisionCostDelta] = field(default_factory=dict)

    def append(self, delta: DecisionCostDelta) -> None:
        if not verify_model_digest(delta, digest_field="cost_delta_digest"):
            raise ValueError("Reference decision-cost digest is invalid")
        for receipt_id in delta.receipt_ids:
            existing = self._deltas.get(receipt_id)
            if existing is not None and existing != delta:
                raise ValueError("Reference cost receipt ID was reused with different content")
            self._deltas[receipt_id] = delta

    def totals(self) -> DecisionCostDelta:
        unique_by_digest = {item.cost_delta_digest: item for item in self._deltas.values()}
        unique = tuple(unique_by_digest[key] for key in sorted(unique_by_digest))
        physical: list[CostAmount] = []
        compensation: list[CostAmount] = []
        for item in unique:
            physical.extend(item.physical_acquisition_costs)
            compensation.extend(item.compensation_costs)
        body = {
            "schema_version": "delta-reference-decision-cost-v1",
            "physical_acquisition_costs": [
                item.model_dump(mode="json")
                for item in sorted(physical, key=lambda item: item.cost_id)
            ],
            "predictor_inference_count": sum(item.predictor_inference_count for item in unique),
            "planning_transition_count": sum(item.planning_transition_count for item in unique),
            "primitive_operation_count": sum(item.primitive_operation_count for item in unique),
            "bytes_read": sum(item.bytes_read for item in unique),
            "bytes_written": sum(item.bytes_written for item in unique),
            "decision_latency_s": sum(item.decision_latency_s for item in unique),
            "acquisition_latency_s": sum(item.acquisition_latency_s for item in unique),
            "service_delay_s": sum(item.service_delay_s for item in unique),
            "compensation_costs": [
                item.model_dump(mode="json")
                for item in sorted(compensation, key=lambda item: item.cost_id)
            ],
            "consistency_violation_units": sum(item.consistency_violation_units for item in unique),
            "unserved_service_units": sum(item.unserved_service_units for item in unique),
            "receipt_ids": tuple(sorted(self._deltas)),
        }
        return DecisionCostDelta(**body, cost_delta_digest=decision_digest(body))


@dataclass(frozen=True)
class CostDeltaInput:
    """Unit-preserving measurements attributable to one durable receipt."""

    receipt_id: str
    physical_acquisition_costs: tuple[CostAmount, ...] = ()
    predictor_inference_count: int = 0
    planning_transition_count: int = 0
    primitive_operation_count: int = 0
    bytes_read: int = 0
    bytes_written: int = 0
    decision_latency_s: int = 0
    acquisition_latency_s: int = 0
    service_delay_s: int = 0
    compensation_costs: tuple[CostAmount, ...] = ()
    consistency_violation_units: int = 0
    unserved_service_units: int = 0


def build_cost_delta(values: CostDeltaInput) -> DecisionCostDelta:
    body = {
        "schema_version": "delta-reference-decision-cost-v1",
        "physical_acquisition_costs": [
            item.model_dump(mode="json") for item in values.physical_acquisition_costs
        ],
        "predictor_inference_count": values.predictor_inference_count,
        "planning_transition_count": values.planning_transition_count,
        "primitive_operation_count": values.primitive_operation_count,
        "bytes_read": values.bytes_read,
        "bytes_written": values.bytes_written,
        "decision_latency_s": values.decision_latency_s,
        "acquisition_latency_s": values.acquisition_latency_s,
        "service_delay_s": values.service_delay_s,
        "compensation_costs": [item.model_dump(mode="json") for item in values.compensation_costs],
        "consistency_violation_units": values.consistency_violation_units,
        "unserved_service_units": values.unserved_service_units,
        "receipt_ids": (values.receipt_id,),
    }
    return DecisionCostDelta(**body, cost_delta_digest=decision_digest(body))
