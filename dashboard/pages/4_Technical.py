# dashboard/pages/4_Technical.py
# Audience: Engineering / ML teams — full pipeline telemetry and model metrics

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dashboard.components.metrics_table import (
    render_ingestion_metrics,
    render_detection_metrics,
    render_supervised_report,
    render_baseline_comparison,
)
from decision.decision_context import DecisionContext
from reporting.stakeholder_views import build_context_from_brief, technical_view
from dashboard.auth import require_page
from reporting.run_store import latest_run_dir

st.set_page_config(page_title="Technical | Decision Intelligence", layout="wide")
require_page(st, "Technical")

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

RUN_DIR = latest_run_dir(PROJECT_ROOT / "data" / "processed")
METRICS_PATH = RUN_DIR / "metrics.json"
FEATURES_PATH = RUN_DIR / "features.parquet"

if not METRICS_PATH.exists() or not FEATURES_PATH.exists():
    st.error("Pipeline output not found. Run the pipeline first.")
    st.code("python scripts/run_pipeline.py")
    st.stop()

try:
    with open(METRICS_PATH, encoding="utf-8") as f:
        metrics = json.load(f)
except (OSError, json.JSONDecodeError) as exc:
    st.error(f"Could not read metrics.json: {exc}. Re-run the pipeline.")
    st.stop()

try:
    df = pd.read_parquet(FEATURES_PATH)
except Exception as exc:
    st.error(f"Could not read features.parquet: {exc}. Re-run the pipeline.")
    st.stop()
di = metrics.get("decision_intelligence", {})

ctx = build_context_from_brief(di, metrics)

view = technical_view(di, ctx, metrics)

# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

st.title(view["page_title"])
st.caption(view["page_caption"])
st.divider()

# Ingestion stats
st.subheader("📥 Ingestion Statistics")
render_ingestion_metrics(metrics)

# Detection rates
st.divider()
st.subheader("🔬 Detection Rates")
render_detection_metrics(metrics)

# Label distribution
st.divider()
st.subheader("🏷️ Label Distribution")
label_counts = df["label_high_risk"].value_counts().rename({0: "Normal", 1: "High Risk"})
st.bar_chart(label_counts)

# Supervised model report
st.divider()
st.subheader("🤖 Supervised Model Report")
render_supervised_report(metrics)

# Baseline comparison
st.divider()
st.subheader("⚖️ Baseline vs Supervised Comparison")
render_baseline_comparison(metrics)

# Decision intelligence signals (technical view)
st.divider()
st.subheader("🧠 Decision Intelligence Signals")
sig = di.get("Signal Summary", {})
c1, c2, c3, c4 = st.columns(4)
c1.metric("Anomaly Rate", sig.get("Anomaly Rate", "N/A"))
c2.metric("High-Risk Label Rate", sig.get("High-Risk Event %", "N/A"))
st.caption(metrics.get("supervised_evaluation", {}).get("interpretation", "Label provenance is unverified."))
c3.metric("Baseline Rate", sig.get("Baseline Flag Rate", "N/A"))
c4.metric("Severity", di.get("Severity", "N/A"))
st.metric("Estimated Exposure", view["Estimated Exposure"])

# Full raw metrics (expandable)
st.divider()
with st.expander("🗄️ Full Raw Metrics JSON"):
    st.json(metrics)

# Pipeline metadata (audit trail)
with st.expander("🧾 Pipeline Metadata (audit trail)"):
    meta = metrics.get("run_metadata", {})
    if meta:
        st.json(meta)
    else:
        st.info("run_metadata not present — re-run the pipeline to capture an audit trail.")

# Feature dataframe
with st.expander("📋 Engineered Features DataFrame"):
    st.dataframe(df.head(100), use_container_width=True)
