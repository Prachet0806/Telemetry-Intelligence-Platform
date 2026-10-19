# dashboard/components/metrics_table.py

import streamlit as st
import pandas as pd


def _fmt_rate(value) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "N/A"
    return f"{v:.1%}"


def _fmt_score(value) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return "—"


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
        st.metric("Baseline Flag Rate", _fmt_rate(rate))
    with c2:
        anon = metrics.get("unsupervised", {}).get("anomaly_rate")
        st.metric("Unsupervised Anomaly Rate", _fmt_rate(anon))


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
    if "warning" in comp and "baseline_rules" not in comp:
        st.warning(comp["warning"])
        return
    if "warning" in comp:
        st.warning(comp["warning"])
    scope = comp.get("evaluation_scope", "").replace("_", " ")
    n_pos = comp.get("n_positives", None)
    if n_pos is not None and n_pos > 0:
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
        c1.metric("Precision", _fmt_score(rules.get("precision")))
        c2.metric("Recall", _fmt_score(rules.get("recall")))
        c3.metric("F1", _fmt_score(rules.get("f1")))
    with col_b:
        st.markdown("**Supervised Model**")
        sup = comp.get("supervised_model", {})
        c1, c2, c3 = st.columns(3)
        c1.metric("Precision", _fmt_score(sup.get("precision")))
        c2.metric("Recall", _fmt_score(sup.get("recall")))
        c3.metric("F1", _fmt_score(sup.get("f1")))
        if sup.get("pr_auc") is not None:
            st.metric("PR-AUC", _fmt_score(sup.get("pr_auc")))
    # Threshold selection (#7): best operating point from PR sweep (configurable
    # via ml/evaluation.select_threshold; supervised threshold stays advisory).
    sel = comp.get("threshold_selection")
    if isinstance(sel, dict) and sel.get("best_threshold") is not None:
        st.divider()
        t1, t2, t3, t4 = st.columns(4)
        t1.metric("Best Threshold", _fmt_score(sel.get("best_threshold")))
        t2.metric("Best F1", _fmt_score(sel.get("best_f1")))
        t3.metric("Best Precision", _fmt_score(sel.get("best_precision")))
        t4.metric("Best Recall", _fmt_score(sel.get("best_recall")))
        st.caption(f"PR-AUC: {_fmt_score(sel.get('pr_auc'))} (advisory — edit threshold in code/config, not auto-applied)")
