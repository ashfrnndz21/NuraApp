"""What a refused unit of work keeps: the refused line, and nothing it wrote on the way.

`app.db.unit_of_work` is the request boundary the API runs every request in. A request that
writes and then is refused rolls the write back — the row, and the ALLOWED line that said it
was written — and keeps the REFUSED line, replayed after the rollback.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEntry, Outcome
from app.db import unit_of_work
from app.identity.service import create_own_profile, register_person
from app.keys.context import OutOfScope, resolve_key_context
from app.keys.grants import grant_key
from app.keys.scopes import KeyRole, Scope
from app.notes.models import Note
from app.notes.service import list_notes, write_note
from app.regions import Region


async def test_a_unit_that_writes_then_refuses_keeps_the_refused_line_and_not_the_write(
    sg: AsyncSession,
) -> None:
    pa = await register_person(sg, region=Region.SG, display_name="Pa", phone_e164="+6591110001")
    profile = await create_own_profile(sg, region=Region.SG, owner=pa)
    owner = await resolve_key_context(sg, region=Region.SG, person_id=pa.id, profile_id=profile.id)
    daughter = await register_person(
        sg, region=Region.SG, display_name="Daughter", phone_e164="+6591110002"
    )
    await grant_key(
        sg,
        context=owner,
        holder=daughter,
        role=KeyRole.CAREGIVER,
        scopes=[Scope.MEDICINES],
        basis="owner_consent",
    )
    held = await resolve_key_context(
        sg, region=Region.SG, person_id=daughter.id, profile_id=profile.id
    )
    await sg.commit()
    lines_before = len((await sg.scalars(select(AuditEntry))).all())

    # One unit: the owner writes a note, then the caregiver reaches for the notes.
    with pytest.raises(OutOfScope):
        async with unit_of_work(sg):
            await write_note(sg, context=owner, text="I did not tell the children.")
            await list_notes(sg, context=held)
    await sg.commit()

    assert (await sg.scalars(select(Note))).all() == []
    after = (await sg.scalars(select(AuditEntry))).all()
    new = [line for line in after if line.actor_person_id in {pa.id, daughter.id}][lines_before:]
    assert [(line.actor_person_id, line.outcome, line.refused_because) for line in new] == [
        (daughter.id, Outcome.REFUSED, "OutOfScope")
    ]
    assert not any(
        line.outcome is Outcome.ALLOWED and line.target == Note.__tablename__ for line in after
    )
