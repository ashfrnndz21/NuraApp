"""The app API: the channel the iOS app talks to.

`create_app` builds the same FastAPI app for `main` and for the tests, from the three things
a deployment is made of: its settings (which region, which database), a session factory on
that database, and the providers that reach the outside world. Nothing here reads the
environment; `main` does that once and passes the result in. The one thing it checks is that
the logging code sender is not being started anywhere but a declared dev run.
"""

from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.ingestion  # wires the label-photo rule onto the memory store
import app.medicines
import app.state  # noqa: F401  — wires State's recompute onto the memory store
from app.channels.api import auth, capture, doors, feed, medicines, profiles
from app.channels.api.deps import Providers
from app.channels.api.refusals import refused
from app.db import KeptSession
from app.errors import Refusal
from app.identity.providers import check_sender
from app.settings import Settings

__all__ = ["Providers", "create_app"]


def create_app(
    settings: Settings,
    session_factory: async_sessionmaker[KeptSession],
    providers: Providers,
) -> FastAPI:
    check_sender(settings, providers.code_sender)
    app = FastAPI(title="Nura", version="0.1.0")
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.providers = providers
    app.add_exception_handler(Refusal, refused)
    app.include_router(auth.router)
    app.include_router(doors.router)
    app.include_router(profiles.router)
    app.include_router(capture.router)
    app.include_router(feed.router)
    app.include_router(medicines.router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
