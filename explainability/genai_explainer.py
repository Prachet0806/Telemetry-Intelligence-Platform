# explainability/genai_explainer.py

import logging
import os

from explainability.prompt_templates import EXPLANATION_PROMPT

logger = logging.getLogger(__name__)

DEFAULT_GENAI_MODEL = "gemini-3.8-flash"


def _load_dotenv_safe() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(override=False)
    except Exception:
        pass


_load_dotenv_safe()
GENAI_MODEL = (os.getenv("GOOGLE_GENAI_MODEL") or "").strip() or DEFAULT_GENAI_MODEL


def generate_explanation(summary: dict) -> str:
    """
    Generate a human-readable explanation strictly from provided facts.
    The model is not allowed to infer or compute metrics.
    """
    try:
        total = summary["total_events"]
        high_risk = summary["high_risk_count"]
        pct = summary["high_risk_percentage"]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"summary missing required keys: {exc}") from exc

    if high_risk == 0:
        factual_block = (
            f"- Total events analyzed: {total}\n"
            f"- High-risk events: 0\n"
        )
    else:
        factual_block = (
            f"- Total events analyzed: {total}\n"
            f"- High-risk events: {high_risk} ({pct}%)\n"
        )

    api_key = (os.getenv("GOOGLE_API_KEY") or "").strip()
    if not api_key:
        return (
            "Telemetry analysis completed.\n\n"
            + factual_block
            + "\nGenAI explanation is unavailable because GOOGLE_API_KEY is not set."
        )

    prompt = EXPLANATION_PROMPT.format(factual_block=factual_block)

    try:
        from google import genai  # lazy so missing dep never breaks imports

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=GENAI_MODEL,
            contents=prompt,
        )
        text = (getattr(response, "text", "") or "").strip()
        return text if text else (
            "Telemetry analysis completed.\n\n" + factual_block
        )
    except Exception as exc:
        logger.warning("GenAI explanation failed (%s); using factual fallback.", type(exc).__name__)
        return "Telemetry analysis completed.\n\n" + factual_block
