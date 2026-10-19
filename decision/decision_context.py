# decision/decision_context.py

from __future__ import annotations
from dataclasses import dataclass


# Confidence gating thresholds for the supervised signal.
MIN_POSITIVE_SUPPORT = 30   # held-out positives needed before we trust the model
MIN_POSITIVE_F1 = 0.60      # positive-class F1 needed for "High" confidence


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

    admin_scope_rate: float | None = None
    """Fraction of events with admin-scope permissions (None if not computed)."""

    # Positive-class ("high risk") metrics from the held-out split -- the
    # minority class is what actually matters; weighted averages hide it.
    supervised_precision: float | None = None
    supervised_recall: float | None = None
    supervised_f1: float | None = None
    supervised_positive_support: int | None = None
    labels_independently_reviewed: bool = False

    def has_supervised_model(self) -> bool:
        return (
            self.supervised_recall is not None
            and self.supervised_precision is not None
            and self.supervised_f1 is not None
            and self.supervised_positive_support is not None
            and self.supervised_positive_support > 0
        )

    def _supervised_is_trustworthy(self) -> bool:
        if not self.has_supervised_model():
            return False
        support_ok = self.supervised_positive_support >= MIN_POSITIVE_SUPPORT
        f1 = self.supervised_f1
        quality_ok = f1 is not None and f1 >= MIN_POSITIVE_F1
        return support_ok and quality_ok

    def validate_ranges(self) -> None:
        """Fail fast on unit swaps or nonsensical signal values."""
        if not 0 <= self.baseline_flag_rate <= 1:
            raise ValueError(f"baseline_flag_rate must be in [0, 1], got {self.baseline_flag_rate}")
        if not 0 <= self.anomaly_rate <= 1:
            raise ValueError(f"anomaly_rate must be in [0, 1], got {self.anomaly_rate}")
        if not 0 <= self.high_risk_percentage <= 100:
            raise ValueError(
                f"high_risk_percentage must be in [0, 100], got {self.high_risk_percentage}"
            )
        if self.total_events < 0:
            raise ValueError(f"total_events must be >= 0, got {self.total_events}")
        if self.admin_scope_rate is not None and not 0 <= self.admin_scope_rate <= 1:
            raise ValueError(f"admin_scope_rate must be in [0, 1], got {self.admin_scope_rate}")

    def confidence_label(self) -> str:
        """
        Human-readable confidence label, gated on actual evidence quality.

        - No supervised model            -> Moderate (rules + unsupervised)
        - Model ran but weak/unreliable   -> Low-Moderate, with reason
        - Model ran and passed gates      -> High
        """
        if not self.has_supervised_model():
            if not self.labels_independently_reviewed:
                return "Provisional (no independently reviewed labels; model and rule agreement is not threat accuracy)"
            return "Moderate (rules + unsupervised only; supervised model unavailable)"

        if self.supervised_positive_support is not None and (
            self.supervised_positive_support < MIN_POSITIVE_SUPPORT
        ):
            return (
                "Low-Moderate (supervised model trained on very few "
                f"positive examples: {self.supervised_positive_support}; "
                "treat model signals as indicative only)"
            )

        if not self._supervised_is_trustworthy():
            return (
                "Low-Moderate (supervised model underperforms on the "
                "minority class; treat model signals as indicative only)"
            )

        if not self.labels_independently_reviewed:
            return "Provisional (strong agreement with supplied labels; labels are not independently reviewed)"

        return "High (multi-signal validation: rules + unsupervised + supervised)"
