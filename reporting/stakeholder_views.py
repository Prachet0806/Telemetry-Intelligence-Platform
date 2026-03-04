# reporting/stakeholder_views.py

from __future__ import annotations

from decision.decision_context import DecisionContext

# ---------------------------------------------------------------------------
# Urgency helper
# ---------------------------------------------------------------------------

_URGENCY_MAP = {
    "Critical": "Immediate (< 1 hour)",
    "High": "Urgent (< 4 hours)",
    "Moderate": "Scheduled (< 24 hours)",
    "Low": "Routine (next business day)",
}


def _urgency(severity: str) -> str:
    return _URGENCY_MAP.get(severity, "Unknown")


# ---------------------------------------------------------------------------
# Stakeholder views
# ---------------------------------------------------------------------------

def executive_view(brief: dict) -> dict:
    """
    Board-level view — business risk, financial exposure, top actions.
    Non-technical language only.
    """
    return {
        "Enterprise Risk Level": brief["Severity"],
        "Risk Summary": brief["Executive Summary"],
        "Estimated Financial Exposure": brief["Estimated Financial Exposure"],
        "Top Recommendations": brief["Recommended Actions"][:3],
        "Confidence": brief["Confidence Level"],
    }


def operations_view(brief: dict) -> dict:
    """
    SRE / Platform engineering view — runbook-oriented, immediate actions.
    """
    return {
        "Operational Risk Level": brief["Severity"],
        "Action Checklist": brief["Recommended Actions"],
        "Action Window": _urgency(brief["Severity"]),
        "Estimated Blast Radius": brief["Estimated Financial Exposure"],
    }


def security_view(brief: dict, ctx: DecisionContext) -> dict:
    """
    SOC / Security engineering view — detection signals and threat indicators.
    """
    return {
        "Severity": brief["Severity"],
        "Anomaly Rate": ctx.anomaly_rate,
        "High-Risk Event %": ctx.high_risk_percentage,
        "Baseline Flag Rate": ctx.baseline_flag_rate,
        "Total Events": ctx.total_events,
        "Supervised Precision": ctx.supervised_precision,
        "Supervised Recall": ctx.supervised_recall,
        "Recommended Actions": brief["Recommended Actions"],
    }


def engineering_view(brief: dict, ctx: DecisionContext, raw_metrics: dict) -> dict:
    """
    Engineering / ML team view — full pipeline telemetry and model metrics.
    """
    return {
        "Severity": brief["Severity"],
        "Pipeline Metrics": raw_metrics,
        "Decision Signals": {
            "anomaly_rate": ctx.anomaly_rate,
            "high_risk_percentage": ctx.high_risk_percentage,
            "baseline_flag_rate": ctx.baseline_flag_rate,
            "total_events": ctx.total_events,
        },
        "Model Available": ctx.has_supervised_model(),
    }
