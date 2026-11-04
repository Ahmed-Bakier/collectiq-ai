"""Tests for the OpenAI-compatible LLM client (mocked HTTP, no real AI calls)."""

import asyncio
import json

import httpx
import pytest

from app.agent.llm import LLMNotConfiguredError, LLMRateLimitError, OpenAICompatibleLLM
from app.agent.tools import TOOL_DEFINITIONS
from tests.fakes import make_settings

COMPLETION_WITH_TOOL_CALL = {
    "id": "chatcmpl-test",
    "object": "chat.completion",
    "created": 0,
    "model": "gemini-3.6-flash",
    "choices": [
        {
            "index": 0,
            "finish_reason": "tool_calls",
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "get_invoice_analysis", "arguments": "{}"},
                        "extra_content": {"google": {"thought_signature": "sig-123"}},
                    }
                ],
            },
        }
    ],
}


def make_llm(handler: httpx.MockTransport) -> OpenAICompatibleLLM:
    return OpenAICompatibleLLM(
        make_settings(llm_api_key="test-llm-key"),
        http_client=httpx.AsyncClient(transport=handler),
        max_retries=0,
    )


def test_parses_tool_calls_and_preserves_provider_fields() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=COMPLETION_WITH_TOOL_CALL)

    llm = make_llm(httpx.MockTransport(handler))
    response = asyncio.run(llm.complete([{"role": "user", "content": "hi"}], TOOL_DEFINITIONS))

    assert response.tool_calls[0].name == "get_invoice_analysis"
    # Gemini thought signatures must be sent back unchanged in the next request.
    assert response.raw_message["tool_calls"][0]["extra_content"] == {"google": {"thought_signature": "sig-123"}}

    body = json.loads(requests[0].content)
    assert body["model"] == "gemini-3.6-flash"
    assert requests[0].url.path.endswith("/chat/completions")
    assert requests[0].headers["Authorization"] == "Bearer test-llm-key"


def test_rate_limit_maps_to_typed_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "quota exceeded", "code": 429}})

    llm = make_llm(httpx.MockTransport(handler))
    with pytest.raises(LLMRateLimitError):
        asyncio.run(llm.complete([{"role": "user", "content": "hi"}], TOOL_DEFINITIONS))


def test_missing_api_key_raises_not_configured() -> None:
    with pytest.raises(LLMNotConfiguredError):
        OpenAICompatibleLLM(make_settings())
