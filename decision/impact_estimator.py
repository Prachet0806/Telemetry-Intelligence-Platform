# decision/impact_estimator.py

from __future__ import annotations
from functools import lru_cache
from pathlib import Path

import yaml

from decision.decision_context import DecisionContext

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "impact_model.yaml"


@lru_cache(maxsize=1)
def _load_model() -> dict:
    with open(_CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)["impact_model"]


def estimate_impact(ctx: DecisionContext) -> float:
    """
    Estimate the potential financial exposure (USD) for the current incident context.

    Uses heuristic multipliers read from config/impact_model.yaml.
    This is intentionally interpretable — no black-box ML.

    Returns
    -------
    float — estimated USD exposure, rounded to 2 decimal places.
    """
    m = _load_model()
    mults = m["multipliers"]

    cost = float(m["base_cost"])

    # High-risk percentage multiplier
    if ctx.high_risk_percentage > mults["high_risk_pct_threshold"]:
        cost *= mults["high_risk_pct_multiplier"]

    # Anomaly rate multiplier
    if ctx.anomaly_rate > mults["anomaly_rate_threshold"]:
        cost *= mults["anomaly_rate_multiplier"]

    # Large event volume multiplier (blast radius proxy)
    if ctx.total_events > mults["large_event_volume"]:
        cost *= mults["large_event_multiplier"]

    return round(cost, 2)
