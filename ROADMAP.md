# ROADMAP

> Prioritised improvement and feature plan for the Enterprise Operational Decision
> Intelligence Platform. Each item maps to the Impact/Effort/Timeline matrix at the
> bottom. Quick wins marked **[x]** are already implemented.

---

## 1. Vision

Turn the current batch pipeline into a continuously-operating decision intelligence
service: reliable ingestion -> trustworthy ML -> explainable, auditable decisions ->
alerting and stakeholder delivery, all validated by automated tests and deployed via
CI/CD.

## 2. Phase flow

Features are sequenced so that each phase de-risks and enables the next:

```
PHASE 0 - Foundations (quick wins)          [in progress]
  Q1 event deduplication  ->   pipeline runs on clean, stable inputs
  Q3 config validation    ->   failures surface at startup, not mid-run
  Q4 audit trail          ->   every decision is reproducible
  Q4 alerting             ->   closes the human-in-the-loop loop
  Q2 run metadata         ->   observability for every run
                          |
                          v
PHASE 1 - Correctness & trust
  19 test suite  ->  unlocks safe iteration on features and ML
  7  eval/calibration  ->  fixes inflated precision; honest baselines
  5  expanded features  ->  better signal separation
  20 (done) config schema  ->  features evolve without breaking YAML
                          |
                          v
PHASE 2 - Decision intelligence depth
  10 weighted severity scoring  ->  configurable, gradation-rich tiers
  12 richer impact model        ->  category/region breakdown + sensitivity
  13 action triage & status     ->  prioritised, persisted runbooks
  14 (done) audit trail         ->  version-pinned briefs for all of the above
                          |
                          v
PHASE 3 - Automation & delivery
  15 (done) alerting            ->  needs severity >= configurable tier
  2  scheduled/incremental      ->  needs #20 validation + #19 tests
  16 export & API               ->  needs #14 audit trail for reproducible briefs
  11 trend/history tracking     ->  persistence layer shared with #13
  17 historical dashboards      ->  depends on #11
                          |
                          v
PHASE 4 - Scale & operations
  21 containerization + CI/CD   ->  depends on #19 tests
  8  drift monitoring/retraining->  depends on #7 evaluation baseline
  3  additional data sources    ->  needs source adapter refactor
  18 role-based access          ->  audit logs from #14/phase-2
  22 (done) structured metrics  ->  feeds drift and health monitoring
```

## 3. Phase 0 - Quick wins (implemented)

| # | Feature | What changed |
|---|---------|--------------|
| Q1 | Event deduplication | `load_logs.py` keeps first occurrence per `event_id`; `duplicate_events` reported in ingestion stats |
| Q3 | Config validation | `decision/config_validation.py` validates all YAML at pipeline startup; fail-fast with clear message |
| Q4 | Audit trail | `metrics.run_metadata` records pipeline version, git commit, dependency versions, config hashes, raw-data hash, duration |
| Q4 | Severity alerting | `reporting/notifications.py` + `config/alerts.yaml` POST a webhook when severity >= `min_severity` (default High); env override `ALERT_WEBHOOK_URL` |
| Q2 | Run metadata / observability | structured `run_metadata` block in `metrics.json`; `Generated At` stamp on the decision brief |

## 4. Phase 1 - Correctness & trust

1. **Test suite (pytest)** — schema validation, router fallback chain, decision layer,
   dashboard helpers. Every later phase depends on this safety net.
   **Status: implemented** (`tests/`, 70+ tests incl. a label-leakage regression
   guard; CI in `.github/workflows/ci.yml`).
 2. **Proper evaluation & calibration** — evaluate baseline-vs-ML on a held-out split
    (**done**: `ml/evaluation.evaluate_models_on_holdout` scores both detectors on the
    identical test rows; the old in-sample `baseline_vs_supervised` metric is retired);
    PR-AUC (`compute_pr_auc`) + fixed 0.5 holdout operating point — **implemented**.
    Threshold calibration is deferred until an independently reviewed validation
    set exists; optimizing against the reported holdout would leak test labels.
 3. **Expanded feature set** — actor/account frequency, rolling-window aggregates,
    user-agent/IP features, hour-of-week seasonality.
    **Status: implemented** (`processing/feature_engineering.py`: `hour_of_week`,
    `is_weekend`, `actor_event_count`, `ip_event_count`, `actor_events_1h`,
    `region_freq`, `login_failed`, …).

## 5. Phase 2 - Decision intelligence depth

4. **Weighted severity scoring** — replace the hard-coded cascade with configurable
   weighted scores + tier bands.
   **Status: implemented** (`decision/severity_engine.score_severity` +
   `config/severity_weights.yaml`; cascade stays authoritative, score is an
   explainable overlay with `Severity Score` + `Severity Contributions` in the brief).
5. **Richer impact model** — cost breakdown by category/region/resource and
   min/max sensitivity ranges.
   **Status: implemented** (`decision/impact_estimator.estimate_impact_detailed` +
   `Estimated Financial Exposure Range` + `Impact Breakdown` in the brief).
6. **Action triage & status** — priority/owner metadata, persisted completion state,
   dependency ordering.
   **Status: implemented** (`decision/playbook_registry.get_enriched_actions` +
   `decision/triage_store.py` SQLite `init_run`/`set_status`/`get_run`; dashboard
   triage controls on the Operations page).

## 6. Phase 3 - Automation & delivery

7. **Scheduled / incremental ingestion** — watermark-persisted, cron/Airflow/APScheduler
   runs with catch-up windows.
   **Status: partial** (`scripts/scheduler.py` + `config/scheduler.yaml`;
   CloudWatch watermark advances only after a persisted live-source run and a
   capped query fails closed instead of silently publishing a truncated batch.
   Event-ID checkpointing is implemented and committed after publication;
   durable AWS page-token resume and live catch-up validation remain open).
8. **Export & API** — PDF/CSV reports plus a FastAPI endpoint serving decision briefs.
   **Status: implemented** (`api/main.py`: `/health`, `/brief/latest`,
   `/brief/{id}`, `/runs`, `/export/csv|pdf`; `reporting/export_utils.py`;
   production `API_KEY` bearer guard on all data routes, with only `/health` public).
9. **Trend / history tracking** — persist per-run briefs; enables historical dashboards
   and long-horizon drift analysis.
   **Status: implemented** (`reporting/history_store.py` SQLite `record_run` /
   `list_runs` / `get_brief` + watermark; WAL-safe for pipeline/dashboard/API).
10. **Historical dashboards** — time-series of severity, exposure, anomaly rate.
    **Status: implemented** (`dashboard/pages/5_History.py`: exposure +
    anomaly/high-risk charts, run table, per-run brief inspector).

## 7. Phase 4 - Scale & operations

11. **Containerization & CI/CD** — Dockerfile/compose, GitHub Actions (syntax,
    config validation, tests, fixture-backed pipeline smoke run).
    **Status: implemented** (`Dockerfile`, `docker-compose.yml` with
    pipeline/scheduler + dashboard + api services, `restart: unless-stopped`,
    `./data:/app/data` persistence; CI compiles, validates configs, runs pytest,
    generates a deterministic smoke fixture, runs the offline dry-run, and builds
    the image. No lint step is configured. The scheduler service requires the
    `scheduler` Compose profile and `scheduler.enabled: true` in config.)
12. **Drift monitoring & retraining** — feature/label distribution checks with alerts
    and retraining triggers.
    **Status: implemented** (`ml/drift.py` PSI + KS + label-rate vs
    `reference_stats.json`; `--retrain` refreshes the reference; `drift.yaml`
    thresholds validated at startup; scipy optional).
13. **Additional data sources** — wire S3 CloudTrail/EventBridge and local
    CSV/Parquet into the automatic router behind a pluggable source adapter.
    **Status: partial** (`ingestion/base.py`, `csv_adapter.py`, and `s3_adapter.py`
    provide a protocol and callable standalone adapters; `source_router` does not
    select them, and there is no EventBridge adapter. The automatic route remains
    CloudWatch → local JSON → development mock. CSV/Parquet and S3 ingestion
    require explicit adapter use and integration into routing remains open).
14. **Role-based access** — stakeholder-gated pages.
   **Status: implemented** (`dashboard/auth.py` + `config/roles.yaml`; page guards
   run before telemetry loads; default passwords work only in development mode).

## 8. Backlog (opportunistic)

- Scenario-driven mock generator (attack/drift scenarios with deterministic seeds)
  — **implemented** (`scripts/generate_mock_telemetry.py --scenario`).
- Feature attribution — **implemented (limited)** as `explainability/attribution.top_features`:
  optional SHAP when installed, otherwise permutation importance. LIME is not
  implemented; this output is an explanatory ranking, not causal attribution.
- Model comparison — **implemented (reporting-only)** as
  `ml/model_selection.select_best_model`: chronological PR-AUC CV compares
  logistic regression and random forest (plus XGBoost when installed). It does
  not search hyperparameters or include SVM; logistic regression remains the
  served model.
- Structured JSON logging + API readiness endpoint — **implemented**
  (`reporting/json_logging.py --json-logs`; `GET /health` reports latest-snapshot
  and history-store checks and can return 503; it does not report
  `runs_recorded`).
- Data retention — **implemented (partial coverage)** (`scripts/prune.py`):
  `history_days` prunes database history/source-event rows, and `processed_days`
  prunes old snapshots/staging data while preserving the latest snapshot.
  `raw_days` is configured but unused; raw-data archival/deletion is not
  implemented.

## 9. Impact x Effort x Timeline matrix

| # | Improvement | Impact | Effort | Timeline | Status |
|---|-------------|--------|--------|----------|--------|
| Q1 | Event deduplication | M | S | 0.5 day | **implemented** |
| Q2 | Run metadata / observability | L-M | S | 1 day | **implemented** |
| Q3 | Config validation | M-H | S | 1 day | **implemented** |
| Q4 | Audit trail | M-H | S | 1-2 days | **implemented** |
| Q4 | Severity alerting | H | S-M | 2-3 days | **implemented** |
| 19 | Test suite | H | M | 3-5 days | **implemented** (70+ tests + CI) |
| 7 | Proper evaluation & calibration | H | M | 2-4 days | **partial** (chronological holdout + PR-AUC; calibration awaits reviewed labels) |
| 5 | Expanded feature set | H | M | 3-5 days | **implemented** |
| 10 | Weighted severity scoring | M-H | S-M | 2-3 days | **implemented** |
| 12 | Richer impact model | M | M | 3-5 days | **implemented** |
| 13 | Action triage & status | M | M | 3-5 days | **implemented** |
| 2 | Scheduled / incremental ingestion | H | L | 1-2 weeks | **partial** (durable page-token resume and live catch-up validation open) |
| 16 | Export & API | H | M | 3-5 days | **implemented** |
| 11 | Trend / history tracking | H | M | 3-5 days | **implemented** |
| 17 | Historical dashboards | M | M | 2-4 days | **implemented** |
| 21 | Containerization & CI/CD | H | M | 3-5 days | **implemented** |
| 8 | Drift monitoring & retraining | H | L | 1-2 weeks | **implemented** |
| 3 | Additional data sources | M | M | 3-5 days | **partial** (standalone CSV/S3 adapters; not wired into router; no EventBridge adapter) |
| 18 | Role-based access | M | M | 2-3 days | **implemented** |
| 22 | Scenario mock generator | M | M | 2-3 days | **implemented** |
| 23 | Feature attribution | M | M | 3-5 days | **partial** (optional SHAP or permutation importance; no LIME) |
| 24 | Model selection & tuning | M | M | 3-5 days | **partial** (candidate comparison only; no hyperparameter search or SVM) |
| 25 | JSON logging & health endpoint | L-M | S | 1-2 days | **implemented** (readiness checks; no run count) |
| 26 | Retention / prune | L-M | S | 1-2 days | **partial** (`raw_days` unused; history and processed artifacts pruned) |

Effort scale: S = <=2 days, M = 3-5 days, L = 1-2 weeks.
