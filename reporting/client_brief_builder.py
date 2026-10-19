# reporting/client_brief_builder.py

from __future__ import annotations

from datetime import datetime, timezone

from decision.decision_context import DecisionContext


def build_client_brief(
    severity: str,
    impact: float,
    actions: list[str],
    ctx: DecisionContext,
    label_basis: str = "Source-provided labels; independent review not established.",
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
    review_guidance = {
        "Critical": "Immediate escalation and review are required.",
        "High": "Urgent review is required.",
        "Moderate": "Scheduled review is recommended within 24 hours.",
        "Low": "No immediate review required; continue routine monitoring.",
    }

    if not isinstance(severity, str) or not severity:
        raise ValueError("severity must be a non-empty string")
    if impact is None or not isinstance(impact, (int, float)):
        raise TypeError("impact must be a number")
    try:
        impact_val = float(impact)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"impact must be numeric: {exc}") from exc
    if impact_val != impact_val:  # NaN
        raise ValueError("impact must not be NaN")
    if impact_val < 0:
        raise ValueError("impact must be non-negative")
    if not isinstance(actions, list):
        raise TypeError("actions must be a list of strings")

    return {
        "Executive Summary": (
            f"Operational telemetry analysis indicates a {severity.upper()} risk posture. "
            f"{review_guidance.get(severity, 'Human review is recommended.')}"
        ),
        "Severity": severity,
        "Estimated Financial Exposure": f"${impact_val:,.2f}",
        "Estimated Financial Exposure Raw": impact_val,
        "Recommended Actions": actions,
        "Confidence Level": ctx.confidence_label(),
        "High-Risk Label Basis": label_basis,
        "Impact Basis": "Illustrative heuristic estimate; not calibrated against realized losses.",
        "Signal Summary": {
            "Anomaly Rate": f"{ctx.anomaly_rate:.1%}",
            "High-Risk Event %": f"{ctx.high_risk_percentage:.1f}%",
            "Baseline Flag Rate": f"{ctx.baseline_flag_rate:.1%}",
            "Total Events Analyzed": ctx.total_events,
        },
        # Machine-readable contract for dashboard/pages (never parse the
        # formatted strings above with float() — they contain "%").
        "Signal Summary Raw": {
            "anomaly_rate": float(ctx.anomaly_rate),
            "high_risk_percentage": float(ctx.high_risk_percentage),
            "baseline_flag_rate": float(ctx.baseline_flag_rate),
            "total_events": int(ctx.total_events),
            "supervised_precision": ctx.supervised_precision,
            "supervised_recall": ctx.supervised_recall,
            "supervised_f1": ctx.supervised_f1,
            "supervised_positive_support": ctx.supervised_positive_support,
        },
        "Generated At": datetime.now(timezone.utc).isoformat(),
    }
