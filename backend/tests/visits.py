"""Helpers for the visit-loop tests: a profile, a doctor, a visit, a reading, a medicine."""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.consent.models import ConsentBasis, ConsentChannel, ConsentPurpose
from app.consent.service import grant_consent
from app.drafts import AppointmentDraft
from app.drugs.registry import DrugMatch, Interaction, LabelFields, Monograph, UnknownDrug
from app.identity.service import create_own_profile, register_person
from app.keys.confirm import confirm
from app.keys.context import KeyContext, resolve_key_context
from app.medicines.service import Reconciled
from app.memory.episodic import record_event, store_artifact
from app.memory.models import (
    Appointment,
    Artifact,
    ArtifactKind,
    EventKind,
    Fact,
    Provider,
    ProviderKind,
    SourceChannel,
)
from app.memory.semantic import assert_fact
from app.memory.spine import add_provider, book_appointment
from app.regions import Region
from tests.medicines_support import REGISTRY, add, label
from tests.support import OPENING_CONSENT

VISITS = Path(__file__).resolve().parent / "fixtures" / "visits"
ROUTINE = "routine-bp-review"
RED_FLAG = "red-flag-chest-pain"

SEPT_3 = datetime(2026, 9, 3, 8, 0, tzinfo=UTC)
VISIT_AT = datetime(2026, 9, 10, 2, 0, tzinfo=UTC)
"""Thursday 10 September, 10 in the morning in Singapore."""


def transcript(label: str) -> str:
    found: dict[str, Any] = json.loads((VISITS / f"{label}.json").read_text())
    return str(found["transcript"])


async def pa(
    session: AsyncSession,
    *,
    language: str = "ms",
    phone: str = "+6591110001",
    recording: bool = True,
) -> KeyContext:
    """Pa, with his own profile and — unless a test says otherwise — his agreement to Nura
    listening at the visit, which every transcript rests on (`ConsentPurpose.RECORDING`)."""
    person = await register_person(session, region=Region.SG, display_name="Pa", phone_e164=phone)
    profile = await create_own_profile(
        session, region=Region.SG, owner=person, consent=OPENING_CONSENT, language=language
    )
    context = await resolve_key_context(
        session, region=Region.SG, person_id=person.id, profile_id=profile.id
    )
    if recording:
        await agree_to_recording(session, context, language=language)
    return context


async def agree_to_recording(session: AsyncSession, context: KeyContext, *, language: str) -> None:
    await grant_consent(
        session,
        context=context,
        purpose=ConsentPurpose.RECORDING,
        captured_via=ConsentChannel.APP,
        basis=ConsentBasis.OWNER,
        language=language if language in ("en", "ms", "zh") else "en",
    )


async def visit(
    session: AsyncSession,
    context: KeyContext,
    *,
    when: datetime = VISIT_AT,
    purpose: str = "blood pressure check",
    doctor: str = "Dr Tan",
) -> tuple[Provider, Appointment]:
    provider = await add_provider(
        session, context=context, name=doctor, kind=ProviderKind.DOCTOR, region=Region.SG
    )
    draft = AppointmentDraft(provider_id=provider.id, scheduled_at=when, purpose=purpose)
    yes = await confirm(session, context, draft)
    appointment = await book_appointment(
        session,
        context=context,
        provider_id=provider.id,
        scheduled_at=when,
        purpose=purpose,
        confirmation_id=yes.id,
    )
    return provider, appointment


async def reading(
    session: AsyncSession,
    context: KeyContext,
    *,
    systolic: int = 138,
    diastolic: int = 84,
    when: datetime = SEPT_3,
) -> Fact:
    event = await record_event(
        session,
        context=context,
        kind=EventKind.READING,
        occurred_at=when,
        label="blood pressure",
        source_channel=SourceChannel.APP,
    )
    return await assert_fact(
        session,
        context=context,
        subject="blood_pressure",
        attribute="reading",
        value={"systolic": systolic, "diastolic": diastolic},
        unit="mmHg",
        confidence=1.0,
        event_id=event.id,
        valid_from=when,
    )


async def label_photo(
    session: AsyncSession, context: KeyContext, digest: str = "a" * 64
) -> Artifact:
    return await store_artifact(
        session,
        context=context,
        kind=ArtifactKind.PHOTO,
        storage_key=f"photos/{context.profile_id}/{digest}",
        content_type="image/jpeg",
        sha256=digest,
        captured_at=SEPT_3,
        source_channel=SourceChannel.APP,
        region=Region.SG,
    )


async def medicine(
    session: AsyncSession,
    context: KeyContext,
    *,
    generic: str = "frusemide",
    strength: str = "40 mg",
    dose: str = "1 tab OM",
) -> Reconciled:
    """A medicine line from a label, the way E04 writes it: identified in the fixture
    registry, confirmed with the person's yes, a Fact and a `MedicationLine`."""
    return await add(session, context, label(generic, strength, dose, quantity=30))


class Unknown:
    """The fixture registry, told to know no monograph for some generics: a line whose
    purpose the licensed data cannot say (`GapKind.MEDICINE_NO_PURPOSE`)."""

    def __init__(self, *generics: str) -> None:
        self._unknown = frozenset(g.lower() for g in generics)

    def identify(self, fields: LabelFields) -> Sequence[DrugMatch]:
        return REGISTRY.identify(fields)

    def interactions(self, generics: Sequence[str]) -> Sequence[Interaction]:
        return REGISTRY.interactions(generics)

    def monograph(self, generic: str) -> Monograph:
        if generic.lower() in self._unknown:
            raise UnknownDrug(f"no monograph for {generic}")
        return REGISTRY.monograph(generic)


def a_week() -> timedelta:
    return timedelta(days=7)


__all__ = ["uuid"]
