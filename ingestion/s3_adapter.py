# ingestion/s3_adapter.py
"""S3 source adapter (#3): downloads a key then delegates to CSVAdapter."""
from __future__ import annotations

import tempfile
from pathlib import Path


class S3Adapter:
    name = "s3"

    def __init__(self, bucket: str, key: str, region: str = "us-east-1"):
        self.bucket = bucket
        self.key = key
        self.region = region

    def fetch(self, start_time=None, end_time=None, max_events: int = 5000) -> list[dict]:
        try:
            import boto3  # type: ignore
            from ingestion.csv_adapter import CSVAdapter
            s3 = boto3.client("s3", region_name=self.region)
            suffix = Path(self.key).suffix or ".csv"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                s3.download_file(self.bucket, self.key, tmp.name)
                return CSVAdapter(tmp.name).fetch(start_time, end_time, max_events)
        except Exception:
            return []
