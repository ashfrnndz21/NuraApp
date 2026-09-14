"""Registering a person and opening their health graph.

Both pin to the region the deployment serves, because health data never leaves its region.
The other doors — setting up a graph for someone else, and the claim that transfers it —
are `app.identity.doors`; this is a person opening his own.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action
from app.audit.trail import record
from app.consent.models import ConsentBasis, ConsentPurpose
from app.consent.service import RecordConsent, check_opening_words, grant_consent
from app.db import utcnow
from app.errors import Refusal
from app.identity.models import Person, Profile
from app.keys.context import owned_profile, profile_for_number, resolve_key_context
from app.keys.scopes import Scope
from app.regions import Region, guard_region


class ProfileAlreadyOwned(Refusal):
    """This person already owns a health graph, and a person owns at most one."""


class AlreadyRegistered(Refusal):
    """This phone number or email is already an account somewhere else."""


class WaitingToBeClaimed(Refusal):
    """A graph was set up for this person's number by someone else, and it is his to claim
    (`app.identity.doors`), not to open again beside."""


async def find_person_by_phone(session: AsyncSession, phone_e164: str) -> Person | None:
    return await session.scalar(select(Person).where(Person.phone_e164 == phone_e164))


async def invitee_by_phone(
    session: AsyncSession,
    *,
    region: Region,
    phone_e164: str,
    name: str = "",
    named_by: uuid.UUID | None = None,
) -> Person:
    """The account a number is — or, for a number that is not one yet, a placeholder carrying
    the name the inviter typed and who typed it, until the person signs in and gives his own.

    An existing account is returned as it is: the answer never says whether the number was
    already known, and nobody renames someone else's account.
    """
    existing = await find_person_by_phone(session, phone_e164)
    if existing is not None:
        guard_region(held_in=existing.region, asked_from=region)
        return existing
    person = Person(
        region=region,
        display_name=name,
        phone_e164=phone_e164,
        named_by_person_id=named_by if name else None,
    )
    session.add(person)
    await session.flush()
    return person


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
    if await owned_profile(session, region=region, owner_person_id=owner.id) is not None:
        raise ProfileAlreadyOwned(f"person {owner.id} already owns a profile")
    if owner.phone_e164 is not None:
        # One graph per number: a graph set up for his number by someone else is his to claim.
        waiting = await profile_for_number(session, region=region, phone_e164=owner.phone_e164)
        if waiting is not None:
            raise WaitingToBeClaimed(f"a graph set up for person {owner.id} waits for his claim")

    moment = utcnow()
    profile = Profile(
        region=region,
        display_name=display_name or owner.display_name,
        language=language or owner.language,
        owner_person_id=owner.id,
        patient_phone_e164=owner.phone_e164,
        created_at=moment,
    )
    session.add(profile)
    await session.flush()

    context = await resolve_key_context(
        session, region=region, person_id=owner.id, profile_id=profile.id
    )
    # Opening a graph is a write to it, written down under the owner's own context.
    await record(
        session,
        context=context,
        action=Action.WRITE,
        scope=Scope.PROFILE,
        target=Profile.__tablename__,
        target_id=profile.id,
        rows=1,
    )
    await grant_consent(
        session,
        context=context,
        purpose=ConsentPurpose.HOLD_HEALTH_RECORD,
        captured_via=consent.captured_via,
        basis=ConsentBasis.OWNER,
        language=consent.language,
        text_version=consent.text_version,
    )
    return profile
