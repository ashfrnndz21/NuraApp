"""The dev-only CORS gate (golden-path PR #332; independent review B3/FIX-BEFORE-MERGE, then
the CI-regression fix that split this off `dev_code_sender`).

`app.channels.api.create_app` adds `CORSMiddleware` only when `settings.mobile_dev_cors` is
true — the mobile golden path's own web target (Expo's Metro dev server has no same-origin
proxy the way `web/`'s Vite dev server does, so the browser calls this API cross-origin
directly). It is deliberately its own flag (`NURA_MOBILE_DEV_CORS=1`), not folded into
`dev_code_sender`: `dev_code_sender` is also true in CI's web job and on laptops that never run
the Expo target, and `CORSMiddleware(allow_origin_regex=...)` makes Starlette add
`Vary: Origin` to every matching response, which the web app's service worker respects — so a
page cached for offline use stops matching, and offline specs fail on a run that never touched
the Expo target at all. This is exactly the regression `test_dev_code_sender_alone_never_registers_cors_middleware`
pins: `dev_code_sender=True` on its own must never register the middleware. A deployment never
sets `NURA_MOBILE_DEV_CORS=1`, so this block is dead code there; the rest of this file pins the
other half of that promise: no CORS headers by default, and — with the flag on — loopback
origins only, never credentials, never a wildcard.
"""

from __future__ import annotations

from pathlib import Path

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from starlette.middleware.cors import CORSMiddleware

from app.channels.api import Providers, create_app
from app.channels.whatsapp.provider import FixtureProvider
from app.db import make_session_factory
from app.delivery.feed.compress import FixtureCompressor, FixtureSearcher
from app.drugs.fixture import FixtureRegistry
from app.identity.providers import LoggingCodeSender, NoCodeSender
from app.ingestion.extract import FixtureExtractor
from app.ingestion.objects import LocalObjectStore
from app.ingestion.transcribe import FixtureTranscriber
from app.reasoning.ranges import FixtureRanges
from app.reasoning.visits.summary import FixtureSummariser
from app.regions import Region
from app.settings import Settings
from tests.conftest import FEED, VISITS
from tests.paper import PAPER
from tests.voice_notes import VOICE

ENV_ORIGIN = "http://localhost:8062"


def _providers(tmp: Path, *, dev: bool) -> Providers:
    return Providers(
        code_sender=LoggingCodeSender() if dev else NoCodeSender(),
        object_store=LocalObjectStore(tmp, Region.SG),
        extractor=FixtureExtractor(PAPER),
        summariser=FixtureSummariser(VISITS),
        transcriber=FixtureTranscriber(VOICE, Region.SG),
        searcher=FixtureSearcher(FEED),
        compressor=FixtureCompressor(FEED),
        drug_registry=FixtureRegistry.load(),
        whatsapp=FixtureProvider(secret="test"),
        reference_ranges=FixtureRanges.load(),
    )


async def _engine_and_sessions():
    engine = create_async_engine("sqlite+aiosqlite://")
    return engine, make_session_factory(engine)


def test_no_dev_code_sender_never_registers_cors_middleware(tmp_path: Path) -> None:
    """`mobile_dev_cors=False` is the gate itself — checked with `demo_mode=True` so the
    fixture providers this test's own scaffolding uses are allowed to run at all
    (`check_fixtures`); a true production run (real, non-fixture providers throughout) is
    outside this test's own scope, but shares the identical `mobile_dev_cors` gate."""
    import anyio

    async def run() -> None:
        engine, sessions = await _engine_and_sessions()
        settings = Settings(region=Region.SG, database_url="sqlite+aiosqlite://", demo_mode=True)
        assert settings.mobile_dev_cors is False
        app = create_app(settings, sessions, _providers(tmp_path, dev=False))
        assert not any(m.cls is CORSMiddleware for m in app.user_middleware)
        await engine.dispose()

    anyio.run(run)


def test_dev_code_sender_alone_never_registers_cors_middleware(tmp_path: Path) -> None:
    """The regression this file exists to pin: `dev_code_sender=True` on its own (the CI web
    job's own setting, and the owner's laptop backend) must never register `CORSMiddleware`.
    Only `mobile_dev_cors=True` does — see the module docstring for why the two must stay
    apart."""
    import anyio

    async def run() -> None:
        engine, sessions = await _engine_and_sessions()
        settings = Settings(
            region=Region.SG, database_url="sqlite+aiosqlite://", dev_code_sender=True
        )
        assert settings.mobile_dev_cors is False
        app = create_app(settings, sessions, _providers(tmp_path, dev=True))
        assert not any(m.cls is CORSMiddleware for m in app.user_middleware)
        await engine.dispose()

    anyio.run(run)


async def test_no_dev_code_sender_response_carries_no_cors_header(tmp_path: Path) -> None:
    engine, sessions = await _engine_and_sessions()
    settings = Settings(region=Region.SG, database_url="sqlite+aiosqlite://", demo_mode=True)
    app = create_app(settings, sessions, _providers(tmp_path, dev=False))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/health", headers={"Origin": ENV_ORIGIN})
    assert "access-control-allow-origin" not in {k.lower() for k in res.headers}
    await engine.dispose()


def test_mobile_dev_cors_registers_cors_middleware_loopback_only_no_credentials(
    tmp_path: Path,
) -> None:
    """The golden-path builder's own run sets both flags together (`NURA_DEV_CODE_SENDER=1`
    for the logging code sender and the fixture providers, `NURA_MOBILE_DEV_CORS=1` for the
    Expo web target's cross-origin calls) — this is that combination."""
    import anyio

    async def run() -> None:
        engine, sessions = await _engine_and_sessions()
        settings = Settings(
            region=Region.SG,
            database_url="sqlite+aiosqlite://",
            dev_code_sender=True,
            mobile_dev_cors=True,
        )
        app = create_app(settings, sessions, _providers(tmp_path, dev=True))
        cors = next((m for m in app.user_middleware if m.cls is CORSMiddleware), None)
        assert cors is not None
        # allow_credentials must be False and the origin must be matched by regex, never "*".
        assert cors.kwargs.get("allow_credentials") is False
        assert cors.kwargs.get("allow_origins") in (None, [])
        origin_regex = cors.kwargs.get("allow_origin_regex")
        assert origin_regex is not None
        import re

        pattern = re.compile(origin_regex)
        assert pattern.fullmatch("http://localhost:8062")
        assert pattern.fullmatch("http://127.0.0.1:8063")
        assert not pattern.fullmatch("https://evil.example.com")
        assert not pattern.fullmatch("http://localhost.evil.example.com:8062")
        await engine.dispose()

    anyio.run(run)


async def test_mobile_dev_cors_response_allows_a_loopback_origin_only(tmp_path: Path) -> None:
    engine, sessions = await _engine_and_sessions()
    settings = Settings(
        region=Region.SG,
        database_url="sqlite+aiosqlite://",
        dev_code_sender=True,
        mobile_dev_cors=True,
    )
    app = create_app(settings, sessions, _providers(tmp_path, dev=True))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        allowed = await client.get("/health", headers={"Origin": ENV_ORIGIN})
        denied = await client.get("/health", headers={"Origin": "https://evil.example.com"})
    assert allowed.headers.get("access-control-allow-origin") == ENV_ORIGIN
    assert "access-control-allow-origin" not in {k.lower() for k in denied.headers}
    await engine.dispose()
