from app.agent.llm.base import LLM, LLMError, LLMResponse, ToolCall
from app.config import settings

__all__ = ["LLM", "LLMError", "LLMResponse", "ToolCall", "get_llm"]


def get_llm() -> LLM:
    if settings.llm_provider == "gemini":
        from app.agent.llm.gemini import GeminiLLM
        return GeminiLLM()
    from app.agent.llm.ollama import OllamaLLM
    return OllamaLLM()
