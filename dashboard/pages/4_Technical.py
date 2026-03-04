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

st.set_page_config(page_title="Technical | Decision Intelligence", layout="wide")

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

METRICS_PATH = PROJECT_ROOT / "data" / "processed" / "metrics.json"
FEATURES_PATH = PROJECT_ROOT / "data" / "processed" / "features.parquet"

if not METRICS_PATH.exists() or not FEATURES_PATH.exists():
    st.error("Pipeline output not found. Run the pipeline first.")
    st.code("python scripts/run_pipeline.py")
    st.stop()

with open(METRICS_PATH) as f:
    metrics = json.load(f)

df = pd.read_parquet(FEATURES_PATH)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.title("⚙️ Technical Metrics")
st.caption("Full pipeline telemetry, model evaluation, and feature diagnostics for engineering teams.")
st.divider()

# ---------------------------------------------------------------------------
# Ingestion stats
# ---------------------------------------------------------------------------

st.subheader("📥 Ingestion Statistics")
render_ingestion_metrics(metrics)

# ---------------------------------------------------------------------------
# Detection rates
# ---------------------------------------------------------------------------

st.divider()
st.subheader("🔬 Detection Rates")
render_detection_metrics(metrics)

# ---------------------------------------------------------------------------
# Label distribution
# ---------------------------------------------------------------------------

st.divider()
st.subheader("🏷️ Label Distribution")
label_counts = df["label_high_risk"].value_counts().rename({0: "Normal", 1: "High Risk"})
st.bar_chart(label_counts)

# ---------------------------------------------------------------------------
# Supervised model report
# ---------------------------------------------------------------------------

st.divider()
st.subheader("🤖 Supervised Model Report")
render_supervised_report(metrics)

# ---------------------------------------------------------------------------
# Baseline comparison
# ---------------------------------------------------------------------------

st.divider()
st.subheader("⚖️ Baseline vs Supervised Comparison")
render_baseline_comparison(metrics)

# ---------------------------------------------------------------------------
# Decision intelligence signals (technical view)
# ---------------------------------------------------------------------------

st.divider()
st.subheader("🧠 Decision Intelligence Signals")
di = metrics.get("decision_intelligence", {})
if di:
    sig = di.get("Signal Summary", {})
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Anomaly Rate", sig.get("Anomaly Rate", "N/A"))
    c2.metric("High-Risk %", sig.get("High-Risk Event %", "N/A"))
    c3.metric("Baseline Rate", sig.get("Baseline Flag Rate", "N/A"))
    c4.metric("Severity", di.get("Severity", "N/A"))
    st.metric("Estimated Exposure", di.get("Estimated Financial Exposure", "N/A"))
else:
    st.info("Decision Intelligence data not yet available. Re-run the pipeline.")

# ---------------------------------------------------------------------------
# Full raw metrics (expandable)
# ---------------------------------------------------------------------------

st.divider()
with st.expander("🗄️ Full Raw Metrics JSON"):
    st.json(metrics)

# ---------------------------------------------------------------------------
# Feature dataframe
# ---------------------------------------------------------------------------

with st.expander("📋 Engineered Features DataFrame"):
    st.dataframe(df.head(100), use_container_width=True)
