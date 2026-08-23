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


def _apply_severity_cap(cost: float, severity: str) -> float:
    """
    Clamp the exposure so it can never contradict the assessed severity.

    Multipliers fire on background dataset characteristics (e.g. an elevated
    admin-scope base rate), which can inflate a genuinely LOW-severity run;
    each tier's cap in config/impact_model.yaml holds the reported exposure
    consistent with the brief (a null cap means uncapped).
    """
    caps = _load_model().get("impact_caps") or {}
    # Engine tiers are title-case ("Low"); cap keys in YAML are lowercase.
    cap = caps.get(severity.lower())
    return cost if cap is None else min(cost, float(cap))


def estimate_impact(ctx: DecisionContext, severity: str | None = None) -> float:
    """
    Estimate the potential financial exposure (USD) for the current incident context.

    Uses heuristic multipliers read from config/impact_model.yaml.
    This is intentionally interpretable — no black-box ML.

    Parameters
    ----------
    ctx : pipeline signal context.
    severity : optional assessed severity. When provided, the result is
        clamped to that tier's configured cap so the reported exposure stays
        coherent with the client brief.

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

    # Admin scope multiplier (elevated privileged-activity rate)
    if (
        ctx.admin_scope_rate is not None
        and ctx.admin_scope_rate > mults.get("admin_scope_threshold", 0)
    ):
        cost *= mults["admin_scope_multiplier"]

    if severity is not None:
        cost = _apply_severity_cap(cost, severity)

    return round(cost, 2)
