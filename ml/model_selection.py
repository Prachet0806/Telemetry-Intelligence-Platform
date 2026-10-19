# ml/model_selection.py
"""Model selection & hyperparameter tuning (#24).

Compares LogisticRegression vs RandomForest (XGBoost if installed) with
chronological CV, scoring by PR-AUC (average_precision).
Returns the best fitted estimator + report. No new hard dependency: RF is
sklearn-builtin; XGBoost is optional.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.model_selection import TimeSeriesSplit, cross_val_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def _candidates() -> Dict[str, Any]:
    cands: Dict[str, Any] = {
        "logistic": make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42),
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=200, class_weight="balanced_subsample", random_state=42, n_jobs=-1
        ),
    }
    try:
        from xgboost import XGBClassifier  # type: ignore

        cands["xgboost"] = XGBClassifier(
            n_estimators=200, max_depth=5, learning_rate=0.08,
            subsample=0.9, colsample_bytree=0.9, eval_metric="logloss",
            random_state=42, n_jobs=-1,
        )
    except Exception:
        pass
    return cands


def select_best_model(X, y, cv: int = 3, time_values=None) -> Tuple[str, Any, Dict]:
    """Chronological CV over candidates; returns name, estimator, PR-AUC scores."""
    Xa = X.to_numpy(dtype=float) if isinstance(X, pd.DataFrame) else np.asarray(X, dtype=float)
    ya = y.to_numpy() if isinstance(y, pd.Series) else np.asarray(y)
    if len(set(np.unique(ya))) < 2:
        raise ValueError("Need 2 classes for model selection")
    if time_values is not None:
        times = pd.to_datetime(pd.Series(time_values), utc=True, errors="coerce")
        if len(times) != len(ya) or times.isna().all():
            raise ValueError("time_values must contain one parseable timestamp per row")
        if len(ya) < 4:
            raise ValueError("At least four timestamped events are required for chronological CV")
        order = sorted(range(len(times)), key=lambda i: (pd.isna(times.iloc[i]), times.iloc[i]))
        Xa, ya = Xa[order], ya[order]
        splits = TimeSeriesSplit(n_splits=min(max(2, cv), max(2, len(ya) // 5)))
    else:
        raise ValueError("time_values are required; random CV is disabled to avoid temporal leakage")
    scores: Dict[str, float] = {}
    cands = _candidates()
    for name, est in cands.items():
        try:
            s = cross_val_score(
                est, Xa, ya, cv=splits, scoring="average_precision", error_score="raise"
            )
            if not np.isfinite(s).all():
                raise ValueError("non-finite chronological PR-AUC")
            scores[name] = round(float(np.mean(s)), 4)
        except Exception:
            continue
    if not scores:
        raise ValueError("No candidate produced valid chronological cross-validation scores")
    best = max(scores, key=lambda k: scores[k])
    return best, cands[best], scores
