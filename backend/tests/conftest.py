"""Two deployments, two databases: one for Singapore and one for Malaysia.

Nothing is shared between them, which is the point: a test that finds a Singapore row in the
Malaysian database has found a bug in the thing this story is about.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db import Base, make_session_factory

# Imported for the side effect of registering every table on the shared metadata.
from tests import support  # noqa: F401


async def _deployment() -> AsyncIterator[AsyncSession]:
    """One region's database: one connection, held open for the length of one test."""
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)

    # SQLite ignores foreign keys unless told otherwise. Postgres does not, and the ties
    # between the memory tables are part of what the tests check, so turn them on.
    @event.listens_for(engine.sync_engine, "connect")
    def _enforce_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with make_session_factory(engine)() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def sg() -> AsyncIterator[AsyncSession]:
    """A session on the Singapore deployment."""
    async for session in _deployment():
        yield session


@pytest.fixture
async def my() -> AsyncIterator[AsyncSession]:
    """A session on the Malaysian deployment."""
    async for session in _deployment():
        yield session
