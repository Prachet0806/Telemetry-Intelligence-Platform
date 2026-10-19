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

from reporting.stakeholder_views import build_context_from_brief, security_view
from dashboard.auth import require_page
from reporting.run_store import latest_run_dir

st.set_page_config(page_title="Security | Decision Intelligence", layout="wide")
require_page(st, "Security")

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

# Build context for security view (prefers Signal Summary Raw; parses "12.5%")
ctx = build_context_from_brief(di, metrics)

view = security_view(di, ctx, metrics)

# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

st.title(view["page_title"])
st.caption(view["page_caption"])
st.divider()

# Key detection metrics
st.subheader("🔍 Detection Signals")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Anomaly Rate", f"{view['Anomaly Rate']:.1%}")
c2.metric("Events Labeled High Risk", f"{view['High-Risk Event %']:.1f}%")
st.caption(di.get("High-Risk Label Basis", "Independent label review is not established."))
c3.metric("Baseline Flag Rate", f"{view['Baseline Flag Rate']:.1%}")
c4.metric("Severity", view["Severity"])

st.divider()

# Risk distribution chart
st.subheader("📊 Risk Label Distribution")
risk_counts = df["label_high_risk"].value_counts().rename({0: "Normal", 1: "High Risk"})
st.bar_chart(risk_counts)

# Anomaly vs Baseline comparison chart
st.subheader("📈 Detection Rate Comparison")
comparison_df = pd.DataFrame(
    {"Detection Rate": [view["baseline_rate"], view["anomaly_rate"]]},
    index=["Baseline Rules", "Unsupervised ML"],
)
st.bar_chart(comparison_df)

# Supervised model report
st.divider()
st.subheader("🤖 Supervised Model Classification Report")
sup = view["supervised_report"]
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

# Baseline vs Supervised comparison
st.divider()
st.subheader("⚖️ Baseline vs Supervised Comparison")
comp = view["baseline_evaluation"]
if comp:
    if "warning" in comp:
        st.warning(comp["warning"])
    else:
        st.json(comp)
else:
    st.info("Held-out comparison unavailable — re-run the pipeline.")

# Feature distribution
st.divider()
st.subheader("🧬 Feature Distributions")
selected_feature = st.selectbox(
    "Select feature to explore",
    options=[c for c in df.columns if c != "label_high_risk"],
)
# Use histogram for continuous features, bar chart for categorical
if df[selected_feature].nunique() > 20:
    # Proper histogram with auto binning (guard constant columns)
    try:
        hist, bins = pd.cut(df[selected_feature], bins=30, retbins=True)
    except ValueError:
        st.bar_chart(df[selected_feature].value_counts())
    else:
        hist_df = hist.value_counts().sort_index()
        hist_df.index = [f"{bins[i]:.1f}–{bins[i+1]:.1f}" for i in range(len(bins) - 1)]
        st.bar_chart(hist_df)
else:
    st.bar_chart(df[selected_feature].value_counts())

# Recommended Actions (security context)
st.divider()
st.subheader("🛡️ Recommended Security Actions")
for action in view["Recommended Actions"]:
    st.markdown(f"▸ {action}")
