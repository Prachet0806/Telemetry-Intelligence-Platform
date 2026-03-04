# dashboard/pages/2_Security.py
# Audience: SOC / Security Engineering — threat indicators and detection logic

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

st.set_page_config(page_title="Security | Decision Intelligence", layout="wide")

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
di = metrics.get("decision_intelligence", {})
signals = di.get("Signal Summary", {})

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.title("🔐 Security Analysis View")
st.caption("Detection signals, threat indicators, and model performance for SOC teams.")
st.divider()

# ---------------------------------------------------------------------------
# Key detection metrics
# ---------------------------------------------------------------------------

st.subheader("🔍 Detection Signals")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Anomaly Rate", signals.get("Anomaly Rate", "N/A"))
c2.metric("High-Risk Events", signals.get("High-Risk Event %", "N/A"))
c3.metric("Baseline Flag Rate", signals.get("Baseline Flag Rate", "N/A"))
c4.metric("Severity", di.get("Severity", "N/A"))

st.divider()

# ---------------------------------------------------------------------------
# Risk distribution chart
# ---------------------------------------------------------------------------

st.subheader("📊 Risk Label Distribution")
risk_counts = df["label_high_risk"].value_counts().rename({0: "Normal", 1: "High Risk"})
st.bar_chart(risk_counts)

# ---------------------------------------------------------------------------
# Anomaly vs Baseline comparison chart
# ---------------------------------------------------------------------------

st.subheader("📈 Detection Rate Comparison")
baseline_rate = metrics.get("baseline", {}).get("positive_rate", 0)
anomaly_rate  = metrics.get("unsupervised", {}).get("anomaly_rate", 0)

comparison_df = pd.DataFrame(
    {"Detection Rate": [baseline_rate, anomaly_rate]},
    index=["Baseline Rules", "Unsupervised ML"],
)
st.bar_chart(comparison_df)

# ---------------------------------------------------------------------------
# Supervised model report
# ---------------------------------------------------------------------------

st.divider()
st.subheader("🤖 Supervised Model Classification Report")

sup = metrics.get("supervised")
if sup:
    rows = [
        {"Class": label, **vals}
        for label, vals in sup.items()
        if isinstance(vals, dict)
    ]
    if rows:
        report_df = pd.DataFrame(rows).set_index("Class")
        st.dataframe(report_df.style.format("{:.3f}", na_rep="—"), use_container_width=True)
    else:
        st.json(sup)
else:
    st.info("Supervised model not available — insufficient label variety in training data.")

# ---------------------------------------------------------------------------
# Baseline vs Supervised comparison
# ---------------------------------------------------------------------------

st.divider()
st.subheader("⚖️ Baseline vs Supervised Comparison")
comp = metrics.get("baseline_vs_supervised")
if comp:
    if "warning" in comp:
        st.warning(comp["warning"])
    else:
        st.json(comp)

# ---------------------------------------------------------------------------
# Feature distribution
# ---------------------------------------------------------------------------

st.divider()
st.subheader("🧬 Feature Distributions")
selected_feature = st.selectbox(
    "Select feature to explore",
    options=[c for c in df.columns if c != "label_high_risk"],
)
st.bar_chart(df[selected_feature].value_counts())

# ---------------------------------------------------------------------------
# Recommended Actions (security context)
# ---------------------------------------------------------------------------

st.divider()
st.subheader("🛡️ Recommended Security Actions")
for action in di.get("Recommended Actions", []):
    st.markdown(f"▸ {action}")
