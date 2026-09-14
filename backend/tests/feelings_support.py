"""What every E17 test needs: a new medicine, his blood pressure, a visit with Dr Tan, a
moment on the timeline, and the fixture registry. Pa and his household come from
`tests.family_support` (Pa owns; Mei chief; Kit caregiver; Siti helper) and
`tests.medicines_support` (Pa alone, in Malay)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import utcnow
from app.drafts import AppointmentDraft, FactDraft
from app.drugs.fixture import FixtureRegistry
from app.keys.confirm import confirm
from app.keys.context import KeyContext
from app.medicines.service import Reconciled
from app.memory.episodic import record_event
from app.memory.models import (
    Appointment,
    ConfidenceState,
    Event,
    EventKind,
    Fact,
    ProviderKind,
    SourceChannel,
)
from app.memory.semantic import assert_fact
from app.memory.spine import add_provider, book_appointment
from app.regions import Region
from tests.medicines_support import add, label

REGISTRY = FixtureRegistry.load()


async def new_medicine(
    session: AsyncSession,
    owner: KeyContext,
    generic: str = "amlodipine",
    strength: str = "5 mg",
    dose: str = "1 tab OD",
) -> Reconciled:
    """A medicine from a label, on his yes, the way the app's card writes one."""
    return await add(session, owner, label(generic, strength, dose))


async def blood_pressure(
    session: AsyncSession,
    owner: KeyContext,
    systolic: int,
    diastolic: int = 84,
    *,
    at: datetime | None = None,
) -> Fact:
    """A blood pressure he typed in, the way `POST /readings` writes one."""
    taken_at = at or utcnow()
    event = await record_event(
        session,
        context=owner,
        kind=EventKind.READING,
        occurred_at=taken_at,
        label="blood pressure",
        source_channel=SourceChannel.APP,
    )
    draft = FactDraft(
        subject="blood_pressure",
        attribute="reading",
        value={"systolic": systolic, "diastolic": diastolic},
        unit="mmHg",
        confidence=1.0,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
        artifact_id=None,
        event_id=event.id,
        episode_id=None,
        supersedes_id=None,
    )
    yes = await confirm(session, owner, draft)
    return await assert_fact(
        session,
        context=owner,
        subject=draft.subject,
        attribute=draft.attribute,
        value=draft.value,
        unit=draft.unit,
        confidence=draft.confidence,
        confidence_state=draft.confidence_state,
        confirmation_id=yes.id,
        event_id=event.id,
        valid_from=taken_at,
    )


async def visit_with(
    session: AsyncSession, owner: KeyContext, *, at: datetime, name: str = "Dr Tan"
) -> Appointment:
    """A visit he has arranged, on his yes: a doctor in his directory and a time."""
    provider = await add_provider(
        session, context=owner, name=name, kind=ProviderKind.DOCTOR, region=Region.SG
    )
    draft = AppointmentDraft(provider_id=provider.id, scheduled_at=at, purpose="check-up")
    yes = await confirm(session, owner, draft)
    return await book_appointment(
        session,
        context=owner,
        provider_id=provider.id,
        scheduled_at=at,
        purpose="check-up",
        confirmation_id=yes.id,
    )


async def happened(
    session: AsyncSession, owner: KeyContext, kind: EventKind, at: datetime, what: str
) -> Event:
    """A moment on his timeline: a visit, a discharge."""
    return await record_event(
        session,
        context=owner,
        kind=kind,
        occurred_at=at,
        label=what,
        source_channel=SourceChannel.APP,
    )
