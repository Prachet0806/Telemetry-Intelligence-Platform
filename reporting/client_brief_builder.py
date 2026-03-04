# reporting/client_brief_builder.py

from __future__ import annotations

from decision.decision_context import DecisionContext


def build_client_brief(
    severity: str,
    impact: float,
    actions: list[str],
    ctx: DecisionContext,
) -> dict:
    """
    Build a structured consulting-grade decision brief.

    This is the canonical output of the Decision Intelligence Layer.
    All stakeholder views and narratives are derived from this brief.

    Parameters
    ----------
    severity : str
        Output of severity_engine.determine_severity()
    impact : float
        Estimated USD exposure from impact_estimator.estimate_impact()
    actions : list[str]
        Recommended actions from action_recommender.recommend_actions()
    ctx : DecisionContext
        Full pipeline signal context.

    Returns
    -------
    dict with keys:
      - Executive Summary
      - Severity
      - Estimated Financial Exposure
      - Estimated Financial Exposure Raw
      - Recommended Actions
      - Confidence Level
      - Signal Summary
    """
    return {
        "Executive Summary": (
            f"Operational telemetry analysis indicates a {severity.upper()} risk posture. "
            f"Immediate review is {'required' if severity in ('Critical', 'High') else 'recommended'}."
        ),
        "Severity": severity,
        "Estimated Financial Exposure": f"${impact:,.2f}",
        "Estimated Financial Exposure Raw": impact,
        "Recommended Actions": actions,
        "Confidence Level": ctx.confidence_label(),
        "Signal Summary": {
            "Anomaly Rate": f"{ctx.anomaly_rate:.1%}",
            "High-Risk Event %": f"{ctx.high_risk_percentage:.1f}%",
            "Baseline Flag Rate": f"{ctx.baseline_flag_rate:.1%}",
            "Total Events Analyzed": ctx.total_events,
        },
    }
