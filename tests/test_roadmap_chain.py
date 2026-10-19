# tests/test_roadmap_chain.py — coverage for roadmap chain (#7,#5,#10,#12,#13,#11,#8,#23,#24,#16,#2,#3,#18)
import pandas as pd


def _ctx():
    from decision.decision_context import DecisionContext
    return DecisionContext(baseline_flag_rate=0.1, anomaly_rate=0.1,
                           high_risk_percentage=5.0, total_events=500, admin_scope_rate=0.1)


def test_eval_pr_auc_and_threshold():
    from ml.evaluation import compute_pr_auc, select_threshold, evaluate_models_on_holdout
    y = [0, 0, 1, 1, 0, 1]
    p = [0.1, 0.2, 0.8, 0.7, 0.3, 0.9]
    assert compute_pr_auc(y, p) > 0.5
    sel = select_threshold(y, p)
    assert 0 <= sel["best_threshold"] <= 1 and sel["pr_auc"] > 0.5
    r = evaluate_models_on_holdout(y, [0, 0, 1, 1, 0, 0], [0, 0, 1, 1, 0, 1], supervised_proba=p)
    assert "threshold_selection" in r and "pr_auc" in r["supervised_model"]


def test_expanded_features_present(events_df):
    from processing.feature_engineering import engineer_features
    feats = engineer_features(events_df)
    for col in ("hour_of_week", "is_weekend", "actor_event_count", "ip_event_count",
                "actor_events_1h", "region_freq", "login_failed"):
        assert col in feats.columns


def test_weighted_severity_gradation():
    from decision.severity_engine import score_severity
    lo = score_severity(_ctx())
    assert lo["tier"] in ("Low", "Moderate", "High", "Critical") and 0 <= lo["score"] <= 100
    assert set(lo["contributions"]) >= {"high_risk_percentage", "anomaly_rate"}


def test_impact_detailed_range():
    from decision.impact_estimator import estimate_impact, estimate_impact_detailed
    d = estimate_impact_detailed(_ctx(), severity="Low", by_region={"us-east-1": 3, "eu-west-1": 1})
    assert d["low"] <= d["point"] <= d["high"]
    assert abs(sum(d["by_region"].values()) - d["point"]) < 1.0
    assert estimate_impact(_ctx(), severity="Low") == d["point"]


def test_triage_enriched_and_store(tmp_path):
    from decision.playbook_registry import get_enriched_actions, get_actions_for_severity
    from decision.triage_store import init_run, set_status, get_run
    assert len(get_actions_for_severity("High")) >= 1
    enriched = get_enriched_actions("High")
    assert all({"id", "title", "owner", "priority"} <= set(a) for a in enriched)
    db = tmp_path / "t.db"
    init_run("r1", enriched, db_path=db)
    set_status("r1", enriched[0]["id"], "done", db_path=db)
    rows = get_run("r1", db_path=db)
    assert rows[0]["status"] in ("open", "done")


def test_history_and_watermark(tmp_path):
    from reporting.history_store import record_run, list_runs, get_brief, set_watermark, get_watermark
    db = tmp_path / "h.db"
    brief = {"Severity": "Low", "Estimated Financial Exposure Raw": 10.0, "Generated At": "2026-01-01T00:00:00+00:00"}
    record_run("r1", brief, {"anomaly_rate": 0.1, "high_risk_pct": 1.0, "total_events": 5}, db_path=db)
    assert list_runs(db_path=db)[0]["run_id"] == "r1"
    assert get_brief("r1", db_path=db)["Severity"] == "Low"
    set_watermark("cloudwatch", "2026-01-02T00:00:00+00:00", db_path=db)
    assert get_watermark(db_path=db).startswith("2026")


def test_drift_and_attribution(events_df):
    from processing.feature_engineering import engineer_features
    from ml.drift import save_reference, check_drift
    from ml.supervised import train_supervised_model
    from explainability.attribution import top_features
    feats = engineer_features(events_df)
    X, y = feats.drop(columns=["label_high_risk"]), feats["label_high_risk"]
    if int(y.sum()) >= 2 and int((y == 0).sum()) >= 2:
        save_reference(X.head(200), y.head(200))
        assert "drift" in check_drift(X.head(200), y.head(200))
        m, _, _ = train_supervised_model(X, y)
        if m is not None:
            t = top_features(m, X.head(100), y.head(100))
            assert t["features"]


def test_model_selection_and_adapters(tmp_path):
    import numpy as np
    from ml.model_selection import select_best_model
    rng = np.random.RandomState(0)
    X = pd.DataFrame(rng.randn(60, 4), columns=list("abcd"))
    y = pd.Series([0] * 30 + [1] * 30)
    name, _, scores = select_best_model(X, y)
    assert name in scores
    from ingestion.csv_adapter import CSVAdapter
    p = tmp_path / "e.csv"
    pd.DataFrame([{"event_id": "x", "timestamp": "2026-01-01T00:00:00Z"}]).to_csv(p, index=False)
    assert CSVAdapter(str(p)).fetch()[0]["event_id"] == "x"


def test_api_and_export_and_auth():
    from fastapi.testclient import TestClient
    from api.main import app
    from reporting.export_utils import brief_to_csv, brief_to_pdf_bytes
    b = {"Severity": "Low", "Estimated Financial Exposure": "$10.00",
         "Confidence Level": "High", "Generated At": "now", "Recommended Actions": ["a"],
         "Signal Summary": {"Anomaly Rate": "1%"}}
    assert "Severity" in brief_to_csv(b) and brief_to_pdf_bytes(b).startswith(b"%PDF")
    c = TestClient(app)
    assert c.get("/health").status_code == 200
    from dashboard.auth import check_login, allowed_pages
    assert check_login("admin", "admin123") == "admin"
    assert "Technical" in allowed_pages("admin")


def test_mock_scenarios(tmp_path):
    from scripts.generate_mock_telemetry import generate_dataset
    p = str(tmp_path / "m.json")
    generate_dataset(n_events=50, output_path=p, seed=1, scenario="attack")
    import json
    assert json.load(open(p))[0]["event_id"]
