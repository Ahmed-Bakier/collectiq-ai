"""Scripted fake LLMs for agent tests. They never call a real AI provider."""

import json
from typing import Any

from app.agent.llm import LLMResponse, LLMToolCall


def tool_call(name: str, arguments: dict[str, Any] | str, call_id: str = "call_1") -> LLMResponse:
    raw_args = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return LLMResponse(
        content=None,
        tool_calls=[LLMToolCall(id=call_id, name=name, arguments=raw_args)],
        raw_message={
            "role": "assistant",
            "tool_calls": [
                {"id": call_id, "type": "function", "function": {"name": name, "arguments": raw_args}}
            ],
        },
    )


def final_answer(text: str) -> LLMResponse:
    return LLMResponse(content=text, raw_message={"role": "assistant", "content": text})


class ScriptedLLM:
    """Returns pre-defined responses in order and records what it received."""

    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = list(responses)
        self.received: list[list[dict[str, Any]]] = []

    @property
    def model(self) -> str:
        return "scripted-test-model"

    async def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMResponse:
        self.received.append(list(messages))
        if not self._responses:
            raise AssertionError("ScriptedLLM ran out of responses")
        return self._responses.pop(0)


class LoopingLLM:
    """Always asks for another tool call, to test the step limit."""

    def __init__(self) -> None:
        self._count = 0

    @property
    def model(self) -> str:
        return "looping-test-model"

    async def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMResponse:
        self._count += 1
        return tool_call("get_invoice_analysis", {}, call_id=f"call_{self._count}")
