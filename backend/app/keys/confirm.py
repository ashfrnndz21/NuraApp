"""Who may give a confirm on a profile.

Nothing changes a medicine, books anything or sends anything without an explicit confirm from
a person. The surface collects the confirm — a tap, a spoken yes — and passes who gave it; this
says who that may be: the person asking, the owner of the graph, or someone holding an active
key on it, and in the region the profile is in. Any other person row — another household's,
the other region's, none at all — is not a confirmer, and the refusal is the same for each,
so the check is not a way to learn which person ids exist.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import utcnow
from app.errors import Refusal
from app.identity.models import Person, Profile
from app.keys.context import KeyContext
from app.keys.models import Key


class NobodyConfirmed(Refusal):
    """A confirm comes from a person on this profile. This named nobody, or somebody else."""


async def require_confirmer(
    session: AsyncSession,
    *,
    context: KeyContext,
    person_id: uuid.UUID,
    now: datetime | None = None,
) -> Person:
    """The person who gave the confirm, or one refusal whatever was wrong with the name."""
    moment = now or utcnow()
    person = await session.get(Person, person_id)
    if person is None or person.region is not context.region:
        raise NobodyConfirmed("a confirm comes from a person on this profile, in this region")
    if person.id == context.person_id:
        return person
    profile = await session.get(Profile, context.profile_id)
    if profile is not None and profile.owner_person_id == person.id:
        return person
    keys = await session.scalars(
        select(Key).where(Key.profile_id == context.profile_id, Key.holder_person_id == person.id)
    )
    if any(key.is_active(moment) for key in keys):
        return person
    raise NobodyConfirmed("a confirm comes from a person on this profile, in this region")
