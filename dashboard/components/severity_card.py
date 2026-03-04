# dashboard/components/severity_card.py

import streamlit as st

_SEVERITY_COLOURS = {
    "Critical": "#dc2626",   # red-600
    "High":     "#ea580c",   # orange-600
    "Moderate": "#ca8a04",   # yellow-600
    "Low":      "#16a34a",   # green-600
}

_SEVERITY_ICONS = {
    "Critical": "🔴",
    "High":     "🟠",
    "Moderate": "🟡",
    "Low":      "🟢",
}


def render_severity_card(severity: str, show_description: bool = True) -> None:
    """
    Render a colour-coded severity badge card.

    Parameters
    ----------
    severity : str
        One of Critical / High / Moderate / Low
    show_description : bool
        Whether to show a one-line description beneath the badge
    """
    colour = _SEVERITY_COLOURS.get(severity, "#6b7280")
    icon = _SEVERITY_ICONS.get(severity, "⚪")

    descriptions = {
        "Critical": "Immediate escalation required. Multi-signal validation indicates elevated threat.",
        "High":     "Urgent review warranted. Elevated activity detected across key risk indicators.",
        "Moderate": "Scheduled review recommended. Anomalous patterns observed above baseline.",
        "Low":      "No immediate concern. Signals within expected operational range.",
    }

    st.markdown(
        f"""
        <div style="
            border-left: 6px solid {colour};
            background: {colour}18;
            border-radius: 8px;
            padding: 16px 20px;
            margin-bottom: 16px;
        ">
            <div style="font-size: 1.1rem; font-weight: 700; color: {colour};">
                {icon} Operational Risk Level: {severity.upper()}
            </div>
            {"<div style='margin-top:6px; color:#4b5563; font-size:0.9rem;'>"
             + descriptions.get(severity, "") + "</div>" if show_description else ""}
        </div>
        """,
        unsafe_allow_html=True,
    )
