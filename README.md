# Enterprise Operational Decision Intelligence Platform

> *Evolved from a telemetry analytics system into a multi-stakeholder decision intelligence platform — detecting risks, estimating impact, recommending actions, and communicating to every audience.*

---

## Overview

The **Enterprise Operational Decision Intelligence Platform** is an end-to-end pipeline that ingests cloud telemetry (real AWS CloudWatch or local mock data), applies deterministic rules and ML, and produces **severity assessments, financial impact estimates, and operational playbook recommendations** for multiple stakeholder audiences.

The system is designed around:

* **Separation of concerns** — ingestion, processing, ML, decision, and reporting are fully independent layers
* **Responsible ML** — ML is decision-support only; no automated enforcement
* **Graceful degradation** — every layer has a safe fallback (CloudWatch → local → mock; GenAI → deterministic)
* **Multi-stakeholder design** — the same pipeline serves Operations, Security, Executive, and Engineering audiences via purpose-built views

---

## Architecture

```
Data Source (CloudWatch or Local)
 ↓
 Source Router (auto-selects best source, fallback chain)
 ↓
 Schema Validation & Ingestion
 ↓
 Feature Engineering
 ↓
 Baseline Rules (Deterministic) ML Detection
 (admin IAM, resource spike, etc.) (Supervised + Unsupervised)
 ↓ ↓
 └──────────────┬─────────────────────┘
 ↓
 Decision Intelligence Layer
 ├─ Severity Engine (Low / Moderate / High / Critical)
 ├─ Impact Estimator (USD exposure estimate)
 ├─ Action Recommender (YAML-driven playbooks)
 └─ Client Brief Builder (structured decision brief)
 ↓
 Stakeholder-Specific Outputs
 ├─ Operations — Runbook checklist + urgency
 ├─ Security — Threat signals + model metrics
 ├─ Executive — Risk posture + exposure + GenAI narrative
 └─ ⚙ Technical — Full pipeline + ML diagnostics
```

---

## Project Structure

```
ai-telemetry-intelligence/
│
├── config/ ← Runtime configuration (no secrets)
│ ├── severity_thresholds.yaml ← Signal → severity mapping
│ ├── impact_model.yaml ← Financial exposure multipliers + severity caps
│ ├── playbooks.yaml ← Severity → action lists
│ ├── cloudwatch.yaml ← AWS log group, lookback, region
│ ├── detection.yaml ← Isolation Forest contamination / seed
│ └── alerts.yaml ← Severity alerting (webhook + threshold)
│
├── data/
│ ├── raw/ ← Telemetry input (JSON)
│ └── processed/ ← Features, models, metrics, rejects
│
├── ingestion/
│ ├── load_logs.py ← Core JSON loader + schema validation
│ ├── validate_schema.py ← Field-level schema enforcement
│ ├── cloudwatch_connector.py ← boto3 CloudWatch fetcher (paginated)
│ ├── cloudwatch_normalizer.py ← CloudTrail → internal schema mapping
│ └── source_router.py ← Fallback orchestrator (CW → local → mock)
│
├── processing/
│ ├── feature_engineering.py ← Behavioral + temporal features
│ └── baseline_rules.py ← Deterministic risk heuristics
│
├── ml/
│ ├── supervised.py ← Logistic Regression risk classifier
│ ├── unsupervised.py ← Isolation Forest anomaly detection
│ └── evaluation.py ← Baseline vs ML comparison
│
├── decision/ ← Decision Intelligence Layer
│ ├── decision_context.py ← DecisionContext dataclass (signal snapshot)
│ ├── severity_engine.py ← Threshold-based severity assessment
│ ├── impact_estimator.py ← Heuristic financial exposure model
│ ├── action_recommender.py ← Playbook lookup by severity
│ ├── playbook_registry.py ← Loads + caches playbooks.yaml
│ └── config_validation.py ← Fail-fast YAML config checks
│
├── reporting/
│ ├── client_brief_builder.py ← Consulting-grade structured brief
│ ├── stakeholder_views.py ← Four audience-specific adapters
│ ├── narrative_generator.py ← GenAI or deterministic narrative
│ └── notifications.py ← Severity webhook alerts
│
├── explainability/
│ ├── genai_explainer.py ← Gemini API wrapper (optional)
│ └── prompt_templates.py ← EXPLANATION_PROMPT + DECISION_NARRATIVE_PROMPT
│
├── dashboard/
│ ├── app.py ← Home page (hero + source badge + nav)
│ ├── components/
│ │ ├── severity_card.py ← Colour-coded risk badge
│ │ ├── impact_card.py ← USD exposure metric
│ │ ├── action_panel.py ← Interactive runbook checklist
│ │ └── metrics_table.py ← Ingestion / ML metric tables
│ └── pages/
│ ├── 1_Operations.py ← SRE / Platform engineering view
│ ├── 2_Security.py ← SOC / Security engineering view
│ ├── 3_Executive.py ← C-Suite / Board view
│ └── 4_Technical.py ← Engineering / ML diagnostics
│
├── scripts/
│ ├── run_pipeline.py ← End-to-end pipeline orchestrator (runnable module)
│ └── generate_mock_telemetry.py ← Synthetic data with latent actor risk
│
├── tests/ ← Pytest suite (schema, ML, decision layer, routing)
├── .github/workflows/ci.yml ← Lint-free compile + config gate + tests
├── pytest.ini
├── .env.example ← Credential template (safe to commit)
├── requirements.txt / requirements-dev.txt
└── README.md
```

---

## Telemetry Schema

All events (from CloudWatch or mock generator) conform to this internal schema:

```json
{
 "event_id": "string (UUID)",
 "timestamp": "ISO-8601 UTC",
 "event_type": "auth | iam_change | api_call",
 "actor_type": "human | service",
 "actor_id": "string",
 "source_ip": "string",
 "region": "string",
 "resource_type":"string",
 "action": "string (CloudTrail eventName or mock action)",
 "risk_level": "low | medium | high",
 "metadata": {
 "policy_scope": "read | write | admin",
 "resource_count": "integer",
 "login_success": "boolean"
 }
}
```

CloudTrail events are normalized to this schema automatically via `cloudwatch_normalizer.py`.

---

## Data Sources & Fallback Chain

The pipeline automatically selects the best available data source:

```
1. AWS CloudWatch Logs (if credentials + log group reachable)
 ↓ fail
2. Local JSON file (data/raw/telemetry_logs.json — cached real or mock data)
 ↓ missing
3. Auto-generated mock (generate_mock_telemetry.py — always works, no credentials)
```

On a truly fresh run (no cached file and no CloudWatch credentials), the router
auto-generates mock data and reports `data_source: "mock"`. Once that data is
cached to `data/raw/telemetry_logs.json`, subsequent runs report it as `local`.

Valid events are deduplicated by `event_id` (first occurrence wins); the number
of dropped duplicates is reported as `duplicate_events` in the ingestion stats.

The dashboard displays a source badge on every page:
- **Live Data** — AWS CloudWatch
- **Local Data** — Cached / fallback
- ⚪ **Mock Data** — Auto-generated

---

## Decision Intelligence Layer

After ML detection, a dedicated layer translates signals into business decisions.

### Severity Engine (`decision/severity_engine.py`)

Reads thresholds from `config/severity_thresholds.yaml`:

| Level | When triggered |
|---|---|
| **Critical** | High-risk % > 20% or anomaly rate > 15% |
| **High** | High-risk % > 10% |
| **Moderate** | Anomaly rate > 8% |
| **Low** | All signals below thresholds |

### Impact Estimator (`decision/impact_estimator.py`)

Applies heuristic multipliers from `config/impact_model.yaml` to a base operational incident cost to produce an estimated financial exposure in USD. Multipliers fire on high-risk event %, anomaly rate, event volume (blast radius), and admin-scope activity rate.

Because multipliers can be driven by background dataset characteristics, the result is **clamped to a per-severity cap** (`impact_caps` in the same YAML) so the reported exposure can never contradict the assessed severity tier — e.g. a Low-severity run will not headline a $600K exposure.

### Action Recommender (`decision/action_recommender.py`)

Looks up severity in `config/playbooks.yaml` and returns the relevant operational runbook. **No code change required to update action lists** — just edit the YAML.

### Client Brief (`reporting/client_brief_builder.py`)

Produces a structured brief consumed by all stakeholder views and GenAI narratives:

```json
{
 "Executive Summary": "Operational telemetry indicates HIGH risk posture...",
 "Severity": "High",
 "Estimated Financial Exposure": "$600,000.00",
 "Recommended Actions": ["...", "..."],
 "Confidence Level": "High (multi-signal validation)",
 "Signal Summary": { ... }
}
```

The brief also carries a `Generated At` ISO timestamp so consumers can verify freshness.

---

## Alerting

When the decision severity meets or exceeds a configurable tier, the pipeline
posts an alert to a generic webhook (Slack, MS Teams, PagerDuty, ...).

Configuration lives in `config/alerts.yaml`:

| Key | Default | Purpose |
|---|---|---|
| `enabled` | `true` | Master switch |
| `min_severity` | `High` | Alert when severity >= this tier |
| `webhook_url` | `""` | Incoming webhook URL (env override: `ALERT_WEBHOOK_URL`) |

Alerting is best-effort: delivery failures are logged and never block the pipeline.
Whether an alert was dispatched is recorded in `metrics.run_metadata.alert_sent`.

---

## Dashboard

Launch with:
```bash
streamlit run dashboard/app.py
```

| Page | Audience | Key Components |
|---|---|---|
| **Home** | All | Decision brief hero, source badge, navigation |
| ** Operations** | SRE / Platform Eng | Severity card, action checklist, urgency window |
| ** Security** | SOC / Security Eng | Detection charts, model report, feature explorer |
| ** Executive** | C-Suite / Board | Risk level, exposure, GenAI consulting narrative |
| **⚙ Technical** | Engineering / ML | Full metrics, label distribution, raw JSON |

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Fill in GOOGLE_API_KEY and/or AWS credentials (all optional)
```

| Variable | Required | Purpose |
|---|---|---|
| `GOOGLE_API_KEY` | Optional | Enables GenAI consulting narratives |
| `AWS_ACCESS_KEY_ID` | Optional | Activates live CloudWatch ingestion |
| `AWS_SECRET_ACCESS_KEY` | Optional | Activates live CloudWatch ingestion |
| `AWS_SESSION_TOKEN` | Optional | For temporary STS credentials |
| `AWS_DEFAULT_REGION` | Optional | Default: `us-east-1` |
| `CLOUDWATCH_LOG_GROUP` | Optional | Default: `CloudTrail/DefaultLogGroup` |
| `ALERT_WEBHOOK_URL` | Optional | Webhook for severity alerts (overrides `config/alerts.yaml`) |

### 3. Run the pipeline

```bash
python scripts/run_pipeline.py
```

Output (example):
```
[SOURCE] Using local fallback data.        ← or "cloudwatch", or mock on a fresh run
[INFO] Ingestion complete
        Data source    : local
        Total events   : 10000
        Valid events   : 10000
        Invalid events : 0
[INFO] Supervised model saved -> data/processed/supervised_model.joblib
[INFO] Running Decision Intelligence Layer...
[DECISION] Severity  : Low
[DECISION] Exposure  : $600,000.00
[DECISION] Actions   : 2 recommended
[SUCCESS] Pipeline executed successfully
```

### 4. Launch the dashboard

```bash
streamlit run dashboard/app.py
```

---

## Artifacts

After a successful run, `data/processed/` contains:

| File | Contents |
|---|---|
| `features.parquet` | Engineered feature dataset |
| `metrics.json` | Ingestion, ML, and `decision_intelligence` block |
| `supervised_model.joblib` | Trained risk classifier (if label variety sufficient) |
| `unsupervised_model.joblib` | Isolation Forest anomaly detector |
| `rejected_events.json` | Schema-invalid events (if any) |

`metrics.json` structure (top-level keys):
```
ingestion • baseline • unsupervised • supervised •
genai_summary • genai_status • baseline_evaluation •
decision_intelligence • run_metadata
```

`baseline_evaluation` scores **both** the deterministic rules and the
supervised classifier on the identical held-out test split, so the numbers
are directly comparable (the previous in-sample `baseline_vs_supervised`
metric was retired because it evaluated only the rules on training data).

`run_metadata` is the audit trail for the run: pipeline version, git commit,
dependency versions, config file hashes, raw-data hash, run duration, and
`alert_sent`. The `ingestion` block now also reports `duplicate_events`.

---

## AWS IAM Requirements (CloudWatch mode)

The IAM user or role must have:

```json
{
 "Effect": "Allow",
 "Action": [
 "logs:FilterLogEvents",
 "logs:DescribeLogGroups"
 ],
 "Resource": "arn:aws:logs:*:*:log-group:CloudTrail/*"
}
```

---

## Design Principles

| Principle | How it's applied |
|---|---|
| **No automated enforcement** | ML and decision layer are advisory only |
| **Graceful fallback everywhere** | CloudWatch → local → mock; GenAI → deterministic |
| **Config over code** | Thresholds, multipliers, playbooks, and anomaly settings are YAML files |
| **Audience-aware outputs** | Same pipeline, four distinct stakeholder views |
| **Interpretable decisions** | Cost model and severity rules use explicit formulas, not ML |
| **Human-in-the-loop** | Confidence labels are gated on real model quality (support + minority-class F1) |
| **Non-circular labels** | `risk_level` depends on latent actor state / event-id jitter, never solely on exported ML features |

---

## Testing & CI

```bash
pip install -r requirements-dev.txt
pytest
```

The suite (70+ tests) covers schema validation, ingestion dedup/fallback routing,
CloudTrail normalization, ML training/evaluation honesty, the decision layer,
config validation gates, and alerting. A regression test asserts that repeated
observable feature tuples carry mixed risk labels — i.e. the supervised target is
not a pure function of the features (label-leakage guard).

GitHub Actions runs compile checks, the config gate (`python -m decision.config_validation`),
and pytest on every push/PR (`.github/workflows/ci.yml`).
