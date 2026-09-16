"""Two deployments, two databases: one for Singapore and one for Malaysia.

Nothing is shared between them, which is the point: a test that finds a Singapore row in the
Malaysian database has found a bug in the thing this story is about.

`sg` and `my` are sessions on each database. `deployment` is the Singapore backend as the app
sees it — the FastAPI app bound to that database and region, an HTTP client on it, and the
fixture code sender the tests read the code back from — so the HTTP tests and the service
tests run against the same tables.

Which database engine: SQLite in memory by default (`make test`, the laptop and the `backend`
CI job). With NURA_TEST_DATABASE_URL set to a Postgres URL (`postgresql+asyncpg://…`, what the
`backend-postgres` CI job sets) every database a test asks for is instead its own schema on
that Postgres, created for the test and dropped after it, so the whole suite runs on the
database a deployment runs on. Postgres is exercised in CI only; nothing here needs one on a
laptop.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Connection, event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool, StaticPool

from app.channels.api import Providers, create_app
from app.channels.whatsapp.provider import FixtureProvider
from app.clock import FrozenClock, SystemClock, set_clock
from app.db import Base, make_session_factory, take_keepers
from app.delivery.feed.clips import FixtureClipRenderer
from app.delivery.feed.compress import FixtureCompressor, FixtureSearcher
from app.drugs.fixture import FixtureRegistry
from app.identity.providers import LoggingCodeSender
from app.ingestion.extract import FixtureExtractor
from app.ingestion.objects import LocalObjectStore
from app.ingestion.speakers import FixtureSeparator
from app.ingestion.transcribe import FixtureTranscriber
from app.keys import confirm  # noqa: F401
from app.reasoning.ranges import FixtureRanges
from app.reasoning.visits.summary import FixtureSummariser
from app.regions import Region
from app.settings import Settings, database_url_for

# Imported for the side effect of registering every table on the shared metadata.
from tests import support  # noqa: F401
from tests.paper import PAPER
from tests.voice_notes import VOICE

VISITS = Path(__file__).resolve().parent / "fixtures" / "visits"
"""The visit transcripts the fixture summariser knows (E05-05)."""
WHATSAPP_SECRET = "nura-test-webhook-secret"
"""The fixed secret the fixture provider signs with in the tests; nothing real."""
WHATSAPP_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "whatsapp"
SPEAKERS = Path(__file__).resolve().parent / "fixtures" / "speakers"
"""Who spoke when in a consult recording, by the digest of the audio (E02-05)."""
FEED = Path(__file__).resolve().parent / "fixtures" / "feed"
"""Where the feed's fixture searcher and compressor answer from (E21)."""
STAFF_TOKEN = "nura-test-pharmacist-token-0001"
"""The one staff token the served test deployment knows (`/review/*`, E22-04); nothing real."""


TEST_DATABASE_URL: str | None = (
    database_url_for(os.environ["NURA_TEST_DATABASE_URL"])
    if os.environ.get("NURA_TEST_DATABASE_URL")
    else None
)
"""A Postgres to run every test's database on, or None for SQLite in memory (the default)."""
ON_POSTGRES = TEST_DATABASE_URL is not None

POSTGRES_TEST_SETTINGS = {"lock_timeout": "10s", "statement_timeout": "60s"}
"""A test that waits on a lock another of its own sessions holds fails in seconds, with the
statement in the message, instead of hanging the CI job."""

LEFT_OPEN = (
    "SELECT pid, state || ': ' || left(query, 200) FROM pg_stat_activity "
    "WHERE backend_type = 'client backend' AND application_name = :schema "
    "AND state IN ('active', 'idle in transaction', 'idle in transaction (aborted)')"
)
"""A connection of this test's own engine — it names itself after the schema — still
mid-transaction or mid-statement. Postgres's own workers (autovacuum) and a second database
the same test holds (`sg` and `my` are two schemas on one server) are not this engine's."""


def _enforce_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
    # SQLite ignores foreign keys unless told otherwise. Postgres does not, and the ties
    # between the memory tables are part of what the tests check, so turn them on.
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@asynccontextmanager
async def empty_database(*, sqlite_foreign_keys: bool = True) -> AsyncIterator[AsyncEngine]:
    """A database with no tables in it, for the length of one test, and gone after it.

    SQLite: one in-memory database on one connection held open for the test. Postgres
    (`NURA_TEST_DATABASE_URL`): a schema of its own on the test server, the engine's search
    path pinned to it, dropped with everything in it at the end. Migration tests turn SQLite's
    foreign keys off, as alembic's batch rewrite needs; Postgres keeps them, always.
    """
    if TEST_DATABASE_URL is None:
        engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
        if sqlite_foreign_keys:
            event.listen(engine.sync_engine, "connect", _enforce_foreign_keys)
        try:
            yield engine
        finally:
            await engine.dispose()
        return
    schema = f"test_{uuid.uuid4().hex}"
    admin = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={
            "server_settings": {
                "search_path": schema,
                "application_name": schema,
                **POSTGRES_TEST_SETTINGS,
            }
        },
    )
    try:
        yield engine
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            # Tests run one at a time, so any other connection still inside a transaction or
            # a statement here is one this test left open. It would hold the locks the drop
            # needs: end it, drop the schema, and name what it last ran.
            left_open = (await connection.execute(text(LEFT_OPEN), {"schema": schema})).all()
            for pid, _query in left_open:
                await connection.execute(text("SELECT pg_terminate_backend(:pid)"), {"pid": pid})
            await connection.execute(text("SET LOCAL lock_timeout = '10s'"))
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()
        if left_open:
            raise AssertionError(
                "the test left a connection open: " + "; ".join(q for _, q in left_open)
            )


@asynccontextmanager
async def regional_database() -> AsyncIterator[AsyncEngine]:
    """One region's database with every table the models declare, for one test."""
    async with empty_database() as engine:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        yield engine


async def on_an_empty_database(body: Callable[[Connection], None]) -> None:
    """Run `body` on a connection to an empty database, in one transaction. For the migration
    tests, which drive alembic's operations directly and so need a synchronous connection:
    on Postgres that is asyncpg's, lent through `run_sync`, so no second driver is needed."""
    async with (
        empty_database(sqlite_foreign_keys=False) as engine,
        engine.begin() as connection,
    ):
        await connection.run_sync(body)


async def _deployment() -> AsyncIterator[AsyncSession]:
    async with regional_database() as engine, make_session_factory(engine)() as session:
        try:
            yield session
        finally:
            # A test is its own channel: `pytest.raises` is its request boundary, and the
            # lines a channel would replay after the rollback are simply left standing,
            # since nothing rolled back. What is dropped here is only the replay; a test
            # of the boundary itself goes through `tests.support.refused_unit`.
            take_keepers(session)


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
    async with regional_database() as engine:
        async for served in _serve_on(engine, region):
            yield served


async def _serve_on(engine: AsyncEngine, region: Region) -> AsyncIterator[Deployment]:
    sessions = make_session_factory(engine)
    sender = LoggingCodeSender(reveal=True)
    settings = Settings(
        region=region,
        database_url="sqlite+aiosqlite://",
        dev_code_sender=True,
        red_flag_tiers=True,
        whatsapp_dev_secret=WHATSAPP_SECRET,
        review_staff=(("pharmacist", STAFF_TOKEN),),
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
        reference_ranges=FixtureRanges.load(),
        speaker_separator=FixtureSeparator(SPEAKERS, region),
        clips=FixtureClipRenderer(FEED),
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


@pytest.fixture
async def deployment() -> AsyncIterator[Deployment]:
    """The Singapore backend, served."""
    async for served in _serve(Region.SG):
        yield served


@pytest.fixture
async def client(deployment: Deployment) -> AsyncClient:
    """An HTTP client on the Singapore backend."""
    return deployment.client
