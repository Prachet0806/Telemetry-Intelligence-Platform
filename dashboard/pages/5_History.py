# dashboard/pages/5_History.py
"""Historical dashboards (#17): time-series of severity, exposure, anomaly rate."""
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dashboard.auth import require_page
from reporting.run_store import latest_artifact_path

require_page(st, "History")
st.title("History & Trends")

try:
    from reporting.history_store import list_runs, get_brief
    runs = list_runs(limit=100)
except Exception as exc:
    st.error(f"History unavailable: {exc}")
    st.stop()

if not runs:
    st.info("No historical runs yet. Run the pipeline at least twice.")
    st.stop()

df = pd.DataFrame(runs)
st.line_chart(df.set_index("timestamp")[["exposure"]])
st.line_chart(df.set_index("timestamp")[["anomaly_rate", "high_risk_pct"]])
st.dataframe(df, use_container_width=True)

sel = st.selectbox("Inspect run", [r["run_id"] for r in runs])
if sel:
    st.json(get_brief(sel) or {})
    csv_path = latest_artifact_path("metrics.json", PROJECT_ROOT / "data" / "processed")
    try:
        m = json.loads(csv_path.read_text(encoding="utf-8"))
        st.download_button("Download latest metrics.json", json.dumps(m, indent=2), "metrics.json")
    except Exception:
        pass
