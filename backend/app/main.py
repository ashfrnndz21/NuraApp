"""The process: one region, one database, the app API on top.

Settings are read once, here, and nowhere else. The code sender comes from
`code_sender_for`: the logging fixture when the deployment is a declared dev run
(`NURA_DEV_CODE_SENDER=1`, which `make dev` sets), and otherwise the process refuses to
start, because there is no real provider yet and the fixture prints login codes. The object
store is the local one under NURA_OBJECT_STORE, pinned to this region; the extractor is
chosen by NURA_EXTRACTOR (`app.ingestion.extract_provider.extractor_for`) — the fixture one
over NURA_PAPER_FIXTURES by default, or the Claude-backed one (E02), which only builds on a
declared demo because Anthropic's API does not process in SG or MY; the transcriber is the
fixture one over NURA_VOICE_FIXTURES, pinned to this region, until a speech provider exists
(E02-06); the drug registry is the fixture one (`NURA_DRUG_REGISTRY=fixture`) until a licensed
client exists (E04); the summariser is the fixture one over NURA_VISIT_FIXTURES until a model
in the region does (E05); the WhatsApp provider is the fixture (`NURA_WHATSAPP_PROVIDER=fixture`,
signing with `NURA_WHATSAPP_DEV_SECRET`), which also only runs on a declared dev run (E19); so
does the fixture voice that says a card aloud (E11-04), and the app push reaches nobody until
the app registers devices (E11-05).
A dev run given NURA_FROZEN_CLOCK starts on a frozen clock (`app.clock.install_frozen`), for
end-to-end runs; anywhere else that setting refuses to start.
Logging is set up so that, on a dev run, the code line is seen.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.channels.api import Providers, create_app
from app.channels.whatsapp.provider import whatsapp_provider_for
from app.clock import install_frozen
from app.db import make_engine, make_session_factory
from app.delivery.feed.clips import FixtureClipRenderer
from app.delivery.feed.compress import FixtureCompressor, FixtureSearcher
from app.delivery.push import push_sender_for
from app.delivery.voice import voice_for
from app.drugs.client import drug_registry_for
from app.identity.providers import code_sender_for
from app.ingestion.extract_provider import extractor_for
from app.ingestion.speakers import FixtureSeparator
from app.ingestion.stores import object_store_for
from app.ingestion.transcribe import FixtureTranscriber
from app.reasoning.ranges import reference_ranges_for
from app.reasoning.visits.summary import FixtureSummariser
from app.search.narrator_provider import narrator_for
from app.settings import MissingSetting, Settings, load_settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s: %(message)s")


def providers_for(settings: Settings) -> Providers:
    """The outside world for this deployment: the code sender, the region's object store,
    the extractor, and the feed's searcher and compressor. A process with nowhere to keep
    bytes, or nothing to read them with, refuses to start rather than guess. Every provider
    here but the store's bucket is a fixture, and `create_app` refuses them all outside a
    declared dev run or demo (`app.fixtures`)."""
    if settings.visit_fixtures is None:
        raise MissingSetting("NURA_VISIT_FIXTURES is not set and there is no other summariser yet")
    if settings.voice_fixtures is None:
        raise MissingSetting("NURA_VOICE_FIXTURES is not set and there is no other transcriber yet")
    if settings.feed_fixtures is None:
        raise MissingSetting("NURA_FEED_FIXTURES is not set and there is no other searcher yet")
    return Providers(
        code_sender=code_sender_for(settings),
        object_store=object_store_for(settings),
        extractor=extractor_for(settings),
        narrator=narrator_for(settings),
        transcriber=FixtureTranscriber(Path(settings.voice_fixtures), settings.region),
        searcher=FixtureSearcher(Path(settings.feed_fixtures)),
        compressor=FixtureCompressor(Path(settings.feed_fixtures)),
        drug_registry=drug_registry_for(settings),
        summariser=FixtureSummariser(Path(settings.visit_fixtures)),
        whatsapp=whatsapp_provider_for(settings),
        reference_ranges=reference_ranges_for(settings),
        voice=voice_for(settings),
        push=push_sender_for(settings),
        # A clip's still (E09-06): the fixture renderer's one committed still, beside the
        # feed's other fixtures; it never makes an excerpt (no ffmpeg here).
        clips=FixtureClipRenderer(Path(settings.feed_fixtures)),
        # Who spoke when in a consult (E02-05): the fixture separator over NURA_SPEAKER_FIXTURES
        # on a laptop; unset, a recording is one stretch by an unknown speaker.
        speaker_separator=None
        if settings.speaker_fixtures is None
        else FixtureSeparator(Path(settings.speaker_fixtures), settings.region),
    )


settings = load_settings()
if (
    install_frozen(settings.frozen_clock, dev_run=settings.dev_code_sender) is not None
    and settings.frozen_clock
):
    logging.getLogger("nura.clock").info(
        "dev run: the clock is frozen at %s (POST /dev/clock moves it)",
        settings.frozen_clock.isoformat(),
    )
engine = make_engine(settings.database_url)
app = create_app(settings, make_session_factory(engine), providers_for(settings))
