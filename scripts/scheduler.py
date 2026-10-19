# scripts/scheduler.py
"""Scheduled / incremental runner (#2): APScheduler loop with watermark catch-up."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _cfg() -> dict:
    p = PROJECT_ROOT / "config" / "scheduler.yaml"
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return data.get("scheduler", {})


def run_once() -> int:
    r = subprocess.run([sys.executable, str(PROJECT_ROOT / "scripts" / "run_pipeline.py")],
                       cwd=str(PROJECT_ROOT))
    if r.returncode:
        print(f"[SCHEDULER] pipeline failed with exit code {r.returncode}")
    return r.returncode


def main() -> int:
    from decision.config_validation import validate_configs
    validate_configs()
    cfg = _cfg()
    if not cfg.get("enabled", False):
        print("[SCHEDULER] disabled by config/scheduler.yaml")
        return 0
    interval_hours = float(cfg["interval_hours"])
    interval = interval_hours * 3600
    misfire_grace = max(1, int(float(cfg["catchup_hours"]) * 3600))
    if cfg.get("run_on_start", True):
        run_once()
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler  # type: ignore
        s = BlockingScheduler()
        s.add_job(
            run_once, "interval", hours=interval_hours,
            max_instances=1, coalesce=True, misfire_grace_time=misfire_grace,
        )
        print(f"[SCHEDULER] every {interval_hours:g}h (APScheduler)")
        s.start()
    except ImportError:
        print(f"[SCHEDULER] APScheduler missing; simple loop every {interval / 3600}h")
        while True:
            time.sleep(interval)
            run_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
