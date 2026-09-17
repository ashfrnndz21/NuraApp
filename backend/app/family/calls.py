"""Upcoming calls with family (design-direction.md, Connect's "Upcoming Call").

A call names a family member, a time, and a way to join: `call_link` when the family has
given one (their own Zoom or Google Meet — in-app video calling needs a video provider Nura
does not have), else Nura rings `with_person_id`'s own phone. It sits on the calendar the way
a visit does, but it is not one: `app.memory.models.Appointment` is tied to a `Provider`
(a doctor, a clinic), never a person, so a family call is its own row
(`app.family.models.ScheduledCall`), under the family scope, the same scope the roster and
the tasks sit under.

Scheduling and cancelling are the chief's or his own, the same footing driving and tasking
rest on (`app.family.common.a_chief`); nothing books or sends without an explicit confirm
from a person (`app.drafts.CallDraft`). Reading the upcoming calls is open to any key that
holds the family scope, the way the roster is.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_read, audited_write
from app.audit.models import Action
from app.audit.trail import record
from app.db import as_utc, utcnow
from app.drafts import CallDraft
from app.errors import Refusal
from app.family.common import a_chief
from app.family.models import ScheduledCall
from app.family.roster import NotOnThisProfile
from app.keys.confirm import consume_confirmation
from app.keys.context import KeyContext, holds_the_profile
from app.keys.scopes import Scope
from app.memory.models import short_label

CALLS_TARGET = ScheduledCall.__tablename__
"""`NotOnThisProfile` (a call is with someone who holds a key on this profile, or its owner,
never a stranger) is `app.family.roster`'s own — the same refusal a task or a roster slot
given to a stranger raises, already registered in `app.channels.api.refusals`."""


class NoSuchCall(Refusal):
    """No scheduled call by that id on this profile."""


class LinkTooLong(Refusal):
    """A call link is a URL a family member pasted in, not a document."""


async def _on_this_profile(session: AsyncSession, context: KeyContext, person_id: uuid.UUID) -> None:
    if not await holds_the_profile(session, profile_id=context.profile_id, person_id=person_id):
        raise NotOnThisProfile(f"person {person_id} holds no key on this profile")


async def call_draft_for(
    session: AsyncSession,
    *,
    context: KeyContext,
    with_person_id: uuid.UUID,
    scheduled_at: datetime,
    call_link: str | None,
) -> CallDraft:
    """What a person is shown before scheduling a call: with whom, when, and the link if
    there is one — recomputed and checked here (a chief or the owner, a family member on
    this profile, a link short enough to be a link) so a yes cannot be minted for a call
    that could never be scheduled."""
    a_chief(context)
    await _on_this_profile(session, context, with_person_id)
    if call_link is not None and len(call_link) > 300:
        raise LinkTooLong("a call link is at most 300 characters")
    return CallDraft(with_person_id=with_person_id, scheduled_at=scheduled_at, call_link=call_link)


@audited(Action.WRITE, Scope.FAMILY, CALLS_TARGET)
async def schedule_call(
    session: AsyncSession,
    *,
    context: KeyContext,
    with_person_id: uuid.UUID,
    scheduled_at: datetime,
    confirmation_id: uuid.UUID,
    call_link: str | None = None,
    label: str | None = None,
) -> ScheduledCall:
    """Put a call with a family member on the calendar, on the setter's own yes — the owner's
    or his chief's, the same footing that arranges the roster and the tasks."""
    draft = await call_draft_for(
        session, context=context, with_person_id=with_person_id, scheduled_at=scheduled_at,
        call_link=call_link,
    )
    await consume_confirmation(session, context, confirmation_id, draft)
    return await audited_write(
        session,
        ScheduledCall,
        context,
        Scope.FAMILY,
        with_person_id=with_person_id,
        scheduled_at=scheduled_at,
        call_link=call_link,
        label=short_label(label) if label else None,
        added_by_person_id=context.person_id,
        added_at=utcnow(),
    )


async def upcoming_calls(session: AsyncSession, *, context: KeyContext) -> list[ScheduledCall]:
    """Every call still ahead of now, soonest first, ties on the same moment broken by id —
    the calls not yet cancelled, from this moment on his wall."""
    now = utcnow()
    found = await audited_read(
        session,
        ScheduledCall,
        context,
        Scope.FAMILY,
        where=(ScheduledCall.cancelled_at.is_(None), ScheduledCall.scheduled_at >= now),
    )
    return sorted(found, key=lambda call: (as_utc(call.scheduled_at), str(call.id)))


async def _require_call(
    session: AsyncSession, *, context: KeyContext, call_id: uuid.UUID
) -> ScheduledCall:
    found = await audited_read(
        session, ScheduledCall, context, Scope.FAMILY, where=(ScheduledCall.id == call_id,)
    )
    if not found:
        raise NoSuchCall(f"no scheduled call {call_id} on this profile")
    return found[0]


@audited(Action.WRITE, Scope.FAMILY, CALLS_TARGET)
async def cancel_call(
    session: AsyncSession, *, context: KeyContext, call_id: uuid.UUID
) -> ScheduledCall:
    """Take a call off the calendar. The owner's or his chief's, like scheduling it."""
    a_chief(context)
    call = await _require_call(session, context=context, call_id=call_id)
    if call.cancelled_at is None:
        call.cancelled_at = utcnow()
        await session.flush()
    await record(
        session,
        context=context,
        action=Action.WRITE,
        scope=Scope.FAMILY,
        target=CALLS_TARGET,
        target_id=call.id,
        rows=1,
    )
    return call


__all__ = [
    "CALLS_TARGET",
    "LinkTooLong",
    "NoSuchCall",
    "NotOnThisProfile",
    "call_draft_for",
    "cancel_call",
    "schedule_call",
    "upcoming_calls",
]
