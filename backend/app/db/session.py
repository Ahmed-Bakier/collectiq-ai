"""Async database engine and session management."""

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.base import Base


def normalize_database_url(url: str) -> str:
    """Map plain URLs to async drivers (sqlite -> aiosqlite, postgres -> asyncpg)."""
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


@lru_cache
def get_engine() -> AsyncEngine:
    return create_async_engine(normalize_database_url(get_settings().database_url))


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request."""
    async with get_sessionmaker()() as session:
        yield session


async def init_db(engine: AsyncEngine | None = None) -> None:
    """Create tables if they do not exist (MVP; migrations are deferred)."""
    from app.db import models  # noqa: F401  Register models on Base.metadata.

    target = engine or get_engine()
    async with target.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
