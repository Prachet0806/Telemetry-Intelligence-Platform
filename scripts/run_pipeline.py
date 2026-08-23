# scripts/run_pipeline.py

import hashlib
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
import yaml
from joblib import dump

# -------------------------------------------------------------------
# Console output — force UTF-8 on Windows so unicode arrows render
# (the default cp1252 codepage raises UnicodeEncodeError on '→').
# -------------------------------------------------------------------

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Surface INFO logs from the source router / connectors (e.g. [SOURCE]).
logging.basicConfig(
    level=logging.INFO, format="%(message)s", stream=sys.stdout, force=True
)

# -------------------------------------------------------------------
# Project root & imports
# -------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ingestion.source_router import load_telemetry_auto
from processing.feature_engineering import engineer_features
from processing.baseline_rules import apply_baseline_rules
from ml.supervised import train_supervised_model
from ml.unsupervised import train_unsupervised_model
from ml.evaluation import evaluate_models_on_holdout
from explainability.genai_explainer import generate_explanation

# Decision Intelligence Layer
from decision.decision_context import DecisionContext
from decision.severity_engine import determine_severity
from decision.impact_estimator import estimate_impact
from decision.action_recommender import recommend_actions
from decision.config_validation import validate_configs
from reporting.client_brief_builder import build_client_brief
from reporting.notifications import send_severity_alert

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

PIPELINE_VERSION = "1.2.0"

SEV_CONFIG_PATH = PROJECT_ROOT / "config" / "severity_thresholds.yaml"
IMPACT_CONFIG_PATH = PROJECT_ROOT / "config" / "impact_model.yaml"
PLAYBOOKS_CONFIG_PATH = PROJECT_ROOT / "config" / "playbooks.yaml"
DETECTION_CONFIG_PATH = PROJECT_ROOT / "config" / "detection.yaml"


def _file_sha256(path: Path) -> str | None:
    """Short content hash of a file, or None if unreadable."""
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()[:16]
    except OSError:
        return None


def _git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() or None
    except Exception:
        return None


def _load_detection_settings() -> tuple[float, int]:
    """Read anomaly-detection settings (already validated at startup)."""
    with open(DETECTION_CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)["detection"]
    return float(cfg["contamination"]), int(cfg["random_state"])


def main() -> int:
    run_started_at = datetime.now(timezone.utc)

    # ---------------------------------------------------------------
    # Startup: fail fast on misconfigured YAML
    # ---------------------------------------------------------------
    try:
        validate_configs()
    except ValueError as exc:
        print(f"{exc}")
        return 1

    contamination, random_state = _load_detection_settings()

    # ---------------------------------------------------------------
    # Ingestion
    # ---------------------------------------------------------------
    df, ingest_stats = load_telemetry_auto(
        raw_path=str(RAW_PATH),
        rejected_path=str(REJECTED_PATH),
    )

    if df.empty:
        raise RuntimeError(
            "Pipeline aborted: no valid events after schema validation."
        )

    print("[INFO] Ingestion complete")
    print(f"        Data source    : {ingest_stats.get('data_source', 'local')}")
    print(f"        Total events   : {ingest_stats['total_events']}")
    print(f"        Valid events   : {ingest_stats['valid_events']}")
    print(f"        Invalid events : {ingest_stats['invalid_events']}")

    # ---------------------------------------------------------------
    # Feature engineering
    # ---------------------------------------------------------------
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    features = engineer_features(df)
    features.to_parquet(FEATURES_PATH)

    X = features.drop(columns=["label_high_risk"])
    y = features["label_high_risk"]

    print("[INFO] Label distribution:")
    print(y.value_counts().to_string())

    # ---------------------------------------------------------------
    # Baseline rules
    # ---------------------------------------------------------------
    baseline_flags = apply_baseline_rules(df)

    # ---------------------------------------------------------------
    # Machine learning
    # ---------------------------------------------------------------
    sup_model, sup_report, sup_split = train_supervised_model(X, y)
    unsup_model, unsup_flags = train_unsupervised_model(
        X, contamination=contamination, random_state=random_state
    )

    # ---------------------------------------------------------------
    # Persist models
    # ---------------------------------------------------------------
    if sup_model is not None:
        dump(sup_model, SUP_MODEL_PATH)
        print(f"[INFO] Supervised model saved -> {SUP_MODEL_PATH}")
    else:
        print(
            "[INFO] Supervised model not generated "
            "(insufficient label variety)."
        )

    dump(unsup_model, UNSUP_MODEL_PATH)
    print(f"[INFO] Unsupervised model saved -> {UNSUP_MODEL_PATH}")

    # ---------------------------------------------------------------
    # Metrics
    # ---------------------------------------------------------------
    metrics = {
        "ingestion": ingest_stats,
        "baseline": {
            "positive_rate": float(baseline_flags.mean()),
        },
        "unsupervised": {
            "anomaly_rate": float(unsup_flags.mean()),
            "contamination": contamination,
        },
        "supervised": sup_report,
    }

    # ---------------------------------------------------------------
    # GenAI summary (optional)
    # ---------------------------------------------------------------
    summary_payload = {
        "total_events": len(df),
        "high_risk_count": int(y.sum()),
        "high_risk_percentage": round(float(y.mean() * 100), 2),
    }
    if os.getenv("GOOGLE_API_KEY"):
        try:
            metrics["genai_summary"] = generate_explanation(summary_payload)
            metrics["genai_status"] = "ok"
        except Exception as exc:
            metrics["genai_summary"] = (
                "GenAI summary unavailable due to an error during generation."
            )
            metrics["genai_status"] = f"error: {type(exc).__name__}"
    else:
        metrics["genai_summary"] = generate_explanation(summary_payload)
        metrics["genai_status"] = "fallback"

    # ---------------------------------------------------------------
    # Held-out comparison: baseline rules vs supervised model,
    # scored on the identical test rows.
    # ---------------------------------------------------------------
    if sup_split is not None:
        y_test = sup_split["y_test"]
        baseline_on_test = baseline_flags.loc[y_test.index]
        metrics["baseline_evaluation"] = evaluate_models_on_holdout(
            y_true=y_test,
            baseline_pred=baseline_on_test,
            supervised_pred=sup_split["supervised_pred"],
        )
    else:
        metrics["baseline_evaluation"] = {
            "warning": (
                "Supervised model unavailable; "
                "held-out comparison skipped."
            )
        }

    # ---------------------------------------------------------------
    # Decision Intelligence Layer
    # ---------------------------------------------------------------
    print("[INFO] Running Decision Intelligence Layer...")

    # Positive-class ("high risk") metrics -- weighted averages hide the
    # minority class this system exists to detect.
    positive_report = (
        sup_report.get("1", {}) if isinstance(sup_report, dict) else {}
    )
    positive_support = positive_report.get("support")

    ctx = DecisionContext(
        baseline_flag_rate=float(metrics["baseline"]["positive_rate"]),
        anomaly_rate=float(metrics["unsupervised"]["anomaly_rate"]),
        high_risk_percentage=summary_payload["high_risk_percentage"],
        total_events=summary_payload["total_events"],
        admin_scope_rate=float((df["metadata.policy_scope"] == "admin").mean()),
        supervised_precision=positive_report.get("precision"),
        supervised_recall=positive_report.get("recall"),
        supervised_f1=positive_report.get("f1-score"),
        supervised_positive_support=(
            int(positive_support) if positive_support is not None else None
        ),
    )

    severity = determine_severity(ctx)
    impact   = estimate_impact(ctx, severity=severity)
    actions  = recommend_actions(severity)
    brief    = build_client_brief(severity, impact, actions, ctx)

    metrics["decision_intelligence"] = brief

    print(f"[DECISION] Severity  : {severity}")
    print(f"[DECISION] Exposure  : ${impact:,.2f}")
    print(f"[DECISION] Actions   : {len(actions)} recommended")

    # ---------------------------------------------------------------
    # Alerting (best-effort; never blocks or crashes the pipeline)
    # ---------------------------------------------------------------
    alert_sent = send_severity_alert(brief)
    if alert_sent:
        print(f"[ALERT] Severity {severity} alert dispatched.")

    # ---------------------------------------------------------------
    # Audit trail & run metadata
    # ---------------------------------------------------------------
    metrics["run_metadata"] = {
        "pipeline_version": PIPELINE_VERSION,
        "git_commit": _git_commit(),
        "python_version": sys.version.split()[0],
        "pandas_version": pd.__version__,
        "numpy_version": np.__version__,
        "sklearn_version": sklearn.__version__,
        "generated_at": run_started_at.isoformat(),
        "run_duration_seconds": round(time.time() - run_started_at.timestamp(), 2),
        "config_hashes": {
            "severity_thresholds": _file_sha256(SEV_CONFIG_PATH),
            "impact_model": _file_sha256(IMPACT_CONFIG_PATH),
            "playbooks": _file_sha256(PLAYBOOKS_CONFIG_PATH),
            "detection": _file_sha256(DETECTION_CONFIG_PATH),
        },
        "raw_events_sha256": _file_sha256(RAW_PATH),
        "alert_sent": alert_sent,
    }

    with open(METRICS_PATH, "w") as f:
        json.dump(metrics, f, indent=2)

    # ---------------------------------------------------------------
    # Completion
    # ---------------------------------------------------------------
    print("[SUCCESS] Pipeline executed successfully")
    print(f"[ARTIFACT] Features      -> {FEATURES_PATH}")
    print(f"[ARTIFACT] Metrics       -> {METRICS_PATH}")
    print(f"[ARTIFACT] Rejected data -> {REJECTED_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
