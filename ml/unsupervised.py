# ml/unsupervised.py
from typing import Any

from sklearn.ensemble import IsolationForest


def train_unsupervised_model(
    X,
    contamination: float = 0.05,
    random_state: int = 42,
) -> tuple[Any, Any]:
    """
    Fit an Isolation Forest and return the model plus anomaly flags.

    Parameters
    ----------
    X : feature matrix/DataFrame.
    contamination : expected anomaly fraction. With a fixed value the
        flagged rate is pinned near this number on every run -- tune it
        together with the severity thresholds that consume `anomaly_rate`
        (config/detection.yaml + config/severity_thresholds.yaml).
    random_state : seed for reproducibility.
    """
    model = IsolationForest(
        contamination=contamination, random_state=random_state
    )
    model.fit(X)

    anomalies = model.predict(X)
    # -1 = anomaly, 1 = normal
    return model, (anomalies == -1).astype(int)
