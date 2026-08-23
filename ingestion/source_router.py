# ingestion/source_router.py
"""
Source router — decides between CloudWatch and local telemetry.

Call `load_telemetry_auto()` instead of `load_telemetry()` in run_pipeline.py.
This is the single place responsible for the fallback chain:

  1. CloudWatch available + credentials valid  →  fetch live data
  2. CloudWatch unavailable / credentials missing  →  use local JSON file
  3. Local JSON file missing  →  generate fresh mock dataset

The returned stats dict includes a 'data_source' key so the dashboard
and pipeline logs can display which path was taken. When the local cache
originated from a previous CloudWatch fetch, `cache_age_hours` is included
so the UI can show staleness.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from ingestion.load_logs import load_telemetry
from ingestion.cloudwatch_connector import (
    fetch_cloudwatch_events,
    is_cloudwatch_available,
)
from ingestion.cloudwatch_normalizer import normalize_cloudtrail_batch

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CW_CONFIG_PATH = _PROJECT_ROOT / "config" / "cloudwatch.yaml"


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _load_cw_config() -> dict[str, Any]:
    """Load cloudwatch.yaml, returning sensible defaults if absent."""
    defaults: dict[str, Any] = {
        "log_group_name": "CloudTrail/DefaultLogGroup",
        "lookback_hours": 24,
        "max_events": 5000,
        "filter_pattern": "",
        "region": "us-east-1",
        "cache_to_local": True,
    }
    if not _CW_CONFIG_PATH.exists():
        return defaults
    with open(_CW_CONFIG_PATH) as f:
        data = yaml.safe_load(f) or {}
    return {**defaults, **data.get("cloudwatch", {})}


def _resolve_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Apply environment-variable overrides on top of YAML config."""
    cfg = dict(cfg)
    cfg["region"] = os.getenv("AWS_DEFAULT_REGION", cfg["region"])
    cfg["log_group_name"] = os.getenv("CLOUDWATCH_LOG_GROUP", cfg["log_group_name"])
    return cfg


def _cache_meta_path(raw_path: str) -> Path:
    """Sidecar metadata file path for the local cache."""
    return Path(raw_path).with_suffix(".meta.json")


def _write_cache_meta(raw_path: str, event_count: int) -> None:
    """Write cache metadata with fetch timestamp and event count."""
    meta = {
        "source": "cloudwatch",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "event_count": event_count,
    }
    meta_path = _cache_meta_path(raw_path)
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def _read_cache_meta(raw_path: str) -> dict | None:
    """Read cache metadata if present and valid."""
    meta_path = _cache_meta_path(raw_path)
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


# ---------------------------------------------------------------------------
# CloudWatch ingestion path
# ---------------------------------------------------------------------------

def _fetch_and_normalize(cfg: dict[str, Any]) -> list[dict] | None:
    """
    Fetch from CloudWatch and normalize to internal schema.

    Returns None if CloudWatch is unavailable or returns zero events.
    """
    log_group = cfg["log_group_name"]
    region    = cfg["region"]

    if not is_cloudwatch_available(log_group, region):
        logger.info(
            "CloudWatch log group '%s' not reachable in '%s'. Using local fallback.",
            log_group, region,
        )
        return None

    raw_events = fetch_cloudwatch_events(
        log_group=log_group,
        lookback_hours=cfg["lookback_hours"],
        max_events=cfg["max_events"],
        region=region,
        filter_pattern=cfg["filter_pattern"],
    )

    if not raw_events:
        logger.info("CloudWatch returned 0 events. Using local fallback.")
        return None

    normalized = normalize_cloudtrail_batch(raw_events)
    logger.info(
        "Normalized %d / %d CloudWatch events.", len(normalized), len(raw_events)
    )
    return normalized if normalized else None


def _cache_events(events: list[dict], raw_path: str) -> None:
    """Write normalized events to the local JSON cache + metadata sidecar."""
    path = Path(raw_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(events, f, indent=2)
    logger.info("Cached %d CloudWatch events → %s", len(events), raw_path)
    _write_cache_meta(raw_path, len(events))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_telemetry_auto(
    raw_path: str,
    rejected_path: str | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Load telemetry from the best available source.

    Priority
    --------
    1. AWS CloudWatch Logs (if credentials + log group are reachable)
    2. Local JSON file at raw_path (mock data or cached CloudWatch data)
    3. Auto-generate fresh mock data (if raw_path is missing)

    Parameters
    ----------
    raw_path : str
        Path to the local JSON telemetry file (used for local fallback and caching).
    rejected_path : str | None
        Path to write schema-rejected events.

    Returns
    -------
    (df, stats) where stats includes:
      - 'data_source': 'cloudwatch' | 'local' | 'mock'
      - 'cache_age_hours': float (only when data_source=='local' and cache came from CW)
    """
    cfg = _resolve_config(_load_cw_config())
    data_source = "local"
    cloudwatch_raw_count = 0
    cache_age_hours = None

    # ------------------------------------------------------------------
    # Attempt 1: CloudWatch
    # ------------------------------------------------------------------
    cw_events = _fetch_and_normalize(cfg)

    if cw_events is not None:
        cloudwatch_raw_count = len(cw_events)
        if cfg.get("cache_to_local", True):
            _cache_events(cw_events, raw_path)
        data_source = "cloudwatch"
        logger.info(
            "[SOURCE] CloudWatch -> %d events fetched and cached.", cloudwatch_raw_count
        )
    else:
        logger.info("[SOURCE] Using local fallback data.")

    # ------------------------------------------------------------------
    # Attempt 2 / 3: Local file (or generate mock if missing)
    # ------------------------------------------------------------------
    if not Path(raw_path).exists():
        logger.info("[SOURCE] Local file missing — generating mock dataset.")
        from scripts.generate_mock_telemetry import generate_dataset
        Path(raw_path).parent.mkdir(parents=True, exist_ok=True)
        generate_dataset(output_path=raw_path)
        if data_source == "local":
            data_source = "mock"
    else:
        # Local file exists — check if it's a stale CW cache
        meta = _read_cache_meta(raw_path)
        if meta and meta.get("source") == "cloudwatch":
            try:
                fetched = datetime.fromisoformat(meta["fetched_at"].replace("Z", "+00:00"))
                cache_age_hours = (datetime.now(timezone.utc) - fetched).total_seconds() / 3600
            except Exception:
                pass

    df, stats = load_telemetry(raw_path, rejected_path=rejected_path)

    # Enrich stats with source metadata
    stats["data_source"] = data_source
    stats["cloudwatch_raw_events"] = cloudwatch_raw_count
    if cache_age_hours is not None:
        stats["cache_age_hours"] = round(cache_age_hours, 1)
    if data_source == "cloudwatch":
        stats["cloudwatch_log_group"] = cfg["log_group_name"]
        stats["cloudwatch_region"]    = cfg["region"]
        stats["cloudwatch_lookback_hours"] = cfg["lookback_hours"]

    return df, stats