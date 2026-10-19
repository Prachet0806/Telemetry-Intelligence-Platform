# dashboard/pages/3_Executive.py
# Audience: C-Suite / Board — business risk, financial exposure, strategic actions

import json
import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dashboard.components.severity_card import render_severity_card
from dashboard.components.impact_card import render_impact_card
from dashboard.components.action_panel import render_urgent_actions
from reporting.narrative_generator import generate_decision_narrative
from reporting.stakeholder_views import (
    executive_view,
    render_common_header,
    render_confidence,
)
from dashboard.auth import require_page
from reporting.run_store import latest_artifact_path

st.set_page_config(page_title="Executive | Decision Intelligence", layout="wide")
require_page(st, "Executive")

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

METRICS_PATH = latest_artifact_path("metrics.json", PROJECT_ROOT / "data" / "processed")

if not METRICS_PATH.exists():
    st.error("No pipeline output found. Run the pipeline first.")
    st.code("python scripts/run_pipeline.py")
    st.stop()

with open(METRICS_PATH) as f:
    metrics = json.load(f)

di = metrics.get("decision_intelligence")
if not di:
    st.error("Decision Intelligence data not found. Re-run the pipeline.")
    st.stop()

view = executive_view(di)

# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

render_common_header(view)

# Risk posture + exposure — hero row
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Enterprise Risk Level", view["Enterprise Risk Level"])
with col2:
    st.metric("Estimated Financial Exposure", view["Estimated Financial Exposure"])
with col3:
    st.metric("Events Analyzed", di.get("Signal Summary", {}).get("Total Events Analyzed", "N/A"))

st.divider()

# Severity card (visual)
render_severity_card(view["Enterprise Risk Level"])
render_impact_card(
    di.get("Estimated Financial Exposure Raw", 0.0),
    view["Enterprise Risk Level"],
)

# Sensitivity range (#12): low/high band already in the brief.
st.divider()
st.subheader("📐 Exposure Sensitivity")
st.metric("Sensitivity Range", view.get("Exposure Range", "N/A"))
_breakdown = view.get("Impact Breakdown") or {}
if _breakdown.get("by_region"):
    st.bar_chart(_breakdown["by_region"])
    st.caption("Pro-rated exposure by region (shares from latest run).")
if _breakdown.get("by_category"):
    st.caption(f"By category: {_breakdown['by_category']}")
if _breakdown.get("contributions"):
    st.caption(f"Fired multipliers: {_breakdown['contributions']}")

# Priority actions
st.divider()
render_urgent_actions(view["Top Recommendations"], n=3)

# Consulting narrative (GenAI or deterministic)
st.divider()
st.subheader("🧠 Strategic Intelligence Briefing")

with st.spinner("Generating executive narrative…"):
    narrative = generate_decision_narrative(di)

st.info(narrative)

# Confidence statement
render_confidence(view["Confidence"])
st.caption(
    "This analysis is generated from multi-signal telemetry (deterministic rules, "
    "unsupervised anomaly detection, and supervised risk classification). "
    "Human review is recommended before executing high-impact actions."
)
