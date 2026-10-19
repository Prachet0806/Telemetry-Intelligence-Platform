# ml/evaluation.py
"""
Honest model evaluation.

All detectors are scored on the SAME held-out test split produced by the
supervised trainer, so numbers are directly comparable and never computed
against the data a model was fitted on.
"""
from typing import Dict, Sequence

from sklearn.metrics import (
    average_precision_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    f1_score,
)


def compute_pr_auc(y_true, y_proba) -> float:
    """Average precision (PR-AUC). Returns 0.0 when undefined."""
    try:
        yt = list(y_true)
        yp = list(y_proba)
        if len(yt) == 0 or len(yt) != len(yp):
            return 0.0
        if len(set(yt)) < 2:
            return 0.0
        return round(float(average_precision_score(yt, yp)), 4)
    except Exception:
        return 0.0


def select_threshold(y_true, y_proba, steps: int = 101) -> Dict:
    """Sweep decision thresholds, return best-F1 operating point.

    Returns {"best_threshold", "best_f1", "best_precision", "best_recall",
    "pr_auc", "curve": [...] (downsampled)}.
    """
    import numpy as np

    yt = np.asarray(list(y_true), dtype=int)
    yp = np.asarray(list(y_proba), dtype=float)
    pr_auc = compute_pr_auc(yt, yp)
    best = {"threshold": 0.5, "f1": 0.0, "precision": 0.0, "recall": 0.0}
    curve = []
    if len(yt) and len(set(yt.tolist())) == 2:
        precision, recall, thresholds = precision_recall_curve(yt, yp)
        for i, t in enumerate(thresholds):
            p = float(precision[i])
            r = float(recall[i])
            f = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
            if f > best["f1"]:
                best = {"threshold": round(float(t), 4), "f1": round(f, 4),
                        "precision": round(p, 4), "recall": round(r, 4)}
        # Downsample curve for metrics.json (every ~10th point, max 20 pts)
        idx = list(range(0, len(thresholds), max(1, len(thresholds) // 20)))
        for i in idx:
            curve.append({"threshold": round(float(thresholds[i]), 4),
                          "precision": round(float(precision[i]), 4),
                          "recall": round(float(recall[i]), 4)})
    return {"best_threshold": best["threshold"], "best_f1": best["f1"],
            "best_precision": best["precision"], "best_recall": best["recall"],
            "pr_auc": pr_auc, "curve": curve}


def evaluate_models_on_holdout(
    y_true,
    baseline_pred,
    supervised_pred,
    supervised_proba=None,
    baseline_proba=None,
) -> Dict:
    """
    Compare the deterministic baseline rules and the supervised classifier
    on identical held-out rows.

    Parameters
    ----------
    y_true : ground-truth labels for the held-out split.
    baseline_pred : baseline-rule flags for those same rows.
    supervised_pred : supervised-model predictions for those same rows.

    Returns
    -------
    dict with per-detector precision / recall / f1 plus split diagnostics.
    """
    def _scores(y_pred) -> Dict[str, float]:
        return {
            "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
            "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
            "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
        }

    y_true_s = list(y_true)
    if len(y_true_s) != len(list(baseline_pred)) or len(y_true_s) != len(list(supervised_pred)):
        raise ValueError("y_true/baseline_pred/supervised_pred length mismatch")
    n_pos = int(sum(1 for v in y_true_s if v == 1))
    result = {
        "evaluation_scope": "held_out_test_split",
        "n_samples": int(len(y_true_s)),
        "n_positives": n_pos,
        "baseline_rules": _scores(baseline_pred),
        "supervised_model": _scores(supervised_pred),
    }
    if supervised_proba is not None:
        try:
            result["supervised_model"]["pr_auc"] = compute_pr_auc(y_true_s, list(supervised_proba))
            result["supervised_model"]["decision_threshold"] = 0.5
        except Exception:
            pass
    if baseline_proba is not None:
        try:
            result["baseline_rules"]["pr_auc"] = compute_pr_auc(y_true_s, list(baseline_proba))
        except Exception:
            pass
    if n_pos == 0:
        result["warning"] = "No positives in holdout; precision/recall are degenerate."
    return result
