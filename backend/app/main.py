"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.routes import actions, agent, audit, health, integrations, invoices
from app.core.config import get_settings
from app.db.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_db()
    yield


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

    # Allow only the configured frontend origin.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    for router in (health.router, integrations.router, invoices.router, agent.router, actions.router, audit.router):
        app.include_router(router, prefix="/api")
    return app


app = create_app()
