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

st.set_page_config(page_title="Executive | Decision Intelligence", layout="wide")

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

METRICS_PATH = PROJECT_ROOT / "data" / "processed" / "metrics.json"

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

severity = di.get("Severity", "Low")
impact = di.get("Estimated Financial Exposure Raw", 0.0)
actions = di.get("Recommended Actions", [])

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.title("🧑‍💼 Executive Risk Dashboard")
st.caption("Enterprise risk posture, estimated financial exposure, and strategic recommendations.")
st.divider()

# ---------------------------------------------------------------------------
# Risk posture + exposure — hero row
# ---------------------------------------------------------------------------

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Enterprise Risk Level", severity)

with col2:
    st.metric("Estimated Financial Exposure", di.get("Estimated Financial Exposure", "N/A"))

with col3:
    st.metric("Events Analyzed", di.get("Signal Summary", {}).get("Total Events Analyzed", "N/A"))

st.divider()

# ---------------------------------------------------------------------------
# Severity card (visual)
# ---------------------------------------------------------------------------

render_severity_card(severity)
render_impact_card(impact, severity)

# ---------------------------------------------------------------------------
# Priority actions
# ---------------------------------------------------------------------------

st.divider()
render_urgent_actions(actions, n=3)

# ---------------------------------------------------------------------------
# Consulting narrative (GenAI or deterministic)
# ---------------------------------------------------------------------------

st.divider()
st.subheader("🧠 Strategic Intelligence Briefing")

with st.spinner("Generating executive narrative…"):
    narrative = generate_decision_narrative(di)

st.info(narrative)

# ---------------------------------------------------------------------------
# Confidence statement
# ---------------------------------------------------------------------------

st.divider()
st.caption(f"**Intelligence Confidence:** {di.get('Confidence Level', 'N/A')}")
st.caption(
    "This analysis is generated from multi-signal telemetry (deterministic rules, "
    "unsupervised anomaly detection, and supervised risk classification). "
    "Human review is recommended before executing high-impact actions."
)
