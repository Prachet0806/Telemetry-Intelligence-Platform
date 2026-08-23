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
from reporting.stakeholder_views import (
    operations_view,
    render_common_header,
    render_signal_summary,
    render_confidence,
)

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

# Build view from the canonical adapter
view = operations_view(di)

# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

render_common_header(view)

# Risk posture
col_left, col_right = st.columns([2, 1])
with col_left:
    render_severity_card(view["Operational Risk Level"])
with col_right:
    st.metric("Action Window", view["Action Window"])
    st.metric("Estimated Blast Radius", view["Estimated Blast Radius"])

# Action checklist
st.divider()
render_action_panel(view["Action Checklist"], title="Operational Runbook — Required Actions")

# Signal summary
st.divider()
st.subheader("📡 Detection Signal Summary")
render_signal_summary(view["Signal Summary"])

# Confidence
render_confidence(view["Confidence"])