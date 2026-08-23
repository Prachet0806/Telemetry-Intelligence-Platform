from processing.baseline_rules import apply_baseline_rules
from processing.feature_engineering import engineer_features


def test_baseline_rules_flag_conditions(events_df):
    flags = apply_baseline_rules(events_df)
    # service + iam_change (i%2 and i%3==0), admin + iam_change (i%10),
    # resource_count > 25 (i%7==0)
    assert flags.sum() > 0
    assert flags.dtype.kind == "i"


def test_baseline_rules_quiet_row():
    import pandas as pd
    from tests.conftest import make_valid_event

    df = pd.json_normalize([make_valid_event()])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    assert apply_baseline_rules(df).sum() == 0


def test_engineer_features_shape_and_label(events_df):
    feats = engineer_features(events_df)

    expected = {
        "hour", "day_of_week", "is_off_hours", "is_service_actor",
        "is_iam_event", "resource_count", "is_admin_scope", "label_high_risk",
    }
    assert set(feats.columns) == expected
    assert len(feats) == len(events_df)
    assert set(feats["label_high_risk"].unique()).issubset({0, 1})
    assert (feats["is_admin_scope"] == (events_df["metadata.policy_scope"] == "admin").astype(int)).all()
