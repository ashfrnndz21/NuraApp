"""The spine: providers, and the appointments with them that everything else hangs off.

The last check-up, the last visit, the next visit. `book_appointment` writes down a visit a
person has arranged; it does not arrange one — nothing here contacts a clinic, and nothing
is booked on anyone's behalf without a person's explicit confirm at the surface.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_read, audited_write
from app.db import as_utc, utcnow
from app.errors import Refusal
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


class NoSuchProvider(Refusal):
    """No provider by that id in this profile's directory."""


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


async def list_providers(
    session: AsyncSession, *, context: KeyContext, now: datetime | None = None
) -> Sequence[Provider]:
    """Every provider this profile has used."""
    found = await audited_read(session, Provider, context, Scope.VISITS, now=now)
    return sorted(found, key=lambda provider: provider.name)


async def book_appointment(
    session: AsyncSession,
    *,
    context: KeyContext,
    provider_id: uuid.UUID,
    scheduled_at: datetime,
    purpose: str,
    status: AppointmentStatus = AppointmentStatus.PLANNED,
    episode_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> Appointment:
    """Write down an appointment a person has arranged with a provider on this profile."""
    named = short_label(purpose)
    found = await audited_read(
        session, Provider, context, Scope.VISITS, where=(Provider.id == provider_id,), now=now
    )
    if not found:
        raise NoSuchProvider(f"no provider {provider_id} on profile {context.profile_id}")
    if episode_id is not None:
        await require_open_episode(session, context=context, episode_id=episode_id, now=now)
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
        booked_at=now or utcnow(),
    )


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
