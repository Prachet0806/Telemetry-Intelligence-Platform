# ingestion/validate_schema.py
"""
Field-level schema validation for incoming telemetry events.

Raises ValueError/TypeError for any violation so the ingestion pipeline
can reject bad events at the boundary (fail-fast).
"""

from datetime import datetime
from typing import Any, Dict


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
    Parse an ISO-8601 timestamp, accepting both 'Z' and '+00:00' UTC forms.

    Raises ValueError if the string is not a valid UTC timestamp.
    """
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def validate_event(event: Dict[str, Any]) -> None:
    """
    Validate a single telemetry event against the internal schema.

    Raises
    ------
    ValueError  — missing field, invalid enum value, unparseable timestamp.
    TypeError   — field exists but has the wrong type.
    """
    for field, expected_type in REQUIRED_FIELDS.items():
        if field not in event:
            raise ValueError(f"Missing required field: {field}")

        value = event[field]

        # Special handling for fields with custom type checks
        if field == "resource_count":
            if not _is_plain_int(value):
                raise TypeError(
                    f"Invalid type for field 'resource_count': expected int, got {type(value).__name__}"
                )
        elif field == "metadata":
            if not isinstance(value, dict):
                raise TypeError(
                    f"Invalid type for field 'metadata': expected dict, got {type(value).__name__}"
                )
        elif not isinstance(value, expected_type):
            raise TypeError(
                f"Invalid type for field '{field}': expected {expected_type.__name__}, got {type(value).__name__}"
            )

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

    # Metadata sub-fields
    metadata = event["metadata"]
    for field, expected_type in METADATA_FIELDS.items():
        if field not in metadata:
            raise ValueError(f"Missing metadata field: {field}")

        value = metadata[field]

        if field == "resource_count":
            if not _is_plain_int(value):
                raise TypeError(
                    f"Invalid type for metadata field 'resource_count': expected int, got {type(value).__name__}"
                )
        elif field == "policy_scope":
            if value not in VALID_POLICY_SCOPES:
                raise ValueError(
                    f"Invalid policy_scope '{value}': must be one of {sorted(VALID_POLICY_SCOPES)}"
                )
        elif not isinstance(value, expected_type):
            raise TypeError(
                f"Invalid type for metadata field '{field}': expected {expected_type.__name__}, got {type(value).__name__}"
            )