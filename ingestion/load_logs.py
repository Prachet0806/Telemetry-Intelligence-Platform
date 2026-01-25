# ingestion/load_logs.py
import json
from collections import Counter
from typing import List, Dict, Any, Optional, Tuple

import pandas as pd

from ingestion.validate_schema import validate_event

def load_telemetry(
    path: str,
    rejected_path: Optional[str] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    with open(path, "r") as f:
        events: List[Dict] = json.load(f)

    valid_events: List[Dict] = []
    rejected_events: List[Dict] = []
    error_types: Counter = Counter()

    for event in events:
        try:
            validate_event(event)
            valid_events.append(event)
        except Exception as exc:
            error_types[type(exc).__name__] += 1
            rejected_events.append(event)

    if rejected_path and rejected_events:
        with open(rejected_path, "w") as f:
            json.dump(rejected_events, f, indent=2)

    df = pd.json_normalize(valid_events)
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"])

    stats = {
        "total_events": len(events),
        "valid_events": len(valid_events),
        "invalid_events": len(rejected_events),
        "error_types": dict(error_types),
        "rejected_path": rejected_path if rejected_events else None,
    }

    return df, stats
