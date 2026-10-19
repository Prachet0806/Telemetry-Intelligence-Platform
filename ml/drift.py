# ml/drift.py
"""Drift monitoring (#8): PSI + KS + label-rate vs reference snapshot."""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REF_PATH = PROJECT_ROOT / "data" / "processed" / "reference_stats.json"


def _psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    if not len(expected) or not len(actual):
        return 0.0
    if len(np.unique(expected)) <= 2:
        categories = np.unique(np.concatenate([expected, actual]))
        e = np.asarray([(expected == value).sum() for value in categories], dtype=float)
        a = np.asarray([(actual == value).sum() for value in categories], dtype=float)
    else:
        qs = np.linspace(0, 100, bins + 1)
        interior = np.unique(np.percentile(expected, qs))[1:-1]
        edges = np.concatenate(([-np.inf], interior, [np.inf]))
        e, _ = np.histogram(expected, bins=edges)
        a, _ = np.histogram(actual, bins=edges)
    e = e / max(1, e.sum())
    a = a / max(1, a.sum())
    psi = 0.0
    for ei, ai in zip(e, a):
        ei = max(ei, 1e-4)
        ai = max(ai, 1e-4)
        psi += (ai - ei) * np.log(ai / ei)
    return round(float(psi), 4)


def _ks(a: np.ndarray, b: np.ndarray) -> float:
    try:
        from scipy.stats import ks_2samp  # type: ignore
        return round(float(ks_2samp(a, b).statistic), 4)
    except Exception:
        # Fallback empirical CDF distance
        x = np.sort(np.concatenate([a, b]))
        ca = np.searchsorted(np.sort(a), x) / max(1, len(a))
        cb = np.searchsorted(np.sort(b), x) / max(1, len(b))
        return round(float(np.max(np.abs(ca - cb))), 4)


def save_reference(X: pd.DataFrame, y=None, reference_path: str | Path | None = None) -> dict:
    Xa = X.to_numpy(dtype=float) if isinstance(X, pd.DataFrame) else np.asarray(X, dtype=float)
    cols = list(X.columns) if isinstance(X, pd.DataFrame) else [f"f{i}" for i in range(Xa.shape[1])]
    ref = {"columns": cols, "means": Xa.mean(axis=0).tolist(),
           "samples": Xa[:2000].tolist(),
           "label_rate": float(np.asarray(y).mean()) if y is not None else None,
           "n": int(len(Xa))}
    path = Path(reference_path) if reference_path is not None else REF_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(ref), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
    return ref


def _drift_thresholds() -> dict:
    from decision.config_validation import _load_config
    try:
        return _load_config("config/drift.yaml").get("drift", {})
    except Exception:
        return {}


def check_drift(X: pd.DataFrame, y=None, psi_th: float | None = None,
                ks_th: float | None = None, label_delta: float | None = None,
                reference_path: str | Path | None = None) -> dict:
    thresholds = _drift_thresholds()
    psi_th = float(thresholds.get("psi_threshold", 0.2) if psi_th is None else psi_th)
    ks_th = float(thresholds.get("ks_threshold", 0.1) if ks_th is None else ks_th)
    label_delta = float(thresholds.get("label_rate_delta", 0.05) if label_delta is None else label_delta)
    min_events = int(thresholds.get("min_reference_events", 500))
    path = Path(reference_path) if reference_path is not None else REF_PATH
    if not path.exists():
        return {"drift": False, "reason": "no_reference", "features": {}}
    ref = json.loads(path.read_text(encoding="utf-8"))
    if int(ref.get("n", 0)) < min_events or len(X) < min_events:
        return {
            "drift": False,
            "reason": "insufficient_events",
            "reference_events": int(ref.get("n", 0)),
            "current_events": int(len(X)),
            "minimum_events": min_events,
            "features": {},
        }
    cols = ref.get("columns", [])
    ref_samples = np.asarray(ref.get("samples", []), dtype=float)
    Xa = X.to_numpy(dtype=float) if isinstance(X, pd.DataFrame) else np.asarray(X, dtype=float)
    cur_cols = list(X.columns) if isinstance(X, pd.DataFrame) else []
    feats = {}
    flagged = []
    for j, col in enumerate(cols):
        if col not in cur_cols or j >= Xa.shape[1] or j >= ref_samples.shape[1]:
            continue
        cj = cur_cols.index(col)
        psi = _psi(ref_samples[:, j], Xa[:, cj])
        ks = _ks(ref_samples[:, j], Xa[:, cj])
        bad = psi > psi_th or ks > ks_th
        feats[col] = {"psi": psi, "ks": ks, "drift": bool(bad)}
        if bad:
            flagged.append(col)
    label_flag = False
    if y is not None and ref.get("label_rate") is not None:
        lr = float(np.asarray(y).mean())
        if abs(lr - float(ref["label_rate"])) > label_delta:
            label_flag = True
    return {"drift": bool(flagged or label_flag), "flagged_features": flagged,
            "label_drift": label_flag, "features": feats}
