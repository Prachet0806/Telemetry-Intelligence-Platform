# decision/triage_store.py
"""Persisted action triage & status (#13). SQLite-backed, shared DB with history."""
from __future__ import annotations

import sqlite3
import os
from datetime import datetime, timezone
from pathlib import Path

_DB = Path(__file__).resolve().parents[1] / "data" / "history.db"


def _conn(db_path: Path | str | None = None):
    p = Path(db_path) if db_path else Path(os.getenv("AI_TELEMETRY_DB_PATH", str(_DB)))
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(p), timeout=30.0, check_same_thread=False)
    # WAL-safe for concurrent pipeline/dashboard/API readers+writers.
    try:
        c.execute("PRAGMA journal_mode=WAL;")
        c.execute("PRAGMA busy_timeout=5000;")
        c.execute("PRAGMA synchronous=NORMAL;")
    except Exception:
        pass
    c.execute("""CREATE TABLE IF NOT EXISTS triage(
        run_id TEXT, action_id TEXT, title TEXT, owner TEXT, priority TEXT,
        status TEXT DEFAULT 'open', updated_at TEXT,
        PRIMARY KEY (run_id, action_id))""")
    c.execute("""CREATE TABLE IF NOT EXISTS triage_events(
        event_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
        action_id TEXT NOT NULL, old_status TEXT NOT NULL, new_status TEXT NOT NULL,
        actor TEXT NOT NULL, reason TEXT NOT NULL, changed_at TEXT NOT NULL)""")
    return c


def _read_conn(db_path: Path | str | None = None):
    p = Path(db_path) if db_path else Path(os.getenv("AI_TELEMETRY_DB_PATH", str(_DB)))
    if not p.is_file():
        return None
    return sqlite3.connect(p.resolve().as_uri() + "?mode=ro", uri=True, timeout=5.0)


def init_run(run_id: str, actions: list[dict], db_path=None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _conn(db_path) as c:
        for a in actions:
            c.execute("INSERT OR IGNORE INTO triage(run_id,action_id,title,owner,priority,status,updated_at)"
                      " VALUES(?,?,?,?,?,'open',?)",
                      (run_id, a.get("id"), a.get("title"), a.get("owner"), a.get("priority"), now))


def allowed_transitions(status: str) -> list[str]:
    transitions = {
        "open": ["open", "in_progress", "skipped"],
        "in_progress": ["in_progress", "open", "done", "skipped"],
        "done": ["done", "in_progress"],
        "skipped": ["skipped", "open", "in_progress"],
    }
    return transitions.get(status, [])


def set_status(run_id: str, action_id: str, status: str, db_path=None,
               actor: str = "unknown", reason: str = "") -> None:
    if status not in ("open", "in_progress", "done", "skipped"):
        raise ValueError(f"bad status {status!r}")
    now = datetime.now(timezone.utc).isoformat()
    with _conn(db_path) as c:
        row = c.execute(
            "SELECT status FROM triage WHERE run_id=? AND action_id=?",
            (run_id, action_id),
        ).fetchone()
        if not row:
            raise KeyError(f"unknown triage action {action_id!r} for run {run_id!r}")
        old_status = row[0]
        if status not in allowed_transitions(old_status):
            raise ValueError(f"transition {old_status!r} -> {status!r} is not allowed")
        if status == old_status and not reason:
            return
        c.execute(
            "INSERT INTO triage_events(run_id,action_id,old_status,new_status,actor,reason,changed_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (run_id, action_id, old_status, status, str(actor)[:128], str(reason)[:1000], now),
        )
        c.execute("UPDATE triage SET status=?, updated_at=? WHERE run_id=? AND action_id=?",
                  (status, now, run_id, action_id))


def get_run(run_id: str, db_path=None) -> list[dict]:
    c = _read_conn(db_path)
    if c is None:
        return []
    try:
        c.row_factory = sqlite3.Row
        rows = c.execute("SELECT * FROM triage WHERE run_id=? ORDER BY action_id", (run_id,)).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        c.close()
