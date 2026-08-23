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
   remaining: PR-AUC and decision-threshold selection.
3. **Expanded feature set** — actor/account frequency, rolling-window aggregates,
   user-agent/IP features, hour-of-week seasonality.

## 5. Phase 2 - Decision intelligence depth

4. **Weighted severity scoring** — replace the hard-coded cascade with configurable
   weighted scores + tier bands.
5. **Richer impact model** — cost breakdown by category/region/resource and
   min/max sensitivity ranges.
6. **Action triage & status** — priority/owner metadata, persisted completion state,
   dependency ordering.

## 6. Phase 3 - Automation & delivery

7. **Scheduled / incremental ingestion** — watermark-persisted, cron/Airflow/APScheduler
   runs with catch-up windows.
8. **Export & API** — PDF/CSV reports plus a FastAPI endpoint serving decision briefs.
9. **Trend / history tracking** — persist per-run briefs; enables historical dashboards
   and long-horizon drift analysis.
10. **Historical dashboards** — time-series of severity, exposure, anomaly rate.

## 7. Phase 4 - Scale & operations

11. **Containerization & CI/CD** — Dockerfile/compose, GitHub Actions (lint, test,
    pipeline smoke run).
12. **Drift monitoring & retraining** — feature/label distribution checks with alerts
    and retraining triggers.
13. **Additional data sources** — S3 CloudTrail, EventBridge, local CSV/Parquet behind a
    pluggable source adapter.
14. **Role-based access** — stakeholder-gated pages.

## 8. Backlog (opportunistic)

- Scenario-driven mock generator (attack/drift scenarios with deterministic seeds)
- SHAP/LIME feature attribution
- Model selection & hyperparameter tuning (RF/XGBoost/SVM + CV)
- Structured JSON logging + pipeline health metrics endpoint
- Data retention / archival policies

## 9. Impact x Effort x Timeline matrix

| # | Improvement | Impact | Effort | Timeline | Status |
|---|-------------|--------|--------|----------|--------|
| Q1 | Event deduplication | M | S | 0.5 day | **implemented** |
| Q2 | Run metadata / observability | L-M | S | 1 day | **implemented** |
| Q3 | Config validation | M-H | S | 1 day | **implemented** |
| Q4 | Audit trail | M-H | S | 1-2 days | **implemented** |
| Q4 | Severity alerting | H | S-M | 2-3 days | **implemented** |
| 19 | Test suite | H | M | 3-5 days | **implemented** (70+ tests + CI) |
| 7 | Proper evaluation & calibration | H | M | 2-4 days | **partially done** (held-out baseline-vs-ML comparison; PR-AUC/calibration pending) |
| 5 | Expanded feature set | H | M | 3-5 days | planned |
| 10 | Weighted severity scoring | M-H | S-M | 2-3 days | planned |
| 12 | Richer impact model | M | M | 3-5 days | planned |
| 13 | Action triage & status | M | M | 3-5 days | planned |
| 2 | Scheduled / incremental ingestion | H | L | 1-2 weeks | planned |
| 16 | Export & API | H | M | 3-5 days | planned |
| 11 | Trend / history tracking | H | M | 3-5 days | planned |
| 17 | Historical dashboards | M | M | 2-4 days | planned |
| 21 | Containerization & CI/CD | H | M | 3-5 days | planned |
| 8 | Drift monitoring & retraining | H | L | 1-2 weeks | planned |
| 3 | Additional data sources | M | M | 3-5 days | planned |
| 18 | Role-based access | M | M | 2-3 days | planned |
| 22 | Scenario mock generator | M | M | 2-3 days | backlog |
| 23 | SHAP/LIME attribution | M | M | 3-5 days | backlog |
| 24 | Model selection & tuning | M | M | 3-5 days | backlog |
| 25 | JSON logging & health metrics | L-M | S | 1-2 days | backlog |

Effort scale: S = <=2 days, M = 3-5 days, L = 1-2 weeks.