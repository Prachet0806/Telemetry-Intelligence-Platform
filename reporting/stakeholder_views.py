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


def _parse_percent(value) -> float:
    """Robustly parse a formatted percent ("12.5%", "5.0%") or raw number.

    Accepts floats (fraction 0-1 or percent 0-100), ints, and strings with
    an optional trailing "%". Strings with "%" are interpreted as percent
    (0-100); bare numerics > 1 are treated as percent, <= 1 as fraction
    for the anomaly/baseline rates. Returns a fraction (0-1) for rate-like
    signals... callers needing percent should multiply by 100.
    """
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        v = float(value)
        return v / 100.0 if v > 1 else v
    s = str(value).strip().rstrip("%").strip()
    try:
        v = float(s)
    except (TypeError, ValueError):
        return 0.0
    # A trailing "%" in the original means percent units.
    if str(value).strip().endswith("%"):
        return v / 100.0
    return v / 100.0 if v > 1 else v


def _parse_high_risk_pct(value) -> float:
    """Parse High-Risk Event % into percent units (0-100)."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        v = float(value)
        return v * 100.0 if 0 <= v <= 1 else v
    s = str(value).strip()
    is_pct = s.endswith("%")
    try:
        v = float(s.rstrip("%").strip())
    except (TypeError, ValueError):
        return 0.0
    if is_pct:
        return v
    return v * 100.0 if 0 <= v <= 1 else v


def _raw_signals(brief: dict) -> dict:
    """Prefer machine-readable Signal Summary Raw; fall back to parsing strings."""
    raw = brief.get("Signal Summary Raw") or {}
    sig = brief.get("Signal Summary", {}) or {}
    def _num(key, default=None):
        v = raw.get(key, None)
        return default if v is None else v
    return {
        "anomaly_rate": _num("anomaly_rate", _parse_percent(sig.get("Anomaly Rate", 0))),
        "high_risk_percentage": _num(
            "high_risk_percentage", _parse_high_risk_pct(sig.get("High-Risk Event %", 0))
        ),
        "baseline_flag_rate": _num(
            "baseline_flag_rate", _parse_percent(sig.get("Baseline Flag Rate", 0))
        ),
        "total_events": _num("total_events", sig.get("Total Events Analyzed", 0)),
        "supervised_precision": _num("supervised_precision"),
        "supervised_recall": _num("supervised_recall"),
    }


# ---------------------------------------------------------------------------
# View adapters
# ---------------------------------------------------------------------------

def build_context_from_brief(brief: dict, metrics: dict) -> DecisionContext:
    """Rebuild a DecisionContext from a persisted brief + metrics.

    Prefers the machine-readable ``Signal Summary Raw`` block; falls back
    to parsing the formatted strings (e.g. "12.5%") and finally to the
    live ``metrics`` blocks. Never raises on missing keys.
    """
    raw = _raw_signals(brief or {})
    baseline = (metrics or {}).get("baseline", {}) or {}
    unsup = (metrics or {}).get("unsupervised", {}) or {}
    try:
        baseline_rate = float(baseline.get("positive_rate", raw["baseline_flag_rate"]))
    except (TypeError, ValueError):
        baseline_rate = raw["baseline_flag_rate"]
    try:
        anomaly = float(unsup.get("anomaly_rate", raw["anomaly_rate"]))
    except (TypeError, ValueError):
        anomaly = raw["anomaly_rate"]
    try:
        total = int(raw["total_events"] or 0)
    except (TypeError, ValueError):
        total = 0
    return DecisionContext(
        baseline_flag_rate=float(baseline_rate or 0.0),
        anomaly_rate=float(anomaly or 0.0),
        high_risk_percentage=float(raw["high_risk_percentage"] or 0.0),
        total_events=total,
        supervised_precision=raw["supervised_precision"],
        supervised_recall=raw["supervised_recall"],
    )

def executive_view(brief: dict) -> dict:
    """
    Board-level view — business risk, financial exposure, top actions.
    Non-technical language only.
    """
    actions = brief.get("Recommended Actions", []) or []
    return {
        "page_title": "🧑‍💼 Executive Risk Dashboard",
        "page_caption": "Enterprise risk posture, estimated financial exposure, and strategic recommendations.",
        "Enterprise Risk Level": brief.get("Severity", "Low"),
        "Risk Summary": brief.get("Executive Summary", ""),
        "Estimated Financial Exposure": brief.get("Estimated Financial Exposure", "N/A"),
        "Exposure Range": brief.get("Estimated Financial Exposure Range", "N/A"),
        "Impact Breakdown": brief.get("Impact Breakdown", {}),
        "Top Recommendations": list(actions)[:3],
        "Confidence": brief.get("Confidence Level", "N/A"),
    }


def operations_view(brief: dict) -> dict:
    """
    SRE / Platform engineering view — runbook-oriented, immediate actions.
    """
    severity = brief.get("Severity", "Low")
    return {
        "page_title": "👷 Operations Command Centre",
        "page_caption": "Runbook-oriented view for SRE and Platform Engineering teams.",
        "Operational Risk Level": severity,
        "Action Window": urgency_label(severity),
        "Estimated Blast Radius": brief.get("Estimated Financial Exposure", "N/A"),
        "Action Checklist": brief.get("Recommended Actions", []) or [],
        "Signal Summary": brief.get("Signal Summary", {}),
        "Confidence": brief.get("Confidence Level", "N/A"),
    }


def security_view(brief: dict, ctx: DecisionContext, metrics: dict) -> dict:
    """
    SOC / Security engineering view — detection signals and threat indicators.
    """
    metrics = metrics or {}
    return {
        "page_title": "🔐 Security Analysis View",
        "page_caption": "Detection signals, threat indicators, and model performance for SOC teams.",
        "Severity": (brief or {}).get("Severity", "Low"),
        "Anomaly Rate": ctx.anomaly_rate,
        "High-Risk Event %": ctx.high_risk_percentage,
        "Baseline Flag Rate": ctx.baseline_flag_rate,
        "Total Events": ctx.total_events,
        "Supervised Precision": ctx.supervised_precision,
        "Supervised Recall": ctx.supervised_recall,
        "Recommended Actions": (brief or {}).get("Recommended Actions", []) or [],
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
    brief = brief or {}
    return {
        "page_title": "⚙️ Technical Metrics",
        "page_caption": "Full pipeline telemetry, model evaluation, and feature diagnostics for engineering teams.",
        "Severity": brief.get("Severity", "Low"),
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