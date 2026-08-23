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
    """Render the held-out baseline-vs-supervised comparison."""
    comp = metrics.get("baseline_evaluation")
    if not comp:
        st.info("Held-out comparison unavailable — re-run the pipeline.")
        return
    if "warning" in comp:
        st.warning(comp["warning"])
    else:
        scope = comp.get("evaluation_scope", "").replace("_", " ")
        if n_pos := comp.get("n_positives"):
            st.caption(
                f"Scored on the held-out test split ({comp.get('n_samples', '?')} rows, "
                f"{n_pos} positive)."
            )
        elif scope:
            st.caption(f"Evaluation scope: {scope}.")
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Baseline Rules**")
            rules = comp.get("baseline_rules", {})
            c1, c2, c3 = st.columns(3)
            c1.metric("Precision", f"{rules.get('precision', 0):.3f}")
            c2.metric("Recall", f"{rules.get('recall', 0):.3f}")
            c3.metric("F1", f"{rules.get('f1', 0):.3f}")
        with col_b:
            st.markdown("**Supervised Model**")
            sup = comp.get("supervised_model", {})
            c1, c2, c3 = st.columns(3)
            c1.metric("Precision", f"{sup.get('precision', 0):.3f}")
            c2.metric("Recall", f"{sup.get('recall', 0):.3f}")
            c3.metric("F1", f"{sup.get('f1', 0):.3f}")
