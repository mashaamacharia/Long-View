"""Gemini through its OpenAI-compatible endpoint. Development and comparison only: the demo and
evals use the open-weights Ollama path. Request/response conversion is unit-tested with a mock
transport; it has not been exercised against the live API."""
from __future__ import annotations

import json
import time
from typing import Any

import httpx

from app.agent.llm.base import LLMError, LLMResponse, ToolCall
from app.config import settings


def to_openai_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for m in messages:
        if m["role"] == "assistant" and m.get("tool_calls"):
            out.append({"role": "assistant", "content": m.get("content") or None, "tool_calls": [
                {"id": c.get("id") or f"call_{i}", "type": "function",
                 "function": {"name": c["name"], "arguments": json.dumps(c["arguments"])}}
                for i, c in enumerate(m["tool_calls"])]})
        elif m["role"] == "tool":
            out.append({"role": "tool", "tool_call_id": m.get("tool_call_id", ""), "content": m["content"]})
        else:
            out.append({"role": m["role"], "content": m["content"]})
    return out


class GeminiLLM:
    provider = "gemini"

    def __init__(self, api_key: str | None = None, model: str | None = None,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.api_key = api_key or settings.gemini_api_key
        self.model = model or settings.gemini_model
        self.base_url = settings.gemini_base_url.rstrip("/")
        self._transport = transport

    async def chat(self, messages, tools=None, *, json_mode=False, max_tokens=None) -> LLMResponse:
        if not self.api_key:
            raise LLMError("GEMINI_API_KEY is not set")
        payload: dict[str, Any] = {"model": self.model, "messages": to_openai_messages(messages),
                                   "temperature": 0, "max_tokens": max_tokens or 700}
        if tools:
            payload["tools"] = tools
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=settings.llm_timeout_s, transport=self._transport) as c:
                r = await c.post(f"{self.base_url}/chat/completions", json=payload,
                                 headers={"Authorization": f"Bearer {self.api_key}"})
            r.raise_for_status()
            msg = r.json()["choices"][0]["message"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            raise LLMError(f"gemini request failed: {type(exc).__name__}: {exc}") from exc
        calls = []
        for i, c in enumerate(msg.get("tool_calls") or []):
            fn = c.get("function", {})
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except ValueError:
                args = {}
            calls.append(ToolCall(name=fn.get("name", ""), arguments=args if isinstance(args, dict) else {},
                                  id=c.get("id") or f"call_{i}"))
        return LLMResponse(content=msg.get("content") or "", tool_calls=calls, seconds=time.monotonic() - t0, model=self.model)
