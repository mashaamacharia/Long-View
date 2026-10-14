"""Ollama native /api/chat (the path verified by scripts/check_tool_calling.py)."""
from __future__ import annotations

import json
import time
from typing import Any

import httpx

from app.agent.llm.base import LLMError, LLMResponse, ToolCall
from app.config import settings


def to_ollama_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for m in messages:
        if m["role"] == "assistant" and m.get("tool_calls"):
            out.append({"role": "assistant", "content": m.get("content", ""),
                        "tool_calls": [{"function": {"name": c["name"], "arguments": c["arguments"]}} for c in m["tool_calls"]]})
        elif m["role"] == "tool":
            out.append({"role": "tool", "tool_name": m.get("name", ""), "content": m["content"]})
        else:
            out.append({"role": m["role"], "content": m["content"]})
    return out


class OllamaLLM:
    provider = "ollama"

    def __init__(self, base_url: str | None = None, model: str | None = None,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.ollama_model
        self._transport = transport

    async def chat(self, messages, tools=None, *, json_mode=False, max_tokens=None) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model, "messages": to_ollama_messages(messages), "stream": False,
            "keep_alive": settings.ollama_keep_alive,
            "options": {"temperature": 0, "seed": 42, "num_ctx": settings.llm_num_ctx, "num_predict": max_tokens or 700},
        }
        if tools:
            payload["tools"] = tools
        if json_mode:
            payload["format"] = "json"
        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=settings.llm_timeout_s, transport=self._transport) as c:
                r = await c.post(f"{self.base_url}/api/chat", json=payload)
            r.raise_for_status()
            msg = r.json()["message"]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise LLMError(f"ollama request failed: {type(exc).__name__}: {exc}") from exc
        calls = []
        for i, c in enumerate(msg.get("tool_calls") or []):
            fn = c.get("function", {})
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except ValueError:
                    args = {}
            calls.append(ToolCall(name=fn.get("name", ""), arguments=args if isinstance(args, dict) else {}, id=f"call_{i}"))
        return LLMResponse(content=msg.get("content") or "", tool_calls=calls, seconds=time.monotonic() - t0, model=self.model)
