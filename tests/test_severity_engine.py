import json

from decision.severity_engine import determine_severity
from tests.conftest import make_ctx


def test_low_when_all_signals_quiet():
    assert determine_severity(make_ctx()) == "Low"


def test_critical_on_high_risk_percentage():
    ctx = make_ctx(high_risk_percentage=25.0)
    assert determine_severity(ctx) == "Critical"


def test_critical_on_anomaly_rate():
    ctx = make_ctx(anomaly_rate=0.20)
    assert determine_severity(ctx) == "Critical"


def test_high_tier():
    assert determine_severity(make_ctx(high_risk_percentage=12.0)) == "High"
    # boundary is inclusive (>=): exactly at threshold fires
    assert determine_severity(make_ctx(high_risk_percentage=10.0)) == "High"
    # strictly-below threshold stays lower
    assert determine_severity(make_ctx(high_risk_percentage=9.9)) != "High"


def test_moderate_on_admin_scope_rate():
    assert determine_severity(make_ctx(admin_scope_rate=0.25)) == "Moderate"


def test_null_thresholds_are_skipped():
    # high tier has anomaly_rate: null -> must not escalate on anomaly alone
    assert determine_severity(make_ctx(anomaly_rate=0.10)) == "Moderate"
