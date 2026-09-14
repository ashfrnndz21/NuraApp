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
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import PROFILE_TARGET
from app.audit.models import Action, Outcome
from app.audit.trail import record
from app.db import take_keepers
from app.errors import Refusal
from app.identity.login import resolve_session
from app.identity.models import LoginSession, Person, Profile
from app.identity.providers import CodeSender
from app.keys.context import KeyContext, NoKey, resolve_key_context
from app.keys.scopes import Scope
from app.regions import OutOfRegion
from app.settings import Settings

log = logging.getLogger("nura.channels.api")


@dataclass(frozen=True, slots=True)
class Providers:
    """The outside world, as the app sees it. Tests pass fixtures; `main` passes the real ones."""

    code_sender: CodeSender


def settings_of(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def providers_of(request: Request) -> Providers:
    providers: Providers = request.app.state.providers
    return providers


async def db(request: Request) -> AsyncIterator[AsyncSession]:
    """One session for the request, and what becomes of it.

    The request runs inside a savepoint. When it succeeds, the savepoint is released and the
    transaction committed. When it is refused, the savepoint is rolled back — so nothing a
    service wrote on the way to its refusal lands half-done — and then the writes a refusal
    is *for* are put back and committed: the audit lines saying who reached for what, and the
    wrong try counted against a code. Those were registered with `app.db.keep_on_refusal` by
    the code that wrote them. Anything else that goes wrong rolls the whole request back.
    """
    async with request.app.state.session_factory() as session:
        try:
            async with session.begin_nested():
                yield session
        except Refusal:
            for keeper in take_keepers(session):
                await keeper(session)
            await session.commit()
            raise
        except BaseException:
            await session.rollback()
            raise
        else:
            take_keepers(session)
            await session.commit()


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

    A `NoKey` on a profile that is here, in this region, is written into that profile's
    trail as a refused read under `Scope.PROFILE`, with a context that holds nothing — the
    owner wants to see the person whose key he closed still reaching. A profile that is not
    here, or is pinned elsewhere, gets no line: there is no graph in this region to write it
    under, and an `OutOfRegion` must leave nothing of another region's profile behind. Both
    go to the channel log by a short handle, never by id.
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
        if isinstance(refusal, NoKey):
            profile = await session.get(Profile, profile_id)
            if profile is not None and profile.region is region:
                await record(
                    session,
                    context=KeyContext(
                        profile_id=profile.id,
                        region=region,
                        person_id=person.id,
                        scopes=frozenset(),
                    ),
                    action=Action.READ,
                    scope=Scope.PROFILE,
                    target=PROFILE_TARGET,
                    outcome=Outcome.REFUSED,
                    refused_because=type(refusal).__name__,
                )
        raise


Context = Annotated[KeyContext, Depends(key_context)]
