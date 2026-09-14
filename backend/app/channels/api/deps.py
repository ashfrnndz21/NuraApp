"""What every route is given: the database, the signed-in person, and the key context.

Three dependencies, in a chain. `db` opens one session per request and decides what happens
to it at the end. `current_person` turns the bearer token into a Person, or refuses.
`key_context` turns the person and the profile in the path into a `KeyContext`, or refuses;
there is no profile route that does not take it, which is the whole of the story's promise.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import Refusal
from app.identity.login import resolve_session
from app.identity.models import LoginSession, Person
from app.identity.providers import CodeSender
from app.keys.context import KeyContext, NoKey, resolve_key_context
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
    """One session for the request, committed at the end — including when it was refused.

    A refusal is not a failure of the request: it is an answer, and the things written on
    the way to it must stay. The wrong try counted against a code, and the audit line that
    says a caregiver reached for the notes, are exactly the rows a refusal exists to leave
    behind. Anything else that goes wrong is rolled back.
    """
    async with request.app.state.session_factory() as session:
        try:
            yield session
        except Refusal:
            await session.commit()
            raise
        except BaseException:
            await session.rollback()
            raise
        else:
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


async def key_context(
    profile_id: uuid.UUID, request: Request, person: CurrentPerson, session: Db
) -> KeyContext:
    """The key context for the profile in the path, or a refusal.

    A refusal here has no profile context to write an audit line under: `NoKey` is the
    absence of one, and `OutOfRegion` means the profile is not this deployment's to write
    about. So the channel logs the reach instead — who, which profile, which route — and
    the refusal goes out by name only.
    """
    try:
        return await resolve_key_context(
            session,
            region=settings_of(request).region,
            person_id=person.id,
            profile_id=profile_id,
        )
    except (NoKey, OutOfRegion) as refusal:
        fields = {
            "refusal": type(refusal).__name__,
            "person_id": str(person.id),
            "profile_id": str(profile_id),
            "route": f"{request.method} {request.url.path}",
        }
        log.info(
            "key context refused: %s", " ".join(f"{k}={v}" for k, v in fields.items()), extra=fields
        )
        raise


Context = Annotated[KeyContext, Depends(key_context)]
