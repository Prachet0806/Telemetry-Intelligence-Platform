# ingestion/cloudwatch_normalizer.py
"""
CloudTrail → platform internal schema normalizer.

CloudTrail log events have a very different shape to the platform's
internal event format.  This module provides a pure-function mapping
layer so neither the connector nor downstream pipeline code needs to
know about CloudTrail specifics.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CloudTrail eventName → platform event_type
# ---------------------------------------------------------------------------

_IAM_ACTIONS = {
    "AttachRolePolicy", "DetachRolePolicy", "CreateRole", "DeleteRole",
    "UpdateRole", "CreateUser", "DeleteUser", "AttachUserPolicy",
    "DetachUserPolicy", "PutRolePolicy", "PutUserPolicy", "CreateAccessKey",
    "UpdateAccessKey", "DeleteAccessKey", "CreateGroup", "AddUserToGroup",
    "RemoveUserFromGroup",
}

_AUTH_ACTIONS = {
    "ConsoleLogin", "AssumeRole", "AssumeRoleWithSAML",
    "AssumeRoleWithWebIdentity", "GetSessionToken", "GetFederationToken",
}


def _derive_event_type(event_name: str) -> str:
    if event_name in _IAM_ACTIONS:
        return "iam_change"
    if event_name in _AUTH_ACTIONS:
        return "auth"
    return "api_call"


# ---------------------------------------------------------------------------
# actor_type mapping
# ---------------------------------------------------------------------------

def _derive_actor_type(user_identity: dict) -> str:
    """Map CloudTrail userIdentity.type to platform actor_type."""
    identity_type = user_identity.get("type", "").lower()
    if identity_type in ("role", "assumerole", "federateduser", "webidentityuser"):
        return "service"
    return "human"


# ---------------------------------------------------------------------------
# Heuristic risk_level from CloudTrail fields
# ---------------------------------------------------------------------------

def _derive_risk_level(
    event_name: str,
    actor_type: str,
    policy_scope: str,
    resource_count: int,
    timestamp_hour: int,
) -> str:
    score = 0
    if actor_type == "service":
        score += 1
    if event_name in _IAM_ACTIONS:
        score += 2
    if policy_scope == "admin":
        score += 2
    if resource_count > 20:
        score += 2
    if timestamp_hour < 6 or timestamp_hour > 22:
        score += 1

    if score >= 6:
        return "high"
    if score >= 3:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# policy_scope inference
# ---------------------------------------------------------------------------

def _derive_policy_scope(event_name: str, request_params: dict | None) -> str:
    """Infer policy scope from action name and request parameters."""
    rp = request_params or {}
    policy_arn = str(rp.get("policyArn", "")).lower()

    if "administrat" in policy_arn or event_name in {"CreateRole", "AttachRolePolicy"}:
        return "admin"
    if "read" in policy_arn or event_name in {"GetObject", "ListBuckets"}:
        return "read"
    return "write"


# ---------------------------------------------------------------------------
# Resource type mapping
# ---------------------------------------------------------------------------

_SOURCE_TO_RESOURCE = {
    "iam.amazonaws.com":          "iam_role",
    "s3.amazonaws.com":           "s3_bucket",
    "ec2.amazonaws.com":          "ec2_instance",
    "lambda.amazonaws.com":       "lambda_function",
    "sts.amazonaws.com":          "iam_role",
    "cloudtrail.amazonaws.com":   "cloudtrail",
    "logs.amazonaws.com":         "cloudwatch_logs",
}


def _derive_resource_type(event_source: str) -> str:
    return _SOURCE_TO_RESOURCE.get(event_source, "aws_resource")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def normalize_cloudtrail_event(raw: dict[str, Any]) -> dict[str, Any] | None:
    """
    Map a single raw CloudTrail event dict to the platform's internal schema.

    Returns None for events that cannot be meaningfully mapped (missing
    required fields).  Callers should filter out None values.

    Parameters
    ----------
    raw : dict
        A single CloudTrail event record (from the Records[] array).

    Returns
    -------
    dict matching the platform schema, or None if the event should be skipped.
    """
    try:
        event_name    = raw.get("eventName", "")
        event_source  = raw.get("eventSource", "")
        aws_region    = raw.get("awsRegion", "us-east-1")
        source_ip     = raw.get("sourceIPAddress", "0.0.0.0")
        timestamp_str = raw.get("eventTime", "")
        user_identity = raw.get("userIdentity", {})
        request_params = raw.get("requestParameters") or {}

        if not event_name or not timestamp_str:
            return None

        # Stable event_id from CloudTrail eventID, or derive one
        event_id = raw.get("eventID") or hashlib.sha256(
            f"{timestamp_str}{event_name}{source_ip}".encode()
        ).hexdigest()[:36]

        actor_type = _derive_actor_type(user_identity)
        actor_id   = (
            user_identity.get("userName")
            or user_identity.get("principalId")
            or user_identity.get("accountId")
            or "unknown"
        )

        event_type    = _derive_event_type(event_name)
        resource_type = _derive_resource_type(event_source)

        # Extract resource count from request parameters heuristically
        resource_count = len(request_params) if isinstance(request_params, list) else 1

        # Parse timestamp hour for off-hours detection
        try:
            from datetime import datetime
            ts_hour = datetime.fromisoformat(
                timestamp_str.replace("Z", "+00:00")
            ).hour
        except ValueError:
            ts_hour = 12

        policy_scope = _derive_policy_scope(event_name, request_params)

        risk_level = _derive_risk_level(
            event_name, actor_type, policy_scope, resource_count, ts_hour
        )

        return {
            "event_id":      event_id,
            "timestamp":     timestamp_str,
            "event_type":    event_type,
            "actor_type":    actor_type,
            "actor_id":      actor_id,
            "source_ip":     source_ip,
            "region":        aws_region,
            "resource_type": resource_type,
            "action":        event_name,
            "risk_level":    risk_level,
            "metadata": {
                "policy_scope":   policy_scope,
                "resource_count": resource_count,
                "login_success":  raw.get("errorCode") is None,
            },
            # Pass-through extra CloudTrail fields for enrichment
            "_cloudtrail": {
                "event_source":   event_source,
                "error_code":     raw.get("errorCode"),
                "error_message":  raw.get("errorMessage"),
                "user_agent":     raw.get("userAgent"),
            },
        }

    except Exception as exc:
        logger.debug("Failed to normalize CloudTrail event: %s", exc)
        return None


def normalize_cloudtrail_batch(
    raw_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Normalize a list of raw CloudTrail events, dropping any that fail.

    Returns
    -------
    list[dict] — only successfully normalized events.
    """
    normalized = [normalize_cloudtrail_event(e) for e in raw_events]
    valid = [e for e in normalized if e is not None]
    skipped = len(raw_events) - len(valid)
    if skipped:
        logger.info("Skipped %d CloudTrail events during normalization.", skipped)
    return valid
