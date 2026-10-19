# ingestion/validate_schema.py
"""
Field-level schema validation for incoming telemetry events.

Raises ValueError/TypeError for any violation so the ingestion pipeline
can reject bad events at the boundary (fail-fast).
"""

from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
import re
from typing import Any, Dict

MAX_STRING_LEN = 512


# Allowed enum values — keep in sync with the documented schema.
VALID_EVENT_TYPES = {"auth", "iam_change", "api_call"}
VALID_ACTOR_TYPES = {"human", "service"}
VALID_RISK_LEVELS = {"low", "medium", "high"}
VALID_POLICY_SCOPES = {"read", "write", "admin"}

REQUIRED_FIELDS = {
    "event_id": str,
    "timestamp": str,
    "event_type": str,
    "actor_type": str,
    "actor_id": str,
    "source_ip": str,
    "region": str,
    "resource_type": str,
    "action": str,
    "risk_level": str,
    "metadata": dict,
}

METADATA_FIELDS = {
    "policy_scope": str,
    "resource_count": int,
    "login_success": bool,
}


def _is_plain_int(value: Any) -> bool:
    """
    Accept int but reject bool (which is a subclass of int in Python).
    """
    return isinstance(value, int) and not isinstance(value, bool)


def _parse_iso_timestamp(value: str) -> datetime:
    """
    Parse an ISO-8601 timestamp, requiring explicit timezone info.

    Naive timestamps (no offset) are rejected so naive/aware mixes can
    never silently corrupt temporal features. Future timestamps more than
    5 minutes ahead are rejected as clock-skew/data errors.
    """
    raw = value
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        raise ValueError(f"timestamp '{raw}' must include timezone info (e.g. Z or +00:00)")
    now = datetime.now(timezone.utc)
    if dt > now + timedelta(minutes=5):
        raise ValueError(f"timestamp '{raw}' is in the future")
    return dt.astimezone(timezone.utc)


def _is_source_address(value: str) -> bool:
    """CloudTrail sourceIPAddress may be an IP, DNS name, or AWS Internal."""
    try:
        ip_address(value)
        return True
    except ValueError:
        if value == "AWS Internal":
            return True
        if len(value) > 253 or not value or value.endswith("."):
            return False
        labels = value.split(".")
        return all(
            1 <= len(label) <= 63
            and re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", label)
            for label in labels
        )


def validate_event(event: Dict[str, Any], strict: bool = False) -> None:
    """
    Validate a single telemetry event against the internal schema.

    Raises
    ------
    ValueError  — missing field, invalid enum value, unparseable timestamp.
    TypeError   — field exists but has the wrong type.
    """
    if not isinstance(event, dict):
        raise TypeError(f"event must be a dict, got {type(event).__name__}")
    if strict:
        extra = set(event) - set(REQUIRED_FIELDS)
        if extra:
            raise ValueError(f"Unexpected top-level fields: {sorted(extra)}")
    for field, expected_type in REQUIRED_FIELDS.items():
        if field not in event:
            raise ValueError(f"Missing required field: {field}")

        value = event[field]

        # Special handling for fields with custom type checks
        if field == "metadata":
            if not isinstance(value, dict):
                raise TypeError(
                    f"Invalid type for field 'metadata': expected dict, got {type(value).__name__}"
                )
        elif not isinstance(value, expected_type):
            raise TypeError(
                f"Invalid type for field '{field}': expected {expected_type.__name__}, got {type(value).__name__}"
            )
        if isinstance(value, str):
            if not value.strip():
                raise ValueError(f"Field '{field}' must be a non-empty string")
            if len(value) > MAX_STRING_LEN:
                raise ValueError(f"Field '{field}' exceeds {MAX_STRING_LEN} chars")

    # Enum checks
    if event["event_type"] not in VALID_EVENT_TYPES:
        raise ValueError(
            f"Invalid event_type '{event['event_type']}': must be one of {sorted(VALID_EVENT_TYPES)}"
        )
    if event["actor_type"] not in VALID_ACTOR_TYPES:
        raise ValueError(
            f"Invalid actor_type '{event['actor_type']}': must be one of {sorted(VALID_ACTOR_TYPES)}"
        )
    if event["risk_level"] not in VALID_RISK_LEVELS:
        raise ValueError(
            f"Invalid risk_level '{event['risk_level']}': must be one of {sorted(VALID_RISK_LEVELS)}"
        )

    # Timestamp parseability (fail-fast vs crash in pd.to_datetime later)
    try:
        _parse_iso_timestamp(event["timestamp"])
    except Exception as exc:
        raise ValueError(f"Invalid timestamp '{event['timestamp']}': {exc}") from exc

    # CloudTrail uses DNS names and "AWS Internal" for service-originated events.
    if not _is_source_address(event["source_ip"]):
        raise ValueError(f"Invalid source address '{event['source_ip']}'")

    # Metadata sub-fields
    metadata = event["metadata"]
    if strict:
        extra_meta = set(metadata) - set(METADATA_FIELDS)
        if extra_meta:
            raise ValueError(f"Unexpected metadata fields: {sorted(extra_meta)}")
    for field, expected_type in METADATA_FIELDS.items():
        if field not in metadata:
            raise ValueError(f"Missing metadata field: {field}")

        value = metadata[field]

        if field == "resource_count":
            if not _is_plain_int(value):
                raise TypeError(
                    f"Invalid type for metadata field 'resource_count': expected int, got {type(value).__name__}"
                )
            if not 0 <= value <= 1_000_000:
                raise ValueError(
                    f"Invalid resource_count {value}: must be in [0, 1000000]"
                )
        elif field == "policy_scope":
            if not isinstance(value, str):
                raise TypeError(
                    f"Invalid type for metadata field 'policy_scope': expected str, got {type(value).__name__}"
                )
            if value not in VALID_POLICY_SCOPES:
                raise ValueError(
                    f"Invalid policy_scope '{value}': must be one of {sorted(VALID_POLICY_SCOPES)}"
                )
        elif not isinstance(value, expected_type):
            raise TypeError(
                f"Invalid type for metadata field '{field}': expected {expected_type.__name__}, got {type(value).__name__}"
            )
