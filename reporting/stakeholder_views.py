# reporting/stakeholder_views.py
"""
Stakeholder-specific view adapters.

Each function consumes the canonical `decision_intelligence` brief and
(optionally) the DecisionContext / raw metrics, and returns a dict of
presentation-ready fields. Dashboard pages just render the returned dict.
"""

from __future__ import annotations

from decision.decision_context import DecisionContext


# ---------------------------------------------------------------------------
# Single source of truth for urgency windows
# ---------------------------------------------------------------------------

_URGENCY_MAP = {
    "Critical": "⏰ Immediate (< 1 hour)",
    "High":     "🕐 Urgent (< 4 hours)",
    "Moderate": "🗓️ Scheduled (< 24 hours)",
    "Low":      "✅ Routine (next business day)",
}


def urgency_label(severity: str) -> str:
    """Return the human-friendly action window for a severity tier."""
    return _URGENCY_MAP.get(severity, "Unknown")


# ---------------------------------------------------------------------------
# View adapters
# ---------------------------------------------------------------------------

def executive_view(brief: dict) -> dict:
    """
    Board-level view — business risk, financial exposure, top actions.
    Non-technical language only.
    """
    return {
        "page_title": "🧑‍💼 Executive Risk Dashboard",
        "page_caption": "Enterprise risk posture, estimated financial exposure, and strategic recommendations.",
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
        "page_title": "👷 Operations Command Centre",
        "page_caption": "Runbook-oriented view for SRE and Platform Engineering teams.",
        "Operational Risk Level": brief["Severity"],
        "Action Window": urgency_label(brief["Severity"]),
        "Estimated Blast Radius": brief["Estimated Financial Exposure"],
        "Action Checklist": brief["Recommended Actions"],
        "Signal Summary": brief.get("Signal Summary", {}),
        "Confidence": brief.get("Confidence Level", "N/A"),
    }


def security_view(brief: dict, ctx: DecisionContext, metrics: dict) -> dict:
    """
    SOC / Security engineering view — detection signals and threat indicators.
    """
    return {
        "page_title": "🔐 Security Analysis View",
        "page_caption": "Detection signals, threat indicators, and model performance for SOC teams.",
        "Severity": brief["Severity"],
        "Anomaly Rate": ctx.anomaly_rate,
        "High-Risk Event %": ctx.high_risk_percentage,
        "Baseline Flag Rate": ctx.baseline_flag_rate,
        "Total Events": ctx.total_events,
        "Supervised Precision": ctx.supervised_precision,
        "Supervised Recall": ctx.supervised_recall,
        "Recommended Actions": brief["Recommended Actions"],
        # Raw metrics for charts/tables
        "risk_counts": None,  # filled by page from features
        "baseline_rate": metrics.get("baseline", {}).get("positive_rate", 0),
        "anomaly_rate": metrics.get("unsupervised", {}).get("anomaly_rate", 0),
        "supervised_report": metrics.get("supervised"),
        "baseline_evaluation": metrics.get("baseline_evaluation"),
        "feature_df": None,  # filled by page
    }


def technical_view(brief: dict, ctx: DecisionContext, metrics: dict) -> dict:
    """
    Engineering / ML team view — full pipeline telemetry and model metrics.
    """
    return {
        "page_title": "⚙️ Technical Metrics",
        "page_caption": "Full pipeline telemetry, model evaluation, and feature diagnostics for engineering teams.",
        "Severity": brief["Severity"],
        "Pipeline Metrics": metrics,
        "Decision Signals": {
            "anomaly_rate": ctx.anomaly_rate,
            "high_risk_percentage": ctx.high_risk_percentage,
            "baseline_flag_rate": ctx.baseline_flag_rate,
            "total_events": ctx.total_events,
        },
        "Model Available": ctx.has_supervised_model(),
        "Estimated Exposure": brief.get("Estimated Financial Exposure", "N/A"),
    }


# ---------------------------------------------------------------------------
# Helpers for rendering common elements
# ---------------------------------------------------------------------------

def render_common_header(view: dict) -> None:
    """Render the standard title + caption + divider used by all pages."""
    import streamlit as st
    st.title(view["page_title"])
    st.caption(view["page_caption"])
    st.divider()


def render_signal_summary(signals: dict) -> None:
    """Render the 4-column signal summary used by Operations/Executive/Technical."""
    import streamlit as st
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Anomaly Rate", signals.get("Anomaly Rate", "N/A"))
    c2.metric("High-Risk Events", signals.get("High-Risk Event %", "N/A"))
    c3.metric("Baseline Flag Rate", signals.get("Baseline Flag Rate", "N/A"))
    c4.metric("Total Events Analyzed", signals.get("Total Events Analyzed", "N/A"))


def render_confidence(confidence: str) -> None:
    """Render the confidence caption."""
    import streamlit as st
    st.divider()
    st.caption(f"**Confidence:** {confidence}")