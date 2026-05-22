from google import genai

from app.core.config import settings


class GeminiClientError(Exception):
    pass


def is_gemini_enabled() -> bool:
    return bool(settings.enable_gemini and settings.gemini_api_key)


def generate_gemini_text(prompt: str, model: str | None = None) -> str:
    if not is_gemini_enabled():
        raise GeminiClientError("Gemini is disabled or GEMINI_API_KEY is missing")

    try:
        client = genai.Client(api_key=settings.gemini_api_key)

        response = client.models.generate_content(
            model=model or settings.gemini_model,
            contents=prompt,
        )

        text = getattr(response, "text", None)

        if not text:
            raise GeminiClientError("Gemini returned empty response")

        return text.strip()

    except Exception as error:
        raise GeminiClientError(str(error)) from error
