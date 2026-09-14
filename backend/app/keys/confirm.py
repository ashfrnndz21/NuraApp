"""Who may give a confirm on a profile.

Nothing changes a medicine, books anything or sends anything without an explicit confirm from
a person. The surface collects the confirm — a tap, a spoken yes — and passes who gave it; this
says who that may be: someone who could open this profile right now — its owner, or a person
holding a key on it that is live at this moment — and who is in the region the profile is in.
That is asked of `resolve_key_context` itself, not of a copy of its rules, so a key that was
closed after the asker's own context was resolved no longer confirms anything, and there is no
second reading of the key table to keep in step. Any other person row — another household's,
the other region's, none at all — is not a confirmer, and the refusal is the same for each,
so the check is not a way to learn which person ids exist.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import Refusal
from app.identity.models import Person
from app.keys.context import KeyContext, resolve_key_context


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
    person = await session.get(Person, person_id)
    if person is None or person.region is not context.region:
        raise NobodyConfirmed("a confirm comes from a person on this profile, in this region")
    try:
        # The profile is in `context.region`, so this cannot be refused for the region; it is
        # refused when the person is nobody to the profile, or held a key that is now closed.
        await resolve_key_context(
            session,
            region=context.region,
            person_id=person.id,
            profile_id=context.profile_id,
            now=now,
        )
    except Refusal as refused:
        raise NobodyConfirmed(
            "a confirm comes from a person on this profile, in this region"
        ) from refused
    return person
