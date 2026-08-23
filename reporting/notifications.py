# reporting/notifications.py
"""
Severity-based alerting.

Posts a JSON payload to a configured webhook (Slack, MS Teams, PagerDuty, ...)
when the decision severity meets or exceeds `min_severity`. The webhook URL can
be set in config/alerts.yaml or overridden with the ALERT_WEBHOOK_URL env var.

Alerting is deliberately best-effort: failures are logged, never raised, so the
pipeline always completes.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import yaml

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[1]
_ALERTS_CONFIG_PATH = _ROOT / "config" / "alerts.yaml"

_ALERT_DEFAULTS = {
    "enabled": True,
    "min_severity": "High",
    "webhook_url": "",
    "retry_attempts": 3,
    "retry_backoff_seconds": 2,
    "payload_format": "slack",  # slack | teams | pagerduty | generic
}

_SEVERITY_RANK = {"Critical": 4, "High": 3, "Moderate": 2, "Low": 1}


def _load_alert_config() -> dict:
    cfg = dict(_ALERT_DEFAULTS)
    if _ALERTS_CONFIG_PATH.exists():
        with open(_ALERTS_CONFIG_PATH) as f:
            data = yaml.safe_load(f) or {}
        cfg.update(data.get("alerts", {}))

    # Env override ONLY when set AND non-empty (fix: empty string no longer disables YAML URL)
    env_url = os.getenv("ALERT_WEBHOOK_URL")
    if env_url:
        cfg["webhook_url"] = env_url
    return cfg


def should_alert(severity: str, cfg: dict | None = None) -> bool:
    """True if a severity meets/exceeds the configured alert threshold."""
    cfg = cfg or _load_alert_config()
    if not cfg.get("enabled", True):
        return False
    if not cfg.get("webhook_url"):
        return False
    min_severity = cfg.get("min_severity", "High")
    return _SEVERITY_RANK.get(severity, 0) >= _SEVERITY_RANK.get(min_severity, 3)


def _build_payload(brief: dict, fmt: str, cfg: dict | None = None) -> Dict[str, Any]:
    """Construct the webhook payload in the requested format."""
    severity = brief.get("Severity", "Low")
    exposure = brief.get("Estimated Financial Exposure", "N/A")
    summary = brief.get("Executive Summary", "")
    actions = brief.get("Recommended Actions", []) or []
    confidence = brief.get("Confidence Level", "N/A")
    signals = brief.get("Signal Summary", {})

    common = {
        "severity": severity,
        "estimated_financial_exposure": brief.get("Estimated Financial Exposure Raw", exposure),
        "summary": summary,
        "recommended_actions": actions,
        "confidence": confidence,
        "signals": signals,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    if fmt == "slack":
        return {
            "text": (
                f"[Decision Intelligence Alert] Severity: {severity}\n"
                f"Estimated Financial Exposure: {exposure}\n"
                f"Summary: {summary}\n"
                f"Recommended Actions: {'; '.join(actions)}"
            ),
            **common,
        }
    if fmt == "teams":
        # MS Teams expects a card structure
        return {
            "type": "message",
            "attachments": [{
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {"type": "TextBlock", "text": f"🚨 Decision Intelligence Alert — {severity}", "weight": "Bolder", "size": "Medium"},
                        {"type": "TextBlock", "text": f"**Exposure:** {exposure}", "wrap": True},
                        {"type": "TextBlock", "text": summary, "wrap": True},
                        {"type": "TextBlock", "text": f"**Actions:**\n" + "\n".join(f"• {a}" for a in actions), "wrap": True},
                        {"type": "TextBlock", "text": f"Confidence: {confidence}", "isSubtle": True},
                    ],
                },
            }],
        }
    if fmt == "pagerduty":
        # PagerDuty Events API v2 format
        pd_key = (cfg or {}).get("pagerduty_routing_key", "")
        return {
            "routing_key": pd_key,
            "event_action": "trigger",
            "payload": {
                "summary": f"Decision Intelligence: {severity} severity",
                "severity": severity.lower(),
                "source": "decision-intelligence-pipeline",
                "custom_details": common,
            },
        }
    # generic: just the structured JSON
    return common


def send_severity_alert(brief: dict, cfg: dict | None = None) -> bool:
    """
    Dispatch an alert for the given decision brief if the severity warrants it.

    Parameters
    ----------
    brief : decision intelligence brief
    cfg : optional config override (used in tests; otherwise loads from YAML)

    Returns True if an alert was dispatched, False otherwise.
    """
    cfg = cfg or _load_alert_config()
    severity = brief.get("Severity", "Low")

    if not should_alert(severity, cfg):
        return False

    url = cfg["webhook_url"]
    payload = _build_payload(brief, cfg.get("payload_format", "slack"), cfg)

    attempts = int(cfg.get("retry_attempts", 3))
    backoff = float(cfg.get("retry_backoff_seconds", 2))

    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                status = response.status
            logger.info(
                "[ALERT] Severity %s alert dispatched to webhook (HTTP %d, attempt %d/%d).",
                severity, status, attempt, attempts,
            )
            return True
        except Exception as exc:
            logger.warning(
                "[ALERT] Attempt %d/%d failed for %s alert: %s (%s).",
                attempt, attempts, severity, type(exc).__name__, exc,
            )
            if attempt < attempts:
                time.sleep(backoff * attempt)  # linear backoff
            continue

    logger.error(
        "[ALERT] All %d attempts failed for %s alert to %s.",
        attempts, severity, url,
    )
    return False