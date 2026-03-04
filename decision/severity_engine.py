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

    Evaluation order: Critical → High → Moderate → Low
    Thresholds are read from config/severity_thresholds.yaml.

    Returns
    -------
    str — one of: "Critical", "High", "Moderate", "Low"
    """
    t = _load_thresholds()

    # Critical: any single trigger is enough
    if (
        ctx.high_risk_percentage > t["critical"]["high_risk_percentage"]
        or ctx.anomaly_rate > t["critical"]["anomaly_rate"]
    ):
        return "Critical"

    # High: high-risk % threshold only
    if ctx.high_risk_percentage > t["high"]["high_risk_percentage"]:
        return "High"

    # Moderate: anomaly rate threshold only
    if ctx.anomaly_rate > t["moderate"]["anomaly_rate"]:
        return "Moderate"

    return "Low"
