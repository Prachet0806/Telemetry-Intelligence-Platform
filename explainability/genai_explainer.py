# explainability/genai_explainer.py

import os
from dotenv import load_dotenv
from google import genai

from explainability.prompt_templates import EXPLANATION_PROMPT

load_dotenv()
def generate_explanation(summary: dict) -> str:
    """
    Generate a human-readable explanation strictly from provided facts.
    The model is not allowed to infer or compute metrics.
    """

    total = summary["total_events"]
    high_risk = summary["high_risk_count"]
    pct = summary["high_risk_percentage"]

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

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return (
            "Telemetry analysis completed.\n\n"
            + factual_block
            + "\nGenAI explanation is unavailable because GOOGLE_API_KEY is not set."
        )

    prompt = EXPLANATION_PROMPT.format(factual_block=factual_block)

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=prompt,
    )

    return response.text or ""
