# decision/action_recommender.py

from __future__ import annotations

from decision.playbook_registry import get_actions_for_severity


def recommend_actions(severity: str) -> list[str]:
    """
    Return the ordered list of recommended operational actions for a given severity.

    Delegates to the playbook registry so action lists are maintained in
    config/playbooks.yaml — no code changes needed to update runbooks.

    Parameters
    ----------
    severity : str
        One of "Critical", "High", "Moderate", "Low".

    Returns
    -------
    list[str] — ordered list of recommended actions.
    """
    return get_actions_for_severity(severity)
