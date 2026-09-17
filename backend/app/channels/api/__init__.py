"""The app API: the channel the web client (and, later, the iOS app) talks to.

`create_app` builds the same FastAPI app for `main` and for the tests, from the three things
a deployment is made of: its settings (which region, which database), a session factory on
that database, and the providers that reach the outside world. Nothing here reads the
environment; `main` does that once and passes the result in. The one thing it checks is that
the logging code sender is not being started anywhere but a declared dev run.

Every route is served twice: at the root (`/profiles/…`, what the checkpoints and `/docs`
use) and under `/api` (`/api/profiles/…`, what the web client calls). The `/api` copy is
the same router with a prefix, so there is one set of handlers and one place a route is
declared; it is left out of the OpenAPI page so each operation appears there once. The
prefix is what lets the web client's dev server proxy the API by one rule and lets the
service worker tell the app's shell (cached) from its data (never cached by path).

When the deployment names a built web client (`NURA_WEB_DIST`, see `app.settings`) and the
directory exists, it is served at `/app` from the same origin as the API. That is how a
phone reaches the app: one address, no cross-origin cookies or CORS.

`GET /health` says the process is up; `GET /health/ready` also asks the database, and is the
one a hosting platform's health check calls (docs/deploy.md). `GET /deployment` says which
region this is and whether it is a demo, which is how the web client knows to show the demo
banner on every screen (`app.demo`, ADR 0008). A demo also gets `DemoNumbersOnly` in front
of every route and a night watch that wipes it each night.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.ingestion  # wires the label-photo rule onto the memory store
import app.medicines
import app.onboarding
import app.state  # noqa: F401  — wires State's recompute onto the memory store
from app.channels.api import (
    account,
    auth,
    capture,
    connectors,
    consent_words,
    delivery,
    dev_clock,
    doors,
    family,
    feed,
    feelings,
    insurance,
    medicines,
    onboarding,
    profiles,
    recording_uploads,
    review,
    routine,
    safety,
    timeline,
    trends,
    visits,
)
from app.channels.api.deps import Providers, settings_of
from app.channels.api.refusals import refused
from app.channels.api.uploads import UploadCaps
from app.channels.whatsapp import api as whatsapp
from app.channels.whatsapp.provider import check_whatsapp_provider
from app.db import KeptSession
from app.demo import DemoNumbersOnly, keep_wiping, wipe_quietly
from app.errors import Refusal
from app.fixtures import check_fixtures
from app.identity.providers import check_sender
from app.settings import Settings

__all__ = ["API_PREFIX", "Providers", "create_app"]

log = logging.getLogger("nura.channels.api")

API_PREFIX = "/api"
"""Where the web client finds the API: every root route, again, under this prefix."""

WEB_MOUNT = "/app"
"""Where the built web client is served when the deployment has one."""


def _api() -> APIRouter:
    api = APIRouter()
    api.include_router(auth.router)
    api.include_router(doors.router)
    api.include_router(profiles.router)
    api.include_router(capture.router)
    api.include_router(feed.router)
    api.include_router(medicines.router)
    api.include_router(visits.router)
    api.include_router(recording_uploads.router)
    api.include_router(safety.router)
    api.include_router(insurance.router)
    api.include_router(whatsapp.router)
    api.include_router(timeline.router)
    api.include_router(family.router)
    api.include_router(feelings.router)
    api.include_router(onboarding.router)
    api.include_router(consent_words.router)
    api.include_router(trends.router)
    api.include_router(routine.router)
    api.include_router(connectors.router)
    api.include_router(delivery.router)
    api.include_router(account.router)
    api.include_router(review.router)
    api.include_router(dev_clock.router)

    @api.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @api.get("/health/ready", response_model=None)
    async def ready(request: Request) -> dict[str, str] | JSONResponse:
        """Up, and the database answers. What a platform's health check and deploy gate ask."""
        try:
            async with request.app.state.session_factory() as session:
                await session.execute(text("SELECT 1"))
        except (SQLAlchemyError, OSError, TimeoutError):
            log.warning("health: the database did not answer", exc_info=True)
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return {"status": "ok"}

    @api.get("/deployment")
    async def deployment(request: Request) -> dict[str, str | bool | None]:
        """Which region this deployment serves, whether it is a demo (ADR 0008), the Web Push
        key the home-screen app subscribes with (null when it has no Web Push), and whether it
        is a declared dev run — where, and only where, a laptop's `nura-dev-` staff token is
        taken (the staff page asks before it sends one)."""
        settings = settings_of(request)
        return {
            "region": settings.region.value,
            "demo": settings.demo_mode,
            "push_key": settings.vapid_public_key,
            "dev": settings.dev_code_sender,
        }

    return api


Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def _demo_lifespan(
    settings: Settings, sessions: async_sessionmaker[KeptSession], object_root: Path | None
) -> Lifespan:
    """A demo checks for the night's wipe before it serves, then every few minutes."""

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await wipe_quietly(sessions, settings.region, object_root)
        watch = asyncio.create_task(keep_wiping(sessions, settings.region, object_root))
        try:
            yield
        finally:
            watch.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watch

    return lifespan


def create_app(
    settings: Settings,
    session_factory: async_sessionmaker[KeptSession],
    providers: Providers,
) -> FastAPI:
    check_sender(settings, providers.code_sender)
    check_whatsapp_provider(settings, providers.whatsapp)
    check_fixtures(settings, providers)
    if settings.demo_mode:
        object_root = getattr(providers.object_store, "root", None)
        app = FastAPI(
            title="Nura (demo — not for real health information)",
            version="0.1.0",
            lifespan=_demo_lifespan(settings, session_factory, object_root),
        )
        app.add_middleware(DemoNumbersOnly)
    else:
        app = FastAPI(title="Nura", version="0.1.0")
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.providers = providers
    app.add_exception_handler(Refusal, refused)
    # Every JSON upload is read against its cap before the app parses it (#133).
    app.add_middleware(UploadCaps, prefixes=("", API_PREFIX))
    api = _api()
    app.include_router(api)
    app.include_router(api, prefix=API_PREFIX, include_in_schema=False)
    if settings.web_dist is not None and Path(settings.web_dist).is_dir():
        app.mount(WEB_MOUNT, StaticFiles(directory=settings.web_dist, html=True), name="web")
    return app
