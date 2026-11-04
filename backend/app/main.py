"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.routes import agent, health, integrations, invoices
from app.core.config import get_settings


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(title=settings.app_name, version="0.1.0")

    # Allow only the configured frontend origin.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    app.include_router(health.router, prefix="/api")
    app.include_router(integrations.router, prefix="/api")
    app.include_router(invoices.router, prefix="/api")
    app.include_router(agent.router, prefix="/api")
    return app


app = create_app()
