import pandas as pd

def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    features = pd.DataFrame()

    # Temporal features
    features["hour"] = df["timestamp"].dt.hour
    features["day_of_week"] = df["timestamp"].dt.dayofweek
    features["is_off_hours"] = features["hour"].isin([0,1,2,3,4,22,23]).astype(int)

    # Actor & event encoding
    features["is_service_actor"] = (df["actor_type"] == "service").astype(int)
    features["is_iam_event"] = (df["event_type"] == "iam_change").astype(int)

    # Scope & impact
    features["resource_count"] = df["metadata.resource_count"]
    features["is_admin_scope"] = (df["metadata.policy_scope"] == "admin").astype(int)

    # Simple label (for supervised ML)
    features["label_high_risk"] = (df["risk_level"] == "high").astype(int)

    return features
