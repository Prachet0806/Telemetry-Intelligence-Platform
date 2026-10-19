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
from dashboard.auth import require_page
from reporting.run_store import latest_artifact_path

st.set_page_config(page_title="Operations | Decision Intelligence", layout="wide")
require_page(st, "Operations")

# ---------------------------------------------------------------------------
# Load decision intelligence data
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

# Triage status (#13): persisted per-run action state (init_run in pipeline).
st.divider()
st.subheader("🗂️ Triage Status")
try:
    from decision.playbook_registry import get_enriched_actions
    from decision.triage_store import set_status, get_run, allowed_transitions
    from reporting.history_store import list_runs as _list_runs
    _runs = _list_runs(limit=1)
    _run_id = (metrics.get("run_metadata", {}) or {}).get("run_id") or (_runs[0]["run_id"] if _runs else None)
    if _run_id:
        _rows = get_run(_run_id)
        if _rows:
            for _r in _rows:
                _c1, _c2 = st.columns([3, 1])
                _c1.markdown(f"**{_r['title']}** ({_r.get('owner','?')} · {_r.get('priority','?')})")
                _reason = _c1.text_input("Update reason", key=f"triage_reason_{_r['action_id']}")
                _choices = allowed_transitions(_r.get("status", "open") or "open")
                _new = _c2.selectbox("Status", _choices,
                                     index=0,
                                     key=f"triage_{_r['action_id']}")
                if _new != _r.get("status"):
                    actor = f"{st.session_state.get('username', 'unknown')} ({st.session_state.get('role', 'unknown')})"
                    set_status(_run_id, _r["action_id"], _new, actor=actor, reason=_reason)
                    st.rerun()
        else:
            st.info("No triage actions for this run yet.")
    else:
        st.info("Run history unavailable — triage initialises after the next pipeline run.")
except Exception as exc:
    st.warning(f"Triage store unavailable: {exc}")

# Signal summary
st.divider()
st.subheader("📡 Detection Signal Summary")
render_signal_summary(view["Signal Summary"])

# Confidence
render_confidence(view["Confidence"])
