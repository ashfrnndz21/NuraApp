"""The spine: providers, and the appointments with them that everything else hangs off.

The last check-up, the last visit, the next visit. `book_appointment` writes down a visit a
person has arranged; it does not arrange one — nothing here contacts a clinic. Nothing is
booked on anyone's behalf without a person's explicit confirm: the surface owes that confirm
and passes who gave it, and the row carries that person. Once written, the one thing an
appointment changes is its status, through `change_appointment_status`, under audit.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_read, audited_write
from app.audit.models import Action
from app.audit.trail import record
from app.consent.models import ConsentPurpose
from app.consent.service import require_consent
from app.db import as_utc, utcnow
from app.drafts import AppointmentDraft, StatusChange
from app.errors import Refusal
from app.keys.confirm import consume_confirmation
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.memory.models import (
    STATUS_CHANGE_IN_PROGRESS,
    Appointment,
    AppointmentStatus,
    Provider,
    ProviderKind,
    short_label,
)
from app.memory.working import require_open_episode
from app.regions import Region

UPCOMING = frozenset({AppointmentStatus.PLANNED, AppointmentStatus.CONFIRMED})

STATUS_GOES_TO: dict[AppointmentStatus, frozenset[AppointmentStatus]] = {
    AppointmentStatus.PLANNED: frozenset(
        {AppointmentStatus.CONFIRMED, AppointmentStatus.CANCELLED}
    ),
    AppointmentStatus.CONFIRMED: frozenset(
        {AppointmentStatus.CANCELLED, AppointmentStatus.ATTENDED, AppointmentStatus.NOT_ATTENDED}
    ),
    AppointmentStatus.CANCELLED: frozenset(),
    AppointmentStatus.ATTENDED: frozenset(),
    AppointmentStatus.NOT_ATTENDED: frozenset(),
}
"""The one path a visit's status takes. Cancelled, attended and not attended are the end of
it: a cancelled visit is not un-cancelled, a visit that happened did not un-happen. To see the
doctor again is a new booking, with its own confirm."""

__all__ = [
    "STATUS_GOES_TO",
    "NoSuchAppointment",
    "NoSuchProvider",
    "NotThatStatusChange",
]


class NoSuchProvider(Refusal):
    """No provider by that id in this profile's directory."""


class NoSuchAppointment(Refusal):
    """No appointment by that id on this profile."""


class NotThatStatusChange(Refusal):
    """A visit's status goes one way. This was a step it does not take (`STATUS_GOES_TO`)."""


@audited(Action.WRITE, Scope.VISITS, Provider.__tablename__)
async def add_provider(
    session: AsyncSession,
    *,
    context: KeyContext,
    name: str,
    kind: ProviderKind,
    region: Region,
    phone_e164: str | None = None,
    address: str | None = None,
) -> Provider:
    """Add a doctor, clinic, hospital or pharmacy to this profile's directory."""
    # The directory is kept on the same footing as the rest of the record (E00-02).
    await require_consent(
        session,
        context=context,
        purpose=ConsentPurpose.HOLD_HEALTH_RECORD,
        scope=Scope.VISITS,
    )
    if not name.strip():
        raise NoSuchProvider("a provider needs a name")
    return await audited_write(
        session,
        Provider,
        context,
        Scope.VISITS,
        name=name.strip(),
        kind=kind,
        region=region,
        phone_e164=phone_e164,
        address=address,
        added_at=utcnow(),
    )


@audited(Action.READ, Scope.VISITS, Provider.__tablename__)
async def list_providers(
    session: AsyncSession, *, context: KeyContext, now: datetime | None = None
) -> Sequence[Provider]:
    """Every provider this profile has used."""
    found = await audited_read(session, Provider, context, Scope.VISITS)
    return sorted(found, key=lambda provider: provider.name)


AppointmentBookedHook = Callable[[AsyncSession, KeyContext, Appointment], Awaitable[None]]

after_appointment_booked: list[AppointmentBookedHook] = []
"""What follows a visit being booked, run once it is written, in the same unit of work and
under the booker's key context — the way `semantic.after_fact_write` follows a fact. The
biography (E01) registers the hand-over of the questions a person kept before there was a
visit to ask them at. A hook that raises a `Refusal` refuses the booking; the ones here must
step aside rather than refuse."""


@audited(Action.WRITE, Scope.VISITS, Appointment.__tablename__)
async def book_appointment(
    session: AsyncSession,
    *,
    context: KeyContext,
    provider_id: uuid.UUID,
    scheduled_at: datetime,
    purpose: str,
    confirmation_id: uuid.UUID,
    status: AppointmentStatus = AppointmentStatus.PLANNED,
    episode_id: uuid.UUID | None = None,
) -> Appointment:
    """Write down an appointment a person has arranged with a provider on this profile.

    `confirmation_id` is the yes the surface wrote down (`app.keys.confirm.confirm`) for an
    `AppointmentDraft` of exactly this provider, time and purpose — a tap, a spoken word.
    Nothing here can supply it and there is no default; it is used once, after every other
    check, and the row records the person who gave it.
    """
    await require_consent(
        session,
        context=context,
        purpose=ConsentPurpose.HOLD_HEALTH_RECORD,
        scope=Scope.VISITS,
    )
    named = short_label(purpose)
    found = await audited_read(
        session, Provider, context, Scope.VISITS, where=(Provider.id == provider_id,)
    )
    if not found:
        raise NoSuchProvider(f"no provider {provider_id} on profile {context.profile_id}")
    if episode_id is not None:
        await require_open_episode(session, context=context, episode_id=episode_id)
    yes = await consume_confirmation(
        session,
        context,
        confirmation_id,
        AppointmentDraft(provider_id=provider_id, scheduled_at=scheduled_at, purpose=named),
    )
    visit = await audited_write(
        session,
        Appointment,
        context,
        Scope.VISITS,
        provider_id=provider_id,
        scheduled_at=scheduled_at,
        status=status,
        purpose=named,
        episode_id=episode_id,
        confirmed_by_person_id=yes.person_id,
        booked_at=utcnow(),
    )
    for followed in after_appointment_booked:
        await followed(session, context, visit)
    return visit


@audited(Action.WRITE, Scope.VISITS, Appointment.__tablename__)
async def change_appointment_status(
    session: AsyncSession,
    *,
    context: KeyContext,
    appointment_id: uuid.UUID,
    status: AppointmentStatus,
    confirmation_id: uuid.UUID,
) -> Appointment:
    """Move a visit one step along `STATUS_GOES_TO`, on a person's confirm.

    Cancelling a booked visit changes a booking, and confirming one is a person's word too,
    so every step uses a yes written down for exactly this `StatusChange` — this visit, to
    this status — and names who gave it in `status_changed_by_person_id`; the person who
    confirmed the booking stays where they were.
    """
    found = await audited_read(
        session,
        Appointment,
        context,
        Scope.VISITS,
        where=(Appointment.id == appointment_id,),
    )
    if not found:
        raise NoSuchAppointment(f"no appointment {appointment_id} on profile {context.profile_id}")
    appointment = found[0]
    if status not in STATUS_GOES_TO[appointment.status]:
        raise NotThatStatusChange(f"a {appointment.status} visit does not become {status}")
    yes = await consume_confirmation(
        session,
        context,
        confirmation_id,
        StatusChange(appointment_id=appointment.id, status=status),
    )
    # The one moment an appointment's status may change: `frozen` in models checks this.
    session.info[STATUS_CHANGE_IN_PROGRESS] = appointment.id
    try:
        appointment.status = status
        appointment.status_changed_by_person_id = yes.person_id
        await session.flush()
    finally:
        session.info.pop(STATUS_CHANGE_IN_PROGRESS, None)
    await record(
        session,
        context=context,
        action=Action.WRITE,
        scope=Scope.VISITS,
        target=Appointment.__tablename__,
        target_id=appointment.id,
        rows=1,
    )
    return appointment


@audited(Action.READ, Scope.VISITS, Appointment.__tablename__)
async def upcoming_appointments(
    session: AsyncSession,
    *,
    context: KeyContext,
    at: datetime | None = None,
    limit: int = 50,
) -> Sequence[Appointment]:
    """The visits still to come at `at` (default now), soonest first."""
    moment = at or utcnow()
    found = await audited_read(
        session,
        Appointment,
        context,
        Scope.VISITS,
        where=(Appointment.scheduled_at >= moment, Appointment.status.in_(UPCOMING)),
    )
    return sorted(found, key=lambda visit: as_utc(visit.scheduled_at))[:limit]
