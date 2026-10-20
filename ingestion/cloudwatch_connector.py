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


class EventLimitExceeded(ValueError):
    """Raised when a query exceeds its configured cap instead of truncating silently."""


def pd_to_ms(v) -> float:
    """Parse ISO str / datetime to epoch ms."""
    from datetime import datetime as _dt
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        v = _dt.fromisoformat(v.replace("Z", "+00:00"))
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.timestamp() * 1000
    raise ValueError(f"bad time {v!r}")


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
        # Ask AWS for an exact-name pattern; prefix pagination can return many
        # unrelated groups and makes a health probe needlessly expensive.
        response = client.describe_log_groups(logGroupNamePattern=log_group)
        return any(
            group.get("logGroupName") == log_group
            for group in response.get("logGroups", [])
        )
    except Exception as exc:
        logger.debug("CloudWatch availability check failed: %s", exc)
        return False


def fetch_cloudwatch_events(
    log_group: str,
    lookback_hours: int = 24,
    max_events: int = 5000,
    region: str | None = None,
    filter_pattern: str = "",
    start_time=None,
    end_time=None,
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

    if not isinstance(log_group, str) or not log_group.strip():
        logger.warning("Invalid log_group %r — using local fallback.", log_group)
        return []
    if not isinstance(lookback_hours, (int, float)) or lookback_hours <= 0:
        logger.warning("Invalid lookback_hours %r — using local fallback.", lookback_hours)
        return []
    if not isinstance(max_events, (int, float)) or int(max_events) <= 0:
        logger.warning("Invalid max_events %r — using local fallback.", max_events)
        return []
    max_events = int(max_events)
    if not isinstance(filter_pattern, str):
        logger.warning("Invalid filter_pattern — ignoring.")
        filter_pattern = ""

    try:
        session = _make_session(region)
        client = session.client("logs")

        start_ms = int(
            (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).timestamp() * 1000
        )
        end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        # Incremental watermark override (#2): explicit window wins over lookback
        try:
            if start_time is not None:
                start_ms = int(pd_to_ms(start_time))
            if end_time is not None:
                end_ms = int(pd_to_ms(end_time))
        except Exception:
            pass

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

        # Paginate through results (break on repeated tokens; backoff on throttle)
        import random as _random

        seen_tokens: set[str] = set()
        backoff = 0.2
        while True:
            try:
                resp = client.filter_log_events(**kwargs)
            except Exception as exc:
                name = type(exc).__name__
                if "Throttl" in name or "RateExceeded" in name:
                    if backoff > 5:
                        raise
                    time.sleep(backoff + _random.uniform(0, 0.2))
                    backoff *= 2
                    continue
                raise
            for log_event in resp.get("events", []):
                message = log_event.get("message") if isinstance(log_event, dict) else None
                if not isinstance(message, str):
                    continue
                try:
                    body = json.loads(message)
                except (json.JSONDecodeError, TypeError):
                    # Skip malformed log entries
                    continue
                try:
                    if isinstance(body, dict):
                        records = body.get("Records", [body])
                        if records is None:
                            records = [body]
                    elif isinstance(body, list):
                        records = body
                    else:
                        continue
                    if not isinstance(records, list):
                        continue
                    raw_events.extend(r for r in records if isinstance(r, dict))
                except (AttributeError, TypeError):
                    continue

                if len(raw_events) > max_events:
                    raise EventLimitExceeded(
                        f"CloudWatch query exceeded max_events={max_events}; "
                        "no partial batch was returned. Increase the limit or narrow the time window."
                    )

            next_token = resp.get("nextToken")
            if len(raw_events) >= max_events and next_token:
                raise EventLimitExceeded(
                    f"CloudWatch query reached max_events={max_events} with more pages available; "
                    "no partial batch was returned. Increase the limit or narrow the time window."
                )
            if not next_token or next_token in seen_tokens:
                if next_token in seen_tokens:
                    logger.warning("Repeated pagination token — stopping.")
                break
            seen_tokens.add(next_token)
            kwargs["nextToken"] = next_token
            time.sleep(0.1)  # light rate-limit courtesy pause
            backoff = 0.2

        logger.info("Fetched %d raw CloudTrail events.", len(raw_events))
        return raw_events

    except ImportError:
        logger.warning("boto3 is not installed — CloudWatch ingestion unavailable.")
        return []
    except EventLimitExceeded:
        raise
    except Exception as exc:
        # Covers: NoCredentialsError, ClientError, EndpointResolutionError, etc.
        logger.warning("CloudWatch fetch failed (%s: %s). Using local fallback.", type(exc).__name__, exc)
        return []
