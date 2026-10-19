# ingestion/source_router.py
"""
Source router — decides between CloudWatch and local telemetry.

Call `load_telemetry_auto()` instead of `load_telemetry()` in run_pipeline.py.
This is the single place responsible for the fallback chain:

  1. CloudWatch available + credentials valid  →  fetch live data
  2. CloudWatch unavailable / credentials missing  →  use local JSON file
  3. Local JSON file missing  →  generate fresh mock dataset

Standalone adapters (#3): `ingestion/csv_adapter.CSVAdapter` and
`ingestion/s3_adapter.S3Adapter` implement the `SourceAdapter` protocol
(`ingestion/base.py`) with watermark-aware `fetch(start_time, end_time,
max_events)` and are used directly (not via this auto chain) — e.g.
`CSVAdapter(path).fetch()` for a local CSV/Parquet export or
`S3Adapter(bucket, key).fetch()` for an S3-hosted CSV. The auto chain above
stays CloudWatch → local → mock only.

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

from ingestion.load_logs import events_to_frame, load_telemetry
from ingestion.cloudwatch_connector import (
    fetch_cloudwatch_events,
    is_cloudwatch_available,
)
from ingestion.cloudwatch_normalizer import normalize_cloudtrail_batch

logger = logging.getLogger(__name__)


class NormalizedCloudWatchBatch(list):
    """Normalized events with raw provider count for provenance metadata."""
    def __init__(self, events, raw_count: int):
        super().__init__(events)
        self.raw_count = raw_count
        self.normalization_skipped = max(0, raw_count - len(events))

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
        "enabled": True,
        "watermark_overlap_minutes": 10,
    }
    if not _CW_CONFIG_PATH.exists():
        return defaults
    try:
        with open(_CW_CONFIG_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"[CONFIG] cloudwatch.yaml is invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("[CONFIG] cloudwatch.yaml must contain a YAML mapping")
    cw = data.get("cloudwatch", {})
    if cw is None:
        cw = {}
    if not isinstance(cw, dict):
        raise ValueError("[CONFIG] cloudwatch.yaml: 'cloudwatch' must be a mapping")
    merged = {**defaults, **cw}
    # Basic type/range validation (fail fast, not mid-fetch)
    if not isinstance(merged.get("cache_to_local", True), bool):
        raise ValueError("[CONFIG] cloudwatch.yaml: cache_to_local must be boolean")
    if not isinstance(merged.get("enabled", True), bool):
        raise ValueError("[CONFIG] cloudwatch.yaml: enabled must be boolean")
    for key in ("lookback_hours", "max_events"):
        v = merged.get(key)
        if not isinstance(v, (int, float)) or isinstance(v, bool) or v <= 0:
            raise ValueError(f"[CONFIG] cloudwatch.yaml: {key} must be a positive number")
    overlap = merged.get("watermark_overlap_minutes", 10)
    if not isinstance(overlap, (int, float)) or isinstance(overlap, bool) or overlap < 0:
        raise ValueError("[CONFIG] cloudwatch.yaml: watermark_overlap_minutes must be non-negative")
    if not isinstance(merged.get("log_group_name", ""), str) or not merged["log_group_name"]:
        raise ValueError("[CONFIG] cloudwatch.yaml: log_group_name must be a non-empty string")
    return merged


def _resolve_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Apply environment-variable overrides on top of YAML config."""
    cfg = dict(cfg)
    # Only non-empty env values override (empty string must not blank the region)
    region = os.getenv("AWS_DEFAULT_REGION")
    if region:
        cfg["region"] = region
    group = os.getenv("CLOUDWATCH_LOG_GROUP")
    if group:
        cfg["log_group_name"] = group
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
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


# ---------------------------------------------------------------------------
# CloudWatch ingestion path
# ---------------------------------------------------------------------------

def _watermark_start_time(source: str = "cloudwatch", overlap_minutes: int = 10):
    """Best-effort watermark read for incremental fetch; None → use lookback."""
    try:
        from reporting.history_store import get_watermark
        wm = get_watermark(source)
        if wm:
            from datetime import timedelta
            start = datetime.fromisoformat(str(wm).replace("Z", "+00:00"))
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            start -= timedelta(minutes=max(0, int(overlap_minutes)))
            logger.info("[SOURCE] Using overlapping watermark window from %s.", start.isoformat())
            return start.isoformat()
    except Exception as exc:
        logger.debug("Watermark read failed, using lookback: %s", exc)
    return None


def _fetch_and_normalize(cfg: dict[str, Any]) -> list[dict] | None:
    """
    Fetch from CloudWatch and normalize to internal schema.

    Incremental (#2): when a watermark exists in data/history.db (written by
    run_pipeline via set_watermark), it is passed as start_time so CloudWatch
    fetch becomes incremental. Falls back to lookback_hours when no watermark
    or on any watermark error. Returns None if CloudWatch is unavailable or
    returns zero events.
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
        start_time=(
            None if cfg.get("_skip_checkpoint") else
            _watermark_start_time(overlap_minutes=cfg.get("watermark_overlap_minutes", 10))
        ),
    )

    if not raw_events:
        logger.info("CloudWatch returned 0 events.")
        return None

    normalized = normalize_cloudtrail_batch(raw_events)
    logger.info(
        "Normalized %d / %d CloudWatch events.", len(normalized), len(raw_events)
    )
    return NormalizedCloudWatchBatch(normalized, raw_count=len(raw_events))


def _cache_events(events: list[dict], raw_path: str) -> None:
    """Write normalized events to the local JSON cache + metadata sidecar."""
    path = Path(raw_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2)
    os.replace(tmp, path)
    logger.info("Cached %d CloudWatch events → %s", len(events), raw_path)
    _write_cache_meta(raw_path, len(events))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_telemetry_auto(
    raw_path: str,
    rejected_path: str | None = None,
    dry_run: bool = False,
    persist_cache: bool = True,
    mock_output_path: str | None = None,
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
    mock_output_path : str | None
        Separate destination for generated development fixtures, so output
        isolation does not overwrite or create files beside the input dataset.
    rejected_path : str | None
        Path to write schema-rejected events.

    Returns
    -------
    (df, stats) where stats includes:
      - 'data_source': 'cloudwatch' | 'local' | 'mock'
      - 'cache_age_hours': float (only when data_source=='local' and cache came from CW)
    """
    cfg = _resolve_config(_load_cw_config())
    reject_output = None if dry_run else rejected_path
    generated_path = mock_output_path or raw_path
    data_source = "local"
    cloudwatch_raw_count = 0
    cache_age_hours = None

    # ------------------------------------------------------------------
    # Attempt 1: CloudWatch (uses live events directly — never discards
    # them in favour of a stale local file).
    # ------------------------------------------------------------------
    cw_events = None
    if cfg.get("enabled", True):
        try:
            fetch_cfg = {**cfg, "_skip_checkpoint": dry_run}
            cw_events = _fetch_and_normalize(fetch_cfg)
        except ValueError:
            raise
        except Exception as exc:
            logger.warning("CloudWatch path failed, using local fallback: %s", exc)
            cw_events = None

    if cw_events is not None:
        cloudwatch_raw_count = getattr(cw_events, "raw_count", len(cw_events))
        if cfg.get("cache_to_local", True) and persist_cache and not dry_run:
            try:
                _cache_events(cw_events, raw_path)
            except OSError as exc:
                logger.warning("Could not cache CloudWatch events: %s", exc)
        data_source = "cloudwatch"
        cache_age_hours = 0.0
        logger.info(
            "[SOURCE] CloudWatch -> %d live events (cached=%s).",
            cloudwatch_raw_count, bool(cfg.get("cache_to_local", True)),
        )
        prior_duplicates = 0
        if not dry_run:
            try:
                from reporting.history_store import processed_event_ids
                ids = [str(event.get("event_id")) for event in cw_events]
                seen = processed_event_ids("cloudwatch", ids)
                fresh_events = [event for event in cw_events if str(event.get("event_id")) not in seen]
                prior_duplicates = len(cw_events) - len(fresh_events)
                raw_count = getattr(cw_events, "raw_count", len(cw_events))
                normalization_skipped = getattr(cw_events, "normalization_skipped", 0)
                cw_events = NormalizedCloudWatchBatch(
                    fresh_events, raw_count=raw_count
                )
                cw_events.normalization_skipped = normalization_skipped
            except Exception as exc:
                raise RuntimeError("Unable to verify CloudWatch event idempotency") from exc
        df, stats = events_to_frame(cw_events, rejected_path=reject_output)
        stats["duplicates_from_prior_runs"] = prior_duplicates
        stats["cloudwatch_normalization_skipped"] = getattr(cw_events, "normalization_skipped", 0)
    else:
        if (
            os.getenv("APP_ENV", "development").lower() == "production"
            and cfg.get("enabled", True)
        ):
            raise RuntimeError(
                "CloudWatch did not return usable events; production fallback to cached or mock data is disabled."
            )
        logger.info("[SOURCE] Using local fallback data.")

        # ------------------------------------------------------------------
        # Attempt 2 / 3: Local file (or generate mock if missing)
        # ------------------------------------------------------------------
        if not Path(raw_path).exists():
            if dry_run or os.getenv("APP_ENV", "development").lower() == "production":
                raise FileNotFoundError(
                    f"Run requires existing local telemetry; missing: {raw_path}"
                )
            logger.info("[SOURCE] Local file missing — generating mock dataset.")
            from scripts.generate_mock_telemetry import generate_dataset
            Path(generated_path).parent.mkdir(parents=True, exist_ok=True)
            generate_dataset(output_path=generated_path)
            raw_path = generated_path
            if data_source == "local":
                data_source = "mock"
        else:
            # Local file exists — check if it's a stale CW cache
            meta = _read_cache_meta(raw_path)
            if isinstance(meta, dict) and meta.get("source") == "cloudwatch":
                try:
                    fetched = datetime.fromisoformat(
                        str(meta["fetched_at"]).replace("Z", "+00:00")
                    )
                    if fetched.tzinfo is None:
                        fetched = fetched.replace(tzinfo=timezone.utc)
                    cache_age_hours = (
                        datetime.now(timezone.utc) - fetched
                    ).total_seconds() / 3600
                except Exception:
                    pass

        try:
            df, stats = load_telemetry(raw_path, rejected_path=reject_output)
        except (FileNotFoundError, ValueError) as exc:
            if dry_run or os.getenv("APP_ENV", "development").lower() == "production":
                raise ValueError(
                    f"Run cannot replace unreadable local telemetry with mock data: {exc}"
                ) from exc
            # Corrupt local file must not break the chain — fall back to mock
            logger.warning("Local telemetry unreadable (%s); generating mock.", exc)
            from scripts.generate_mock_telemetry import generate_dataset
            Path(generated_path).parent.mkdir(parents=True, exist_ok=True)
            generate_dataset(output_path=generated_path)
            raw_path = generated_path
            data_source = "mock"
            df, stats = load_telemetry(raw_path, rejected_path=reject_output)

    # Enrich stats with source metadata
    stats["data_source"] = data_source
    stats["cloudwatch_raw_events"] = cloudwatch_raw_count
    if cache_age_hours is not None:
        stats["cache_age_hours"] = round(cache_age_hours, 1)
    if data_source == "cloudwatch":
        stats["cloudwatch_log_group"] = cfg["log_group_name"]
        stats["cloudwatch_region"]    = cfg["region"]
        stats["cloudwatch_lookback_hours"] = cfg["lookback_hours"]
        stats["cloudwatch_watermark_overlap_minutes"] = cfg.get("watermark_overlap_minutes", 10)

    return df, stats
