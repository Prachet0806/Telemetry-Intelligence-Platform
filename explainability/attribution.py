# explainability/attribution.py
"""Feature attribution (#23): permutation importance (no new dep) + SHAP if installed."""
from __future__ import annotations

import numpy as np


def permutation_importance(model, X, y, top_k: int = 5, seed: int = 42) -> list[dict]:
    """Model-agnostic attribution via single-pass permutation (fast, sklearn-free extra)."""
    import pandas as pd

    rng = np.random.RandomState(seed)
    cols = list(X.columns) if isinstance(X, pd.DataFrame) else [f"f{i}" for i in range(np.asarray(X).shape[1])]
    Xa = X.to_numpy(dtype=float) if isinstance(X, pd.DataFrame) else np.asarray(X, dtype=float)
    ya = y.to_numpy() if isinstance(y, pd.Series) else np.asarray(y)
    try:
        base = float(model.score(Xa, ya))
    except Exception:
        base = 0.0
    drops = []
    for j, col in enumerate(cols):
        Xp = Xa.copy()
        rng.shuffle(Xp[:, j])
        try:
            s = float(model.score(Xp, ya))
        except Exception:
            s = base
        drops.append({"feature": col, "importance": round(max(0.0, base - s), 4)})
    drops.sort(key=lambda d: d["importance"], reverse=True)
    return drops[:top_k]


def shap_top_features(model, X, top_k: int = 5) -> list[dict] | None:
    """SHAP when installed, else None (caller falls back to permutation)."""
    try:
        import shap  # type: ignore
    except Exception:
        return None
    try:
        Xa = X.to_numpy(dtype=float) if hasattr(X, "to_numpy") else np.asarray(X, dtype=float)
        explainer = shap.Explainer(model, Xa)
        vals = explainer(Xa[:100]).values
        mean_abs = np.abs(vals).mean(axis=0)
        cols = list(X.columns) if hasattr(X, "columns") else [f"f{i}" for i in range(Xa.shape[1])]
        ranked = sorted(zip(cols, mean_abs), key=lambda t: float(t[1]), reverse=True)[:top_k]
        return [{"feature": k, "importance": round(float(v), 4)} for k, v in ranked]
    except Exception:
        return None


def top_features(model, X, y, top_k: int = 5) -> dict:
    """Prefer SHAP, fall back to permutation importance."""
    s = shap_top_features(model, X, top_k=top_k)
    if s:
        return {"method": "shap", "features": s}
    return {"method": "permutation", "features": permutation_importance(model, X, y, top_k=top_k)}
