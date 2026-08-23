import pytest
import yaml

import decision.config_validation as cv


def _write(tmp_path, relative, content):
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        target.write_text(content, encoding="utf-8")
    else:
        target.write_text(yaml.safe_dump(content), encoding="utf-8")


def _skeleton(tmp_path):
    """Minimal valid config set; individual tests break one piece."""
    _write(tmp_path, "config/severity_thresholds.yaml", {
        "thresholds": {
            "critical": {"high_risk_percentage": 20, "anomaly_rate": 0.15, "admin_scope_rate": None},
            "high": {"high_risk_percentage": 10, "admin_scope_rate": None},
            "moderate": {"high_risk_percentage": None, "anomaly_rate": 0.08, "admin_scope_rate": 0.20},
        }
    })
    _write(tmp_path, "config/impact_model.yaml", {
        "impact_model": {
            "base_cost": 100000,
            "multipliers": {k: 1.0 for k in (
                "high_risk_pct_threshold", "high_risk_pct_multiplier",
                "anomaly_rate_threshold", "anomaly_rate_multiplier",
                "large_event_volume", "large_event_multiplier",
                "admin_scope_threshold", "admin_scope_multiplier",
            )},
            "impact_caps": {"critical": None, "high": 2000000,
                            "moderate": 750000, "low": 250000},
        }
    })
    _write(tmp_path, "config/playbooks.yaml", {
        "playbooks": {t: ["do a thing"] for t in ("Critical", "High", "Moderate", "Low")}
    })
    _write(tmp_path, "config/alerts.yaml", {
        "alerts": {"enabled": True, "min_severity": "High", "webhook_url": ""}
    })
    _write(tmp_path, "config/detection.yaml", {
        "detection": {"contamination": 0.05, "random_state": 42}
    })


def _run_on(tmp_path):
    original = cv._ROOT
    cv._ROOT = tmp_path
    try:
        cv.validate_configs()
    finally:
        cv._ROOT = original


def test_valid_config_set_passes(tmp_path):
    _skeleton(tmp_path)
    _run_on(tmp_path)  # must not raise


def test_missing_file_fails_fast(tmp_path):
    _skeleton(tmp_path)
    (tmp_path / "config" / "alerts.yaml").unlink()
    with pytest.raises(ValueError, match="alerts.yaml is missing"):
        _run_on(tmp_path)


def test_inverted_impact_caps_rejected(tmp_path):
    _skeleton(tmp_path)
    data = yaml.safe_load((tmp_path / "config/impact_model.yaml").read_text())
    data["impact_model"]["impact_caps"]["low"] = 3000000
    _write(tmp_path, "config/impact_model.yaml", data)
    with pytest.raises(ValueError, match="impact_caps"):
        _run_on(tmp_path)


def test_unreachable_anomaly_tier_rejected(tmp_path):
    """
    Regression for the 'structurally unreachable severity tier' flaw: an
    anomaly threshold at or below contamination can never fire.
    """
    _skeleton(tmp_path)
    data = yaml.safe_load((tmp_path / "config/detection.yaml").read_text())
    data["detection"]["contamination"] = 0.09   # moderate tier needs > 0.08
    _write(tmp_path, "config/detection.yaml", data)
    with pytest.raises(ValueError, match="can never fire"):
        _run_on(tmp_path)


def test_bad_contamination_range_rejected(tmp_path):
    _skeleton(tmp_path)
    data = yaml.safe_load((tmp_path / "config/detection.yaml").read_text())
    data["detection"]["contamination"] = 1.5
    _write(tmp_path, "config/detection.yaml", data)
    with pytest.raises(ValueError, match=r"\(0, 0\.5\]"):
        _run_on(tmp_path)


def test_playbook_non_string_action_rejected(tmp_path):
    _skeleton(tmp_path)
    data = yaml.safe_load((tmp_path / "config/playbooks.yaml").read_text())
    data["playbooks"]["High"] = [123]
    _write(tmp_path, "config/playbooks.yaml", data)
    with pytest.raises(ValueError, match="playbooks.High"):
        _run_on(tmp_path)


def test_monotonic_severity_thresholds_enforced(tmp_path):
    _skeleton(tmp_path)
    data = yaml.safe_load((tmp_path / "config/severity_thresholds.yaml").read_text())
    data["thresholds"]["high"]["high_risk_percentage"] = 25  # > critical's 20
    _write(tmp_path, "config/severity_thresholds.yaml", data)
    with pytest.raises(ValueError, match="must not increase"):
        _run_on(tmp_path)
