# ml/supervised.py
from typing import Any, Dict, Tuple

from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report


def train_supervised_model(
    X, y
) -> Tuple[Any, Dict[str, Any], Dict[str, Any] | None]:
    """
    Train the logistic risk classifier on a stratified hold-out split.

    Returns
    -------
    (model, report, split)
        model   : fitted estimator or None when class variety is insufficient.
        report  : classification_report dict on the held-out test split.
        split   : {"y_test", "supervised_pred"} so callers can evaluate other
                  detectors (e.g. baseline rules) on the exact same rows --
                  or None when no model was trained.
    """
    if y.nunique() < 2:
        return None, {
            "warning": "Insufficient class variety for supervised training.",
            "class_counts": y.value_counts().to_dict(),
        }, None

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, random_state=42, stratify=y
    )

    model = LogisticRegression(max_iter=500, class_weight="balanced")
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    report = classification_report(
        y_test,
        y_pred,
        output_dict=True,
        zero_division=0,
    )

    split = {
        "y_test": y_test,
        "supervised_pred": y_pred,
    }

    return model, report, split
