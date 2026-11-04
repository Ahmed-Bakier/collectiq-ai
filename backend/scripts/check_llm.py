"""Diagnose the LLM provider configuration. Never prints the API key.

Usage (from backend/): python scripts/check_llm.py
"""

import asyncio
import sys
from pathlib import Path

import openai
from openai import AsyncOpenAI

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402

TEST_MESSAGES = [{"role": "user", "content": "Reply with the single word: ok"}]


async def try_request(client: AsyncOpenAI, model: str, label: str, **extra: str) -> None:
    try:
        response = await client.chat.completions.create(model=model, messages=TEST_MESSAGES, **extra)
        text = (response.choices[0].message.content or "").strip()[:50]
        print(f"[{label}] OK -> {text}")
    except openai.APIStatusError as exc:
        print(f"[{label}] HTTP {exc.status_code}: {str(exc)[:400]}")
    except openai.APIError as exc:
        print(f"[{label}] {type(exc).__name__}: {str(exc)[:400]}")


async def main() -> None:
    settings = get_settings()
    print("Base URL:        ", settings.llm_base_url)
    print("Model:           ", settings.llm_model)
    print("Reasoning effort:", settings.llm_reasoning_effort)
    print("API key set:     ", settings.llm_configured)
    if not settings.llm_configured:
        return

    client = AsyncOpenAI(
        api_key=settings.llm_api_key.get_secret_value(),
        base_url=settings.llm_base_url,
        max_retries=0,
        timeout=60,
    )

    await try_request(client, settings.llm_model, "plain request")
    if settings.llm_reasoning_effort:
        await try_request(
            client,
            settings.llm_model,
            "with reasoning_effort",
            reasoning_effort=settings.llm_reasoning_effort,
        )

    try:
        models = [model.id async for model in client.models.list()]
        flash = sorted(model_id for model_id in models if "flash" in model_id)
        print("Available flash models:", ", ".join(flash) or "none")
    except openai.APIError as exc:
        print("Could not list models:", type(exc).__name__)


if __name__ == "__main__":
    asyncio.run(main())
