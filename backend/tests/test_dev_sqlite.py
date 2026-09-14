"""The laptop's and CI's database answers every request when a page is reopened mid-write.

A page reopened while the page before it was still composing its feed cards met a 500 on
its first reads (`GET /me`, `GET /profiles/{id}`): SQLite said "database is locked". Left to
itself it begins a transaction as a reader and upgrades it at the first write, and every
audited read writes its line, so of two overlapping requests one failed at once. With the
engine `make_engine` builds, every SQLite transaction begins IMMEDIATE and waits for the one
before it; over the same overlap the old engine failed in every trial.
"""

from __future__ import annotations

import asyncio
import random
from pathlib import Path

from httpx import ASGITransport, AsyncClient

from app.channels.api import Providers, create_app
from app.channels.whatsapp.provider import FixtureProvider
from app.db import Base, make_engine, make_session_factory
from app.delivery.feed.compress import FixtureCompressor, FixtureSearcher
from app.drugs.fixture import FixtureRegistry
from app.identity.providers import LoggingCodeSender
from app.ingestion.extract import FixtureExtractor
from app.ingestion.objects import LocalObjectStore
from app.ingestion.transcribe import FixtureTranscriber
from app.regions import Region
from app.settings import Settings
from tests.conftest import FEED, WHATSAPP_FIXTURES, WHATSAPP_SECRET
from tests.paper import PAPER
from tests.voice_notes import VOICE


async def test_a_reopened_page_is_answered_while_the_feed_is_still_writing(tmp_path: Path) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'dev.db'}"
    engine = make_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sender = LoggingCodeSender(reveal=True)
    app = create_app(
        Settings(
            region=Region.SG,
            database_url=url,
            dev_code_sender=True,
            whatsapp_dev_secret=WHATSAPP_SECRET,
        ),
        make_session_factory(engine),
        Providers(
            code_sender=sender,
            object_store=LocalObjectStore(tmp_path / "objects", Region.SG),
            extractor=FixtureExtractor(PAPER),
            transcriber=FixtureTranscriber(VOICE, Region.SG),
            searcher=FixtureSearcher(FEED),
            compressor=FixtureCompressor(FEED),
            drug_registry=FixtureRegistry.load(),
            whatsapp=FixtureProvider(secret=WHATSAPP_SECRET, fixtures=WHATSAPP_FIXTURES),
        ),
    )
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            words = (await client.get("/consent/wording", params={"language": "en"})).json()
            for _ in range(4):
                phone = f"+659777{random.randint(0, 9999):04d}"
                await client.post("/auth/phone/start", json={"phone_e164": phone})
                verified = await client.post(
                    "/auth/phone/verify",
                    json={"phone_e164": phone, "code": sender.last_code(phone)},
                )
                headers = {"Authorization": f"Bearer {verified.json()['token']}"}
                opened = await client.post(
                    "/profiles/mine",
                    headers=headers,
                    json={
                        "consent": {
                            "wording_version": words["version"],
                            "language": "en",
                            "captured_via": "app",
                        },
                        "display_name": "Pa",
                        "language": "en",
                    },
                )
                profile = opened.json()["profile_id"]

                async def after(path: str, delay: float, headers: dict[str, str] = headers) -> int:
                    await asyncio.sleep(delay)
                    return (await client.get(path, headers=headers)).status_code

                # The page before the reload asks for the feed (it composes and writes today's
                # cards); the reopened page asks who he is and whose papers, a moment later.
                answered = await asyncio.gather(
                    after(f"/profiles/{profile}/feed", 0),
                    after("/me", 0.005),
                    after(f"/profiles/{profile}", 0.01),
                )
                assert answered == [200, 200, 200]
    finally:
        await engine.dispose()


def test_a_deployment_database_is_left_as_it_is() -> None:
    engine = make_engine("postgresql+asyncpg://nura@localhost/nura")
    assert engine.sync_engine.dialect.name == "postgresql"
