"""Durable, retryable webhook delivery queue keyed by immutable run ID."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from reporting.notifications import _load_alert_config, send_severity_alert, should_alert

_DB = Path(__file__).resolve().parents[1] / "data" / "history.db"
_MAX_ATTEMPTS = 5


def _connection(db_path=None):
    path = Path(db_path) if db_path is not None else Path(os.getenv("AI_TELEMETRY_DB_PATH", str(_DB)))
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("""CREATE TABLE IF NOT EXISTS alert_outbox(
        run_id TEXT PRIMARY KEY, brief_json TEXT NOT NULL, status TEXT NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL, last_error TEXT)""")
    return conn


def enqueue_alert(run_id: str, brief: dict, db_path=None) -> bool:
    """Queue an eligible alert once. Returns whether a new row was created."""
    cfg = _load_alert_config()
    if not should_alert(str(brief.get("Severity", "Low")), cfg):
        return False
    now = datetime.now(timezone.utc).isoformat()
    with _connection(db_path) as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO alert_outbox"
            " (run_id,brief_json,status,attempts,created_at,updated_at,last_error)"
            " VALUES(?,?,'pending',0,?,?,NULL)",
            (run_id, json.dumps(brief, default=str), now, now),
        )
        return cur.rowcount == 1


def dispatch_pending(db_path=None, limit: int = 50) -> dict[str, int]:
    """Claim and dispatch pending alerts; stale claims become retryable."""
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    counts = {"sent": 0, "failed": 0, "skipped": 0}
    with _connection(db_path) as conn:
        rows = conn.execute(
            "SELECT run_id,brief_json,attempts FROM alert_outbox "
            "WHERE (status IN ('pending','failed') OR (status='sending' AND updated_at < ?)) "
            "AND attempts < ? ORDER BY created_at LIMIT ?",
            (cutoff, _MAX_ATTEMPTS, max(1, min(int(limit), 500))),
        ).fetchall()
    for run_id, raw_brief, attempts in rows:
        now = datetime.now(timezone.utc).isoformat()
        with _connection(db_path) as conn:
            cur = conn.execute(
                "UPDATE alert_outbox SET status='sending',attempts=attempts+1,updated_at=?,last_error=NULL "
                "WHERE run_id=? AND (status IN ('pending','failed') OR (status='sending' AND updated_at < ?))",
                (now, run_id, cutoff),
            )
            if cur.rowcount != 1:
                continue
        try:
            brief = json.loads(raw_brief)
            ok = send_severity_alert(brief, idempotency_key=run_id)
            status = "sent" if ok else "failed"
            error = None if ok else "delivery attempt did not succeed"
        except Exception as exc:
            status, error = "failed", f"{type(exc).__name__}: {exc}"[:500]
        with _connection(db_path) as conn:
            conn.execute(
                "UPDATE alert_outbox SET status=?,updated_at=?,last_error=? WHERE run_id=?",
                (status, datetime.now(timezone.utc).isoformat(), error, run_id),
            )
        counts[status] = counts.get(status, 0) + 1
    return counts
