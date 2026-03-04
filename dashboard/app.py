# dashboard/app.py
# Home page — Decision Intelligence hero overview
# Multi-stakeholder pages are in dashboard/pages/

import json
import os
import subprocess
import sys
import time
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

# -------------------------------------------------------------------
# Paths
# -------------------------------------------------------------------

DATA_DIR      = PROJECT_ROOT / "data" / "processed"
FEATURES_PATH = DATA_DIR / "features.parquet"
METRICS_PATH  = DATA_DIR / "metrics.json"

# -------------------------------------------------------------------
# Streamlit setup
# -------------------------------------------------------------------

st.set_page_config(
    page_title="Enterprise Operational Decision Intelligence Platform",
    page_icon="🧠",
    layout="wide",
)

# -------------------------------------------------------------------
# Helper: run pipeline
# -------------------------------------------------------------------

def run_pipeline():
    return subprocess.run(
        [sys.executable, str(PIPELINE_SCRIPT)],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )

# -------------------------------------------------------------------
# First-run handling
# -------------------------------------------------------------------

if not FEATURES_PATH.exists():
    st.title("🧠 Enterprise Operational Decision Intelligence Platform")
    st.error("Processed telemetry not found.")
    st.markdown(
        "No processed data was detected. "
        "Run the analytics pipeline to generate decision intelligence outputs."
    )
    st.code("python scripts/run_pipeline.py")

    if st.button("▶ Run Pipeline Now", type="primary"):
        with st.spinner("Running pipeline…"):
            try:
                result = run_pipeline()
                st.success("Pipeline completed successfully.")
                st.text_area("Pipeline Output", result.stdout, height=250)
                time.sleep(1)
                st.rerun()
            except subprocess.CalledProcessError as exc:
                st.error("Pipeline execution failed.")
                st.text_area("Error Output", exc.stderr, height=250)
    st.stop()

# -------------------------------------------------------------------
# Load data
# -------------------------------------------------------------------

df = pd.read_parquet(FEATURES_PATH)

metrics = None
if METRICS_PATH.exists():
    with open(METRICS_PATH, "r") as f:
        metrics = json.load(f)

di = (metrics or {}).get("decision_intelligence", {})

# -------------------------------------------------------------------
# Page header
# -------------------------------------------------------------------

st.title("🧠 Enterprise Operational Decision Intelligence Platform")
st.caption(
    "Multi-signal telemetry analysis → severity assessment → impact estimation → "
    "stakeholder-specific operational guidance"
)
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
    c4.metric("⚠️ High-Risk Events",  signals.get("High-Risk Event %", "N/A"))

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
    # Fallback to legacy metrics display if no decision intelligence yet
    st.subheader("Overview")
    st.metric("Total Events", len(df))
    high_risk_pct = round(df["label_high_risk"].mean() * 100, 2)
    st.metric("High-Risk Events (%)", high_risk_pct)
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
if st.button("🔄 Re-run Pipeline", help="Re-run the full analytics pipeline to refresh decision intelligence"):
    with st.spinner("Running pipeline…"):
        try:
            result = run_pipeline()
            st.success("Pipeline refreshed successfully.")
            time.sleep(1)
            st.rerun()
        except subprocess.CalledProcessError as exc:
            st.error("Pipeline failed.")
            st.text_area("Error Output", exc.stderr, height=200)
