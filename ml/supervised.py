# ml/supervised.py
from typing import Any, Dict, Tuple

from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report

def train_supervised_model(X, y) -> Tuple[Any, Dict[str, Any]]:
    if y.nunique() < 2:
        return None, {
            "warning": "Insufficient class variety for supervised training.",
            "class_counts": y.value_counts().to_dict(),
        }

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, random_state=42
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

    return model, report
