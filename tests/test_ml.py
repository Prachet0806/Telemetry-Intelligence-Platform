import numpy as np
import pandas as pd
import pytest

from ml.evaluation import evaluate_models_on_holdout
from ml.supervised import train_supervised_model
from ml.unsupervised import train_unsupervised_model


def _synthetic(n=4000, seed=0):
    """
    Features correlated with the label but NOT deterministically:
    y = XOR(noisy threshold) so perfect accuracy is impossible and the
    trainer's held-out metrics are meaningful.
    """
    rng = np.random.default_rng(seed)
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    y = ((x1 > 0.3) ^ (rng.random(n) < 0.15)).astype(int)  # ~15% label noise
    X = pd.DataFrame({"x1": x1, "x2": x2, "noise": rng.random(n)})
    return X, pd.Series(y)


def test_supervised_trains_and_returns_held_out_split():
    X, y = _synthetic()
    timestamps = pd.date_range("2026-01-01", periods=len(X), freq="min", tz="UTC")
    model, report, split = train_supervised_model(X, y, time_values=timestamps)

    assert model is not None
    assert "1" in report and "0" in report
    assert split is not None
    y_test = split["y_test"]
    assert len(y_test) == len(split["supervised_pred"])
    assert split["strategy"] == "chronological"
    assert split["X_train"].index.max() < y_test.index.min()
    # held-out metrics are honest (not perfect on noisy labels)
    assert report["1"]["recall"] < 1.0


def test_supervised_skips_single_class():
    X, _ = _synthetic(n=200)
    y = pd.Series([1] * 200)
    model, report, split = train_supervised_model(X, y)

    assert model is None
    assert "warning" in report
    assert split is None


def test_holdout_evaluation_structure_and_symmetry():
    y_true = pd.Series([0, 1, 1, 0, 1])
    baseline = pd.Series([0, 1, 0, 0, 1])
    supervised = pd.Series([0, 1, 1, 0, 0])

    result = evaluate_models_on_holdout(y_true, baseline, supervised)

    assert result["evaluation_scope"] == "held_out_test_split"
    assert result["n_samples"] == 5
    assert result["n_positives"] == 3
    # evaluation module reports scores rounded to 4dp
    assert result["baseline_rules"]["recall"] == pytest.approx(2 / 3, abs=1e-3)
    assert result["supervised_model"]["recall"] == pytest.approx(2 / 3, abs=1e-3)
    assert result["baseline_rules"]["precision"] == pytest.approx(1.0, abs=1e-3)
    assert result["supervised_model"]["precision"] == pytest.approx(1.0, abs=1e-3)


def test_unsupervised_respects_contamination_and_seed():
    X, _ = _synthetic(n=3000)
    _, flags_a = train_unsupervised_model(X, contamination=0.10, random_state=7)
    _, flags_b = train_unsupervised_model(X, contamination=0.10, random_state=7)
    _, flags_c = train_unsupervised_model(X, contamination=0.25, random_state=7)

    rate = flags_a.mean()
    assert 0.05 <= rate <= 0.20           # near requested contamination
    assert (flags_a == flags_b).all()      # reproducible with same seed
    assert flags_c.mean() > rate           # higher contamination -> more flags
