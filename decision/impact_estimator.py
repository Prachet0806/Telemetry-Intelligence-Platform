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
    if not isinstance(severity, str) or not severity.strip():
        raise ValueError(f"severity must be a non-empty string, got {severity!r}")
    caps = _load_model().get("impact_caps") or {}
    norm = {str(k).lower(): v for k, v in caps.items()}
    key = severity.strip().lower()
    if key not in ("critical", "high", "moderate", "low"):
        raise ValueError(f"Unknown severity tier: {severity!r}")
    cap = norm.get(key)
    return cost if cap is None else min(cost, float(cap))


def reload_model() -> dict:
    """Clear cached model (tests / config edits)."""
    _load_model.cache_clear()
    return _load_model()


def estimate_impact(ctx: DecisionContext, severity: str | None = None) -> float:
    """Backward-compatible scalar entry point (see estimate_impact_detailed)."""
    return estimate_impact_detailed(ctx, severity=severity)["point"]


def estimate_impact_detailed(
    ctx: DecisionContext,
    severity: str | None = None,
    by_category: dict | None = None,
    by_region: dict | None = None,
) -> dict:
    """Richer impact model (#12): point + sensitivity range + breakdown.

    by_category/by_region map name -> event count share helper; when omitted,
    breakdown is derived from fired multipliers (contributions). Sensitivity
    range is +/- sensitivity_pct (default 25%) around the capped point.
    Returns {"point", "low", "high", "contributions", "by_category", "by_region"}.
    """
    m = _load_model()
    mults = m["multipliers"]
    ctx.validate_ranges()

    cost = float(m["base_cost"])
    contributions: dict = {"base_cost": cost}

    # High-risk percentage multiplier
    if ctx.high_risk_percentage > mults["high_risk_pct_threshold"]:
        cost *= mults["high_risk_pct_multiplier"]
        contributions["high_risk"] = mults["high_risk_pct_multiplier"]

    # Anomaly rate multiplier
    if ctx.anomaly_rate > mults["anomaly_rate_threshold"]:
        cost *= mults["anomaly_rate_multiplier"]
        contributions["anomaly"] = mults["anomaly_rate_multiplier"]

    # Large event volume multiplier (blast radius proxy)
    if ctx.total_events > mults["large_event_volume"]:
        cost *= mults["large_event_multiplier"]
        contributions["volume"] = mults["large_event_multiplier"]

    # Admin scope multiplier (elevated privileged-activity rate)
    if (
        ctx.admin_scope_rate is not None
        and ctx.admin_scope_rate > mults.get("admin_scope_threshold", 0)
    ):
        cost *= mults["admin_scope_multiplier"]
        contributions["admin_scope"] = mults["admin_scope_multiplier"]

    # Caps ALWAYS apply — default to Low (fail-safe, never uncapped by accident).
    sev = severity if severity is not None else "Low"
    cost = _apply_severity_cap(cost, sev)
    point = round(cost, 2)
    sens_value = m.get("sensitivity_pct", 0.25)
    sens = 0.25 if sens_value is None else float(sens_value)
    if not 0 <= sens <= 1:
        raise ValueError("sensitivity_pct must be in [0, 1]")
    low = round(point * (1 - sens), 2)
    high = round(point * (1 + sens), 2)
    # Pro-rate point across categories/regions when shares provided
    def _prorate(shares: dict | None) -> dict:
        if not shares:
            return {}
        normalized = {str(k): max(0.0, float(v)) for k, v in shares.items()}
        tot = sum(normalized.values())
        if tot <= 0:
            return {}
        return {k: round(point * v / tot, 2) for k, v in normalized.items()}
    return {"point": point, "low": low, "high": high,
            "contributions": contributions,
            "by_category": _prorate(by_category),
            "by_region": _prorate(by_region)}
