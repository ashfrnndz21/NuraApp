"""A provider's handle for a family's WhatsApp group, resolved to the profile it belongs to (#158).

A message posted in the family's group names the group by the provider's handle, and nothing
else: whose family it is has to be read before anyone's key can be resolved, exactly as the
sender's number is read (`app.identity.service.find_person_by_phone`). This is that read, in
the keys module with the other doors that come before a context (`app.keys.context`): the
handle's row, the profile it names — here and pinned to this region, or nothing — and one
READ line on that profile's trail, written as Nura's own reach (the system, no person as the
actor), so every look-up of a family by its group is on the family's own trail.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action, Channel
from app.audit.trail import record
from app.channels.whatsapp.models import WhatsAppGroup
from app.keys.context import KeyContext, Standing, profile_by_id
from app.keys.scopes import Scope
from app.regions import Region

GROUP = WhatsAppGroup.__tablename__
NO_PERSON = uuid.UUID(int=0)
"""The person on a context that names nobody: Nura's own reach before any key is resolved.
A system line writes no actor (`app.audit.trail.record`), so this id is never on the trail."""


async def profile_for_group(
    session: AsyncSession, *, region: Region, provider_group_id: str
) -> uuid.UUID | None:
    """The profile whose family group the provider's handle names, or None when no group here
    has that handle, or its profile is not in this region. Found, it is written down: a
    system READ of the group row, under the family's part, on that profile's trail."""
    group = await session.scalar(
        select(WhatsAppGroup).where(WhatsAppGroup.provider_group_id == provider_group_id)
    )
    if group is None:
        return None
    profile = await profile_by_id(session, region=region, profile_id=group.profile_id)
    if profile is None:
        return None
    await record(
        session,
        context=KeyContext(
            profile_id=profile.id,
            region=profile.region,
            person_id=profile.owner_person_id or NO_PERSON,
            scopes=frozenset({Scope.FAMILY}),
            standing=Standing.SYSTEM,
        ),
        action=Action.READ,
        scope=Scope.FAMILY,
        target=GROUP,
        target_id=group.id,
        rows=1,
        channel=Channel.WHATSAPP,
    )
    return profile.id


__all__ = ["profile_for_group"]
