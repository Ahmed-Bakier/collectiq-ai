"""Per-visitor limit on AI requests, protecting the AI provider quota on a public demo.

In-memory sliding window per client IP (single instance). Disabled when
AI_RATE_LIMIT_PER_HOUR is 0. Only endpoints that call the LLM are counted.
"""

import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from app.core.config import get_settings

WINDOW_SECONDS = 3600.0
_hits: dict[str, deque[float]] = defaultdict(deque)


def is_ai_request(request: Request) -> bool:
    path = request.url.path
    return request.method == "POST" and (
        path in ("/api/agent/runs", "/api/autopilot/run") or (path.startswith("/api/actions/") and path.endswith("/redraft"))
    )


def client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def allow(key: str, limit: int, now: float | None = None) -> bool:
    current = time.monotonic() if now is None else now
    hits = _hits[key]
    while hits and current - hits[0] >= WINDOW_SECONDS:
        hits.popleft()
    if len(hits) >= limit:
        return False
    hits.append(current)
    return True


def reset() -> None:
    _hits.clear()


async def ai_rate_limit_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    limit = get_settings().ai_rate_limit_per_hour
    if limit > 0 and is_ai_request(request) and not allow(client_key(request), limit):
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": "rate_limited",
                    "message": f"Demo limit reached: {limit} AI requests per hour. Please try again later.",
                    "paypal_debug_id": None,
                }
            },
        )
    return await call_next(request)
