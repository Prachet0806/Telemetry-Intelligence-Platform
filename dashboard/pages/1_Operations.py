# dashboard/pages/1_Operations.py
# Audience: SRE / Platform Engineering — runbook-oriented, immediate actions

import json
import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dashboard.components.severity_card import render_severity_card
from dashboard.components.impact_card import render_impact_card
from dashboard.components.action_panel import render_action_panel

st.set_page_config(page_title="Operations | Decision Intelligence", layout="wide")

# ---------------------------------------------------------------------------
# Load decision intelligence data
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
    st.error("Decision Intelligence data not found in metrics.json. Re-run the pipeline.")
    st.stop()

severity = di.get("Severity", "Low")
impact = di.get("Estimated Financial Exposure Raw", 0.0)
actions = di.get("Recommended Actions", [])
signals = di.get("Signal Summary", {})

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.title("👷 Operations Command Centre")
st.caption("Runbook-oriented view for SRE and Platform Engineering teams.")
st.divider()

# ---------------------------------------------------------------------------
# Risk posture
# ---------------------------------------------------------------------------

col_left, col_right = st.columns([2, 1])

with col_left:
    render_severity_card(severity)

with col_right:
    urgency_map = {
        "Critical": "⏰ Immediate (< 1 hour)",
        "High":     "🕐 Urgent (< 4 hours)",
        "Moderate": "🗓️ Scheduled (< 24 hours)",
        "Low":      "✅ Routine (next business day)",
    }
    st.metric("Action Window", urgency_map.get(severity, "Unknown"))
    st.metric("Estimated Blast Radius", di.get("Estimated Financial Exposure", "N/A"))

# ---------------------------------------------------------------------------
# Action checklist
# ---------------------------------------------------------------------------

st.divider()
render_action_panel(actions, title="Operational Runbook — Required Actions")

# ---------------------------------------------------------------------------
# Signal summary
# ---------------------------------------------------------------------------

st.divider()
st.subheader("📡 Detection Signal Summary")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Anomaly Rate", signals.get("Anomaly Rate", "N/A"))
c2.metric("High-Risk Events", signals.get("High-Risk Event %", "N/A"))
c3.metric("Baseline Flag Rate", signals.get("Baseline Flag Rate", "N/A"))
c4.metric("Total Events Analyzed", signals.get("Total Events Analyzed", "N/A"))

# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------

st.divider()
st.caption(f"**Confidence:** {di.get('Confidence Level', 'N/A')}")
