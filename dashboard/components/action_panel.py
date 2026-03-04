# dashboard/components/action_panel.py

import streamlit as st


def render_action_panel(actions: list[str], title: str = "Recommended Actions") -> None:
    """
    Render an interactive action checklist.

    Parameters
    ----------
    actions : list[str]
        List of recommended action strings from the playbook registry.
    title : str
        Optional panel title override.
    """
    st.subheader(f"📋 {title}")
    if not actions:
        st.info("No actions required at this time.")
        return

    for i, action in enumerate(actions):
        st.checkbox(action, key=f"action_{i}_{action[:20]}", value=False)

    st.caption(
        "Check off actions as they are completed. "
        "State is not persisted between sessions — use your incident tracking system to record progress."
    )


def render_urgent_actions(actions: list[str], n: int = 2) -> None:
    """
    Render the top-N actions as highlighted callouts (for executive / hero sections).
    """
    st.subheader("⚡ Priority Actions")
    for action in actions[:n]:
        st.error(f"▸ {action}" if n <= 2 else action)
    if len(actions) > n:
        st.caption(f"+ {len(actions) - n} additional actions on the Operations page.")
