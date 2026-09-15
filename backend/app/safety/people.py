"""The two reads of a Person row the safety layer makes, each with a line on the trail.

A Person is an account, not profile data, so `scoped_select` cannot reach it and
`app.audit.access.person_display_name` gates a key holder's name on `Scope.FAMILY`. The
emergency card and the not-feeling-well button need two names an emergency-only key may see
(ADR 0002): the chief's, with his number — an EMERGENCY key exists for the moment the patient
cannot speak, and the card is useless without someone to call — and the patient's own, for the
check-in. Both reads go through here: the key or the profile that names the person was read
a moment ago under the caller's scope, and the account row is read for its name, number and
language only, with a READ line under that same scope.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action
from app.audit.trail import record
from app.identity.models import Person, Profile
from app.keys.context import KeyContext
from app.keys.scopes import Scope

PERSON_TARGET = Person.__tablename__


async def key_holder(
    session: AsyncSession, context: KeyContext, person_id: uuid.UUID, /, *, scope: Scope
) -> Person | None:
    """The account a key on this profile names — read under the scope the key was read
    under, with a READ line naming the account. None if the account is gone."""
    context.require(scope)
    person = await session.get(Person, person_id)
    await record(
        session,
        context=context,
        action=Action.READ,
        scope=scope,
        target=PERSON_TARGET,
        target_id=person_id,
        rows=0 if person is None else 1,
    )
    return person


async def owner_of(
    session: AsyncSession, context: KeyContext, profile: Profile, /
) -> Person | None:
    """The patient's own account, for a notice to him: whose graph it is is what every key
    opens, so the read is under `Scope.PROFILE`, with a READ line."""
    if profile.owner_person_id is None:
        return None
    return await key_holder(session, context, profile.owner_person_id, scope=Scope.PROFILE)
