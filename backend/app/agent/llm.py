"""Provider-agnostic LLM client using the OpenAI-compatible Chat Completions API.

Works with Google Gemini (default), Groq, OpenAI and other compatible providers
by changing LLM_BASE_URL / LLM_MODEL / LLM_API_KEY only.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx
import openai
from openai import AsyncOpenAI

from app.core.config import Settings

logger = logging.getLogger(__name__)

LLM_TIMEOUT_SECONDS = 60.0


class LLMError(Exception):
    """Base error for AI provider failures."""


class LLMNotConfiguredError(LLMError):
    """Raised when no LLM API key is configured."""


class LLMRateLimitError(LLMError):
    """Raised when the AI provider rate limit or quota is reached."""


@dataclass(frozen=True)
class LLMToolCall:
    id: str
    name: str
    arguments: str  # Raw JSON produced by the model. Untrusted until validated.


@dataclass(frozen=True)
class LLMResponse:
    content: str | None
    tool_calls: list[LLMToolCall] = field(default_factory=list)
    # The provider's assistant message, appended to the conversation unchanged.
    # This preserves provider-specific fields such as Gemini thought signatures.
    raw_message: dict[str, Any] = field(default_factory=dict)


class LLM(Protocol):
    @property
    def model(self) -> str: ...

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse: ...


class OpenAICompatibleLLM:
    """LLM client for any OpenAI-compatible provider."""

    def __init__(
        self,
        settings: Settings,
        http_client: httpx.AsyncClient | None = None,
        max_retries: int = 2,
    ) -> None:
        if not settings.llm_configured:
            raise LLMNotConfiguredError("LLM API key is not configured.")
        self._settings = settings
        self._client = AsyncOpenAI(
            api_key=settings.llm_api_key.get_secret_value(),
            base_url=settings.llm_base_url,
            timeout=LLM_TIMEOUT_SECONDS,
            max_retries=max_retries,
            http_client=http_client,
        )

    @property
    def model(self) -> str:
        return self._settings.llm_model

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:
            # Plain completions (e.g. message drafting) are sent without tools.
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if self._settings.llm_reasoning_effort:
            kwargs["reasoning_effort"] = self._settings.llm_reasoning_effort

        try:
            response = await self._client.chat.completions.create(**kwargs)
        except openai.RateLimitError as exc:
            raise LLMRateLimitError("The AI provider rate limit was reached.") from exc
        except openai.APIError as exc:
            logger.warning(
                "LLM provider error: type=%s status=%s message=%s",
                type(exc).__name__,
                getattr(exc, "status_code", None),
                str(exc)[:300],
            )
            raise LLMError("The AI provider returned an error.") from exc

        if not response.choices:
            raise LLMError("The AI provider returned no choices.")

        message = response.choices[0].message
        tool_calls: list[LLMToolCall] = []
        for call in message.tool_calls or []:
            function = getattr(call, "function", None)
            if function is None:
                continue  # Only function tools are supported.
            tool_calls.append(
                LLMToolCall(id=call.id, name=function.name, arguments=function.arguments or "{}")
            )

        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            raw_message=message.model_dump(exclude_none=True),
        )
