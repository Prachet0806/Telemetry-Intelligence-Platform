# decision/severity_engine.py

from __future__ import annotations
from functools import lru_cache
from pathlib import Path

import yaml

from decision.decision_context import DecisionContext

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "severity_thresholds.yaml"
_WEIGHTS_PATH = Path(__file__).resolve().parents[1] / "config" / "severity_weights.yaml"


def _validate_unit(signal: str, value: float) -> None:
    """Fail fast on percent/fraction unit swaps."""
    if signal == "high_risk_percentage":
        if not 0 <= value <= 100:
            raise ValueError(
                f"high_risk_percentage must be a percent in [0, 100], got {value}"
            )
    else:
        if not 0 <= value <= 1:
            raise ValueError(f"{signal} must be a fraction in [0, 1], got {value}")


@lru_cache(maxsize=1)
def _load_thresholds() -> dict:
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"[CONFIG] severity_thresholds.yaml unreadable: {exc}") from exc
    if not isinstance(data, dict) or "thresholds" not in data:
        raise ValueError("[CONFIG] severity_thresholds.yaml: missing 'thresholds' key")
    return data["thresholds"]


def reload_thresholds() -> dict:
    """Clear the cached thresholds (tests / config edits)."""
    _load_thresholds.cache_clear()
    _load_weights.cache_clear()
    return _load_thresholds()


@lru_cache(maxsize=1)
def _load_weights() -> dict:
    try:
        with open(_WEIGHTS_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return data.get("severity_weights", {}) or {}


def score_severity(ctx: DecisionContext) -> dict:
    """Weighted severity score (#10): gradation-rich, explainable.

    Returns {"score", "tier", "contributions"}; falls back to equal
    weights when config is absent. Never raises on missing signals.
    """
    ctx.validate_ranges()
    cfg = _load_weights()
    weights = (cfg.get("weights") or {})
    w_hr = float(weights.get("high_risk_percentage", 0.35))
    w_an = float(weights.get("anomaly_rate", 0.25))
    w_ad = float(weights.get("admin_scope_rate", 0.25))
    w_bl = float(weights.get("baseline_flag_rate", 0.15))
    total_w = w_hr + w_an + w_ad + w_bl or 1.0
    c_hr = w_hr * (ctx.high_risk_percentage / 100.0)
    c_an = w_an * float(ctx.anomaly_rate)
    c_ad = w_ad * float(ctx.admin_scope_rate or 0.0)
    c_bl = w_bl * float(ctx.baseline_flag_rate)
    import math
    vol_ref = float(cfg.get("volume_reference", 10000) or 10000)
    vol_bonus = float(cfg.get("volume_max_bonus", 5.0) or 0.0)
    bonus = 0.0
    if ctx.total_events > vol_ref and vol_ref > 0:
        bonus = min(vol_bonus, vol_bonus * math.log10(ctx.total_events / vol_ref + 1))
    score = (c_hr + c_an + c_ad + c_bl) / total_w * 100.0 + bonus
    score = round(max(0.0, min(100.0, score)), 2)
    bands = cfg.get("bands", {}) or {}
    b_crit = float(bands.get("critical", 70))
    b_high = float(bands.get("high", 50))
    b_mod = float(bands.get("moderate", 30))
    tier = "Low"
    if score >= b_crit:
        tier = "Critical"
    elif score >= b_high:
        tier = "High"
    elif score >= b_mod:
        tier = "Moderate"
    return {"score": score, "tier": tier,
            "contributions": {"high_risk_percentage": round(c_hr / total_w * 100, 2),
                              "anomaly_rate": round(c_an / total_w * 100, 2),
                              "admin_scope_rate": round(c_ad / total_w * 100, 2),
                              "baseline_flag_rate": round(c_bl / total_w * 100, 2),
                              "volume_bonus": round(bonus, 2)}}


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
    ctx.validate_ranges()
    t = _load_thresholds()

    def _above(tier: dict, signal: str, value: float | None) -> bool:
        threshold = tier.get(signal)
        if value is None or threshold is None:
            return False
        _validate_unit(signal, value)
        return value >= threshold

    # Critical: any single trigger is enough
    if (
        _above(t["critical"], "high_risk_percentage", ctx.high_risk_percentage)
        or _above(t["critical"], "anomaly_rate", ctx.anomaly_rate)
        or _above(t["critical"], "admin_scope_rate", ctx.admin_scope_rate)
    ):
        return "Critical"

    # High: high-risk % or sustained elevated privileged activity
    if _above(t["high"], "high_risk_percentage", ctx.high_risk_percentage) or _above(
        t["high"], "admin_scope_rate", ctx.admin_scope_rate
    ):
        return "High"

    # Moderate: anomaly rate or sustained elevated privileged activity
    if (
        _above(t["moderate"], "anomaly_rate", ctx.anomaly_rate)
        or _above(t["moderate"], "admin_scope_rate", ctx.admin_scope_rate)
    ):
        return "Moderate"

    return "Low"
