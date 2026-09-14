"""Two deployments, two databases: one for Singapore and one for Malaysia.

Nothing is shared between them, which is the point: a test that finds a Singapore row in the
Malaysian database has found a bug in the thing this story is about.

`sg` and `my` are sessions on each database. `deployment` is the Singapore backend as the app
sees it — the FastAPI app bound to that database and region, an HTTP client on it, and the
fixture code sender the tests read the code back from — so the HTTP tests and the service
tests run against the same tables.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.channels.api import Providers, create_app
from app.channels.whatsapp.provider import FixtureProvider
from app.clock import FrozenClock, SystemClock, set_clock
from app.db import Base, make_session_factory, take_keepers
from app.delivery.feed.compress import FixtureCompressor, FixtureSearcher
from app.drugs.fixture import FixtureRegistry
from app.identity.providers import LoggingCodeSender
from app.ingestion.extract import FixtureExtractor
from app.ingestion.objects import LocalObjectStore
from app.ingestion.transcribe import FixtureTranscriber
from app.keys import confirm  # noqa: F401
from app.reasoning.visits.summary import FixtureSummariser
from app.regions import Region
from app.settings import Settings

# Imported for the side effect of registering every table on the shared metadata.
from tests import support  # noqa: F401
from tests.paper import PAPER
from tests.voice_notes import VOICE

VISITS = Path(__file__).resolve().parent / "fixtures" / "visits"
"""The visit transcripts the fixture summariser knows (E05-05)."""
WHATSAPP_SECRET = "nura-test-webhook-secret"
"""The fixed secret the fixture provider signs with in the tests; nothing real."""
WHATSAPP_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "whatsapp"
FEED = Path(__file__).resolve().parent / "fixtures" / "feed"
"""Where the feed's fixture searcher and compressor answer from (E21)."""


async def _engine() -> AsyncEngine:
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
    return engine


async def _deployment() -> AsyncIterator[AsyncSession]:
    engine = await _engine()
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


@dataclass(frozen=True, slots=True)
class Deployment:
    """One backend, as a test reaches it: over HTTP, and underneath, on its own database."""

    region: Region
    client: AsyncClient
    sessions: async_sessionmaker[AsyncSession]
    sender: LoggingCodeSender
    objects: LocalObjectStore
    whatsapp: FixtureProvider


async def _serve(region: Region) -> AsyncIterator[Deployment]:
    engine = await _engine()
    sessions = make_session_factory(engine)
    sender = LoggingCodeSender(reveal=True)
    settings = Settings(
        region=region,
        database_url="sqlite+aiosqlite://",
        dev_code_sender=True,
        whatsapp_dev_secret=WHATSAPP_SECRET,
    )
    # The object store is a fresh directory per served deployment, one region under it,
    # gone at the end: what the local store does under backend/var/objects on a laptop.
    root = Path(tempfile.mkdtemp(prefix="nura-objects-"))
    objects = LocalObjectStore(root, region)
    whatsapp = FixtureProvider(secret=WHATSAPP_SECRET, fixtures=WHATSAPP_FIXTURES)
    providers = Providers(
        code_sender=sender,
        object_store=objects,
        extractor=FixtureExtractor(PAPER),
        summariser=FixtureSummariser(VISITS),
        transcriber=FixtureTranscriber(VOICE, region),
        searcher=FixtureSearcher(FEED),
        compressor=FixtureCompressor(FEED),
        drug_registry=FixtureRegistry.load(),
        whatsapp=whatsapp,
    )
    app = create_app(settings, sessions, providers)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://nura.test"
        ) as client:
            yield Deployment(
                region=region,
                client=client,
                sessions=sessions,
                sender=sender,
                objects=objects,
                whatsapp=whatsapp,
            )
    finally:
        shutil.rmtree(root, ignore_errors=True)
    await engine.dispose()


@pytest.fixture
async def deployment() -> AsyncIterator[Deployment]:
    """The Singapore backend, served."""
    async for served in _serve(Region.SG):
        yield served


@pytest.fixture
async def client(deployment: Deployment) -> AsyncClient:
    """An HTTP client on the Singapore backend."""
    return deployment.client
