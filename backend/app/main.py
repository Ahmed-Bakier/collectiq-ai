"""FastAPI application entry point."""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.frontend import mount_frontend
from app.api.rate_limit import ai_rate_limit_middleware
from app.api.routes import (
    actions,
    agent,
    audit,
    autopilot,
    health,
    insights,
    integrations,
    invoices,
    payment_links,
    safety,
    webhooks,
)
from app.core.config import get_settings
from app.db.session import init_db
from app.mcp_server import BearerTokenAuth, build_mcp_server
from app.services.autopilot import autopilot_scheduler


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()
    mcp = build_mcp_server()
    mcp_app = mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await init_db()
        interval = get_settings().autopilot_interval_minutes
        scheduler: asyncio.Task[None] | None = None
        if interval > 0:
            scheduler = asyncio.create_task(autopilot_scheduler(interval))
        async with mcp.session_manager.run():
            yield
        if scheduler is not None:
            scheduler.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await scheduler

    app = FastAPI(title=settings.app_name, version="1.1.0", lifespan=lifespan)

    # Allow only the configured frontend origin (same origin in production).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.middleware("http")(ai_rate_limit_middleware)

    register_exception_handlers(app)

    for router in (
        health.router,
        integrations.router,
        invoices.router,
        payment_links.router,
        agent.router,
        actions.router,
        audit.router,
        autopilot.router,
        insights.router,
        safety.router,
        webhooks.router,
    ):
        app.include_router(router, prefix="/api")

    # MCP server for other AI agents (read + propose only), behind a bearer token.
    app.mount("/mcp", BearerTokenAuth(mcp_app))

    # Production: serve the built frontend from the same origin (after all API routes).
    if settings.frontend_dist_dir:
        dist = Path(settings.frontend_dist_dir)
        if (dist / "index.html").is_file():
            mount_frontend(app, dist)
    return app


app = create_app()
