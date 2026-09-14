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
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.ingestion  # wires the label-photo rule onto the memory store
import app.medicines
import app.state  # noqa: F401  — wires State's recompute onto the memory store
from app.channels.api import (
    auth,
    capture,
    consent_words,
    delivery,
    doors,
    family,
    feed,
    medicines,
    profiles,
    safety,
    timeline,
    visits,
)
from app.channels.api.deps import Providers
from app.channels.api.refusals import refused
from app.channels.whatsapp import api as whatsapp
from app.channels.whatsapp.provider import check_whatsapp_provider
from app.db import KeptSession
from app.errors import Refusal
from app.identity.providers import check_sender
from app.settings import Settings

__all__ = ["API_PREFIX", "Providers", "create_app"]

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
    api.include_router(safety.router)
    api.include_router(whatsapp.router)
    api.include_router(timeline.router)
    api.include_router(family.router)
    api.include_router(consent_words.router)
    api.include_router(delivery.router)

    @api.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return api


def create_app(
    settings: Settings,
    session_factory: async_sessionmaker[KeptSession],
    providers: Providers,
) -> FastAPI:
    check_sender(settings, providers.code_sender)
    check_whatsapp_provider(settings, providers.whatsapp)
    app = FastAPI(title="Nura", version="0.1.0")
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.providers = providers
    app.add_exception_handler(Refusal, refused)
    api = _api()
    app.include_router(api)
    app.include_router(api, prefix=API_PREFIX, include_in_schema=False)
    if settings.web_dist is not None and Path(settings.web_dist).is_dir():
        app.mount(WEB_MOUNT, StaticFiles(directory=settings.web_dist, html=True), name="web")
    return app
