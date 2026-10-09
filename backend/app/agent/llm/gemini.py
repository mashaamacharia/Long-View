"""Gemini: development/comparison only. The demo and evals use the open-weights Ollama path."""
from typing import Any

from app.config import settings


class GeminiLLM:
    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        # TODO: implement with google-genai (client = genai.Client(api_key=settings.gemini_api_key))
        raise NotImplementedError("Gemini provider not implemented yet")
