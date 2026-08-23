# ingestion/cloudwatch_connector.py
"""
AWS CloudWatch Logs connector.

Fetches raw log events from a CloudWatch Log Group (typically a CloudTrail
destination) using boto3.  All AWS exceptions are caught and surfaced as an
empty list so callers can implement fallback logic cleanly.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)


def _make_session(region: str):
    """Create a boto3 session, letting boto3 resolve credentials from the
    standard chain: env vars → ~/.aws/credentials → instance profile."""
    import boto3  # local import so missing boto3 doesn't break the module

    return boto3.Session(region_name=region)


def is_cloudwatch_available(log_group: str, region: str) -> bool:
    """
    Quick probe: can we reach CloudWatch and does the log group exist?

    Returns False (never raises) on any boto3 / credential error.
    """
    try:
        session = _make_session(region)
        client = session.client("logs")
        # logGroupNamePattern without wildcards is an exact match; using it
        # instead of prefix+limit avoids false negatives when several log
        # groups share a prefix (e.g. "CloudTrail/a", "CloudTrail/b").
        resp = client.describe_log_groups(logGroupNamePattern=log_group, limit=1)
        groups = resp.get("logGroups", [])
        return any(g["logGroupName"] == log_group for g in groups)
    except Exception as exc:
        logger.debug("CloudWatch availability check failed: %s", exc)
        return False


def fetch_cloudwatch_events(
    log_group: str,
    lookback_hours: int = 24,
    max_events: int = 5000,
    region: str | None = None,
    filter_pattern: str = "",
) -> list[dict[str, Any]]:
    """
    Fetch raw CloudTrail log events from a CloudWatch Logs group.

    Parameters
    ----------
    log_group : str
        CloudWatch Log Group name.
    lookback_hours : int
        How far back to query (relative to now UTC).
    max_events : int
        Hard ceiling on total events returned (across all pagination pages).
    region : str | None
        AWS region. Defaults to AWS_DEFAULT_REGION env var, then 'us-east-1'.
    filter_pattern : str
        Optional CloudWatch filter/metric pattern string.

    Returns
    -------
    list[dict] — parsed CloudTrail event dicts ready for normalisation.
                 Returns an empty list (never raises) on any failure.
    """
    if region is None:
        region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

    try:
        session = _make_session(region)
        client = session.client("logs")

        start_ms = int(
            (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).timestamp() * 1000
        )
        end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

        raw_events: list[dict] = []
        kwargs: dict[str, Any] = {
            "logGroupName": log_group,
            "startTime": start_ms,
            "endTime": end_ms,
            "limit": min(max_events, 10000),
        }
        if filter_pattern:
            kwargs["filterPattern"] = filter_pattern

        logger.info(
            "Fetching CloudWatch events from '%s' (last %d hours, max %d)...",
            log_group, lookback_hours, max_events,
        )

        # Paginate through results
        while True:
            resp = client.filter_log_events(**kwargs)
            for log_event in resp.get("events", []):
                try:
                    body = json.loads(log_event["message"])
                    # CloudTrail wraps events in a "Records" array
                    records = body.get("Records", [body])
                    raw_events.extend(records)
                except (json.JSONDecodeError, KeyError):
                    # Skip malformed log entries
                    continue

                if len(raw_events) >= max_events:
                    logger.info("Reached max_events limit (%d).", max_events)
                    return raw_events[:max_events]

            next_token = resp.get("nextToken")
            if not next_token:
                break
            kwargs["nextToken"] = next_token
            time.sleep(0.1)  # light rate-limit courtesy pause

        logger.info("Fetched %d raw CloudTrail events.", len(raw_events))
        return raw_events

    except ImportError:
        logger.warning("boto3 is not installed — CloudWatch ingestion unavailable.")
        return []
    except Exception as exc:
        # Covers: NoCredentialsError, ClientError, EndpointResolutionError, etc.
        logger.warning("CloudWatch fetch failed (%s: %s). Using local fallback.", type(exc).__name__, exc)
        return []
