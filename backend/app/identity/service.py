"""Registering a person and opening their health graph.

Both pin to the region the deployment serves, because health data never leaves its region.
The proxy doors — setting up a profile for someone else and the claim that transfers it —
belong to E01; this story covers only a person opening his own graph.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.consent.models import ConsentBasis, ConsentPurpose
from app.consent.service import RecordConsent, check_opening_words, grant_consent
from app.db import utcnow
from app.errors import Refusal
from app.identity.models import Person, Profile
from app.keys.context import resolve_key_context
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
    consent: RecordConsent,
    display_name: str | None = None,
    language: str | None = None,
    now: datetime | None = None,
) -> Profile:
    """Open the health graph this person owns. It is pinned here and it never moves.

    Opening it is agreeing to Nura keeping it: `consent` says which words he read, in which
    language, captured how, and a `HOLD_HEALTH_RECORD` consent is recorded on the new
    profile in the same transaction (E00-02). The words must be today's words on file for
    this region; anything else refuses before a row is written, so there is no profile
    without its consent.
    """
    guard_region(held_in=owner.region, asked_from=region)
    check_opening_words(consent, region)
    # The one read of a profile row without a key context, and the one place it is right:
    # no context can exist before the profile does, and this asks only whether one does.
    # Refusals here (the words, or a graph already owned) happen before there is a profile
    # to pin a trail line to, so the channel logs them at the account, not the trail.
    existing = await session.scalar(select(Profile).where(Profile.owner_person_id == owner.id))
    if existing is not None:
        raise ProfileAlreadyOwned(f"person {owner.id} already owns profile {existing.id}")

    moment = now or utcnow()
    profile = Profile(
        region=region,
        display_name=display_name or owner.display_name,
        language=language or owner.language,
        owner_person_id=owner.id,
        created_at=moment,
    )
    session.add(profile)
    await session.flush()

    context = await resolve_key_context(
        session, region=region, person_id=owner.id, profile_id=profile.id, now=moment
    )
    await grant_consent(
        session,
        context=context,
        purpose=ConsentPurpose.HOLD_HEALTH_RECORD,
        captured_via=consent.captured_via,
        basis=ConsentBasis.OWNER,
        language=consent.language,
        text_version=consent.text_version,
        now=moment,
    )
    return profile
