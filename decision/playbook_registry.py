# decision/playbook_registry.py

from __future__ import annotations
from functools import lru_cache
from pathlib import Path

import yaml

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "playbooks.yaml"


@lru_cache(maxsize=1)
def load_playbooks() -> dict[str, list[str]]:
    """
    Load and cache the playbook registry from config/playbooks.yaml.

    Returns
    -------
    dict mapping severity label -> list of action strings.
    """
    with open(_CONFIG_PATH, "r") as f:
        data = yaml.safe_load(f)
    return data["playbooks"]


def get_actions_for_severity(severity: str) -> list[str]:
    """
    Convenience wrapper — returns the action list for a given severity label.
    Falls back to the Low playbook if the severity is not found.
    """
    playbooks = load_playbooks()
    return playbooks.get(severity, playbooks.get("Low", ["No immediate action required"]))
