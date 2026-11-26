"""Deployment readiness: LLM fallback, AI rate limit, single-origin frontend serving."""

import asyncio
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.agent.llm import FallbackLLM, LLMNotConfiguredError, LLMRateLimitError, LLMResponse
from app.api import rate_limit
from app.core.config import get_settings
from app.main import create_app
from tests.test_autopilot import drafting_llm, make_book, setup


class FakeModel:
    def __init__(self, name: str, error: Exception | None = None) -> None:
        self.name = name
        self.error = error
        self.calls = 0

    @property
    def model(self) -> str:
        return self.name

    async def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMResponse:
        self.calls += 1
        if self.error:
            raise self.error
        return LLMResponse(content=f"answer from {self.name}")


def test_fallback_model_is_used_after_a_rate_limit() -> None:
    primary = FakeModel("primary", LLMRateLimitError("quota"))
    fallback = FakeModel("fallback")

    response = asyncio.run(FallbackLLM(primary, fallback).complete([], []))

    assert response.content == "answer from fallback"
    assert (primary.calls, fallback.calls) == (1, 1)


def test_missing_configuration_is_not_hidden_by_the_fallback() -> None:
    fallback = FakeModel("fallback")
    with pytest.raises(LLMNotConfiguredError):
        asyncio.run(FallbackLLM(FakeModel("primary", LLMNotConfiguredError("no key")), fallback).complete([], []))
    assert fallback.calls == 0


def test_ai_requests_are_rate_limited_per_visitor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ai_rate_limit_per_hour", 1)
    rate_limit.reset()
    client = setup(make_book(), drafting_llm(6))

    assert client.post("/api/autopilot/run").status_code == 200
    blocked = client.post("/api/autopilot/run")
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"
    assert client.get("/api/autopilot/settings").status_code == 200  # Reads are never limited.
    rate_limit.reset()


def test_backend_serves_the_built_frontend(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>CollectIQ</html>")
    (tmp_path / "assets" / "app.js").write_text("console.log('ok')")
    monkeypatch.setattr(get_settings(), "frontend_dist_dir", str(tmp_path))
    client = TestClient(create_app())

    assert "CollectIQ" in client.get("/clients").text  # Client-side route -> index.html
    assert "console.log" in client.get("/assets/app.js").text
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/does-not-exist").status_code == 404
