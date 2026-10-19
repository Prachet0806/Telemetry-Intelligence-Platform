from decision.impact_estimator import estimate_impact
from tests.conftest import make_ctx


def _inflated_ctx() -> object:
    """Background admin activity + volume inflate the multiplier product."""
    return make_ctx(
        high_risk_percentage=0.3,     # below 15 -> no multiplier
        anomaly_rate=0.05,            # below 0.10 -> no multiplier
        total_events=10000,           # x1.5
        admin_scope_rate=0.06,        # x4
    )


def test_raw_product_is_inflated_by_background_rates():
    # Caps ALWAYS apply now (fail-safe default = Low): 100k * 1.5 * 4 = 600k
    # raw is clamped to the Low cap of 250k.
    assert estimate_impact(_inflated_ctx()) == 250000.0


def test_low_severity_cap_keeps_brief_coherent():
    """
    Regression: LOW severity used to report a $600K exposure driven purely
    by background dataset characteristics. The cap must clamp it.
    """
    assert estimate_impact(_inflated_ctx(), severity="Low") == 250000.0


def test_caps_widen_with_severity():
    ctx = make_ctx(
        high_risk_percentage=30,   # x3
        anomaly_rate=0.20,         # x2
        total_events=5000,         # x1.5
        admin_scope_rate=0.10,     # x4
    )
    raw = estimate_impact(ctx, severity="Critical")  # 100k * 36 = 3.6M uncapped
    assert raw == 3600000.0
    assert estimate_impact(ctx, severity="Moderate") == 750000.0
    assert estimate_impact(ctx, severity="High") == 2000000.0
    assert estimate_impact(ctx, severity="Critical") == 3600000.0


def test_no_severity_argument_keeps_legacy_behaviour():
    assert estimate_impact(make_ctx(total_events=10)) == 100000.0
