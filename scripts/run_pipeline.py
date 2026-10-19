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
from decision.severity_engine import determine_severity, score_severity
from decision.impact_estimator import estimate_impact, estimate_impact_detailed
from decision.action_recommender import recommend_actions
from decision.playbook_registry import get_enriched_actions
from decision.config_validation import validate_configs
from reporting.client_brief_builder import build_client_brief

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


def _atomic_json_dump(path: Path, payload: dict) -> None:
    """Write JSON atomically so concurrent dashboard reads never see partial files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    os.replace(tmp, path)


def _hash_events(events: list[dict] | None) -> str | None:
    """Stable hash for CloudWatch live events (no local file to hash)."""
    if not events:
        return None
    try:
        canonical = json.dumps(events, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    except Exception:
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
    try:
        with open(DETECTION_CONFIG_PATH, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)["detection"]
        return float(cfg["contamination"]), int(cfg["random_state"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError(
            f"[CONFIG] detection.yaml is unreadable or invalid: {exc}"
        ) from exc


def _parse_args(argv: list[str] | None = None):
    import argparse

    p = argparse.ArgumentParser(description="Run the decision-intelligence pipeline.")
    p.add_argument("--skip-alerts", action="store_true", help="Do not dispatch webhooks.")
    p.add_argument("--output-dir", default=None, help="Override data/processed output dir.")
    p.add_argument("--dry-run", action="store_true", help="Compute without writing artifacts.")
    p.add_argument("--offline", action="store_true", help="Skip CloudWatch even if configured.")
    p.add_argument("--json-logs", action="store_true", help="Structured JSON logging.")
    p.add_argument("--retrain", action="store_true", help="Force reference-stats refresh + model selection.")
    return p.parse_args(sys.argv[1:] if argv is None else argv)


def main(argv: list[str] | None = None) -> int:
    import time as _time

    run_started_wall = datetime.now(timezone.utc)
    run_started_mono = _time.monotonic()
    args = _parse_args(argv)
    if getattr(args, "json_logs", False):
        try:
            from reporting.json_logging import setup_json_logging
            setup_json_logging()
        except Exception:
            pass
    import uuid as _uuid
    run_id = run_started_wall.strftime("%Y%m%dT%H%M%S") + "-" + _uuid.uuid4().hex[:6]

    # ---------------------------------------------------------------
    # Startup: fail fast on misconfigured YAML
    # ---------------------------------------------------------------
    try:
        validate_configs()
    except ValueError as exc:
        print(f"{exc}")
        return 1

    contamination, random_state = _load_detection_settings()
    out_dir = Path(args.output_dir) if args.output_dir else PROCESSED_DIR
    if args.output_dir:
        os.environ["AI_TELEMETRY_DB_PATH"] = str(out_dir / "history.db")
    rejected_path = out_dir / "rejected_events.json"
    mock_output_path = out_dir / "raw" / "mock_telemetry.json" if args.output_dir else None

    # ---------------------------------------------------------------
    # Ingestion (offline flag forces local/mock path)
    # ---------------------------------------------------------------
    from ingestion import source_router as _router

    _orig_fetch = _router._fetch_and_normalize
    if args.offline:
        _router._fetch_and_normalize = lambda cfg: None  # type: ignore
    try:
        df, ingest_stats = load_telemetry_auto(
            raw_path=str(RAW_PATH),
            rejected_path=str(rejected_path),
            dry_run=args.dry_run,
            persist_cache=args.output_dir is None,
            mock_output_path=str(mock_output_path) if mock_output_path else None,
        )
    finally:
        _router._fetch_and_normalize = _orig_fetch

    if df.empty:
        if (
            ingest_stats.get("data_source") == "cloudwatch"
            and int(ingest_stats.get("duplicates_from_prior_runs", 0)) > 0
            and int(ingest_stats.get("cloudwatch_normalization_skipped", 0)) == 0
        ):
            print("[INFO] No new CloudWatch events after event-ID deduplication; no run published.")
            return 0
        print("[ERROR] Pipeline aborted: no valid events after schema validation.")
        return 1

    print("[INFO] Ingestion complete")
    print(f"        Data source    : {ingest_stats.get('data_source', 'local')}")
    print(f"        Total events   : {ingest_stats['total_events']}")
    print(f"        Valid events   : {ingest_stats['valid_events']}")
    print(f"        Invalid events : {ingest_stats['invalid_events']}")

    # ---------------------------------------------------------------
    # Feature engineering
    # ---------------------------------------------------------------
    runs_dir = out_dir / "runs"
    staging_dir = runs_dir / f".{run_id}.tmp"
    final_run_dir = runs_dir / run_id
    features_path = staging_dir / "features.parquet"
    metrics_path = staging_dir / "metrics.json"
    sup_model_path = staging_dir / "supervised_model.joblib"
    unsup_model_path = staging_dir / "unsupervised_model.joblib"
    if not args.dry_run:
        staging_dir.mkdir(parents=True, exist_ok=False)

    try:
        features = engineer_features(df)
    except KeyError as exc:
        print(f"[ERROR] Feature engineering failed (missing column): {exc}")
        return 1
    if not args.dry_run:
        try:
            features.to_parquet(features_path)
        except OSError as exc:
            print(f"[ERROR] Could not write features: {exc}")
            return 1

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
    sup_model, sup_report, sup_split = train_supervised_model(
        X, y, time_values=df["timestamp"]
    )
    unsup_model, unsup_flags = train_unsupervised_model(
        X, contamination=contamination, random_state=random_state,
        time_values=df["timestamp"],
    )
    unsup_eval_idx = getattr(unsup_model, "evaluation_indices_", None)
    if unsup_eval_idx is not None:
        unsup_eval_flags = unsup_flags.iloc[unsup_eval_idx]
    else:
        unsup_eval_flags = unsup_flags
    unsup_anomaly_rate = float(unsup_eval_flags.mean())

    # ---------------------------------------------------------------
    # Persist models
    # ---------------------------------------------------------------
    if not args.dry_run:
        try:
            if sup_model is not None:
                dump(sup_model, sup_model_path)
                print(f"[INFO] Supervised model saved -> {sup_model_path}")
            else:
                print(
                    "[INFO] Supervised model not generated "
                    "(insufficient label variety)."
                )
        except OSError as exc:
            print(f"[ERROR] Could not persist supervised model: {exc}")
            return 1

        try:
            dump(unsup_model, unsup_model_path)
            print(f"[INFO] Unsupervised model saved -> {unsup_model_path}")
        except OSError as exc:
            print(f"[ERROR] Could not persist unsupervised model: {exc}")
            return 1
    else:
        print("[INFO] Dry run — skipping model persistence.")

    # ---------------------------------------------------------------
    # Metrics
    # ---------------------------------------------------------------
    metrics = {
        "ingestion": ingest_stats,
        "baseline": {
            "positive_rate": float(baseline_flags.mean()),
        },
        "unsupervised": {
            "anomaly_rate": unsup_anomaly_rate,
            "contamination": contamination,
            "evaluation_strategy": "chronological_holdout",
            "evaluation_events": int(len(unsup_eval_flags)),
        },
        "supervised": sup_report,
    }
    source_name = str(ingest_stats.get("data_source", "unknown"))
    if source_name == "cloudwatch":
        label_basis = "Rule-derived label assigned by the CloudTrail normalizer; not independently adjudicated."
    elif source_name == "mock":
        label_basis = "Synthetic label assigned by the mock generator; not a real incident outcome."
    else:
        label_basis = "Source-provided risk_level label; provenance and independent review are unverified."
    metrics["label_provenance"] = {
        "target_field": "risk_level",
        "high_risk_class": "high",
        "basis": label_basis,
        "independently_reviewed": False,
    }
    metrics["supervised_evaluation"] = {
        "strategy": (sup_split or {}).get("strategy", "unavailable"),
        "label_provenance": label_basis,
        "interpretation": "Predictive agreement with supplied labels; not validated threat-detection accuracy.",
    }

    # ---------------------------------------------------------------
    # GenAI summary (optional)
    # ---------------------------------------------------------------
    summary_payload = {
        "total_events": len(df),
        "high_risk_count": int(y.sum()),
        "high_risk_percentage": round(float(y.mean() * 100), 2),
    }
    post_publish_error = None
    if args.dry_run:
        metrics["genai_summary"] = None
        metrics["genai_status"] = "skipped_dry_run"
    elif os.getenv("GOOGLE_API_KEY", "").strip():
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
        try:
            baseline_on_test = baseline_flags.reindex(y_test.index)
            if baseline_on_test.isna().any():
                raise KeyError("baseline index misaligned with test split")
        except (KeyError, AttributeError) as exc:
            print(f"[ERROR] Baseline/test alignment failed: {exc}")
            return 1
        metrics["baseline_evaluation"] = evaluate_models_on_holdout(
            y_true=y_test,
            baseline_pred=baseline_on_test,
            supervised_pred=sup_split["supervised_pred"],
            supervised_proba=sup_split.get("supervised_proba"),
        )
    else:
        metrics["baseline_evaluation"] = {
            "warning": (
                "Supervised model unavailable; "
                "held-out comparison skipped."
            )
        }

    # ---------------------------------------------------------------
    # Model selection (#24, reporting-only; LR remains the served model)
    # ---------------------------------------------------------------
    try:
        from ml.model_selection import select_best_model
        if sup_split is None:
            raise ValueError("chronological training split unavailable")
        _X_train = sup_split["X_train"]
        _y_train = sup_split["y_train"]
        _times_train = df.loc[_X_train.index, "timestamp"]
        _best_name, _, _scores = select_best_model(
            _X_train, _y_train, time_values=_times_train
        )
        metrics["model_selection"] = {
            "best": _best_name,
            "pr_auc_cv": _scores,
            "evaluation_scope": "chronological_training_window_only",
        }
    except Exception as exc:
        metrics["model_selection"] = {"warning": f"selection skipped: {exc}"}

    # ---------------------------------------------------------------
    # Drift monitoring (#8) + reference snapshot
    # ---------------------------------------------------------------
    try:
        from ml.drift import save_reference, check_drift
        from pathlib import Path as _P
        _ref = _P(out_dir) / "reference_stats.json"
        if not args.dry_run and (getattr(args, "retrain", False) or not _ref.exists()):
            save_reference(X, y, reference_path=_ref)
            metrics["drift"] = {"drift": False, "reason": "reference_refreshed"}
        elif not _ref.exists():
            metrics["drift"] = {"warning": "reference unavailable; dry run skipped reference creation"}
        else:
            metrics["drift"] = check_drift(X, y, reference_path=_ref)
        if metrics["drift"].get("drift"):
            print(f"[DRIFT] flagged: {metrics['drift'].get('flagged_features')}")
    except Exception as exc:
        metrics["drift"] = {"warning": f"drift skipped: {exc}"}

    # ---------------------------------------------------------------
    # Attribution (#23)
    # ---------------------------------------------------------------
    try:
        from explainability.attribution import top_features
        if sup_model is not None and sup_split is not None:
            metrics["attribution"] = top_features(
                sup_model, sup_split["X_train"], sup_split["y_train"]
            )
    except Exception as exc:
        metrics["attribution"] = {"warning": f"attribution skipped: {exc}"}

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

    admin_scope_rate = None
    if "metadata.policy_scope" in df.columns:
        try:
            admin_scope_rate = float((df["metadata.policy_scope"] == "admin").mean())
        except Exception:
            admin_scope_rate = None

    ctx = DecisionContext(
        baseline_flag_rate=float(metrics["baseline"]["positive_rate"]),
        anomaly_rate=float(metrics["unsupervised"]["anomaly_rate"]),
        high_risk_percentage=summary_payload["high_risk_percentage"],
        total_events=summary_payload["total_events"],
        admin_scope_rate=admin_scope_rate,
        supervised_precision=positive_report.get("precision"),
        supervised_recall=positive_report.get("recall"),
        supervised_f1=positive_report.get("f1-score"),
        supervised_positive_support=(
            int(positive_support) if positive_support is not None else None
        ),
    )

    severity = determine_severity(ctx)
    # Weighted gradation (#10, explainable overlay — cascade stays authoritative)
    try:
        sev_scored = score_severity(ctx)
    except Exception:
        sev_scored = {"score": None, "tier": severity, "contributions": {}}
    metrics["severity_weighted"] = sev_scored
    # Richer impact (#12): breakdown by event_type / region
    try:
        _cat = df["event_type"].value_counts().to_dict() if "event_type" in df.columns else None
        _reg = df["region"].value_counts().to_dict() if "region" in df.columns else None
        impact_detail = estimate_impact_detailed(ctx, severity=severity, by_category=_cat, by_region=_reg)
    except Exception:
        impact_detail = {"point": estimate_impact(ctx, severity=severity), "low": None, "high": None,
                         "contributions": {}, "by_category": {}, "by_region": {}}
    impact = impact_detail["point"]
    metrics["impact_detail"] = impact_detail
    actions = recommend_actions(severity)
    try:
        enriched = get_enriched_actions(severity)
        metrics["triage_actions"] = enriched
    except Exception:
        enriched = []
    brief = build_client_brief(severity, impact, actions, ctx, label_basis=label_basis)
    # Attach gradation + range to brief (additive, no schema break)
    brief["Severity Score"] = sev_scored.get("score")
    brief["Severity Contributions"] = sev_scored.get("contributions", {})
    brief["Weighted Severity Tier"] = sev_scored.get("tier")
    brief["Severity Basis"] = "Tier follows configured cascade thresholds; weighted score is advisory."
    if impact_detail.get("low") is not None:
        brief["Estimated Financial Exposure Range"] = f"${impact_detail['low']:,.2f} - ${impact_detail['high']:,.2f}"
        brief["Impact Breakdown"] = {"by_category": impact_detail.get("by_category", {}),
                                     "by_region": impact_detail.get("by_region", {}),
                                     "contributions": impact_detail.get("contributions", {})}

    metrics["decision_intelligence"] = brief

    print(f"[DECISION] Severity  : {severity}")
    print(f"[DECISION] Exposure  : ${impact:,.2f}")
    print(f"[DECISION] Actions   : {len(actions)} recommended")

    # ---------------------------------------------------------------
    # Alert eligibility is recorded now; dispatch occurs only after publication.
    # ---------------------------------------------------------------
    alert_eligible = False
    if not args.skip_alerts and not args.dry_run:
        try:
            from reporting.notifications import _load_alert_config, should_alert
            alert_eligible = should_alert(
                severity, _load_alert_config()
            )
        except Exception as exc:
            print(f"[WARN] Alert eligibility check failed: {type(exc).__name__}")
    elif args.dry_run:
        print("[INFO] Dry run — skipping alert queue and dispatch.")
    else:
        print("[INFO] Skipping alerts (--skip-alerts).")

    # ---------------------------------------------------------------
    # Audit trail & run metadata
    # ---------------------------------------------------------------
    raw_hash = _file_sha256(RAW_PATH)
    if raw_hash is None and source_name == "mock" and mock_output_path is not None:
        raw_hash = _file_sha256(mock_output_path)
    if raw_hash is None and ingest_stats.get("data_source") == "cloudwatch":
        raw_hash = f"cw-live:{ingest_stats.get('cloudwatch_raw_events', 0)}"
    metrics["run_metadata"] = {
        "pipeline_version": PIPELINE_VERSION,
        "run_id": run_id,
        "git_commit": _git_commit(),
        "python_version": sys.version.split()[0],
        "pandas_version": pd.__version__,
        "numpy_version": np.__version__,
        "sklearn_version": sklearn.__version__,
        "generated_at": run_started_wall.isoformat(),
        "run_duration_seconds": round(_time.monotonic() - run_started_mono, 2),
        "config_hashes": {
            "severity_thresholds": _file_sha256(SEV_CONFIG_PATH),
            "impact_model": _file_sha256(IMPACT_CONFIG_PATH),
            "playbooks": _file_sha256(PLAYBOOKS_CONFIG_PATH),
            "detection": _file_sha256(DETECTION_CONFIG_PATH),
        },
        "raw_events_sha256": raw_hash,
        "alert_sent": None,
        "alert_status": "queued" if alert_eligible else (
            "dry_run" if args.dry_run else (
                "skipped" if args.skip_alerts else "not_eligible_or_disabled"
            )
        ),
        "args": {
            "skip_alerts": args.skip_alerts,
            "offline": args.offline,
            "dry_run": args.dry_run,
            "output_dir": str(out_dir),
        },
    }

    if args.dry_run:
        print("[INFO] Dry run — skipping metrics write.")
    else:
        try:
            metrics["run_metadata"]["artifact_dir"] = str(
                final_run_dir.relative_to(out_dir)
            )
            _atomic_json_dump(metrics_path, metrics)
            manifest = {
                "run_id": run_id,
                "generated_at": run_started_wall.isoformat(),
                "source": ingest_stats.get("data_source", "unknown"),
                "artifacts": [
                    "features.parquet", "metrics.json",
                    "supervised_model.joblib", "unsupervised_model.joblib",
                ],
            }
            _atomic_json_dump(staging_dir / "manifest.json", manifest)
            from reporting.run_store import publish_run
            publish_run(
                staging_dir, final_run_dir, out_dir,
                run_id, run_started_wall.isoformat(),
            )
            features_path = final_run_dir / "features.parquet"
            metrics_path = final_run_dir / "metrics.json"
        except OSError as exc:
            print(f"[ERROR] Could not publish run artifacts: {exc}")
            return 1
        except (ValueError, FileNotFoundError) as exc:
            print(f"[ERROR] Run publication failed: {exc}")
            return 1
        if not args.skip_alerts:
            try:
                from reporting.alert_outbox import enqueue_alert, dispatch_pending
                if alert_eligible:
                    enqueue_alert(run_id, brief)
                delivered = dispatch_pending()
                if delivered.get("sent"):
                    print(f"[ALERT] Outbox dispatched {delivered['sent']} alert(s).")
                elif delivered.get("failed"):
                    print(f"[WARN] Outbox delivery failed for {delivered['failed']} alert(s).")
            except Exception as exc:
                print(f"[WARN] Could not dispatch through alert outbox: {type(exc).__name__}")
                post_publish_error = f"alert outbox persistence failed ({type(exc).__name__})"
        # History + triage persistence (#11, #13) follows publication; failures
        # remain visible and leave the ingestion checkpoint unadvanced.
        try:
            from reporting.history_store import record_run, commit_ingestion_checkpoint
            from decision.triage_store import init_run as _triage_init
            record_run(run_id, brief, {"anomaly_rate": float(metrics["unsupervised"]["anomaly_rate"]),
                                       "high_risk_percentage": summary_payload["high_risk_percentage"],
                                       "total_events": summary_payload["total_events"]})
            if enriched:
                _triage_init(run_id, enriched)
            # Advance the checkpoint only after immutable artifacts and history
            # are durable. A checkpoint failure must be visible so the next run
            # can safely replay the overlapping window.
            if (
                ingest_stats.get("data_source") == "cloudwatch"
                and int(ingest_stats.get("cloudwatch_normalization_skipped", 0)) == 0
                and int(ingest_stats.get("invalid_events", 0)) == 0
            ):
                _ts = pd.to_datetime(df["timestamp"], utc=True, errors="coerce").max()
                if pd.notna(_ts):
                    _records = df[["event_id", "timestamp"]].to_dict("records")
                    commit_ingestion_checkpoint("cloudwatch", _records, _ts.isoformat())
        except Exception as exc:
            print(f"[WARN] History persist failed (continuing): {exc}")
            post_publish_error = f"history/checkpoint persistence failed ({type(exc).__name__})"

    # ---------------------------------------------------------------
    # Completion
    # ---------------------------------------------------------------
    if post_publish_error:
        print("[WARN] Pipeline artifacts were published with follow-up persistence errors.")
    else:
        print("[SUCCESS] Pipeline executed successfully")
    print(f"[ARTIFACT] Features      -> {features_path}")
    print(f"[ARTIFACT] Metrics       -> {metrics_path}")
    print(f"[ARTIFACT] Rejected data -> {rejected_path}")
    if post_publish_error:
        print(f"[ERROR] Run artifacts are published, but {post_publish_error}; retry is safe.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
