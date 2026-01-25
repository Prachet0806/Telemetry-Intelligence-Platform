from sklearn.metrics import precision_score, recall_score

def evaluate_against_baseline(y_true, y_pred):
    return {
        "precision": precision_score(y_true, y_pred),
        "recall": recall_score(y_true, y_pred),
    }
