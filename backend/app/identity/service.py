"""Registering a person and opening their health graph.

Both pin to the region the deployment serves, because health data never leaves its region.
The proxy doors — setting up a profile for someone else and the claim that transfers it —
belong to E01; this story covers only a person opening his own graph.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import Refusal
from app.identity.models import Person, Profile
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
) -> Profile:
    """Open the health graph this person owns. It is pinned here and it never moves."""
    guard_region(held_in=owner.region, asked_from=region)
    existing = await session.scalar(select(Profile).where(Profile.owner_person_id == owner.id))
    if existing is not None:
        raise ProfileAlreadyOwned(f"person {owner.id} already owns profile {existing.id}")

    profile = Profile(
        region=region,
        display_name=display_name or owner.display_name,
        language=language or owner.language,
        owner_person_id=owner.id,
    )
    session.add(profile)
    await session.flush()
    return profile
