# ingestion/csv_adapter.py
"""CSV/Parquet local source adapter (#3): reads a file into internal-schema events."""
from __future__ import annotations

from pathlib import Path

import pandas as pd


class CSVAdapter:
    name = "csv"

    def __init__(self, path: str):
        self.path = path

    def fetch(self, start_time=None, end_time=None, max_events: int = 5000) -> list[dict]:
        p = Path(self.path)
        if not p.exists():
            return []
        if p.suffix.lower() in (".parquet", ".pq"):
            df = pd.read_parquet(p)
        else:
            df = pd.read_csv(p)
        if start_time is not None and "timestamp" in df.columns:
            try:
                ts = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
                df = df[(ts >= pd.to_datetime(start_time, utc=True)) &
                        (ts <= pd.to_datetime(end_time, utc=True) if end_time else True)]
            except Exception:
                pass
        df = df.head(max_events)
        return df.to_dict(orient="records")
