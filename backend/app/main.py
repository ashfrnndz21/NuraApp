"""The process: one region, one database, the app API on top.

Settings are read once, here, and nowhere else. The code sender comes from
`code_sender_for`: the logging fixture when the deployment is a declared dev run
(`NURA_DEV_CODE_SENDER=1`, which `make dev` sets), and otherwise the process refuses to
start, because there is no real provider yet and the fixture prints login codes. The object
store is the local one under NURA_OBJECT_STORE, pinned to this region; the extractor is the
fixture one over NURA_PAPER_FIXTURES until the real one exists (E02); the transcriber is the
fixture one over NURA_VOICE_FIXTURES, pinned to this region, until a speech provider exists
(E02-06); the drug registry is the fixture one (`NURA_DRUG_REGISTRY=fixture`) until a licensed
client exists (E04); the WhatsApp provider is the fixture (`NURA_WHATSAPP_PROVIDER=fixture`,
signing with `NURA_WHATSAPP_DEV_SECRET`), which also only runs on a declared dev run (E19).
Logging is set up so that, on a dev run, the code line is seen.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.channels.api import Providers, create_app
from app.channels.whatsapp.provider import whatsapp_provider_for
from app.db import make_engine, make_session_factory
from app.delivery.feed.compress import FixtureCompressor, FixtureSearcher
from app.drugs.client import drug_registry_for
from app.identity.providers import code_sender_for
from app.ingestion.extract import FixtureExtractor
from app.ingestion.objects import LocalObjectStore
from app.ingestion.transcribe import FixtureTranscriber
from app.reasoning.ranges import reference_ranges_for
from app.settings import MissingSetting, Settings, load_settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s: %(message)s")


def providers_for(settings: Settings) -> Providers:
    """The outside world for this deployment: the code sender, the region's object store,
    the extractor, and the feed's searcher and compressor. A process with nowhere to keep
    bytes, or nothing to read them with, refuses to start rather than guess."""
    if settings.object_store_root is None:
        raise MissingSetting("NURA_OBJECT_STORE is not set")
    if settings.paper_fixtures is None:
        raise MissingSetting("NURA_PAPER_FIXTURES is not set and there is no other extractor yet")
    if settings.voice_fixtures is None:
        raise MissingSetting("NURA_VOICE_FIXTURES is not set and there is no other transcriber yet")
    if settings.feed_fixtures is None:
        raise MissingSetting("NURA_FEED_FIXTURES is not set and there is no other searcher yet")
    return Providers(
        code_sender=code_sender_for(settings),
        object_store=LocalObjectStore(Path(settings.object_store_root), settings.region),
        extractor=FixtureExtractor(Path(settings.paper_fixtures)),
        transcriber=FixtureTranscriber(Path(settings.voice_fixtures), settings.region),
        searcher=FixtureSearcher(Path(settings.feed_fixtures)),
        compressor=FixtureCompressor(Path(settings.feed_fixtures)),
        drug_registry=drug_registry_for(settings),
        whatsapp=whatsapp_provider_for(settings),
        reference_ranges=reference_ranges_for(settings),
    )


settings = load_settings()
engine = make_engine(settings.database_url)
app = create_app(settings, make_session_factory(engine), providers_for(settings))
