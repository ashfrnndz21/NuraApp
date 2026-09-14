"""The spine over HTTP: a doctor in his directory, and a visit he has arranged.

    POST /profiles/{id}/providers        a doctor in the profile's directory
    GET  /profiles/{id}/providers
    POST /profiles/{id}/appointments     write a visit down, with the yes for it
    GET  /profiles/{id}/appointments     the visits still to come

These are the visit loop's routes (E05, #105), in its shape exactly — paths, bodies, the yes
minted at `POST /profiles/{id}/confirmations` with subject `appointment` — added here because
the anticipation nudge and the feeling note need a visit on the spine and main had no route to
one. Whichever of the two lands second drops its copy; `tests/test_feelings_api.py` refuses
an app with a route declared twice, so the merge cannot quietly keep both.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.channels.api.deps import Context, Db
from app.db import as_utc
from app.memory.models import Appointment, AppointmentStatus, Provider, ProviderKind
from app.memory.spine import add_provider, book_appointment, list_providers, upcoming_appointments
from app.regions import Region

PHONE = r"^\+[1-9][0-9]{7,14}$"

router = APIRouter(prefix="/profiles", tags=["visits"])


class ProviderIn(BaseModel):
    """A doctor, clinic, hospital or pharmacy to add to the profile's own directory."""

    name: str = Field(min_length=1, max_length=120)
    kind: ProviderKind = ProviderKind.DOCTOR
    phone_e164: str | None = Field(default=None, pattern=PHONE)
    address: str | None = Field(default=None, max_length=300)


class ProviderOut(BaseModel):
    provider_id: uuid.UUID
    name: str
    kind: ProviderKind
    region: Region

    @classmethod
    def of(cls, provider: Provider) -> ProviderOut:
        return cls(
            provider_id=provider.id, name=provider.name, kind=provider.kind, region=provider.region
        )


class AppointmentIn(BaseModel):
    """Write down a visit a person has arranged, with the yes minted for exactly it."""

    provider_id: uuid.UUID
    scheduled_at: datetime
    purpose: str = Field(min_length=1, max_length=80)
    confirmation_id: uuid.UUID


class AppointmentOut(BaseModel):
    appointment_id: uuid.UUID
    provider_id: uuid.UUID
    scheduled_at: datetime
    status: AppointmentStatus
    purpose: str
    confirmed_by_person_id: uuid.UUID

    @classmethod
    def of(cls, appointment: Appointment) -> AppointmentOut:
        return cls(
            appointment_id=appointment.id,
            provider_id=appointment.provider_id,
            scheduled_at=as_utc(appointment.scheduled_at),
            status=appointment.status,
            purpose=appointment.purpose,
            confirmed_by_person_id=appointment.confirmed_by_person_id,
        )


@router.post("/{profile_id}/providers", status_code=status.HTTP_201_CREATED)
async def add_a_provider(body: ProviderIn, context: Context, session: Db) -> ProviderOut:
    """A doctor, clinic, hospital or pharmacy in this profile's own directory."""
    provider = await add_provider(
        session,
        context=context,
        name=body.name,
        kind=body.kind,
        region=context.region,
        phone_e164=body.phone_e164,
        address=body.address,
    )
    return ProviderOut.of(provider)


@router.get("/{profile_id}/providers")
async def providers(context: Context, session: Db) -> list[ProviderOut]:
    return [ProviderOut.of(one) for one in await list_providers(session, context=context)]


@router.post("/{profile_id}/appointments", status_code=status.HTTP_201_CREATED)
async def book(body: AppointmentIn, context: Context, session: Db) -> AppointmentOut:
    """Write down a visit a person has arranged, on the yes minted for exactly this
    provider, time and purpose. Nothing here contacts a clinic."""
    appointment = await book_appointment(
        session,
        context=context,
        provider_id=body.provider_id,
        scheduled_at=body.scheduled_at,
        purpose=body.purpose,
        confirmation_id=body.confirmation_id,
    )
    return AppointmentOut.of(appointment)


@router.get("/{profile_id}/appointments")
async def appointments(context: Context, session: Db) -> list[AppointmentOut]:
    """The visits still to come, soonest first."""
    return [AppointmentOut.of(one) for one in await upcoming_appointments(session, context=context)]
