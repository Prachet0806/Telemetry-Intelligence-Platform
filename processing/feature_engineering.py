# processing/feature_engineering.py
from collections import Counter, defaultdict, deque

import numpy as np
import pandas as pd


def _freq_map(series: pd.Series) -> dict:
    vc = series.fillna("__missing__").value_counts()
    return vc.to_dict()


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        raise ValueError("engineer_features: input DataFrame is empty")
    required = ["timestamp", "actor_type", "event_type",
                "metadata.resource_count", "metadata.policy_scope", "risk_level"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise KeyError(f"engineer_features: missing columns {missing}")

    features = pd.DataFrame(index=df.index)

    # Temporal features (coerce strings; drop NaT downstream via ML guards)
    ts = pd.to_datetime(df["timestamp"], utc=True, errors="coerce", format="mixed")
    features["hour"] = ts.dt.hour.fillna(12).astype(int)
    features["day_of_week"] = ts.dt.dayofweek.fillna(0).astype(int)
    features["is_off_hours"] = ((features["hour"] < 6) | (features["hour"] > 22)).astype(int)
    # Hour-of-week seasonality (0-167) + weekend flag
    features["hour_of_week"] = (features["day_of_week"] * 24 + features["hour"]).astype(int)
    features["is_weekend"] = (features["day_of_week"] >= 5).astype(int)

    # Actor & event encoding
    features["is_service_actor"] = (df["actor_type"] == "service").astype(int)
    features["is_iam_event"] = (df["event_type"] == "iam_change").astype(int)
    features["is_auth_event"] = (df["event_type"] == "auth").astype(int) if "event_type" in df.columns else 0

    # Scope & impact (clip outliers so raw counts don't dominate linear/distance models)
    rc = pd.to_numeric(df["metadata.resource_count"], errors="coerce").fillna(1).clip(0, 1000)
    features["resource_count"] = rc.astype(int)
    features["resource_count_log"] = rc.apply(lambda v: float(__import__("numpy").log1p(v))).astype(float)
    features["is_admin_scope"] = (df["metadata.policy_scope"] == "admin").astype(int)

    # Causal event-history features: only current and earlier events contribute.
    # Batch-wide counts leak future/holdout event frequencies into earlier rows.
    n_rows = len(df)
    actor_ids = df["actor_id"].fillna("__missing__").astype(str).to_numpy() if "actor_id" in df else np.full(n_rows, "__all__")
    ips = df["source_ip"].fillna("__missing__").astype(str).to_numpy() if "source_ip" in df else np.full(n_rows, "__all__")
    timestamps = ts.tolist()
    order = sorted(range(n_rows), key=lambda i: (pd.isna(timestamps[i]), timestamps[i] if not pd.isna(timestamps[i]) else pd.Timestamp.max.tz_localize("UTC")))
    actor_counts, ip_counts = Counter(), Counter()
    category_counts = {c: Counter() for c in ("region", "resource_type", "action")}
    category_values = {
        c: (df[c].fillna("__missing__").astype(str).to_numpy() if c in df else np.full(n_rows, "__missing__"))
        for c in category_counts
    }
    actor_windows_1h = defaultdict(deque)
    actor_windows_24h = defaultdict(deque)
    actor_total = np.ones(n_rows, dtype=int)
    ip_total = np.ones(n_rows, dtype=int)
    rolling_1h = np.ones(n_rows, dtype=int)
    rolling_24h = np.ones(n_rows, dtype=int)
    category_rates = {c: np.zeros(n_rows, dtype=float) for c in category_counts}
    observed = 0
    for i in order:
        t = timestamps[i]
        actor, ip = actor_ids[i], ips[i]
        actor_total[i] = actor_counts[actor] + 1
        ip_total[i] = ip_counts[ip] + 1
        actor_counts[actor] += 1
        ip_counts[ip] += 1
        if not pd.isna(t):
            window_24h = actor_windows_24h[actor]
            while window_24h and (t - window_24h[0]).total_seconds() > 24 * 3600:
                window_24h.popleft()
            window_1h = actor_windows_1h[actor]
            while window_1h and (t - window_1h[0]).total_seconds() > 3600:
                window_1h.popleft()
            rolling_24h[i] = len(window_24h) + 1
            rolling_1h[i] = len(window_1h) + 1
            window_24h.append(t)
            window_1h.append(t)
        else:
            rolling_1h[i] = rolling_24h[i] = 1
        for col, counts in category_counts.items():
            category_rates[col][i] = counts[category_values[col][i]] / max(1, observed)
            counts[category_values[col][i]] += 1
        observed += 1
    features["actor_event_count"] = actor_total
    features["ip_event_count"] = ip_total
    features["actor_events_1h"] = rolling_1h
    features["actor_events_24h"] = rolling_24h
    features["region_freq"] = category_rates["region"]
    features["resource_freq"] = category_rates["resource_type"]
    features["action_freq"] = category_rates["action"]
    # login_success: 1/0, missing -> 1 (assume success when not an auth event)
    login_col = None
    for cand in ("metadata.login_success", "metadata_login_success"):
        if cand in df.columns:
            login_col = cand
            break
    if login_col is not None:
        features["login_failed"] = (~df[login_col].fillna(True).astype(bool)).astype(int)
    else:
        features["login_failed"] = 0

    # Simple label (for supervised ML)
    features["label_high_risk"] = (df["risk_level"] == "high").astype(int)

    return features
