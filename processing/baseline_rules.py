import pandas as pd

def apply_baseline_rules(df: pd.DataFrame) -> pd.Series:
    rules = (
        (df["metadata.resource_count"] > 25) |
        ((df["actor_type"] == "service") & (df["event_type"] == "iam_change")) |
        ((df["metadata.policy_scope"] == "admin") & (df["event_type"] == "iam_change"))
    )
    return rules.astype(int)
