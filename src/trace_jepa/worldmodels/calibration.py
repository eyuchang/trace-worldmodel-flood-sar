from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class IsotonicCalibrator:
    thresholds: np.ndarray
    values: np.ndarray

    @classmethod
    def fit(cls, scores: np.ndarray, outcomes: np.ndarray) -> "IsotonicCalibrator":
        scores = np.asarray(scores, dtype=np.float64).reshape(-1)
        outcomes = np.asarray(outcomes, dtype=np.float64).reshape(-1)
        if len(scores) != len(outcomes) or len(scores) < 2:
            raise ValueError("calibration requires paired scores and at least two rows")
        order = np.argsort(scores, kind="stable")
        sorted_scores = scores[order]
        sorted_outcomes = outcomes[order]

        # Identical model scores are one calibration support point. Aggregate
        # them before PAV; otherwise stable ordering could assign different
        # calibrated values to indistinguishable predictions.
        unique_scores, first_indices, counts = np.unique(
            sorted_scores, return_index=True, return_counts=True
        )
        grouped_outcomes = np.add.reduceat(sorted_outcomes, first_indices) / counts

        weights: list[float] = []
        means: list[float] = []
        starts: list[int] = []
        ends: list[int] = []
        for index, value in enumerate(grouped_outcomes):
            weights.append(float(counts[index]))
            means.append(float(value))
            starts.append(index)
            ends.append(index)
            while len(means) >= 2 and means[-2] > means[-1]:
                weight = weights[-2] + weights[-1]
                mean = (weights[-2] * means[-2] + weights[-1] * means[-1]) / weight
                weights[-2:] = [weight]
                means[-2:] = [mean]
                ends[-2:] = [ends[-1]]
                starts.pop()

        thresholds = np.asarray([unique_scores[end] for end in ends], dtype=np.float64)
        values = np.clip(np.asarray(means, dtype=np.float64), 0.0, 1.0)
        return cls(thresholds=thresholds, values=values)

    def transform(self, scores: np.ndarray | float) -> np.ndarray:
        values = np.asarray(scores, dtype=np.float64)
        indices = np.searchsorted(self.thresholds, values, side="left")
        indices = np.clip(indices, 0, len(self.values) - 1)
        return self.values[indices]


def expected_calibration_error(
    probability: np.ndarray,
    outcome: np.ndarray,
    *,
    bins: int = 10,
) -> float:
    probability = np.asarray(probability, dtype=np.float64).reshape(-1)
    outcome = np.asarray(outcome, dtype=np.float64).reshape(-1)
    if len(probability) != len(outcome) or not len(probability):
        raise ValueError("ECE requires non-empty paired arrays")
    edges = np.linspace(0.0, 1.0, bins + 1)
    total = float(len(probability))
    error = 0.0
    for index in range(bins):
        lower, upper = edges[index], edges[index + 1]
        mask = (probability >= lower) & (
            probability <= upper if index == bins - 1 else probability < upper
        )
        if mask.any():
            error += (
                float(mask.sum())
                / total
                * abs(float(probability[mask].mean()) - float(outcome[mask].mean()))
            )
    return error
