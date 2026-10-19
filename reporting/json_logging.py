# reporting/json_logging.py
"""Structured JSON logging (#25)."""
from __future__ import annotations

import json
import logging
import sys


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {"level": record.levelname, "logger": record.name,
                   "msg": record.getMessage(), "run_id": getattr(record, "run_id", None)}
        return json.dumps(payload)


def setup_json_logging(level: int = logging.INFO) -> None:
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(JSONFormatter())
    root = logging.getLogger()
    root.handlers = [h]
    root.setLevel(level)
