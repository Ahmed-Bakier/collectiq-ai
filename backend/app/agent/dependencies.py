"""FastAPI dependencies for the AI agent."""

from functools import lru_cache

from app.agent.llm import LLM, OpenAICompatibleLLM
from app.core.config import get_settings


@lru_cache
def get_llm() -> LLM:
    """Return a shared LLM client. Raises LLMNotConfiguredError without an API key."""
    return OpenAICompatibleLLM(get_settings())
