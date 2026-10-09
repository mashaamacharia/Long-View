from typing import Any

import httpx

from app.config import settings


class OllamaLLM:
    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": settings.ollama_model,
            "messages": messages,
            "stream": False,
            "options": {"num_ctx": 8192, "temperature": 0.2},
        }
        if tools:
            payload["tools"] = tools
        r = httpx.post(f"{settings.ollama_base_url}/api/chat", json=payload, timeout=600)
        r.raise_for_status()
        return r.json()["message"]
