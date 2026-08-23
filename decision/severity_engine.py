# decision/severity_engine.py

from __future__ import annotations
from functools import lru_cache
from pathlib import Path

import yaml

from decision.decision_context import DecisionContext

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "severity_thresholds.yaml"


@lru_cache(maxsize=1)
def _load_thresholds() -> dict:
    with open(_CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)["thresholds"]


def determine_severity(ctx: DecisionContext) -> str:
    """
    Translate pipeline signals into a business severity label.

    Evaluation order: Critical → High → Moderate → Low.
    Thresholds are read from config/severity_thresholds.yaml. Any tier key
    set to null is skipped, so tiers can key off any subset of signals.

    Returns
    -------
    str — one of: "Critical", "High", "Moderate", "Low"
    """
    t = _load_thresholds()

    def _above(tier: dict, signal: str, value: float | None) -> bool:
        threshold = tier.get(signal)
        return value is not None and threshold is not None and value > threshold

    # Critical: any single trigger is enough
    if (
        _above(t["critical"], "high_risk_percentage", ctx.high_risk_percentage)
        or _above(t["critical"], "anomaly_rate", ctx.anomaly_rate)
        or _above(t["critical"], "admin_scope_rate", ctx.admin_scope_rate)
    ):
        return "Critical"

    # High: high-risk % threshold only
    if _above(t["high"], "high_risk_percentage", ctx.high_risk_percentage):
        return "High"

    # Moderate: anomaly rate or sustained elevated privileged activity
    if (
        _above(t["moderate"], "anomaly_rate", ctx.anomaly_rate)
        or _above(t["moderate"], "admin_scope_rate", ctx.admin_scope_rate)
    ):
        return "Moderate"

    return "Low"
