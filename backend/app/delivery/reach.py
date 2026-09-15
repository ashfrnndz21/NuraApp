"""Whom Nura can reach, and how: for the owner and his chief (#163, #148).

A red flag goes to each person every way they can be reached (`triggers.deliver`): an app push
when they have a device, WhatsApp when they have a number and did not answer no to it, and the
notice on their family page always. Here is that, per person holding a live key, so the chief
sees who Nura cannot message on WhatsApp — and who it reaches only in the app — rather than
finding out when something is wrong. Owner and chief only, like the delivery log.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import person_display_name
from app.channels.whatsapp.opt_in import said_no
from app.db import as_utc, utcnow
from app.delivery.push import PushSender
from app.delivery.reach_words import reach_lines
from app.delivery.triggers.preferences import owner_or_chief
from app.identity.models import Person
from app.keys.context import KeyContext
from app.keys.grants import list_keys


@dataclass(frozen=True, slots=True)
class Reach:
    """One person on his circle, and how Nura reaches them."""

    person_id: uuid.UUID
    whatsapp: bool
    """They have a number and did not answer no to WhatsApp."""
    push: bool
    """They have a device a push reaches."""
    lines: list[str]
    """What the chief reads when WhatsApp cannot reach them; none when it can."""


async def who_nura_reaches(
    session: AsyncSession, *, context: KeyContext, push: PushSender, language: str | None
) -> list[Reach]:
    """Each person holding a live key, once, in the order they were let in."""
    owner_or_chief(context)
    moment = utcnow()
    found: list[Reach] = []
    seen: set[uuid.UUID] = set()
    for key in sorted(
        await list_keys(session, context=context), key=lambda k: as_utc(k.granted_at)
    ):
        if key.holder_person_id in seen or not key.is_active(moment):
            continue
        seen.add(key.holder_person_id)
        person = await session.get(Person, key.holder_person_id)
        whatsapp = (
            person is not None
            and bool(person.phone_e164)
            and not await said_no(session, context=context, person_id=key.holder_person_id)
        )
        pushed = await push.reachable(session, context, key.holder_person_id)
        lines: list[str] = []
        if not whatsapp:
            name = await person_display_name(session, context, key.holder_person_id)
            lines = reach_lines(name, push=pushed, language=language)
        found.append(Reach(key.holder_person_id, whatsapp, pushed, lines))
    return found
