# scripts/prune.py
"""Data retention / archival (#backlog): TTL pruning per config/retention.yaml."""
from __future__ import annotations

import sqlite3
import json
import re
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
_RUN_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


def _days(value, default: int) -> int:
    try:
        days = int(value)
    except (TypeError, ValueError):
        return default
    return days if days > 0 else default


def main() -> int:
    cfg = {}
    try:
        cfg = (yaml.safe_load((ROOT / "config" / "retention.yaml").read_text(encoding="utf-8")) or {}).get("retention", {})
    except Exception:
        pass
    hist_days = _days(cfg.get("history_days", 365), 365)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=hist_days)).isoformat()
    db = ROOT / "data" / "history.db"
    if db.exists():
        with sqlite3.connect(str(db)) as c:
            tables = {row[0] for row in c.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if "runs" in tables:
                c.execute("DELETE FROM runs WHERE timestamp < ?", (cutoff,))
                if "triage" in tables:
                    c.execute("DELETE FROM triage WHERE run_id NOT IN (SELECT run_id FROM runs)")
                if "triage_events" in tables:
                    c.execute("DELETE FROM triage_events WHERE run_id NOT IN (SELECT run_id FROM runs)")
                print(f"[RETENTION] pruned history older than {cutoff}")
            if "source_events" in tables:
                c.execute("DELETE FROM source_events WHERE event_time < ?", (cutoff,))
            if not cfg.get("watermark_keep", True) and "watermark" in tables:
                c.execute("DELETE FROM watermark")
    # Keep the latest immutable snapshot; expire old snapshots and abandoned staging dirs.
    proc_days = _days(cfg.get("processed_days", 60), 60)
    now = time.time()
    processed = ROOT / "data" / "processed"
    runs_dir = processed / "runs"
    latest_run = None
    try:
        marker = json.loads((processed / "latest.json").read_text(encoding="utf-8"))
        latest_run = marker.get("run_id") if isinstance(marker, dict) else None
        if not isinstance(latest_run, str) or not _RUN_ID.fullmatch(latest_run):
            latest_run = None
    except (OSError, json.JSONDecodeError):
        pass
    cutoff_epoch = now - proc_days * 86400
    if runs_dir.is_dir():
        for path in runs_dir.iterdir():
            try:
                if path.is_symlink() or not path.is_dir() or path.stat().st_mtime >= cutoff_epoch:
                    continue
                if path.name.startswith(".") and path.name.endswith(".tmp"):
                    shutil.rmtree(path)
                    print(f"[RETENTION] removed abandoned run staging directory {path.name}")
                elif _RUN_ID.fullmatch(path.name) and path.name != latest_run:
                    shutil.rmtree(path)
                    print(f"[RETENTION] removed expired run snapshot {path.name}")
            except OSError as exc:
                print(f"[RETENTION] could not remove {path.name}: {exc}")
    # Remove stale root-level temporary files created by older pipeline versions.
    for path in processed.glob("*.tmp"):
        try:
            if path.is_file() and now - path.stat().st_mtime > proc_days * 86400:
                path.unlink(missing_ok=True)
        except OSError as exc:
            print(f"[RETENTION] could not remove {path.name}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
