from app.agent.llm.base import LLM
from app.config import settings


def get_llm() -> LLM:
    if settings.llm_provider == "gemini":
        from app.agent.llm.gemini import GeminiLLM
        return GeminiLLM()
    from app.agent.llm.ollama import OllamaLLM
    return OllamaLLM()
