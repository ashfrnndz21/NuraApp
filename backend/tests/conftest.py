"""Two deployments, two databases: one for Singapore and one for Malaysia.

Nothing is shared between them, which is the point: a test that finds a Singapore row in the
Malaysian database has found a bug in the thing this story is about.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from app.clock import FrozenClock, SystemClock, set_clock
from app.db import Base, make_session_factory, take_keepers
from app.keys import confirm  # noqa: F401

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
        try:
            yield session
        finally:
            # A test is its own channel: `pytest.raises` is its request boundary, and the
            # lines a channel would replay after the rollback are simply left standing, since
            # nothing rolled back. What is dropped here is only the replay; a test of the
            # boundary itself goes through `tests.support.refused_unit`.
            take_keepers(session)
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


FROZEN_AT = datetime(2026, 9, 3, 8, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def clock() -> Iterator[FrozenClock]:
    """The one clock, frozen: a test moves it, nothing else does, and no service takes a time.

    Every timestamp and every check against time in the app reads `app.clock`; a caller
    cannot pass a `now`. So a test that needs time to pass steps this.
    """
    frozen = FrozenClock(FROZEN_AT)
    set_clock(frozen)
    yield frozen
    set_clock(SystemClock())
