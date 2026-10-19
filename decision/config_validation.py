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
            if key == "high_risk_percentage":
                _require(
                    value is None or (_is_number(value) and 0 <= value <= 100),
                    f"severity_thresholds.yaml: thresholds.{tier}.{key} "
                    "must be a percent in [0, 100] or null",
                )
            else:
                _require(
                    value is None or (_is_number(value) and 0 <= value <= 1),
                    f"severity_thresholds.yaml: thresholds.{tier}.{key} "
                    "must be a fraction in [0, 1] or null",
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
    _require(
        _is_number(model.get("base_cost")) and model.get("base_cost") > 0,
        "impact_model.yaml: base_cost must be a positive number",
    )
    sensitivity = model.get("sensitivity_pct", 0.25)
    _require(
        _is_number(sensitivity) and 0 <= sensitivity <= 1,
        "impact_model.yaml: sensitivity_pct must be in [0, 1]",
    )

    multipliers = model.get("multipliers")
    _require(isinstance(multipliers, dict), "impact_model.yaml: multipliers must be a mapping")
    required = (
        "high_risk_pct_threshold", "high_risk_pct_multiplier",
        "anomaly_rate_threshold", "anomaly_rate_multiplier",
        "large_event_volume", "large_event_multiplier",
        "admin_scope_threshold", "admin_scope_multiplier",
    )
    for key in required:
        v = multipliers.get(key)
        if key in ("large_event_volume",):
            _require(
                _is_number(v) and v >= 0,
                f"impact_model.yaml: multipliers.{key} must be a non-negative number",
            )
        else:
            _require(
                _is_number(v) and v > 0,
                f"impact_model.yaml: multipliers.{key} must be a positive number",
            )

    # Severity caps: optional section; values are positive numbers or null,
    # and caps must widen as severity rises. Keys are lowercase
    # (critical/high/moderate/low); accept Title-case too for robustness.
    caps = model.get("impact_caps")
    if caps is not None:
        _require(isinstance(caps, dict), "impact_model.yaml: impact_caps must be a mapping")
        norm_caps = {str(k).lower(): v for k, v in caps.items()}
        for tier in ("critical", "high", "moderate", "low"):
            value = norm_caps.get(tier)
            _require(
                value is None or (_is_number(value) and value > 0),
                f"impact_model.yaml: impact_caps.{tier} must be a positive number or null",
            )
        present = [
            (norm_caps[tier], tier)
            for tier in ("low", "moderate", "high")
            if norm_caps.get(tier) is not None
        ]
        for (v_a, t_a), (v_b, t_b) in zip(present, present[1:]):
            _require(
                v_a <= v_b,
                f"impact_model.yaml: impact_caps.{t_a} ({v_a}) exceeds "
                f"{t_b} ({v_b}); caps must widen with severity",
            )
        _require(
            "critical" not in norm_caps or norm_caps["critical"] is None or norm_caps["critical"] >= max(
                (v for v in (norm_caps.get("high"),) if v is not None), default=0
            ),
            "impact_model.yaml: impact_caps.critical must be null or the largest cap",
        )


def _validate_playbooks() -> None:
    data = _load_config("config/playbooks.yaml")
    _require("playbooks" in data, "playbooks.yaml: missing 'playbooks' key")
    playbooks = data["playbooks"]
    for tier in _SEVERITY_TIERS:
        actions = playbooks.get(tier)
        _require(isinstance(actions, list) and len(actions) > 0,
                 f"playbooks.yaml: playbooks.{tier} must be a non-empty list")
        ids = []
        dependencies = {}
        for index, a in enumerate(actions, 1):
            _require(isinstance(a, (str, dict)),
                     f"playbooks.yaml: playbooks.{tier} entries must be strings or mappings")
            if isinstance(a, dict):
                _require(isinstance(a.get("title"), str) and bool(a.get("title").strip()),
                         f"playbooks.yaml: playbooks.{tier} dict entries need a 'title'")
            action_id = a.get("id", f"{tier[:3].upper()}-{index}") if isinstance(a, dict) else f"{tier[:3].upper()}-{index}"
            _require(isinstance(action_id, str) and action_id,
                     f"playbooks.yaml: playbooks.{tier} action IDs must be non-empty strings")
            ids.append(action_id)
            deps = a.get("depends_on", []) if isinstance(a, dict) else []
            _require(isinstance(deps, list) and all(isinstance(dep, str) for dep in deps),
                     f"playbooks.yaml: playbooks.{tier} depends_on must be a list of IDs")
            dependencies[action_id] = deps
        _require(len(ids) == len(set(ids)), f"playbooks.yaml: duplicate action IDs in {tier}")
        known = set(ids)
        for action_id, deps in dependencies.items():
            _require(set(deps) <= known,
                     f"playbooks.yaml: {action_id} references unknown dependencies")
        state = {}

        def visit(action_id):
            _require(state.get(action_id) != 1,
                     f"playbooks.yaml: dependency cycle in {tier} at {action_id}")
            if state.get(action_id) == 2:
                return
            state[action_id] = 1
            for dependency in dependencies[action_id]:
                visit(dependency)
            state[action_id] = 2

        for action_id in ids:
            visit(action_id)


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

    The unsupervised rate is measured on held-out scores (see
    ml/unsupervised.py), so it varies around `contamination` instead of
    being pinned to it. Thresholds far above contamination therefore fire
    rarely (low sensitivity); thresholds far below fire constantly (low
    specificity). Both are valid configurations, so this gate fails only
    on nonsensical values and warns otherwise.
    """
    import logging as _logging

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
                _is_number(rate) and 0 < rate <= 1,
                f"detection.yaml: severity '{tier}' anomaly_rate must be in (0, 1], got {rate}",
            )
            if rate > 3 * contamination:
                _logging.getLogger(__name__).warning(
                    "[CONFIG] severity '%s' anomaly_rate %.3f is far above "
                    "contamination %.3f and will fire rarely; consider lowering "
                    "the threshold or raising contamination.",
                    tier, rate, contamination,
                )
            elif rate < contamination / 3:
                _logging.getLogger(__name__).warning(
                    "[CONFIG] severity '%s' anomaly_rate %.3f is far below "
                    "contamination %.3f and will fire on most runs.",
                    tier, rate, contamination,
                )

    return contamination, random_state


def _validate_scheduler() -> None:
    path = _ROOT / "config" / "scheduler.yaml"
    if not path.exists():
        return
    data = _load_config("config/scheduler.yaml")
    cfg = data.get("scheduler")
    _require(isinstance(cfg, dict), "scheduler.yaml: scheduler must be a mapping")
    _require(isinstance(cfg.get("enabled", False), bool), "scheduler.yaml: enabled must be boolean")
    _require(isinstance(cfg.get("run_on_start", True), bool), "scheduler.yaml: run_on_start must be boolean")
    for key in ("interval_hours", "catchup_hours"):
        value = cfg.get(key)
        _require(
            _is_number(value) and value > 0,
            f"scheduler.yaml: {key} must be a positive number",
        )


def _validate_drift() -> None:
    path = _ROOT / "config" / "drift.yaml"
    if not path.exists():
        return
    cfg = _load_config("config/drift.yaml").get("drift")
    _require(isinstance(cfg, dict), "drift.yaml: drift must be a mapping")
    for key in ("psi_threshold", "ks_threshold"):
        value = cfg.get(key)
        _require(_is_number(value) and value > 0, f"drift.yaml: {key} must be positive")
    delta = cfg.get("label_rate_delta")
    _require(_is_number(delta) and 0 <= delta <= 1, "drift.yaml: label_rate_delta must be in [0, 1]")
    minimum = cfg.get("min_reference_events")
    _require(isinstance(minimum, int) and not isinstance(minimum, bool) and minimum > 0,
             "drift.yaml: min_reference_events must be a positive integer")


def _validate_retention_and_roles() -> None:
    retention_path = _ROOT / "config" / "retention.yaml"
    if retention_path.exists():
        cfg = _load_config("config/retention.yaml").get("retention")
        _require(isinstance(cfg, dict), "retention.yaml: retention must be a mapping")
        for key in ("raw_days", "processed_days", "history_days"):
            value = cfg.get(key)
            _require(isinstance(value, int) and not isinstance(value, bool) and value > 0,
                     f"retention.yaml: {key} must be a positive integer")
        _require(isinstance(cfg.get("watermark_keep", True), bool),
                 "retention.yaml: watermark_keep must be boolean")
    roles_path = _ROOT / "config" / "roles.yaml"
    if roles_path.exists():
        data = _load_config("config/roles.yaml")
        users, pages = data.get("users"), data.get("pages")
        _require(isinstance(users, dict) and users, "roles.yaml: users must be a non-empty mapping")
        _require(isinstance(pages, dict) and pages, "roles.yaml: pages must be a non-empty mapping")
        defined_roles = set()
        for username, user in users.items():
            _require(isinstance(username, str) and isinstance(user, dict), "roles.yaml: each user must be a mapping")
            _require(isinstance(user.get("password_env"), str) and user["password_env"],
                     f"roles.yaml: {username} requires password_env")
            _require(isinstance(user.get("role"), str) and user["role"],
                     f"roles.yaml: {username} requires role")
            defined_roles.add(user["role"])
        for page, allowed in pages.items():
            _require(isinstance(page, str) and isinstance(allowed, list),
                     "roles.yaml: page access must be a list of roles")
            _require(all(isinstance(role, str) for role in allowed),
                     f"roles.yaml: page {page!r} role entries must be strings")
            _require(set(allowed) <= defined_roles,
                     f"roles.yaml: page {page!r} references an undefined role")


def _validate_severity_weights() -> None:
    path = _ROOT / "config" / "severity_weights.yaml"
    if not path.exists():
        return
    cfg = _load_config("config/severity_weights.yaml").get("severity_weights")
    _require(isinstance(cfg, dict), "severity_weights.yaml: severity_weights must be a mapping")
    weights = cfg.get("weights")
    _require(isinstance(weights, dict) and weights, "severity_weights.yaml: weights must be a non-empty mapping")
    values = list(weights.values())
    _require(all(_is_number(v) and v >= 0 for v in values),
             "severity_weights.yaml: weights must be non-negative numbers")
    _require(sum(values) > 0, "severity_weights.yaml: at least one weight must be positive")
    bands = cfg.get("bands", {})
    _require(isinstance(bands, dict), "severity_weights.yaml: bands must be a mapping")
    ordered = [bands.get(key) for key in ("moderate", "high", "critical")]
    if all(value is not None for value in ordered):
        _require(all(_is_number(v) and 0 <= v <= 100 for v in ordered),
                 "severity_weights.yaml: severity bands must be in [0, 100]")
        _require(ordered[0] <= ordered[1] <= ordered[2],
                 "severity_weights.yaml: bands must increase from moderate to critical")


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
    _contamination, _random_state = _validate_detection()
    _validate_scheduler()
    _validate_drift()
    _validate_retention_and_roles()
    _validate_severity_weights()
    _validate_optional("config/severity_weights.yaml", "severity_weights")
    _validate_optional("config/scheduler.yaml", "scheduler")
    _validate_optional("config/drift.yaml", "drift")
    _validate_optional("config/retention.yaml", "retention")
    _validate_optional("config/roles.yaml", "users")
    return [
        "severity_thresholds.yaml",
        "impact_model.yaml",
        "playbooks.yaml",
        "alerts.yaml",
        "detection.yaml",
    ]


def _validate_optional(relative_path: str, expected_key: str) -> None:
    path = _ROOT / relative_path
    if not path.exists():
        return
    with open(path, "r") as f:
        data = yaml.safe_load(f)
    _require(isinstance(data, dict) and expected_key in data,
             f"{relative_path}: missing '{expected_key}' key")


if __name__ == "__main__":
    print(f"[CONFIG] Validated: {', '.join(validate_configs())}")
