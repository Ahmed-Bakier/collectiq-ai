"""FastAPI dependencies for the AI agent."""

from functools import lru_cache

from app.agent.llm import LLM, FallbackLLM, LLMNotConfiguredError, OpenAICompatibleLLM
from app.core.config import get_settings


@lru_cache
def get_llm() -> LLM:
    """Return a shared LLM client. Raises LLMNotConfiguredError without an API key."""
    settings = get_settings()
    fallback_model = (settings.llm_fallback_model or "").strip()
    if not fallback_model or fallback_model == settings.llm_model:
        return OpenAICompatibleLLM(settings)
    # Fail over quickly: one SDK retry on the primary, then the fallback model.
    primary = OpenAICompatibleLLM(settings, max_retries=1)
    return FallbackLLM(primary, OpenAICompatibleLLM(settings, model=fallback_model))


def get_optional_llm() -> LLM | None:
    """The LLM if configured; None lets the autopilot fall back to message templates."""
    try:
        return get_llm()
    except LLMNotConfiguredError:
        return None
