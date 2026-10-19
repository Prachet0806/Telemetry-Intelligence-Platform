"""Regression tests for the hardening fixes (brief contract, fail-closed
playbooks, always-capped impact, inclusive severity boundaries, SSRF guard,
live CloudWatch path)."""

import pytest

from decision.decision_context import DecisionContext
from reporting.client_brief_builder import build_client_brief
from reporting.stakeholder_views import (
    _parse_high_risk_pct,
    _parse_percent,
    build_context_from_brief,
)
from tests.conftest import make_ctx


def _brief():
    ctx = make_ctx(high_risk_percentage=12.5, anomaly_rate=0.05)
    return build_client_brief("High", 150000.0, ["Do X"], ctx)


def test_brief_carries_machine_readable_raw_block():
    brief = _brief()
    raw = brief["Signal Summary Raw"]
    assert raw["high_risk_percentage"] == pytest.approx(12.5)
    assert raw["anomaly_rate"] == pytest.approx(0.05)
    # Display strings still formatted for humans
    assert brief["Signal Summary"]["High-Risk Event %"] == "12.5%"


def test_context_rebuild_parses_legacy_percent_strings():
    legacy = {
        "Severity": "High",
        "Signal Summary": {
            "Anomaly Rate": "5.0%",
            "High-Risk Event %": "12.5%",
            "Baseline Flag Rate": "10.0%",
            "Total Events Analyzed": 100,
        },
    }
    ctx = build_context_from_brief(legacy, {})
    assert ctx.high_risk_percentage == pytest.approx(12.5)
    assert ctx.anomaly_rate == pytest.approx(0.05)
    assert ctx.baseline_flag_rate == pytest.approx(0.10)
    assert ctx.total_events == 100


def test_percent_parsers():
    assert _parse_percent("5.0%") == pytest.approx(0.05)
    assert _parse_percent(0.05) == pytest.approx(0.05)
    assert _parse_high_risk_pct("12.5%") == pytest.approx(12.5)
    assert _parse_high_risk_pct(0.125) == pytest.approx(12.5)


def test_playbook_fail_closed_and_case_insensitive():
    from decision.action_recommender import recommend_actions

    assert recommend_actions("critical") == recommend_actions("Critical")
    with pytest.raises(ValueError, match="Unknown severity"):
        recommend_actions("Bogus")


def test_impact_always_capped_without_severity():
    from decision.impact_estimator import estimate_impact

    ctx = make_ctx(
        high_risk_percentage=30, anomaly_rate=0.20,
        total_events=5000, admin_scope_rate=0.10,
    )
    assert estimate_impact(ctx) == 250000.0  # Low-cap default, not 3.6M
    assert estimate_impact(ctx, severity="Critical") == 3600000.0
    with pytest.raises(ValueError, match="Unknown severity"):
        estimate_impact(ctx, severity="Bogus")


def test_severity_boundary_inclusive_and_units_validated():
    from decision.severity_engine import determine_severity

    assert determine_severity(make_ctx(high_risk_percentage=10.0)) == "High"
    with pytest.raises(ValueError, match="percent"):
        determine_severity(make_ctx(high_risk_percentage=150.0))


def test_context_range_validation():
    with pytest.raises(ValueError, match="anomaly_rate"):
        DecisionContext(
            baseline_flag_rate=0.1, anomaly_rate=5.0,
            high_risk_percentage=5.0, total_events=10,
        ).validate_ranges()


def test_webhook_ssrf_guard_blocks_metadata_ip():
    from reporting.notifications import send_severity_alert

    brief = {
        "Severity": "Critical",
        "Estimated Financial Exposure": "$1.00",
        "Executive Summary": "x",
        "Recommended Actions": ["a"],
        "Confidence Level": "High",
        "Signal Summary": {},
    }
    cfg = {
        "enabled": True,
        "webhook_url": "http://169.254.169.254/latest/meta-data/",
        "retry_attempts": 1,
        "retry_backoff_seconds": 0,
        "payload_format": "slack",
    }
    assert send_severity_alert(brief, cfg) is False


def test_router_uses_live_events_when_cache_disabled(monkeypatch, tmp_path):
    """cache_to_local=False must still analyse live CW events, not stale cache."""
    import json

    from ingestion import source_router as router
    from tests.conftest import make_valid_event

    raw_path = str(tmp_path / "telemetry.json")
    # Stale local file with 1 low-risk event
    stale = [make_valid_event(event_id="stale-1")]
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(stale, f)

    live = [make_valid_event(event_id=f"live-{i}", risk_level="high") for i in range(5)]
    monkeypatch.setattr(router, "_fetch_and_normalize", lambda cfg: live)
    monkeypatch.setattr(router, "_load_cw_config", lambda: {
        "log_group_name": "g", "lookback_hours": 1, "max_events": 100,
        "filter_pattern": "", "region": "us-east-1",
        "cache_to_local": False, "enabled": True,
    })

    df, stats = router.load_telemetry_auto(raw_path)
    assert stats["data_source"] == "cloudwatch"
    assert stats["valid_events"] == 5
    assert "live-0" in set(df["event_id"])
