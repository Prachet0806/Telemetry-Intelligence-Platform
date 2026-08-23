# ml/evaluation.py
"""
Honest model evaluation.

All detectors are scored on the SAME held-out test split produced by the
supervised trainer, so numbers are directly comparable and never computed
against the data a model was fitted on.
"""
from typing import Dict

from sklearn.metrics import precision_score, recall_score, f1_score


def evaluate_models_on_holdout(
    y_true,
    baseline_pred,
    supervised_pred,
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

    return {
        "evaluation_scope": "held_out_test_split",
        "n_samples": int(len(y_true)),
        "n_positives": int(sum(y_true)),
        "baseline_rules": _scores(baseline_pred),
        "supervised_model": _scores(supervised_pred),
    }
