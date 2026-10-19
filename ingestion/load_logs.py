# ingestion/load_logs.py
import json
from collections import Counter
from typing import List, Dict, Any, Optional, Tuple

import pandas as pd

from ingestion.validate_schema import validate_event

def events_to_frame(
    events: List[Dict],
    rejected_path: Optional[str] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Validate/dedup an in-memory event list (CloudWatch path).

    Same semantics as load_telemetry() but without re-reading a file,
    so live CloudWatch events are never discarded in favour of stale cache.
    """
    valid_events: List[Dict] = []
    rejected_events: List[Dict] = []
    error_types: Counter = Counter()

    for event in events:
        if not isinstance(event, dict):
            error_types["NonDictEvent"] += 1
            rejected_events.append({"event": event, "error": "NonDictEvent"})
            continue
        try:
            validate_event(event)
            valid_events.append(event)
        except Exception as exc:
            error_types[type(exc).__name__] += 1
            rejected_events.append({"event": event, "error": f"{type(exc).__name__}: {exc}"})

    seen_ids: set[str] = set()
    unique_events: List[Dict] = []
    duplicate_count = 0
    for event in valid_events:
        event_id = event.get("event_id")
        if event_id in seen_ids:
            duplicate_count += 1
            continue
        seen_ids.add(event_id)
        unique_events.append(event)

    if rejected_path and rejected_events:
        _write_rejects(rejected_path, rejected_events)

    df = pd.json_normalize(unique_events)
    if not df.empty and "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(
            df["timestamp"], utc=True, errors="coerce", format="mixed"
        )

    stats = {
        "total_events": len(events),
        "valid_events": len(unique_events),
        "invalid_events": len(rejected_events),
        "duplicate_events": duplicate_count,
        "error_types": dict(error_types),
        "rejected_path": rejected_path if rejected_events else None,
    }
    return df, stats


def _write_rejects(rejected_path: str, rejected_events: List[Dict]) -> None:
    import os
    from pathlib import Path as _Path

    path = _Path(rejected_path)
    if path.parent and str(path.parent) not in ("", "."):
        path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp") if path.suffix else _Path(str(path) + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rejected_events, f, indent=2)
    os.replace(tmp, path)


def load_telemetry(
    path: str,
    rejected_path: Optional[str] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            events = json.load(f)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Telemetry file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Telemetry file is not valid JSON: {path}: {exc}") from exc
    if not isinstance(events, list):
        raise ValueError(
            f"Telemetry file must contain a JSON array, got {type(events).__name__}"
        )
    return events_to_frame(events, rejected_path=rejected_path)
