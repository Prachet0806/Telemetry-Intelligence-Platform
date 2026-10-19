# api/main.py
"""FastAPI service (#16): briefs, runs, health, export."""
from __future__ import annotations

import json
import hmac
import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

PROJECT_ROOT = Path(__file__).resolve().parents[1]

app = FastAPI(title="Decision Intelligence API", version="1.0.0")

_bearer = HTTPBearer(auto_error=False)


def _require_api_key(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> None:
    """Require bearer credentials for data routes; allow open access only in development."""
    expected = os.getenv("API_KEY", "").strip()
    if not expected:
        if os.getenv("APP_ENV", "development").lower() == "production":
            raise HTTPException(503, "API is not configured with an API key")
        return
    token = (creds.credentials if creds else "").strip()
    if not hmac.compare_digest(token, expected):
        raise HTTPException(401, "Invalid or missing API key")


def _latest_brief() -> dict:
    from reporting.run_store import latest_artifact_path
    mp = latest_artifact_path("metrics.json", PROJECT_ROOT / "data" / "processed")
    if not mp.exists():
        raise HTTPException(404, "No pipeline run yet")
    data = json.loads(mp.read_text(encoding="utf-8"))
    return data.get("decision_intelligence", {})


@app.get("/health")
def health(response: Response):
    from reporting.history_store import storage_status
    from reporting.run_store import latest_artifact_path
    try:
        latest = latest_artifact_path("metrics.json", PROJECT_ROOT / "data" / "processed")
        has_snapshot = latest.is_file()
    except Exception:
        has_snapshot = False
    try:
        history = storage_status()
    except Exception:
        history = "unavailable"
    ready = has_snapshot and history == "ok"
    if not ready:
        response.status_code = 503
    return {
        "status": "ok" if ready else "degraded",
        "checks": {"latest_snapshot": has_snapshot, "history_store": history},
    }


@app.get("/brief/latest", dependencies=[Depends(_require_api_key)])
def brief_latest():
    return _latest_brief()


@app.get("/brief/{run_id}", dependencies=[Depends(_require_api_key)])
def brief_by_id(run_id: str):
    from reporting.history_store import get_brief
    b = get_brief(run_id)
    if not b:
        raise HTTPException(404, f"run {run_id} not found")
    return b


@app.get("/runs", dependencies=[Depends(_require_api_key)])
def runs(limit: int = Query(default=20, ge=1, le=200)):
    from reporting.history_store import list_runs
    return list_runs(limit=limit)


@app.get("/export/csv", dependencies=[Depends(_require_api_key)])
def export_csv():
    from reporting.export_utils import brief_to_csv
    return Response(brief_to_csv(_latest_brief()), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=brief.csv"})


@app.get("/export/pdf", dependencies=[Depends(_require_api_key)])
def export_pdf():
    from reporting.export_utils import brief_to_pdf_bytes
    try:
        content = brief_to_pdf_bytes(_latest_brief())
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    return Response(content, media_type="application/pdf",
                    headers={"Content-Disposition": "attachment; filename=brief.pdf"})
