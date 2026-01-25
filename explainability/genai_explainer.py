import os

from dotenv import load_dotenv
from google import genai

from explainability.prompt_templates import EXPLANATION_PROMPT

load_dotenv()

def generate_explanation(summary: str) -> str:
    prompt = EXPLANATION_PROMPT.format(summary=summary)

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return (
            "GenAI explanation is unavailable because GOOGLE_API_KEY is not set. "
            "Set it in a .env file to enable Gemini summaries."
        )

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=prompt,
    )
    return response.text or ""
