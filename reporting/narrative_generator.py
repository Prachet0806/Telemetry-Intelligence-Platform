# reporting/narrative_generator.py

from __future__ import annotations
import os

from dotenv import load_dotenv

load_dotenv()


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
    severity = brief["Severity"]
    exposure = brief["Estimated Financial Exposure"]
    actions = brief["Recommended Actions"]
    signals = brief.get("Signal Summary", {})

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

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return fallback

    # -----------------------------------------------------------------------
    # GenAI narrative (consulting-grade)
    # -----------------------------------------------------------------------
    from explainability.prompt_templates import DECISION_NARRATIVE_PROMPT
    from google import genai

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
            model="gemini-2.0-flash",
            contents=prompt,
        )
        return response.text or fallback
    except Exception:
        return fallback
