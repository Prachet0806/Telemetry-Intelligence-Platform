# Telemetry Intelligence Platform

## Overview

The **Telemetry Intelligence Platform** is an end-to-end analytics pipeline that ingests cloud and security telemetry, applies deterministic rules and foundational machine learning, and produces **explainable, human-readable insights** for operational and governance use cases.

The project is intentionally designed to emphasize:

* **End-to-end correctness**
* **Observability and guardrails**
* **Responsible ML usage**
* **Clear separation of concerns**
* **Enterprise-style failure handling**

Rather than focusing on real-time automation or advanced ML, the system prioritizes **interpretability, safety, and reliability**, aligning with expectations in regulated and large-scale environments.

---

## High-Level Architecture

```
Telemetry Logs (Mock / CloudTrail-style)
        ↓
Ingestion & Schema Validation
        ↓
Feature Engineering
        ↓
Baseline Rules (Deterministic)
        ↓
Machine Learning
  ├─ Supervised (Known risk patterns)
  └─ Unsupervised (Anomaly detection)
        ↓
Metrics & Artifact Persistence
        ↓
Explainability Layer (Optional GenAI)
        ↓
Dashboard (Streamlit)
```

---

## Project Structure

```
telemetry-intelligence-platform/
│
├── data/
│   ├── raw/                  # Raw telemetry input (JSON)
│   ├── processed/            # Features, metrics, models, rejected events
│
├── ingestion/                # Loading + schema validation
├── processing/               # Feature engineering + baseline rules
├── ml/                       # Supervised & unsupervised ML
├── explainability/           # AI explainability (optional GenAI)
├── dashboard/                # Streamlit UI
├── scripts/                  # Orchestration & data generation
├── requirements.txt
└── README.md
```

---

## Telemetry Model

Each telemetry event follows a strict schema:

```json
{
  "event_id": "string",
  "timestamp": "ISO-8601",
  "event_type": "auth | iam_change | api_call",
  "actor_type": "human | service",
  "actor_id": "string",
  "region": "string",
  "resource_type": "string",
  "action": "string",
  "risk_level": "low | medium | high",
  "metadata": {
    "policy_scope": "read | write | admin",
    "resource_count": "integer",
    "login_success": "boolean"
  }
}
```

Mock data is used to ensure:

* Reproducibility
* No dependency on live cloud credentials
* Safe experimentation

---

## End-to-End Workflow

1. **Data Generation (Optional)**

   * Synthetic telemetry is generated if no raw data exists.

2. **Ingestion & Validation**

   * Each event is schema-validated.
   * Invalid events are tracked, categorized, and optionally persisted.
   * Ingestion statistics are recorded.

3. **Feature Engineering**

   * Raw logs are converted into behavioral, ML-ready features.

4. **Baseline Rules**

   * Deterministic heuristics flag obvious risk patterns.
   * Provides a non-ML safety baseline.

5. **Machine Learning**

   * **Supervised ML** reinforces known risk patterns (precision-oriented).
   * **Unsupervised ML** detects anomalous behavior.
   * Supervised training is safely skipped if labels lack diversity.

6. **Metrics & Artifacts**

   * Features, models, and metrics are persisted for downstream use.

7. **Explainability**

   * Optional GenAI layer converts metrics into plain-English summaries.
   * Falls back to a safe message if no API key is configured.

8. **Dashboard**

   * Displays telemetry volume, risk distribution, and pipeline metrics.
   * Fails gracefully if the pipeline has not been run.

---

## Machine Learning Philosophy

The ML layer is **decision-support only**.

* ML augments deterministic logic; it does not replace it.
* Outputs are validated against baseline rules.
* No automated remediation or enforcement exists.
* Supervised learning is guarded against single-class failure cases.

This mirrors how ML is typically used in **governance, security, and risk analytics**.

---

## Explainability & Responsible AI

* GenAI is used **only for explanation**, not decisions.
* GenAI is **optional** and gated by `GOOGLE_API_KEY`.
* The interface contract supports future model changes without altering pipeline semantics.

---

## Running the Project

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure GenAI (optional)

Create a `.env` file in the project root:

```bash
GOOGLE_API_KEY=your_api_key_here
```

If not set, the dashboard will display a safe fallback message instead of
an AI-generated explanation.

### 3. Run the Pipeline

```bash
python scripts/run_pipeline.py
```

This will:

* Generate telemetry if missing
* Run ingestion, processing, ML
* Persist features, metrics, and models

### 4. Launch the Dashboard

```bash
streamlit run dashboard/app.py
```

---

## Outputs & Artifacts

After a successful run, `data/processed/` will contain:

* `features.parquet` — feature-engineered dataset
* `metrics.json` — ingestion, baseline, and ML metrics
* `supervised_model.joblib` — trained model (if applicable)
* `unsupervised_model.joblib`
* `rejected_events.json` — invalid telemetry (if any)

---

## Known Limitations

* Telemetry is synthetic and may not capture all real-world edge cases
* Risk labels are rule-derived, not human-curated
* No real-time or streaming ingestion
* No automated remediation
* GenAI explainability is optional and depends on API availability

These constraints are **intentional** to preserve clarity, safety, and reviewability.

---

## Extension Plan (High-Level)

Future enhancements could include:

* Real CloudTrail ingestion via S3
* Entity-level behavioral baselining (UEBA)
* Streaming ingestion (optional)
* Model drift detection
* Role-based dashboards
* CI/CD and data quality metrics

All extensions would preserve **human-in-the-loop governance**.

