# ml/unsupervised.py
from sklearn.ensemble import IsolationForest

def train_unsupervised_model(X):
    model = IsolationForest(contamination=0.05, random_state=42)
    model.fit(X)

    anomalies = model.predict(X)
    # -1 = anomaly, 1 = normal
    return model, (anomalies == -1).astype(int)
