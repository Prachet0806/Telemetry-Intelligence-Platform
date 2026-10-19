# ingestion/base.py
"""Pluggable source adapter interface (#3)."""
from __future__ import annotations

from typing import Protocol


class SourceAdapter(Protocol):
    name: str

    def fetch(self, start_time=None, end_time=None, max_events: int = 5000) -> list[dict]:
        ...
