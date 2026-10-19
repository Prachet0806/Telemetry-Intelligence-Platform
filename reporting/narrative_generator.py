# reporting/narrative_generator.py

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

DEFAULT_GENAI_NARRATIVE_MODEL = "gemini-3.8-flash"

try:
    from dotenv import load_dotenv

    load_dotenv(override=False)
except Exception:
    pass

GENAI_NARRATIVE_MODEL = (
    (os.getenv("GOOGLE_GENAI_MODEL") or "").strip()
    or DEFAULT_GENAI_NARRATIVE_MODEL
)


def _sanitize(value, limit: int = 2000) -> str:
    s = "" if value is None else str(value)
    s = "".join(ch for ch in s if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    return s[:limit]


def generate_decision_narrative(brief: dict) -> str:
    """
    Generate a consulting-grade executive narrative from the decision brief.

    If GOOGLE_API_KEY is set, delegates to Gemini to produce a polished
    one-paragraph narrative. Otherwise returns a deterministic fallback.

    Parameters
    ----------
    brief : dict
        Output of client_brief_builder.build_client_brief()

    Returns
    -------
    str — single coherent paragraph suitable for executive communication.
    """
    severity = _sanitize(brief.get("Severity", "Low"), 50)
    exposure = _sanitize(brief.get("Estimated Financial Exposure", "N/A"), 100)
    actions = brief.get("Recommended Actions", []) or []
    actions = [_sanitize(a, 500) for a in actions][:10]
    signals = brief.get("Signal Summary", {}) or {}

    # -----------------------------------------------------------------------
    # Deterministic fallback (always works, no API needed)
    # -----------------------------------------------------------------------
    action_text = "; ".join(actions[:3]) if actions else "no immediate action required"
    fallback = (
        f"Telemetry analysis has identified a {severity.upper()} operational risk posture "
        f"with an estimated financial exposure of {exposure}. "
        f"Detection signals include: anomaly rate of {signals.get('Anomaly Rate', 'N/A')}, "
        f"high-risk events at {signals.get('High-Risk Event %', 'N/A')}, "
        f"and a baseline flag rate of {signals.get('Baseline Flag Rate', 'N/A')}. "
        f"Recommended immediate actions: {action_text}."
    )

    api_key = (os.getenv("GOOGLE_API_KEY") or "").strip()
    if not api_key:
        return fallback

    # -----------------------------------------------------------------------
    # GenAI narrative (consulting-grade)
    # -----------------------------------------------------------------------
    try:
        from explainability.prompt_templates import DECISION_NARRATIVE_PROMPT
        from google import genai  # lazy import inside try so missing dep falls back
    except ImportError as exc:
        logger.warning("GenAI narrative unavailable (missing dependency): %s", exc)
        return fallback

    prompt = DECISION_NARRATIVE_PROMPT.format(
        severity=severity,
        exposure=exposure,
        anomaly_rate=signals.get("Anomaly Rate", "N/A"),
        high_risk_pct=signals.get("High-Risk Event %", "N/A"),
        baseline_rate=signals.get("Baseline Flag Rate", "N/A"),
        actions="\n".join(f"- {a}" for a in actions),
        confidence=brief.get("Confidence Level", "High"),
    )

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=GENAI_NARRATIVE_MODEL,
            contents=prompt,
        )
        return (getattr(response, "text", "") or "").strip() or fallback
    except Exception as exc:
        logger.warning("GenAI narrative failed (%s); using fallback.", type(exc).__name__)
        return fallback
