"""Shared pytest fixtures: every test gets its own temporary SQLite database."""

import asyncio
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.session import get_session, init_db
from app.main import app


@pytest.fixture(autouse=True)
def db_sessionmaker(tmp_path: Path) -> Iterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}", poolclass=NullPool)
    asyncio.run(init_db(engine))
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    yield sessionmaker
    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())
