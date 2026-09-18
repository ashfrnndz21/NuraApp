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

Once a deployment names `NURA_REVIEW_ORIGIN` (#145, before real data), `ReviewOrigin` splits
the pharmacist's review queue onto that hostname alone: `/app/review`, `/review/*` and
`/api/review/*` answer there and nowhere else, everything else answers everywhere but there,
and the review origin's answers carry a strict `Content-Security-Policy`. Unset, nothing
changes: the review queue stays on the app's own origin, `/app/review`, W6 (#137)'s posture —
fine for a demo, where nothing behind either surface is real.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

import app.ingestion  # wires the label-photo rule onto the memory store
import app.medicines
import app.onboarding
import app.state  # noqa: F401  — wires State's recompute onto the memory store
from app.channels.api import (
    account,
    analyst,
    auth,
    capture,
    connectors,
    consent_words,
    delivery,
    demo_signin,
    dev_clock,
    doors,
    family,
    feed,
    feelings,
    health_tab,
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

REVIEW_PATHS = ("/app/review", "/review", "/api/review")
"""Every path the pharmacist's review queue answers on: its page under the web mount, and its
API at the root and under `/api` (ADR 0007). `ReviewOrigin` (#145) keeps these off the
patient's origin once a deployment names a review origin, and keeps everything else off the
review origin."""

_ALWAYS_BOTH = ("/health", "/health/ready", "/api/health", "/api/health/ready")
"""Answered on every hostname regardless of `NURA_REVIEW_ORIGIN`: a hosting platform's own
health check may be pointed at either origin, and up-or-down is not a secret either keeps."""

_REVIEW_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; "
    "form-action 'none'"
)


class WrongOrigin(Refusal):
    """The pharmacist's review queue and the patient app are never served on each other's
    origin (#145): a request for one on the other's hostname is refused. Written down nowhere
    but the log — it names no profile and touches nobody's trail."""


def _host_of(scope: Scope) -> str:
    host = dict(scope.get("headers") or []).get(b"host", b"")
    return host.split(b":")[0].decode("latin-1").lower()


def _is_review_path(path: str) -> bool:
    return any(path == prefix or path.startswith(prefix + "/") for prefix in REVIEW_PATHS)


class ReviewOrigin:
    """Splits the pharmacist's review queue onto its own hostname, once a deployment names one
    (`NURA_REVIEW_ORIGIN`, #145, docs/adr/0008-demo-mode.md "Before real data").

    One process still serves both — the same container, the same database — split by the Host
    header alone, the way two hostnames pointed at the same service commonly are: a request
    under `REVIEW_PATHS` is refused (`WrongOrigin`, 404) unless its Host is the review origin,
    and a request to the review origin for anything else is refused the same way, so a
    review-origin page can never serve the patient app either. A health check answers on both
    (`_ALWAYS_BOTH`): up-or-down is not part of what this splits. The review origin's answers
    carry a strict `Content-Security-Policy` and `X-Frame-Options: DENY` — its own posture, no
    looser and no tighter than the patient app needs, never shared between them.

    Unset, this does nothing: the constructor is never called, and `/app/review` stays where
    W6 (#137) put it, on the app's own origin — never linked from the patient app, fine for a
    demo where nothing behind either surface is real.
    """

    def __init__(self, app: ASGIApp, *, review_origin: str) -> None:
        self.app = app
        self.review_origin = review_origin

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in _ALWAYS_BOTH:
            await self.app(scope, receive, send)
            return
        review_path = _is_review_path(scope["path"])
        on_review_origin = _host_of(scope) == self.review_origin
        if review_path != on_review_origin:
            # Not routed through `refused()` (Refusal's usual door, which answers from inside
            # FastAPI's own exception handling): this boundary sits outside it, in the ASGI
            # middleware stack, so the same shape — `{"refusal": "<ClassName>"}` — is built by
            # hand. Logged, never on a trail: this names no profile, touches nobody's record.
            refusal = WrongOrigin("wrong origin for this page")
            log.warning("review origin: refused %s on the wrong host", scope["path"])
            response = JSONResponse({"refusal": type(refusal).__name__}, status_code=404)
            await response(scope, receive, send)
            return
        if not on_review_origin:
            await self.app(scope, receive, send)
            return

        async def send_hardened(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Content-Security-Policy"] = _REVIEW_CSP
                headers["X-Frame-Options"] = "DENY"
                headers["X-Content-Type-Options"] = "nosniff"
            await send(message)

        await self.app(scope, receive, send_hardened)


def _api() -> APIRouter:
    api = APIRouter()
    api.include_router(analyst.router)
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
    api.include_router(health_tab.router)
    api.include_router(health_tab.catalog_router)
    api.include_router(onboarding.router)
    api.include_router(consent_words.router)
    api.include_router(trends.router)
    api.include_router(routine.router)
    api.include_router(connectors.router)
    api.include_router(delivery.router)
    api.include_router(account.router)
    api.include_router(review.router)
    api.include_router(dev_clock.router)
    api.include_router(demo_signin.router)

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
    settings: Settings,
    sessions: async_sessionmaker[KeptSession],
    object_root: Path | None,
    seed: Callable[[], Awaitable[None]] | None,
) -> Lifespan:
    """A demo checks for the night's wipe before it serves, then every few minutes.

    `seed`, given on a deployment with NURA_DEMO_SEED=1, runs once here regardless of
    whether tonight's wipe was due — the fresh-deploy case, an empty database that is not
    "due" for a wipe it has never had — and again every time `wipe_quietly`/`keep_wiping`
    actually empties the tables (`app.demo.wipe_if_due`'s own `after_wipe`), so Pa's profile
    and Mei as his chief are there again the moment the demo forgets them."""

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await wipe_quietly(sessions, settings.region, object_root, after_wipe=seed)
        if seed is not None:
            await seed()
        watch = asyncio.create_task(
            keep_wiping(sessions, settings.region, object_root, after_wipe=seed)
        )
        try:
            yield
        finally:
            watch.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watch

    return lifespan


def _seed_only_lifespan(seed: Callable[[], Awaitable[None]]) -> Lifespan:
    """A dev run given NURA_DEMO_SEED=1 has no nightly wipe to hang a reseed off — only a
    demo does (`app.demo`) — so it seeds once, here, before the app serves its first request."""

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await seed()
        yield

    return lifespan


def create_app(
    settings: Settings,
    session_factory: async_sessionmaker[KeptSession],
    providers: Providers,
    *,
    seed: Callable[[], Awaitable[None]] | None = None,
) -> FastAPI:
    """`seed`, on a deployment with NURA_DEMO_SEED=1 (`main.providers_for`'s caller wires
    it), seeds Pa's profile and Mei as his chief before the app serves — and, on a demo,
    again after every night's wipe. Tests that build their own app pass none."""
    check_sender(settings, providers.code_sender)
    check_whatsapp_provider(settings, providers.whatsapp)
    check_fixtures(settings, providers)
    if settings.demo_mode:
        object_root = getattr(providers.object_store, "root", None)
        app = FastAPI(
            title="Nura (demo — not for real health information)",
            version="0.1.0",
            lifespan=_demo_lifespan(settings, session_factory, object_root, seed),
        )
        app.add_middleware(DemoNumbersOnly)
    elif seed is not None:
        app = FastAPI(title="Nura", version="0.1.0", lifespan=_seed_only_lifespan(seed))
    else:
        app = FastAPI(title="Nura", version="0.1.0")
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.providers = providers
    app.add_exception_handler(Refusal, refused)
    # Every JSON upload is read against its cap before the app parses it (#133).
    app.add_middleware(UploadCaps, prefixes=("", API_PREFIX))
    if settings.review_origin is not None:
        # #145, before real data: the review queue and the patient app are split by origin.
        app.add_middleware(ReviewOrigin, review_origin=settings.review_origin)
    api = _api()
    app.include_router(api)
    app.include_router(api, prefix=API_PREFIX, include_in_schema=False)
    if settings.web_dist is not None and Path(settings.web_dist).is_dir():
        app.mount(WEB_MOUNT, StaticFiles(directory=settings.web_dist, html=True), name="web")
    return app
