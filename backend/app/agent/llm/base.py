from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class LLMError(Exception):
    """The model could not be reached or returned something unusable."""


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    id: str = ""


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    seconds: float = 0.0
    model: str = ""


class LLM(Protocol):
    """Messages use one internal shape (OpenAI-like), converted per provider:
      {"role": "system"|"user", "content": str}
      {"role": "assistant", "content": str, "tool_calls": [{"id", "name", "arguments": dict}]}
      {"role": "tool", "tool_call_id": str, "name": str, "content": str}
    """

    provider: str
    model: str

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, *,
                   json_mode: bool = False, max_tokens: int | None = None) -> LLMResponse: ...
