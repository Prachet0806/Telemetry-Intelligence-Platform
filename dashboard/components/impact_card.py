# dashboard/components/impact_card.py

import streamlit as st


def render_impact_card(impact: float, severity: str) -> None:
    """
    Render the estimated financial exposure card.

    Parameters
    ----------
    impact : float
        Raw USD exposure value from impact_estimator.
    severity : str
        Used to colour the delta indicator.
    """
    delta_map = {
        "Critical": "⬆ Critical exposure — immediate containment recommended",
        "High":     "⬆ High exposure — urgent review required",
        "Moderate": "⚠ Moderate exposure — monitor and schedule review",
        "Low":      "✓ Low exposure — within acceptable operational range",
    }
    delta_text = delta_map.get(severity, "")

    col1, col2 = st.columns([1, 2])
    with col1:
        st.metric(
            label="💰 Estimated Financial Exposure",
            value=f"${impact:,.0f}",
            delta=delta_text,
            delta_color="inverse" if severity in ("Critical", "High") else "normal",
        )
    with col2:
        st.caption(
            "This estimate is derived from a heuristic impact model using "
            "event volume, risk label distribution, and anomaly rate as inputs. "
            "It represents potential operational loss if the risk is not remediated."
        )
