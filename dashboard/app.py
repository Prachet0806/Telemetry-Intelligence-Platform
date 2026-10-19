# dashboard/app.py
# Home page — Decision Intelligence hero overview
# Multi-stakeholder pages are in dashboard/pages/

import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# -------------------------------------------------------------------
# Project root & imports
# -------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PIPELINE_SCRIPT = PROJECT_ROOT / "scripts" / "run_pipeline.py"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dashboard.components.severity_card import render_severity_card
from dashboard.components.impact_card import render_impact_card
from dashboard.components.action_panel import render_urgent_actions
from dashboard.auth import render_login, require_page
from reporting.run_store import latest_run_dir

# -------------------------------------------------------------------
# Paths
# -------------------------------------------------------------------

DATA_DIR      = PROJECT_ROOT / "data" / "processed"
RUN_DIR       = latest_run_dir(DATA_DIR)
FEATURES_PATH = RUN_DIR / "features.parquet"
METRICS_PATH  = RUN_DIR / "metrics.json"

# -------------------------------------------------------------------
# Streamlit setup
# -------------------------------------------------------------------

st.set_page_config(
    page_title="Enterprise Operational Decision Intelligence Platform",
    page_icon="🧠",
    layout="wide",
)

render_login(st)
require_page(st, "Home")

# -------------------------------------------------------------------
# Helper: run pipeline
# -------------------------------------------------------------------

def run_pipeline():
    return subprocess.run(
        [sys.executable, str(PIPELINE_SCRIPT), "--skip-alerts"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        timeout=600,
    )


def render_source_badge(data_source: str, cache_age_hours: float | None = None) -> None:
    """Render a colour-coded data source pill in the sidebar and inline."""
    if data_source == "cloudwatch":
        badge_html = (
            '<span style="background:#16a34a;color:white;padding:3px 10px;'
            'border-radius:999px;font-size:0.82rem;font-weight:600;">'
            '🟢 Live Data &nbsp;|&nbsp; AWS CloudWatch</span>'
        )
    elif data_source == "mock":
        badge_html = (
            '<span style="background:#6b7280;color:white;padding:3px 10px;'
            'border-radius:999px;font-size:0.82rem;font-weight:600;">'
            '⚪ Mock Data &nbsp;|&nbsp; Auto-generated</span>'
        )
    else:
        # Local fallback — show cache age if we have it
        if cache_age_hours is not None:
            age_str = f"{cache_age_hours:.1f}h ago"
            badge_html = (
                f'<span style="background:#ca8a04;color:white;padding:3px 10px;'
                f'border-radius:999px;font-size:0.82rem;font-weight:600;">'
                f'🟡 Local Data &nbsp;|&nbsp; Cached from CloudWatch ({age_str})</span>'
            )
        else:
            badge_html = (
                '<span style="background:#ca8a04;color:white;padding:3px 10px;'
                'border-radius:999px;font-size:0.82rem;font-weight:600;">'
                '🟡 Local Data &nbsp;|&nbsp; Cached / fallback</span>'
            )
    st.markdown(badge_html, unsafe_allow_html=True)
    with st.sidebar:
        st.markdown("**Data Source**")
        st.markdown(badge_html, unsafe_allow_html=True)
        st.divider()

# -------------------------------------------------------------------
# First-run handling
# -------------------------------------------------------------------

if not FEATURES_PATH.exists() or not METRICS_PATH.exists():
    st.title("🧠 Enterprise Operational Decision Intelligence Platform")
    st.error("Processed telemetry not found.")
    st.markdown(
        "No processed data was detected. "
        "Run the analytics pipeline to generate decision intelligence outputs."
    )
    st.code("python scripts/run_pipeline.py")

    if st.session_state.get("role") in ("operator", "admin") and st.button("▶ Run Pipeline Now", type="primary"):
        with st.spinner("Running pipeline…"):
            try:
                result = run_pipeline()
                st.success("Pipeline completed successfully.")
                st.text_area("Pipeline Output", result.stdout[-4000:], height=250)
                st.rerun()
            except subprocess.TimeoutExpired:
                st.error("Pipeline timed out after 10 minutes.")
            except subprocess.CalledProcessError as exc:
                st.error("Pipeline execution failed.")
                st.text_area("Error Output", (exc.stderr or "")[-4000:], height=250)
    elif st.session_state.get("role") not in ("operator", "admin"):
        st.info("Pipeline runs can be started by an operator or admin.")
    st.stop()

# -------------------------------------------------------------------
# Load data
# -------------------------------------------------------------------

try:
    df = pd.read_parquet(FEATURES_PATH)
except Exception as exc:
    st.error(f"Could not read features.parquet: {exc}. Re-run the pipeline.")
    st.stop()

metrics = None
try:
    with open(METRICS_PATH, "r", encoding="utf-8") as f:
        metrics = json.load(f)
except (OSError, json.JSONDecodeError) as exc:
    st.error(f"Could not read metrics.json: {exc}. Re-run the pipeline.")
    st.stop()

di = (metrics or {}).get("decision_intelligence", {})
ingestion = (metrics or {}).get("ingestion", {})
data_source = ingestion.get("data_source", "local")
cache_age_hours = ingestion.get("cache_age_hours")

# -------------------------------------------------------------------
# Page header
# -------------------------------------------------------------------

st.title("🧠 Enterprise Operational Decision Intelligence Platform")
st.caption(
    "Multi-signal telemetry analysis → severity assessment → impact estimation → "
    "stakeholder-specific operational guidance"
)

render_source_badge(data_source, cache_age_hours)
st.divider()

# -------------------------------------------------------------------
# Decision Intelligence hero section
# -------------------------------------------------------------------

if di:
    severity = di.get("Severity", "Low")
    impact   = di.get("Estimated Financial Exposure Raw", 0.0)
    actions  = di.get("Recommended Actions", [])
    signals  = di.get("Signal Summary", {})

    # KPI row
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🔴 Risk Level",        severity)
    c2.metric("💰 Est. Exposure",     di.get("Estimated Financial Exposure", "N/A"))
    c3.metric("📡 Anomaly Rate",      signals.get("Anomaly Rate", "N/A"))
    c4.metric("⚠️ Events Labeled High Risk", signals.get("High-Risk Event %", "N/A"))
    st.caption(f"Label basis: {di.get('High-Risk Label Basis', 'Unknown; independent review not established.')}")
    st.caption(di.get("Impact Basis", "Exposure estimate is not calibrated against realized losses."))

    st.divider()

    col_l, col_r = st.columns([3, 2])
    with col_l:
        render_severity_card(severity)
        render_impact_card(impact, severity)
    with col_r:
        render_urgent_actions(actions, n=3)

    st.divider()

    # Executive summary line
    st.info(f"**Intelligence Brief:** {di.get('Executive Summary', '')}")
    st.caption(f"Confidence: {di.get('Confidence Level', 'N/A')}")

else:
    # Fallback when no decision intelligence yet (guard against schema drift)
    st.subheader("Overview")
    st.metric("Total Events", len(df))
    if "label_high_risk" in df.columns and len(df):
        high_risk_pct = round(float(df["label_high_risk"].mean()) * 100, 2)
        st.metric("High-Risk Events (%)", high_risk_pct)
    else:
        st.info("No label column found in features.")
    st.info("⚠️ Decision Intelligence data not found. Re-run the pipeline to upgrade the dashboard.")

# -------------------------------------------------------------------
# Navigation callout
# -------------------------------------------------------------------

st.divider()
st.subheader("📂 Stakeholder Views")
st.markdown(
    """
    Use the **sidebar** to navigate to the stakeholder-specific views:

    | Page | Audience | Focus |
    |------|----------|-------|
    | 👷 **Operations** | SRE / Platform Engineering | Runbook actions, urgency |
    | 🔐 **Security** | SOC / Security Engineering | Threat signals, detection metrics |
    | 🧑‍💼 **Executive** | C-Suite / Board | Business risk, exposure, narrative |
    | ⚙️ **Technical** | Engineering / ML | Model metrics, pipeline diagnostics |
    """
)

# -------------------------------------------------------------------
# Re-run pipeline button (footer)
# -------------------------------------------------------------------

st.divider()
if st.session_state.get("role") in ("operator", "admin") and st.button("🔄 Re-run Pipeline", help="Re-run the full analytics pipeline to refresh decision intelligence"):
    with st.spinner("Running pipeline…"):
        try:
            result = run_pipeline()
            st.success("Pipeline refreshed successfully.")
            st.rerun()
        except subprocess.TimeoutExpired:
            st.error("Pipeline timed out after 10 minutes.")
        except subprocess.CalledProcessError as exc:
            st.error("Pipeline failed.")
            st.text_area("Error Output", (exc.stderr or "")[-4000:], height=200)
