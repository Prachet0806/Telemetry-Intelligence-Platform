# ml/unsupervised.py
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def train_unsupervised_model(
    X,
    contamination: float,
    random_state: int = 42,
    time_values=None,
) -> tuple[Any, Any]:
    """
    Fit an Isolation Forest and return the model plus anomaly flags.

    The rate is measured with held-out scoring so it can genuinely vary:
    fit on a 70% train split (scaled), derive the score threshold at the
    `contamination` percentile of train scores, then flag the FULL matrix
    against that frozen threshold. The reported ``anomaly_rate`` therefore
    moves with the data instead of being pinned to `contamination`.

    Parameters
    ----------
    X : feature matrix/DataFrame (must NOT contain the label column).
    contamination : expected anomaly fraction, 0 < c <= 0.5 (required —
        no stale default; pass config/detection.yaml value).
    random_state : seed for reproducibility.
    """
    if contamination is None or not isinstance(contamination, (int, float)):
        raise ValueError("contamination must be a number in (0, 0.5]")
    if not 0 < float(contamination) <= 0.5:
        raise ValueError("contamination must satisfy 0 < c <= 0.5")
    if isinstance(X, pd.DataFrame) and "label_high_risk" in X.columns:
        raise ValueError("X must not contain the 'label_high_risk' label column")

    X_arr = X.to_numpy(dtype=float) if isinstance(X, pd.DataFrame) else np.asarray(X, dtype=float)
    if X_arr.size == 0:
        raise ValueError("X is empty")
    if not np.isfinite(X_arr).all():
        raise ValueError("X contains NaN or infinite values; clean features first")

    # Fit only on earlier events when timestamps are available. Report rates
    # from later events so training rows do not inflate the monitoring signal.
    n = len(X_arr)
    if time_values is not None:
        times = pd.to_datetime(pd.Series(time_values), utc=True, errors="coerce")
        if len(times) != n or times.isna().all():
            raise ValueError("time_values must contain one parseable timestamp per row")
        order = sorted(range(n), key=lambda i: (pd.isna(times.iloc[i]), times.iloc[i]))
        split_at = max(1, min(n - 1, int(n * 0.7)))
        idx_train, idx_eval = np.asarray(order[:split_at]), np.asarray(order[split_at:])
        if len(idx_eval) == 0:
            raise ValueError("At least two events are required for chronological anomaly scoring")
        X_train = X_arr[idx_train]
    elif n >= 10:
        idx_train, idx_eval = train_test_split(
            np.arange(n), test_size=0.3, random_state=random_state
        )
        X_train = X_arr[idx_train]
    else:
        idx_train, idx_eval = np.arange(n), np.arange(n)
        X_train = X_arr

    model = make_pipeline(
        StandardScaler(),
        IsolationForest(contamination=contamination, random_state=random_state),
    )
    model.fit(X_train)

    # Frozen threshold from train scores; apply to full data.
    scaler = model.named_steps["standardscaler"]
    iso = model.named_steps["isolationforest"]
    train_scores = iso.score_samples(scaler.transform(X_train))
    threshold = float(np.percentile(train_scores, 100.0 * float(contamination)))
    full_scores = iso.score_samples(scaler.transform(X_arr))
    flags = (full_scores <= threshold).astype(int)
    model.evaluation_indices_ = np.asarray(idx_eval)

    if isinstance(X, pd.DataFrame):
        return model, pd.Series(flags, index=X.index)
    return model, flags
