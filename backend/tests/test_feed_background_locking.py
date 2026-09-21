"""#297 defect 1: a background learning job must never hold SQLite's write lock while it
waits on the network.

`tests/conftest.py`'s `deployment` fixture serves every test on one StaticPool *in-memory*
SQLite connection, wrapped in `_serialized` so the background run's genuinely concurrent
sessions never corrupt each other's savepoint stack — which also, as a side effect, hides
this exact bug: every session there waits its turn anyway, so nothing ever meets the lock.
This module serves its own deployment instead, on a real *file-backed* SQLite database with
a real (unserialized) connection pool — `make dev`'s and the owner's test copy's own setup —
where `app.db.make_engine`'s BEGIN IMMEDIATE transactions really do take the single write
lock for as long as a session is open, the way the live incident on 2026-09-18 did.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
import threading
import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.channels.api import Providers, create_app
from app.channels.whatsapp.provider import FixtureProvider
from app.db import Base, make_engine, make_session_factory
from app.delivery.feed import background as feed_background
from app.delivery.feed.clips import FixtureClipRenderer
from app.delivery.feed.compress import FixtureCompressor, FixtureSearcher, Found, Searcher
from app.delivery.feed.models import CardType, FeedItem
from app.drugs.fixture import FixtureRegistry
from app.identity.closure_models import AccountClosure
from app.identity.providers import LoggingCodeSender
from app.ingestion.extract import FixtureExtractor
from app.ingestion.objects import LocalObjectStore
from app.ingestion.speakers import FixtureSeparator
from app.ingestion.transcribe import FixtureTranscriber
from app.reasoning.ranges import FixtureRanges
from app.reasoning.visits.summary import FixtureSummariser
from app.regions import Region
from app.settings import Settings
from tests.api import bearer, own_profile, register_by_phone
from tests.conftest import (
    FEED,
    SPEAKERS,
    STAFF_TOKEN,
    VISITS,
    WHATSAPP_FIXTURES,
    WHATSAPP_SECRET,
    Deployment,
)
from tests.paper import PAPER
from tests.test_feed_api import _feed, _reading
from tests.voice_notes import VOICE

log = logging.getLogger("tests.test_feed_background_locking")

PA = "+6593210001"


class GatedSearcher:
    """A `Searcher` whose `search` blocks the calling *thread* (never the event loop —
    `search.search_and_compress` runs it through `asyncio.to_thread`, exactly like the real
    Claude adapter) until the test releases `gate`, then delegates to a real `FixtureSearcher`
    so the cards a run makes can still be checked once it is released. `threading.Event`, not
    `asyncio.Event`: this runs off-thread, and only a thread-safe primitive can be waited on
    and set from different threads/tasks safely."""

    def __init__(self, gate: threading.Event, delegate: Searcher) -> None:
        self.gate = gate
        self.delegate = delegate
        self.calls = 0

    def search(
        self,
        kind: str,
        terms: Sequence[str],
        domains: Sequence[str],
        *,
        queries: Sequence[str] | None = None,
    ) -> Sequence[Found]:
        self.calls += 1
        self.gate.wait(timeout=10)
        return self.delegate.search(kind, terms, domains)

    def find(
        self, words: Sequence[str], domains: Sequence[str], *, media: str | None = None
    ) -> Sequence[Found]:
        return self.delegate.find(words, domains, media=media)


@dataclass(frozen=True, slots=True)
class GatedDeployment(Deployment):
    searcher: GatedSearcher = field(default=None)  # type: ignore[assignment]


@asynccontextmanager
async def _served_on_a_real_file(gate: threading.Event) -> AsyncIterator[GatedDeployment]:
    """A served deployment on a real file-backed SQLite database — never the in-memory,
    StaticPool, serialized one `tests/conftest.py`'s own `deployment` fixture uses — so a
    session opened by the background run really does take the file's one write lock, the
    same as `make dev` and the owner's own test copy."""
    from httpx import ASGITransport, AsyncClient

    with tempfile.TemporaryDirectory(prefix="nura-lock-test-") as tmp:
        db_path = Path(tmp) / "feed_lock_test.db"
        engine = make_engine(f"sqlite+aiosqlite:///{db_path}")
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            sessions = make_session_factory(engine)
            sender = LoggingCodeSender(reveal=True)
            settings = Settings(
                region=Region.SG,
                database_url=f"sqlite+aiosqlite:///{db_path}",
                dev_code_sender=True,
                red_flag_tiers=True,
                whatsapp_dev_secret=WHATSAPP_SECRET,
                review_staff=(("pharmacist", STAFF_TOKEN),),
            )
            root = Path(tempfile.mkdtemp(prefix="nura-lock-objects-"))
            objects = LocalObjectStore(root, Region.SG)
            whatsapp = FixtureProvider(secret=WHATSAPP_SECRET, fixtures=WHATSAPP_FIXTURES)
            searcher = GatedSearcher(gate, FixtureSearcher(FEED))
            providers = Providers(
                code_sender=sender,
                object_store=objects,
                extractor=FixtureExtractor(PAPER),
                summariser=FixtureSummariser(VISITS),
                transcriber=FixtureTranscriber(VOICE, Region.SG),
                searcher=searcher,
                compressor=FixtureCompressor(FEED),
                drug_registry=FixtureRegistry.load(),
                whatsapp=whatsapp,
                reference_ranges=FixtureRanges.load(),
                speaker_separator=FixtureSeparator(SPEAKERS, Region.SG),
                clips=FixtureClipRenderer(FEED),
            )
            app = create_app(settings, sessions, providers)
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://nura.test"
                ) as client:
                    yield GatedDeployment(
                        region=Region.SG,
                        client=client,
                        sessions=sessions,
                        sender=sender,
                        objects=objects,
                        whatsapp=whatsapp,
                        searcher=searcher,
                    )
            finally:
                import shutil

                shutil.rmtree(root, ignore_errors=True)
        finally:
            await engine.dispose()


@pytest.fixture(autouse=True)
async def _isolated_runs() -> AsyncIterator[None]:
    feed_background._runs.clear()
    yield
    try:
        await feed_background.drain()
    except Exception:  # noqa: BLE001 — a safety net only; the test's own failure stands
        log.warning("feed background: a task outlived its test and could not be drained cleanly")


async def test_another_write_request_answers_fast_while_a_job_is_mid_search() -> None:
    """The regression case for #297 defect 1: while a background job's `Searcher.search` is
    blocked (standing in for a real 20-40s model call), another authenticated write-path
    request must answer in a second or two, not hang behind SQLite's write lock for the
    length of the search — the failure observed live on 2026-09-18 (`/dev/quick-signin`
    itself hung past 25s while 0 of 14 jobs had completed)."""
    gate = threading.Event()
    async with _served_on_a_real_file(gate) as deployment:
        pa = await register_by_phone(deployment, PA, "Pa")
        profile_id = await own_profile(deployment, pa)

        # A reading gives State a gap to plan a learning job for (the same setup
        # `tests/test_feed_background.py`'s own "state moves" test uses) — before the first
        # `GET /feed`, exactly like that test: calling it earlier would claim "nothing due"
        # for the day before there was anything to plan.
        await _reading(deployment, profile_id, pa["token"], 138, 84)

        # This starts today's background run; the searcher blocks the moment its one job
        # reaches `search.search_and_compress` (off-thread, `asyncio.to_thread`).
        started = await _feed(deployment, profile_id, pa["token"])
        assert started["jobs"]["state"] == "looking"
        # Give the background task a moment to actually reach the blocked call.
        for _ in range(50):
            if deployment.searcher.calls:
                break
            await asyncio.sleep(0.05)
        assert deployment.searcher.calls, "the background job never reached the searcher"

        try:
            # The write path that mattered live: any authenticated request that writes
            # (`resolve_session` itself does, `app.identity.login`). A second reading is a
            # plain, ordinary one.
            answered = await asyncio.wait_for(
                deployment.client.post(
                    f"/profiles/{profile_id}/readings",
                    json={"systolic": 130, "diastolic": 80},
                    headers=bearer(pa["token"]),
                ),
                timeout=3.0,
            )
        except TimeoutError:
            pytest.fail(
                "a write request hung behind the background job's search — the database's "
                "write lock was held across the network wait (#297 defect 1)"
            )
        assert answered.status_code == 201, answered.text

        # And a plain GET /feed answers fast too, mid-search.
        mid = await asyncio.wait_for(_feed(deployment, profile_id, pa["token"]), timeout=3.0)
        assert mid["jobs"]["state"] == "looking"

        gate.set()
        await feed_background.drain()

        # The run reaches "done" once released — never stuck "looking" forever. (The reading
        # posted above while the job was mid-search moved State, so the job's own card may be
        # refused as stale rather than made — `app.state.service.StaleState`, correct,
        # unrelated behaviour; `test_a_released_job_still_makes_its_card_on_a_real_file_db`
        # below checks the "cards land" half with nothing else moving State meanwhile.)
        settled = await _feed(deployment, profile_id, pa["token"])
        assert settled["jobs"]["state"] == "done"


async def test_a_released_job_still_makes_its_card_on_a_real_file_db() -> None:
    """The other half of the same regression: the phased fix (`search.prepare_job` /
    `search_and_compress` / `write_job_results`, each on its own short session) must still
    leave the job's card in storage once the network call it was waiting on returns — the
    three-phase split must not lose a write between its own sessions."""
    gate = threading.Event()
    gate.set()  # never actually block: this test is about the write landing, not the wait
    async with _served_on_a_real_file(gate) as deployment:
        pa = await register_by_phone(deployment, PA, "Pa")
        profile_id = await own_profile(deployment, pa)
        await _reading(deployment, profile_id, pa["token"], 138, 84)

        await _feed(deployment, profile_id, pa["token"])
        await feed_background.drain()

        settled = await _feed(deployment, profile_id, pa["token"])
        assert settled["jobs"]["state"] == "done"
        learning = [item for item in settled["items"] if item["type"] == "learning"]
        assert learning, "the job's own card landed once its phases all ran"


async def test_a_pause_during_the_blocked_search_is_never_undone() -> None:
    """#291 review, REQUIRED 1: `session.merge()`ing the job object carried across the network
    wait copies every one of its load-time column values onto the fresh row —
    `expire_on_commit=False` means that object never lost its stale `enabled=True`, so a pause
    `pause_job` wrote while the search was blocked was silently overwritten back to `True` by
    phase 3's write, with no error and no trail. `run_job` now re-fetches the job fresh by id
    (`session.get`, never `.merge`) and skips writing cards for it when it comes back paused."""
    gate = threading.Event()
    async with _served_on_a_real_file(gate) as deployment:
        pa = await register_by_phone(deployment, PA, "Pa")
        profile_id = await own_profile(deployment, pa)
        await _reading(deployment, profile_id, pa["token"], 138, 84)

        started = await _feed(deployment, profile_id, pa["token"])
        assert started["jobs"]["state"] == "looking"
        for _ in range(50):
            if deployment.searcher.calls:
                break
            await asyncio.sleep(0.05)
        assert deployment.searcher.calls, "the background job never reached the searcher"

        listed = await deployment.client.get(
            f"/profiles/{profile_id}/search-jobs", headers=bearer(pa["token"])
        )
        assert listed.status_code == 200, listed.text
        [job] = listed.json()
        job_id = job["job_id"]

        paused = await deployment.client.patch(
            f"/profiles/{profile_id}/search-jobs/{job_id}",
            json={"enabled": False},
            headers=bearer(pa["token"]),
        )
        assert paused.status_code == 200, paused.text
        assert paused.json()["enabled"] is False

        gate.set()
        await feed_background.drain()

        after = await deployment.client.get(
            f"/profiles/{profile_id}/search-jobs", headers=bearer(pa["token"])
        )
        [job_after] = after.json()
        assert job_after["enabled"] is False, (
            "a pause made while the job was mid-search must never be undone by its own "
            "phase-3 write"
        )

        settled = await _feed(deployment, profile_id, pa["token"])
        learning = [item for item in settled["items"] if item["type"] == "learning"]
        assert not learning, "no cards are written for a job that came back paused"


async def test_a_closing_account_during_the_blocked_search_writes_no_card() -> None:
    """#291 review, REQUIRED 2: phase 3 must re-validate at write time, not trust the context
    it carried across the wait — an account that started closing while the search was
    blocked must refuse the write, the same as `resolve_key_context` already refuses any
    other reach to a closing account. `run_job` re-resolves the context fresh in phase 3
    (`resolve_key_context`) for exactly this."""
    gate = threading.Event()
    async with _served_on_a_real_file(gate) as deployment:
        pa = await register_by_phone(deployment, PA, "Pa")
        profile_id = await own_profile(deployment, pa)
        await _reading(deployment, profile_id, pa["token"], 138, 84)

        started = await _feed(deployment, profile_id, pa["token"])
        assert started["jobs"]["state"] == "looking"
        for _ in range(50):
            if deployment.searcher.calls:
                break
            await asyncio.sleep(0.05)
        assert deployment.searcher.calls, "the background job never reached the searcher"

        # Closed directly at the database, mid-search: the full closure flow (preview,
        # confirm) is not what this test is about — only that phase 3 notices, fresh, that
        # the account is now closing.
        async with deployment.sessions() as session:
            session.add(
                AccountClosure(
                    profile_id=uuid.UUID(profile_id),
                    requested_by_person_id=uuid.UUID(pa["person_id"]),
                    delete_after=datetime.now(UTC) + timedelta(days=30),
                )
            )
            await session.commit()

        gate.set()
        await feed_background.drain()

        # The run itself never crashes or hangs on the closing account — it settles, with
        # nothing written for the job whose write phase found the account closing.
        async with deployment.sessions() as session:
            items = (
                await session.scalars(
                    select(FeedItem).where(
                        FeedItem.profile_id == uuid.UUID(profile_id),
                        FeedItem.type == CardType.LEARNING,
                    )
                )
            ).all()
        assert not items, "no card is ever written once the account started closing mid-run"
