"""Registering a person and opening their health graph.

Both pin to the region the deployment serves, because health data never leaves its region.
The proxy doors — setting up a profile for someone else and the claim that transfers it —
belong to E01; this story covers only a person opening his own graph.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action
from app.audit.trail import record
from app.errors import Refusal
from app.identity.models import Person, Profile
from app.keys.context import KeyContext, owned_profile
from app.keys.scopes import ALL_SCOPES, Scope
from app.regions import Region, guard_region


class ProfileAlreadyOwned(Refusal):
    """This person already owns a health graph, and a person owns at most one."""


class AlreadyRegistered(Refusal):
    """This phone number or email is already an account somewhere else."""


async def find_person_by_phone(session: AsyncSession, phone_e164: str) -> Person | None:
    return await session.scalar(select(Person).where(Person.phone_e164 == phone_e164))


async def register_person(
    session: AsyncSession,
    *,
    region: Region,
    display_name: str,
    phone_e164: str | None = None,
    email: str | None = None,
    language: str = "en",
) -> Person:
    """Register an account, or return the one this phone number already is.

    Accounts are deduplicated by phone number: two siblings setting up from two phones must
    not end up as two accounts for the same number.
    """
    if phone_e164 is not None:
        existing = await find_person_by_phone(session, phone_e164)
        if existing is not None:
            guard_region(held_in=existing.region, asked_from=region)
            return existing
    if email is not None:
        by_email = await session.scalar(select(Person).where(Person.email == email))
        if by_email is not None:
            raise AlreadyRegistered(f"{email} is already an account")

    person = Person(
        region=region,
        display_name=display_name,
        language=language,
        phone_e164=phone_e164,
        email=email,
    )
    session.add(person)
    await session.flush()
    return person


async def create_own_profile(
    session: AsyncSession,
    *,
    region: Region,
    owner: Person,
    display_name: str | None = None,
    language: str | None = None,
    consent: Mapping[str, Any] | None = None,
) -> Profile:
    """Open the health graph this person owns. It is pinned here and it never moves.

    Opening a graph is a write to it, and it is written down as one, under the owner's own
    context, in the same transaction.

    `consent` is the agreement the owner gave to Nura holding his record: its wording
    version, the language he saw it in, and how it was captured. It is carried here so the
    door takes it from the first day; recording it as a Consent row is E00-02, which types
    this parameter, makes it required, and records `HOLD_HEALTH_RECORD` from it. Until that
    lands the values are required and validated at the door, and not yet stored.
    """
    # E00-02 seam: `consent` becomes a typed, required record written by the consent service.
    # Until then the door (`POST /profiles/mine`) refuses rather than reach here with values
    # it would have to drop.
    del consent
    guard_region(held_in=owner.region, asked_from=region)
    # The one context-less look at a profile row: there is no context yet, because there is
    # no profile yet — this is the check that there is not one already.
    if await owned_profile(session, region=region, owner_person_id=owner.id) is not None:
        raise ProfileAlreadyOwned(f"person {owner.id} already owns a profile")

    profile = Profile(
        region=region,
        display_name=display_name or owner.display_name,
        language=language or owner.language,
        owner_person_id=owner.id,
    )
    session.add(profile)
    await session.flush()
    await record(
        session,
        context=KeyContext(
            profile_id=profile.id, region=region, person_id=owner.id, scopes=ALL_SCOPES
        ),
        action=Action.WRITE,
        scope=Scope.PROFILE,
        target=Profile.__tablename__,
        target_id=profile.id,
        rows=1,
    )
    return profile
