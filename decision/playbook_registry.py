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


def _normalize_severity(severity: str) -> str:
    if not isinstance(severity, str) or not severity.strip():
        raise ValueError(f"severity must be a non-empty string, got {severity!r}")
    key = severity.strip().lower()
    mapping = {"critical": "Critical", "high": "High", "moderate": "Moderate", "low": "Low"}
    if key not in mapping:
        raise ValueError(
            f"Unknown severity tier {severity!r}; expected one of {sorted(mapping.values())}"
        )
    return mapping[key]


def _titles(actions) -> list[str]:
    """Normalize string-or-dict playbook entries to title strings."""
    out = []
    for a in actions or []:
        if isinstance(a, str):
            out.append(a)
        elif isinstance(a, dict) and isinstance(a.get("title"), str):
            out.append(a["title"])
    return out


def get_enriched_actions(severity: str) -> list[dict]:
    """Structured triage actions (#13): {id, title, owner, priority, sla_hours, depends_on}."""
    playbooks = load_playbooks()
    norm = _normalize_severity(severity)
    lowered = {str(k).lower(): v for k, v in playbooks.items()}
    actions = lowered.get(norm.lower(), playbooks.get(norm))
    if not isinstance(actions, list) or not actions:
        raise ValueError(f"No playbook actions configured for severity {norm!r}")
    enriched = []
    for i, a in enumerate(actions, 1):
        if isinstance(a, str):
            enriched.append({"id": f"{norm[:3].upper()}-{i}", "title": a,
                             "owner": "on-call", "priority": "P2" if norm in ("Critical", "High") else "P3",
                             "sla_hours": 1 if norm == "Critical" else (4 if norm == "High" else 24),
                             "depends_on": []})
        elif isinstance(a, dict):
            a = dict(a)
            a.setdefault("id", f"{norm[:3].upper()}-{i}")
            a.setdefault("owner", "on-call")
            a.setdefault("priority", "P2")
            a.setdefault("sla_hours", 4)
            a.setdefault("depends_on", [])
            enriched.append(a)
    # Dependency ordering: topological sort by depends_on ids (stable)
    by_id = {e["id"]: e for e in enriched}
    if len(by_id) != len(enriched):
        raise ValueError(f"Duplicate playbook action IDs for severity {norm!r}")
    ordered, state, stack = [], {}, []

    def visit(action_id):
        mark = state.get(action_id, 0)
        if mark == 2:
            return
        if mark == 1:
            cycle = " -> ".join(stack + [action_id])
            raise ValueError(f"Playbook dependency cycle: {cycle}")
        state[action_id] = 1
        stack.append(action_id)
        entry = by_id[action_id]
        dependencies = entry.get("depends_on", []) or []
        if not isinstance(dependencies, list):
            raise ValueError(f"depends_on for {action_id!r} must be a list")
        for dep in dependencies:
            if dep not in by_id:
                raise ValueError(f"Unknown dependency {dep!r} referenced by {action_id!r}")
            visit(dep)
        stack.pop()
        state[action_id] = 2
        ordered.append(entry)

    for entry in enriched:
        visit(entry["id"])
    return ordered


def get_actions_for_severity(severity: str) -> list[str]:
    """
    Convenience wrapper — returns the action list for a given severity label.

    Severity is matched case-insensitively; unknown tiers raise (fail-closed
    so a typo in "Critical" can never silently under-respond with Low).
    """
    playbooks = load_playbooks()
    norm = _normalize_severity(severity)
    # Accept either Title-case or lowercase YAML keys.
    lowered = {str(k).lower(): v for k, v in playbooks.items()}
    actions = lowered.get(norm.lower(), playbooks.get(norm))
    titles = _titles(actions)
    if not titles:
        raise ValueError(f"No playbook actions configured for severity {norm!r}")
    return titles
