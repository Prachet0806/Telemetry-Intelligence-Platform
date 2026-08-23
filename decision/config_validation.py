# decision/config_validation.py
"""
Fail-fast validation of the YAML config files used by the decision layer.

Call `validate_configs()` at pipeline startup so misconfiguration surfaces
with a clear message instead of a mid-run KeyError / wrong-severity bug.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]

_SEVERITY_TIERS = ("Critical", "High", "Moderate", "Low")


def _load_config(relative_path: str) -> dict:
    path = _ROOT / relative_path
    if not path.exists():
        raise ValueError(f"{relative_path} is missing")
    with open(path, "r") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{relative_path} must contain a YAML mapping")
    return data


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"[CONFIG] {message}")


def _validate_severity_thresholds() -> None:
    data = _load_config("config/severity_thresholds.yaml")
    _require("thresholds" in data, "severity_thresholds.yaml: missing 'thresholds' key")
    thresholds = data["thresholds"]

    required_tiers = {
        "critical": ["high_risk_percentage", "anomaly_rate", "admin_scope_rate"],
        "high": ["high_risk_percentage", "admin_scope_rate"],
        "moderate": ["anomaly_rate", "admin_scope_rate"],
    }
    for tier, keys in required_tiers.items():
        _require(tier in thresholds, f"severity_thresholds.yaml: missing tier '{tier}'")
        for key in keys:
            value = thresholds[tier].get(key)
            _require(
                value is None or (_is_number(value) and value >= 0),
                f"severity_thresholds.yaml: thresholds.{tier}.{key} "
                "must be a non-negative number or null",
            )

    # Tier sanity: each signal's threshold must loosen monotonically from
    # critical -> moderate, otherwise lower tiers could fire before higher ones.
    for key in ("high_risk_percentage", "anomaly_rate"):
        values = [
            thresholds.get(tier, {}).get(key)
            for tier in ("critical", "high", "moderate")
        ]
        present = [(i, v) for i, v in enumerate(values) if v is not None]
        for (i_a, v_a), (i_b, v_b) in zip(present, present[1:]):
            _require(
                v_a >= v_b,
                f"severity_thresholds.yaml: thresholds.{key} must not increase "
                f"as severity decreases ({v_a} at stricter tier followed by "
                f"{v_b})",
            )


def _validate_impact_model() -> None:
    data = _load_config("config/impact_model.yaml")
    _require("impact_model" in data, "impact_model.yaml: missing 'impact_model' key")
    model = data["impact_model"]
    _require(_is_number(model.get("base_cost")), "impact_model.yaml: base_cost must be a number")

    multipliers = model.get("multipliers")
    _require(isinstance(multipliers, dict), "impact_model.yaml: multipliers must be a mapping")
    required = (
        "high_risk_pct_threshold", "high_risk_pct_multiplier",
        "anomaly_rate_threshold", "anomaly_rate_multiplier",
        "large_event_volume", "large_event_multiplier",
        "admin_scope_threshold", "admin_scope_multiplier",
    )
    for key in required:
        _require(
            _is_number(multipliers.get(key)),
            f"impact_model.yaml: multipliers.{key} must be a number",
        )

    # Severity caps: optional section; values are positive numbers or null,
    # and caps must widen as severity rises.
    caps = model.get("impact_caps")
    if caps is not None:
        _require(isinstance(caps, dict), "impact_model.yaml: impact_caps must be a mapping")
        for tier in _SEVERITY_TIERS:
            value = caps.get(tier)
            _require(
                value is None or (_is_number(value) and value > 0),
                f"impact_model.yaml: impact_caps.{tier} must be a positive number or null",
            )
        present = [
            (caps[tier], tier)
            for tier in ("low", "moderate", "high")
            if caps.get(tier) is not None
        ]
        for (v_a, t_a), (v_b, t_b) in zip(present, present[1:]):
            _require(
                v_a <= v_b,
                f"impact_model.yaml: impact_caps.{t_a} ({v_a}) exceeds "
                f"{t_b} ({v_b}); caps must widen with severity",
            )
        _require(
            "critical" not in caps or caps["critical"] is None or caps["critical"] >= max(
                (v for v in (caps.get("high"),) if v is not None), default=0
            ),
            "impact_model.yaml: impact_caps.critical must be null or the largest cap",
        )


def _validate_playbooks() -> None:
    data = _load_config("config/playbooks.yaml")
    _require("playbooks" in data, "playbooks.yaml: missing 'playbooks' key")
    playbooks = data["playbooks"]
    for tier in _SEVERITY_TIERS:
        actions = playbooks.get(tier)
        _require(
            isinstance(actions, list) and all(isinstance(a, str) for a in actions),
            f"playbooks.yaml: playbooks.{tier} must be a list of strings",
        )


def _validate_alerts() -> None:
    data = _load_config("config/alerts.yaml")
    _require("alerts" in data, "alerts.yaml: missing 'alerts' key")
    alerts = data["alerts"]
    _require(isinstance(alerts.get("enabled", True), bool), "alerts.yaml: alerts.enabled must be boolean")
    min_severity = alerts.get("min_severity", "High")
    _require(
        min_severity in _SEVERITY_TIERS,
        "alerts.yaml: alerts.min_severity must be Critical/High/Moderate/Low",
    )
    webhook = alerts.get("webhook_url", "")
    _require(webhook is None or isinstance(webhook, str), "alerts.yaml: alerts.webhook_url must be a string")

    # Optional retry / backoff settings
    retry = alerts.get("retry_attempts")
    if retry is not None:
        _require(isinstance(retry, int) and retry > 0, "alerts.yaml: alerts.retry_attempts must be a positive integer")
    backoff = alerts.get("retry_backoff_seconds")
    if backoff is not None:
        _require(isinstance(backoff, (int, float)) and backoff >= 0, "alerts.yaml: alerts.retry_backoff_seconds must be a non-negative number")

    # Optional payload format
    fmt = alerts.get("payload_format")
    if fmt is not None:
        _require(fmt in ("slack", "teams", "pagerduty", "generic"), "alerts.yaml: alerts.payload_format must be slack|teams|pagerduty|generic")

    # PagerDuty-specific routing key
    pd_key = alerts.get("pagerduty_routing_key")
    if pd_key is not None:
        _require(isinstance(pd_key, str), "alerts.yaml: alerts.pagerduty_routing_key must be a string")


def _validate_detection() -> tuple[float, float]:
    """
    Validate detection settings and cross-check them against the severity
    thresholds that consume `anomaly_rate`.

    Isolation Forest with fixed `contamination` c flags ~c of events every
    run, so any anomaly_rate tier threshold <= c is structurally unreachable.
    """
    data = _load_config("config/detection.yaml")
    _require("detection" in data, "detection.yaml: missing 'detection' key")
    detection = data["detection"]

    contamination = detection.get("contamination")
    _require(
        _is_number(contamination) and 0 < contamination <= 0.5,
        "detection.yaml: detection.contamination must be a number in (0, 0.5]",
    )
    random_state = detection.get("random_state")
    _require(
        isinstance(random_state, int) and not isinstance(random_state, bool),
        "detection.yaml: detection.random_state must be an integer",
    )

    thresholds = _load_config("config/severity_thresholds.yaml").get("thresholds", {})
    for tier in ("moderate", "critical"):
        rate = thresholds.get(tier, {}).get("anomaly_rate")
        if rate is not None:
            _require(
                rate > contamination,
                f"detection.yaml: severity '{tier}' triggers at anomaly_rate > {rate}, "
                f"but contamination pins the observed rate near {contamination} -- "
                "the tier can never fire. Raise this threshold above contamination "
                "or lower contamination.",
            )

    return contamination, random_state


def validate_configs() -> list[str]:
    """
    Validate all decision-layer YAML configs.

    Raises ValueError on the first problem found (with a clear message).
    Returns the list of validated config names.
    """
    _validate_severity_thresholds()
    _validate_impact_model()
    _validate_playbooks()
    _validate_alerts()
    _validate_detection()
    return [
        "severity_thresholds.yaml",
        "impact_model.yaml",
        "playbooks.yaml",
        "alerts.yaml",
        "detection.yaml",
    ]


if __name__ == "__main__":
    print(f"[CONFIG] Validated: {', '.join(validate_configs())}")
