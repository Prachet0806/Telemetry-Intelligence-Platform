# dashboard/components/metrics_table.py

import streamlit as st
import pandas as pd


def render_ingestion_metrics(metrics: dict) -> None:
    """Render ingestion statistics as a clean metric row."""
    ing = metrics.get("ingestion", {})
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Total Events", ing.get("total_events", "N/A"))
    with c2:
        st.metric("Valid Events", ing.get("valid_events", "N/A"))
    with c3:
        st.metric("Invalid Events Dropped", ing.get("invalid_events", "N/A"))


def render_detection_metrics(metrics: dict) -> None:
    """Render baseline + unsupervised detection rates."""
    c1, c2 = st.columns(2)
    with c1:
        rate = metrics.get("baseline", {}).get("positive_rate")
        st.metric(
            "Baseline Flag Rate",
            f"{rate:.1%}" if rate is not None else "N/A",
        )
    with c2:
        anon = metrics.get("unsupervised", {}).get("anomaly_rate")
        st.metric(
            "Unsupervised Anomaly Rate",
            f"{anon:.1%}" if anon is not None else "N/A",
        )


def render_supervised_report(metrics: dict) -> None:
    """Render the supervised model classification report as a DataFrame table."""
    sup = metrics.get("supervised")
    if not sup:
        st.info("Supervised model was not trained (insufficient label variety).")
        return

    rows = []
    for label, values in sup.items():
        if isinstance(values, dict):
            rows.append({"Class": label, **values})

    if rows:
        df = pd.DataFrame(rows).set_index("Class")
        st.dataframe(df.style.format("{:.3f}", na_rep="—"), use_container_width=True)
    else:
        st.json(sup)


def render_baseline_comparison(metrics: dict) -> None:
    """Render baseline vs supervised comparison."""
    comp = metrics.get("baseline_vs_supervised")
    if not comp:
        return
    if "warning" in comp:
        st.warning(comp["warning"])
    else:
        st.json(comp)
