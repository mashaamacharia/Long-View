from typing import Any, Protocol


class LLM(Protocol):
    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        ...
