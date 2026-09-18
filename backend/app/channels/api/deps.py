"""What every route is given: the database, the signed-in person, and the key context.

Three dependencies, in a chain. `db` opens one session per request and decides what happens
to it at the end. `current_person` turns the bearer token into a Person, or refuses.
`key_context` turns the person and the profile in the path into a `KeyContext`, or refuses;
there is no profile route that does not take it, which is the whole of the story's promise.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.whatsapp.provider import WhatsAppProvider
from app.db import unit_of_work
from app.delivery.feed.clips import ClipRenderer
from app.delivery.feed.compress import Compressor, Searcher
from app.delivery.push import NoDevices, PushSender
from app.delivery.voice import FixtureVoice, Voice
from app.drugs.registry import DrugRegistry
from app.errors import Refusal
from app.identity.login import resolve_session
from app.identity.models import LoginSession, Person
from app.identity.providers import CodeSender
from app.ingestion.extract import Extractor
from app.ingestion.objects import ObjectStore
from app.ingestion.speakers import SpeakerSeparator
from app.ingestion.transcribe import Transcriber
from app.insurance.cost_expectation import Estimator, RuleEstimator
from app.keys.context import KeyContext, NoKey, resolve_key_context
from app.reasoning.navigation.models import Drafter
from app.reasoning.navigation.rule_drafter import RuleDrafter
from app.reasoning.ranges import FixtureRanges, ReferenceRanges
from app.reasoning.visits.summary import Summariser
from app.regions import OutOfRegion
from app.search.asker import Asker, RuleBasedAsker
from app.search.narrate import FixtureNarrator, Narrator
from app.search.retrieve import KeywordRetriever, Retriever
from app.settings import Settings

log = logging.getLogger("nura.channels.api")


@dataclass(frozen=True, slots=True)
class Providers:
    """The outside world, as the app sees it. Tests pass fixtures; `main` passes the real ones."""

    code_sender: CodeSender
    object_store: ObjectStore
    """Where artefact bytes go: one store, pinned to this deployment's region."""
    extractor: Extractor
    """What reads a photo into fields with confidence; the fixture one until the real one."""
    summariser: Summariser
    """What reads a visit transcript into actions, changes, follow-ups and facts heard; the
    fixture one until a model in the region exists (E05-05)."""
    transcriber: Transcriber
    """What hears a voice note, in this deployment's region; the fixture one until a speech
    provider in the region exists (E02-06)."""
    searcher: Searcher
    """What finds pages for a self-search job, from allowlisted sources only (E21)."""
    compressor: Compressor
    """What turns a page into the lines a card says, with its cite; the fixture one (E21)."""
    drug_registry: DrugRegistry
    """The licensed drug data behind its port (`app.drugs`): identification, interactions and
    monographs come from it and from nowhere else."""
    whatsapp: WhatsAppProvider
    """The business solution provider behind its port (`app.channels.whatsapp.provider`);
    the fixture on a laptop and in the tests, which sends nothing anywhere."""
    reference_ranges: ReferenceRanges = field(default_factory=FixtureRanges.load)
    """The reference ranges the lab trend reads (E09-01, `app.reasoning.ranges`): the fixture
    table until a licensed one is signed off. `main` chooses it by `NURA_REFERENCE_RANGES`; the
    default is there so a test that builds `Providers` for another purpose need not name it,
    the way `retriever` is."""
    voice: Voice = field(default_factory=FixtureVoice)
    """What says a card aloud (E11-04), behind its port (`app.delivery.voice`); `main` passes
    the fixture on a dev run and refuses to start anywhere else until a speech provider exists."""
    push: PushSender = field(default_factory=NoDevices)
    """What reaches a person's app with a content-free push (`app.delivery.push`); nobody
    until the app registers devices, so the app channel falls through."""
    speaker_separator: SpeakerSeparator | None = None
    """Who spoke when in a consult recording, in this deployment's region (E02-05): the
    fixture one on a laptop; None where no separator is configured, and then a recording is
    kept as one stretch by an unknown speaker (`app.ingestion.speakers.Unseparated`)."""
    clips: ClipRenderer | None = None
    """What makes a clip's still and, where the licence allows, its excerpt (E09-06,
    `app.delivery.feed.clips`): the fixture on a laptop and the demo, which serves one still
    and never an excerpt; None where none is configured, and a clip is its narration and
    captions alone."""
    retriever: Retriever = field(default_factory=KeywordRetriever)
    """Which things on the record a question is about, for Ask (E03-05): keywords until a
    model-backed retriever exists behind the same port; the tests pass a fixture one."""
    narrator: Narrator = field(default_factory=FixtureNarrator)
    """What says Ask's and Find's trace steps aloud (the narrated-trace story): the fixture
    label, unchanged, until a Claude-backed narrator is chosen on a declared demo
    (`app.search.narrator_provider.narrator_for`); the tests pass the fixture one."""
    asker: Asker = field(default_factory=RuleBasedAsker)
    """What answers `POST /{id}/ask/stream` (Ask as an agent): the rule-based retriever,
    unchanged, until the agent asker is chosen on a declared demo
    (`app.search.asker_provider.asker_for`); the tests pass the rule-based one."""
    drafter: Drafter = field(default_factory=RuleDrafter)
    """What writes a care-navigation drafted message (T3): the catalogue's own templates,
    unchanged, until the Claude-backed drafter is chosen on a declared demo
    (`app.reasoning.navigation.drafter_provider.drafter_for`); the tests pass the rule one."""
    estimator: Estimator = field(default_factory=RuleEstimator)
    """What answers `GET /{id}/visits/{appointment_id}/cost` (T3, cost expectation): the
    cached fee-benchmark table, unchanged, until the Claude-refined estimator is chosen on a
    declared demo or dev run (`app.insurance.cost_expectation.estimator_for`); the tests pass
    the rule one."""


def settings_of(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def providers_of(request: Request) -> Providers:
    providers: Providers = request.app.state.providers
    return providers


@asynccontextmanager
async def session_scope(request: Request) -> AsyncIterator[AsyncSession]:
    """One session, and what becomes of it: the request boundary `db` (below) wraps as a
    FastAPI dependency, for a route whose whole response is computed before it is sent.

    The request is one `app.db.unit_of_work`: a savepoint that is released on success and
    rolled back on a `Refusal`, after which the boundary replays what a refusal keeps — the
    refused audit lines, the wrong try counted against a code — and this commits them. So a
    refused request leaves the record of the reaching and nothing it wrote on the way. Any
    other failure rolls the whole request back.

    A stream calls this directly, itself, inside the body it streams — never through `Depends
    (db)` — because FastAPI closes a `yield` dependency's exit stack the moment the endpoint
    function *returns*, which for a `StreamingResponse` is the moment the (unread) generator
    is handed back, well before Starlette actually drives that generator to send the body.
    A session from `Depends(db)` would already be closed by the time a streamed step tried to
    read with it. See `app.channels.api.timeline.ask_stream`, `app.channels.api.feed.
    find_pages_stream`.
    """
    async with request.app.state.session_factory() as session:
        try:
            async with unit_of_work(session):
                yield session
        except Refusal:
            await session.commit()
            raise
        except BaseException:
            await session.rollback()
            raise
        else:
            await session.commit()


async def db(request: Request) -> AsyncIterator[AsyncSession]:
    """One session per request (see `session_scope`), as a FastAPI dependency: every route
    but a stream, whose whole response is computed while the dependency is still open."""
    async with session_scope(request) as session:
        yield session


Db = Annotated[AsyncSession, Depends(db)]


def _bearer(header: str | None) -> str | None:
    if header is None:
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


@dataclass(frozen=True, slots=True)
class SignedIn:
    person: Person
    login: LoginSession


async def current_login(request: Request, session: Db) -> SignedIn:
    """Who is calling, from the bearer token. `NoSession` for anything else."""
    person, login = await resolve_session(
        session,
        region=settings_of(request).region,
        token=_bearer(request.headers.get("authorization")),
    )
    return SignedIn(person=person, login=login)


async def current_person(signed_in: Annotated[SignedIn, Depends(current_login)]) -> Person:
    return signed_in.person


CurrentPerson = Annotated[Person, Depends(current_person)]


def _reach_id(person_id: uuid.UUID, profile_id: uuid.UUID) -> str:
    """A short handle for one person reaching for one profile, for the log.

    The ids themselves stay out of the log: the profile id is health data's address and the
    person id is someone's. The handle is enough to see the same pair reaching again.
    """
    return hashlib.sha256(f"{person_id}:{profile_id}".encode()).hexdigest()[:8]


def _route_of(request: Request) -> str:
    """The route as declared — `/profiles/{profile_id}/notes` — never the path as called,
    which carries the profile id."""
    matched = request.scope.get("route")
    template = getattr(matched, "path", None)
    return f"{request.method} {template or '?'}"


async def key_context(
    profile_id: uuid.UUID, request: Request, person: CurrentPerson, session: Db
) -> KeyContext:
    """The key context for the profile in the path, or a refusal.

    A `NoKey` from a person the profile knows — its owner, or someone who once held a key —
    is written into that profile's trail by the resolver itself (`app.keys.context`), as a
    refused read under `Scope.PROFILE` with a context that holds nothing: the owner wants to
    see the person whose key he closed still reaching. A stranger, a profile that is not
    here, or one pinned elsewhere gets no line: nothing can be found or placed by asking, and
    an `OutOfRegion` must leave nothing of another region's profile behind. Every refusal
    goes to the channel log by a short handle, never by id.
    """
    region = settings_of(request).region
    try:
        return await resolve_key_context(
            session, region=region, person_id=person.id, profile_id=profile_id
        )
    except (NoKey, OutOfRegion) as refusal:
        log.info(
            "key context refused: refusal=%s reach=%s route=%s",
            type(refusal).__name__,
            _reach_id(person.id, profile_id),
            _route_of(request),
        )
        # The trail line for a person the profile knows is written by the resolver itself.
        raise


Context = Annotated[KeyContext, Depends(key_context)]


async def closing_key_context(
    profile_id: uuid.UUID, request: Request, person: CurrentPerson, session: Db
) -> KeyContext:
    """The key context even while the owner's closing of his account stands (#143): for the
    doors that stay open to him, the closing's status and his undo. Who may use them is the
    service's to say (`app.identity.closing`)."""
    return await resolve_key_context(
        session,
        region=settings_of(request).region,
        person_id=person.id,
        profile_id=profile_id,
        while_closing=True,
    )


ClosingContext = Annotated[KeyContext, Depends(closing_key_context)]
