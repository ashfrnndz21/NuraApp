"""The spine: providers, and the appointments with them that everything else hangs off.

The last check-up, the last visit, the next visit. `book_appointment` writes down a visit a
person has arranged; it does not arrange one — nothing here contacts a clinic. Nothing is
booked on anyone's behalf without a person's explicit confirm: the surface owes that confirm
and passes who gave it, and the row carries that person. Once written, the one thing an
appointment changes is its status, through `change_appointment_status`, under audit.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_read, audited_write
from app.audit.models import Action
from app.audit.trail import record
from app.db import as_utc, utcnow
from app.errors import Refusal
from app.keys.confirm import ConfirmSubject, consume_confirmation
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.memory.models import (
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
    now: datetime | None = None,
) -> Provider:
    """Add a doctor, clinic, hospital or pharmacy to this profile's directory."""
    if not name.strip():
        raise NoSuchProvider("a provider needs a name")
    return await audited_write(
        session,
        Provider,
        context,
        Scope.VISITS,
        now=now,
        name=name.strip(),
        kind=kind,
        region=region,
        phone_e164=phone_e164,
        address=address,
        added_at=now or utcnow(),
    )


@audited(Action.READ, Scope.VISITS, Provider.__tablename__)
async def list_providers(
    session: AsyncSession, *, context: KeyContext, now: datetime | None = None
) -> Sequence[Provider]:
    """Every provider this profile has used."""
    found = await audited_read(session, Provider, context, Scope.VISITS, now=now)
    return sorted(found, key=lambda provider: provider.name)


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
    now: datetime | None = None,
) -> Appointment:
    """Write down an appointment a person has arranged with a provider on this profile.

    `confirmation_id` is the yes the surface wrote down (`app.keys.confirm.confirm`, for an
    APPOINTMENT) when the person confirmed — a tap, a spoken word. Nothing here can supply
    it and there is no default; it is used once, after every other check, and the row
    records the person who gave it.
    """
    named = short_label(purpose)
    found = await audited_read(
        session, Provider, context, Scope.VISITS, where=(Provider.id == provider_id,), now=now
    )
    if not found:
        raise NoSuchProvider(f"no provider {provider_id} on profile {context.profile_id}")
    if episode_id is not None:
        await require_open_episode(session, context=context, episode_id=episode_id, now=now)
    yes = await consume_confirmation(
        session, context, confirmation_id, subject=ConfirmSubject.APPOINTMENT, now=now
    )
    return await audited_write(
        session,
        Appointment,
        context,
        Scope.VISITS,
        now=now,
        provider_id=provider_id,
        scheduled_at=scheduled_at,
        status=status,
        purpose=named,
        episode_id=episode_id,
        confirmed_by_person_id=yes.person_id,
        booked_at=now or utcnow(),
    )


@audited(Action.WRITE, Scope.VISITS, Appointment.__tablename__)
async def change_appointment_status(
    session: AsyncSession,
    *,
    context: KeyContext,
    appointment_id: uuid.UUID,
    status: AppointmentStatus,
    confirmation_id: uuid.UUID,
    now: datetime | None = None,
) -> Appointment:
    """Move a visit one step along `STATUS_GOES_TO`, on a person's confirm.

    Cancelling a booked visit changes a booking, and confirming one is a person's word too,
    so every step uses a yes written down for this visit (`confirm`, APPOINTMENT_STATUS with
    the visit's id) and names who gave it in `status_changed_by_person_id`; the person who
    confirmed the booking stays where they were.
    """
    found = await audited_read(
        session,
        Appointment,
        context,
        Scope.VISITS,
        where=(Appointment.id == appointment_id,),
        now=now,
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
        subject=ConfirmSubject.APPOINTMENT_STATUS,
        subject_id=appointment.id,
        now=now,
    )
    appointment.status = status
    appointment.status_changed_by_person_id = yes.person_id
    await session.flush()
    await record(
        session,
        context=context,
        action=Action.WRITE,
        scope=Scope.VISITS,
        target=Appointment.__tablename__,
        target_id=appointment.id,
        rows=1,
        now=now,
    )
    return appointment


@audited(Action.READ, Scope.VISITS, Appointment.__tablename__)
async def upcoming_appointments(
    session: AsyncSession,
    *,
    context: KeyContext,
    now: datetime | None = None,
    limit: int = 50,
) -> Sequence[Appointment]:
    """The visits still to come, soonest first."""
    moment = now or utcnow()
    found = await audited_read(
        session,
        Appointment,
        context,
        Scope.VISITS,
        where=(Appointment.scheduled_at >= moment, Appointment.status.in_(UPCOMING)),
        now=now,
    )
    return sorted(found, key=lambda visit: as_utc(visit.scheduled_at))[:limit]
