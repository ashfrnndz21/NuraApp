"""The household every E12 test starts from: Pa owns his graph; Mei holds a chief key; Kit a
caregiver key; Siti a helper key. Each rests on Pa's own per-person consent, as in CP4."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.models import Person, Profile
from app.identity.service import create_own_profile, register_person
from app.keys.context import KeyContext, resolve_key_context
from app.keys.grants import grant_key
from app.keys.models import Key
from app.keys.scopes import ALL_SCOPES, ROLE_SCOPES, KeyRole, KeyWindow, Scope
from app.regions import Region
from tests.support import OPENING_CONSENT, agree_to_family_sharing

MONDAY = datetime(2026, 9, 14, 2, 0, tzinfo=UTC)
"""Monday 14 September 2026, 10 in the morning on Pa's wall in Singapore."""


@dataclass
class Household:
    profile: Profile
    pa: Person
    mei: Person
    kit: Person
    siti: Person
    mei_key: Key
    kit_key: Key
    siti_key: Key

    async def ctx(self, session: AsyncSession, person: Person) -> KeyContext:
        """Resolve afresh: what this person may see of Pa's graph right now."""
        return await resolve_key_context(
            session, region=Region.SG, person_id=person.id, profile_id=self.profile.id
        )


async def household(
    session: AsyncSession,
    *,
    kit_scopes: frozenset[Scope] = ROLE_SCOPES[KeyRole.CAREGIVER] | {Scope.FAMILY},
    language: str = "en",
) -> Household:
    pa = await register_person(
        session, region=Region.SG, display_name="Pa", phone_e164="+6591110001"
    )
    mei = await register_person(
        session, region=Region.SG, display_name="Mei", phone_e164="+6592220002"
    )
    kit = await register_person(
        session, region=Region.SG, display_name="Kit", phone_e164="+6595550003"
    )
    siti = await register_person(
        session, region=Region.SG, display_name="Siti", phone_e164="+6597770004"
    )
    profile = await create_own_profile(
        session,
        region=Region.SG,
        owner=pa,
        consent=OPENING_CONSENT,
        display_name="Pa",
        language=language,
    )
    owner = await resolve_key_context(
        session, region=Region.SG, person_id=pa.id, profile_id=profile.id
    )
    await agree_to_family_sharing(session, owner, mei, scopes=ALL_SCOPES, relationship="daughter")
    await agree_to_family_sharing(session, owner, kit, scopes=kit_scopes, relationship="son")
    await agree_to_family_sharing(
        session, owner, siti, scopes=ROLE_SCOPES[KeyRole.HELPER], relationship="helper"
    )
    mei_key = await grant_key(
        session, context=owner, holder=mei, role=KeyRole.CHIEF, window=KeyWindow.ALWAYS
    )
    kit_key = await grant_key(
        session,
        context=owner,
        holder=kit,
        role=KeyRole.CAREGIVER,
        scopes=kit_scopes,
        window=KeyWindow.ALWAYS,
    )
    siti_key = await grant_key(
        session, context=owner, holder=siti, role=KeyRole.HELPER, window=KeyWindow.ALWAYS
    )
    return Household(
        profile=profile,
        pa=pa,
        mei=mei,
        kit=kit,
        siti=siti,
        mei_key=mei_key,
        kit_key=kit_key,
        siti_key=siti_key,
    )
