# ml/supervised.py
from typing import Any, Dict, Tuple

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

MIN_POSITIVE_FOR_STRATIFY = 2
MIN_POSITIVE_SUPPORT_WARN = 30


def train_supervised_model(
    X, y, time_values=None
) -> Tuple[Any, Dict[str, Any], Dict[str, Any] | None]:
    """
    Train the logistic risk classifier on a chronological hold-out split.

    Guards: rejects label leakage (label col in X), NaN/inf, single class,
    and too-few positives for a meaningful holdout. Features are standardized
    inside a Pipeline (fit on train only).

    Returns
    -------
    (model, report, split)
        model   : fitted Pipeline or None when class variety is insufficient.
        report  : classification_report dict on the held-out test split.
        split   : {"y_test", "supervised_pred"} so callers can evaluate other
                  detectors (e.g. baseline rules) on the exact same rows --
                  or None when no model was trained.
    """
    if isinstance(X, pd.DataFrame) and "label_high_risk" in X.columns:
        raise ValueError("X must not contain the 'label_high_risk' label column")
    X_arr = X.to_numpy(dtype=float) if isinstance(X, pd.DataFrame) else np.asarray(X, dtype=float)
    y_arr = y.to_numpy() if isinstance(y, pd.Series) else np.asarray(y)
    if len(X_arr) != len(y_arr):
        raise ValueError("X and y length mismatch")
    if not np.isfinite(X_arr).all():
        raise ValueError("X contains NaN or infinite values; clean features first")

    counts = pd.Series(y_arr).value_counts()
    if len(counts) < 2:
        return None, {
            "warning": "Insufficient class variety for supervised training.",
            "class_counts": {str(k): int(v) for k, v in counts.items()},
        }, None
    if int(counts.min()) < MIN_POSITIVE_FOR_STRATIFY:
        return None, {
            "warning": "Minority class too small for stratified split.",
            "class_counts": {str(k): int(v) for k, v in counts.items()},
        }, None

    if time_values is not None:
        times = pd.to_datetime(pd.Series(time_values), utc=True, errors="coerce")
        if len(times) != len(y_arr) or times.isna().all():
            raise ValueError("time_values must contain one parseable timestamp per row")
        if len(times) < 3:
            return None, {
                "warning": "At least three timestamped events are required for a chronological split.",
                "class_counts": {str(k): int(v) for k, v in counts.items()},
            }, None
        order = sorted(range(len(times)), key=lambda i: (pd.isna(times.iloc[i]), times.iloc[i]))
        split_at = max(1, min(len(order) - 1, int(len(order) * 0.7)))
        train_idx, test_idx = order[:split_at], order[split_at:]
        if len(np.unique(y_arr[train_idx])) < 2:
            return None, {
                "warning": "Chronological training window contains only one class; model not trained.",
                "class_counts": {str(k): int(v) for k, v in counts.items()},
            }, None
        if isinstance(X, (pd.DataFrame, pd.Series)):
            X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
            y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]
        else:
            X_arr, y_arr = np.asarray(X_arr), np.asarray(y_arr)
            X_train, X_test = X_arr[train_idx], X_arr[test_idx]
            y_train, y_test = y_arr[train_idx], y_arr[test_idx]
        split_strategy = "chronological"
    else:
        raise ValueError(
            "time_values are required; random splits are disabled to avoid temporal leakage"
        )

    model = make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42),
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    try:
        y_proba = model.predict_proba(X_test)[:, 1]
    except Exception:
        y_proba = None
    report = classification_report(
        y_test,
        y_pred,
        output_dict=True,
        zero_division=0,
    )
    if isinstance(y_test, pd.Series) and int((y_test == 1).sum()) < MIN_POSITIVE_SUPPORT_WARN:
        report["warning"] = (
            f"Only {int((y_test == 1).sum())} positives in holdout; "
            "treat minority-class metrics as indicative only."
        )

    split = {
        "y_test": y_test,
        "supervised_pred": y_pred,
        "supervised_proba": y_proba,
        "strategy": split_strategy,
        "X_train": X_train,
        "y_train": y_train,
    }

    return model, report, split
