"""Immutable per-run artifact publication with an atomic latest-run pointer."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


def latest_run_dir(root: str | Path) -> Path:
    """Resolve the committed run directory once for a consistent multi-file read."""
    base = Path(root)
    marker_path = base / "latest.json"
    if not marker_path.exists():
        return base
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        run_id = marker.get("run_id") if isinstance(marker, dict) else None
        if isinstance(run_id, str) and _SAFE_RUN_ID.fullmatch(run_id):
            return base / "runs" / run_id
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    # A corrupt or incomplete pointer must not silently select stale legacy output.
    return base / "runs" / "__invalid_latest_marker__"


def latest_artifact_path(name: str, root: str | Path) -> Path:
    """Resolve an artifact from the committed latest run, with legacy fallback."""
    if Path(name).name != name:
        raise ValueError("artifact name must be a basename")
    return latest_run_dir(root) / name


def publish_run(staging_dir: str | Path, final_dir: str | Path,
                root: str | Path, run_id: str, generated_at: str) -> Path:
    """Commit a completed staging directory, then atomically switch latest.json."""
    stage = Path(staging_dir)
    final = Path(final_dir)
    base = Path(root)
    if not _SAFE_RUN_ID.fullmatch(run_id):
        raise ValueError("unsafe run_id")
    if not stage.is_dir():
        raise FileNotFoundError(f"run staging directory does not exist: {stage}")
    final.parent.mkdir(parents=True, exist_ok=True)
    os.replace(stage, final)
    marker = {"run_id": run_id, "generated_at": generated_at}
    marker_path = base / "latest.json"
    tmp = marker_path.with_name(f".{marker_path.name}.{os.getpid()}.{run_id}.tmp")
    try:
        tmp.write_text(json.dumps(marker, indent=2), encoding="utf-8")
        os.replace(tmp, marker_path)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
    return final
