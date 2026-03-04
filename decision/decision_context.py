# decision/decision_context.py

from __future__ import annotations
from dataclasses import dataclass


@dataclass
class DecisionContext:
    """
    A structured snapshot of all pipeline signals needed by the decision layer.

    This decouples business logic from raw model objects — the decision engine
    only needs pre-computed metrics, not sklearn models or DataFrames.
    """

    baseline_flag_rate: float
    """Fraction of events flagged by deterministic baseline rules."""

    anomaly_rate: float
    """Fraction of events flagged as anomalous by the unsupervised model."""

    high_risk_percentage: float
    """Percentage of events labelled high-risk (supervised label distribution)."""

    total_events: int
    """Total number of valid events processed in this pipeline run."""

    supervised_precision: float | None = None
    """Weighted precision from the supervised classifier (None if model unavailable)."""

    supervised_recall: float | None = None
    """Weighted recall from the supervised classifier (None if model unavailable)."""

    def has_supervised_model(self) -> bool:
        return (
            self.supervised_precision is not None
            and self.supervised_recall is not None
        )

    def confidence_label(self) -> str:
        """
        Returns a human-readable confidence label for reports.
        High if supervised model ran; Moderate otherwise.
        """
        if self.has_supervised_model():
            return "High (multi-signal validation: rules + unsupervised + supervised)"
        return "Moderate (rules + unsupervised only; supervised model unavailable)"
