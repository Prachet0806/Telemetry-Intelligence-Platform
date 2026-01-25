# scripts/run_pipeline.py

import json
import sys
from pathlib import Path

from joblib import dump

# -------------------------------------------------------------------
# Project root & imports
# -------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ingestion.load_logs import load_telemetry
from processing.feature_engineering import engineer_features
from processing.baseline_rules import apply_baseline_rules
from ml.supervised import train_supervised_model
from ml.unsupervised import train_unsupervised_model
from ml.evaluation import evaluate_against_baseline
from scripts.generate_mock_telemetry import generate_dataset

# -------------------------------------------------------------------
# Paths
# -------------------------------------------------------------------

RAW_PATH = PROJECT_ROOT / "data" / "raw" / "telemetry_logs.json"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

FEATURES_PATH = PROCESSED_DIR / "features.parquet"
REJECTED_PATH = PROCESSED_DIR / "rejected_events.json"
METRICS_PATH = PROCESSED_DIR / "metrics.json"

SUP_MODEL_PATH = PROCESSED_DIR / "supervised_model.joblib"
UNSUP_MODEL_PATH = PROCESSED_DIR / "unsupervised_model.joblib"

PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# -------------------------------------------------------------------
# Ensure raw data exists
# -------------------------------------------------------------------

if not RAW_PATH.exists():
    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    print("[INFO] No raw telemetry found. Generating mock dataset.")
    generate_dataset(output_path=str(RAW_PATH))

# -------------------------------------------------------------------
# Ingestion
# -------------------------------------------------------------------

df, ingest_stats = load_telemetry(
    str(RAW_PATH),
    rejected_path=str(REJECTED_PATH),
)

if df.empty:
    raise RuntimeError(
        "Pipeline aborted: no valid events after schema validation."
    )

print("[INFO] Ingestion complete")
print(f"        Total events   : {ingest_stats['total_events']}")
print(f"        Valid events   : {ingest_stats['valid_events']}")
print(f"        Invalid events : {ingest_stats['invalid_events']}")

# -------------------------------------------------------------------
# Feature engineering
# -------------------------------------------------------------------

features = engineer_features(df)
features.to_parquet(FEATURES_PATH)

X = features.drop(columns=["label_high_risk"])
y = features["label_high_risk"]

print("[INFO] Label distribution:")
print(y.value_counts().to_string())

# -------------------------------------------------------------------
# Baseline rules
# -------------------------------------------------------------------

baseline_flags = apply_baseline_rules(df)

# -------------------------------------------------------------------
# Machine learning
# -------------------------------------------------------------------

sup_model, sup_report = train_supervised_model(X, y)
unsup_model, unsup_flags = train_unsupervised_model(X)

# -------------------------------------------------------------------
# Persist models
# -------------------------------------------------------------------

if sup_model is not None:
    dump(sup_model, SUP_MODEL_PATH)
    print(f"[INFO] Supervised model saved → {SUP_MODEL_PATH}")
else:
    print(
        "[INFO] Supervised model not generated "
        "(insufficient label variety)."
    )

dump(unsup_model, UNSUP_MODEL_PATH)
print(f"[INFO] Unsupervised model saved → {UNSUP_MODEL_PATH}")

# -------------------------------------------------------------------
# Metrics
# -------------------------------------------------------------------

metrics = {
    "ingestion": ingest_stats,
    "baseline": {
        "positive_rate": float(baseline_flags.mean()),
    },
    "unsupervised": {
        "anomaly_rate": float(unsup_flags.mean()),
    },
    "supervised": sup_report,
}

metrics["baseline_vs_supervised"] = (
    evaluate_against_baseline(y, baseline_flags)
    if sup_model is not None
    else {
        "warning": (
            "Supervised model unavailable; "
            "baseline comparison skipped."
        )
    }
)

with open(METRICS_PATH, "w") as f:
    json.dump(metrics, f, indent=2)

# -------------------------------------------------------------------
# Completion
# -------------------------------------------------------------------

print("[SUCCESS] Pipeline executed successfully")
print(f"[ARTIFACT] Features      → {FEATURES_PATH}")
print(f"[ARTIFACT] Metrics       → {METRICS_PATH}")
print(f"[ARTIFACT] Rejected data → {REJECTED_PATH}")
