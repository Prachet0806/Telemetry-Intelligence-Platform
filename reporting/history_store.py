# reporting/history_store.py
"""Trend / history tracking (#11): SQLite persistence for per-run briefs."""
from __future__ import annotations

import json
import os
import sqlite3
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
    c.execute("""CREATE TABLE IF NOT EXISTS runs(
        run_id TEXT PRIMARY KEY, timestamp TEXT, severity TEXT,
        exposure REAL, anomaly_rate REAL, high_risk_pct REAL,
        total_events INTEGER, brief_json TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS watermark(
        source TEXT PRIMARY KEY, last_event_time TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS source_events(
        source TEXT NOT NULL, event_id TEXT NOT NULL, event_time TEXT,
        first_seen_at TEXT NOT NULL, PRIMARY KEY(source,event_id))""")
    return c


def _read_conn(db_path: Path | str | None = None):
    """Open an existing SQLite store read-only without creating files or schema."""
    p = Path(db_path) if db_path else Path(os.getenv("AI_TELEMETRY_DB_PATH", str(_DB)))
    if not p.is_file():
        return None
    uri = p.resolve().as_uri() + "?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=5.0)


def record_run(run_id: str, brief: dict, signals: dict, db_path=None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    raw = signals
    with _conn(db_path) as c:
        c.execute("INSERT OR REPLACE INTO runs VALUES(?,?,?,?,?,?,?,?)",
                  (run_id, brief.get("Generated At", now),
                   brief.get("Severity", "Low"),
                   float(brief.get("Estimated Financial Exposure Raw", 0.0) or 0.0),
                   float(raw.get("anomaly_rate", 0.0) or 0.0),
                   float(raw.get("high_risk_percentage", 0.0) or 0.0),
                   int(raw.get("total_events", 0) or 0),
                   json.dumps(brief, default=str)))


def list_runs(limit: int = 50, db_path=None) -> list[dict]:
    c = _read_conn(db_path)
    if c is None:
        return []
    try:
        c.row_factory = sqlite3.Row
        rows = c.execute("SELECT run_id,timestamp,severity,exposure,anomaly_rate,high_risk_pct,total_events"
                         " FROM runs ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        c.close()


def get_brief(run_id: str, db_path=None) -> dict | None:
    c = _read_conn(db_path)
    if c is None:
        return None
    try:
        c.row_factory = sqlite3.Row
        r = c.execute("SELECT brief_json FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return json.loads(r["brief_json"]) if r else None
    except sqlite3.OperationalError:
        return None
    finally:
        c.close()


def get_watermark(source: str = "cloudwatch", db_path=None) -> str | None:
    c = _read_conn(db_path)
    if c is None:
        return None
    try:
        r = c.execute("SELECT last_event_time FROM watermark WHERE source=?", (source,)).fetchone()
        return r[0] if r else None
    except sqlite3.OperationalError:
        return None
    finally:
        c.close()


def set_watermark(source: str, last_event_time: str, db_path=None) -> None:
    with _conn(db_path) as c:
        c.execute(
            "INSERT INTO watermark(source,last_event_time) VALUES(?,?) "
            "ON CONFLICT(source) DO UPDATE SET last_event_time="
            "CASE WHEN julianday(watermark.last_event_time) IS NULL OR "
            "julianday(excluded.last_event_time) > julianday(watermark.last_event_time) "
            "THEN excluded.last_event_time ELSE watermark.last_event_time END",
            (source, last_event_time),
        )


def processed_event_ids(source: str, event_ids: list[str], db_path=None) -> set[str]:
    """Return known source IDs in bounded SQL batches."""
    if not event_ids:
        return set()
    found: set[str] = set()
    c = _read_conn(db_path)
    if c is None:
        return set()
    try:
        for start in range(0, len(event_ids), 900):
            batch = event_ids[start:start + 900]
            marks = ",".join("?" for _ in batch)
            rows = c.execute(
                f"SELECT event_id FROM source_events WHERE source=? AND event_id IN ({marks})",
                [source, *batch],
            ).fetchall()
            found.update(row[0] for row in rows)
    except sqlite3.OperationalError:
        return set()
    finally:
        c.close()
    return found


def storage_status(db_path=None) -> str:
    """Read-only storage readiness check; never creates the database."""
    c = _read_conn(db_path)
    if c is None:
        return "missing"
    try:
        c.execute("SELECT 1 FROM runs LIMIT 1")
        return "ok"
    except sqlite3.OperationalError:
        return "unavailable"
    finally:
        c.close()


def commit_ingestion_checkpoint(source: str, events: list[dict],
                                last_event_time: str, db_path=None) -> None:
    """Persist processed IDs and monotonic watermark in one SQLite transaction."""
    now = datetime.now(timezone.utc).isoformat()
    records = [
        (source, str(event["event_id"]), str(event.get("timestamp", "")), now)
        for event in events if event.get("event_id")
    ]
    with _conn(db_path) as c:
        c.executemany(
            "INSERT OR IGNORE INTO source_events(source,event_id,event_time,first_seen_at) "
            "VALUES(?,?,?,?)", records,
        )
        c.execute(
            "INSERT INTO watermark(source,last_event_time) VALUES(?,?) "
            "ON CONFLICT(source) DO UPDATE SET last_event_time="
            "CASE WHEN julianday(watermark.last_event_time) IS NULL OR "
            "julianday(excluded.last_event_time) > julianday(watermark.last_event_time) "
            "THEN excluded.last_event_time ELSE watermark.last_event_time END",
            (source, last_event_time),
        )
