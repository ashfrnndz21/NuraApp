"""What every timeline test needs: Pa's record, arranged in time.

Pa owns his profile. Dr Tan is in his directory. A check-up ten days ago happened; a visit a
week from now is booked inside the chest infection he is going through, which began four days
ago; two blood pressures, the second taken during the illness; a lab paper with two facts on
it, hung off the illness; his blood pressure tablet, on Dr Tan's name. Mei is his chief.
Everything is written through the services, with the yes each write needs, the way the app
writes it. The clock is the frozen one: Thursday 3 September 2026, four in the afternoon on
his wall.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEntry, Outcome
from app.clock import now
from app.drafts import AppointmentDraft, AttachDraft, FactDraft, StatusChange
from app.family.privacy import mark_only_me, only_me_draft
from app.keys.confirm import confirm
from app.keys.context import KeyContext, resolve_key_context
from app.keys.scopes import ALL_SCOPES, KeyRole, Scope
from app.medicines.service import Reconciled
from app.memory.attach import attach_to_episode
from app.memory.episodic import record_event, store_artifact
from app.memory.models import (
    Appointment,
    AppointmentStatus,
    Artifact,
    ArtifactKind,
    Attachment,
    ConfidenceState,
    Episode,
    EpisodeKind,
    EventKind,
    Fact,
    Provider,
    ProviderKind,
    Recording,
    SourceChannel,
)
from app.memory.semantic import assert_fact
from app.memory.spine import add_provider, book_appointment, change_appointment_status
from app.memory.working import open_episode
from app.regions import Region
from tests.medicines_support import add, label, let_in, pa

PAPER_DAY = datetime(2023, 9, 6, 16, 0, tzinfo=UTC)
"""Thursday 7 September 2023, midnight on his clock: the date on the lab paper."""

MEI_PHONE = "+6592220002"
KIT_PHONE = "+6595550003"
SITI_PHONE = "+6597770004"


async def book(
    session: AsyncSession,
    context: KeyContext,
    provider: Provider,
    at: datetime,
    purpose: str,
    *,
    steps: Iterable[AppointmentStatus] = (),
    episode_id: uuid.UUID | None = None,
) -> Appointment:
    """Write down a visit on the person's yes, then walk it along its status, a yes a step."""
    draft = AppointmentDraft(provider_id=provider.id, scheduled_at=at, purpose=purpose)
    visit = await book_appointment(
        session,
        context=context,
        provider_id=provider.id,
        scheduled_at=at,
        purpose=purpose,
        confirmation_id=(await confirm(session, context, draft)).id,
        episode_id=episode_id,
    )
    for status in steps:
        yes = await confirm(session, context, StatusChange(appointment_id=visit.id, status=status))
        visit = await change_appointment_status(
            session,
            context=context,
            appointment_id=visit.id,
            status=status,
            confirmation_id=yes.id,
        )
    return visit


async def reading(
    session: AsyncSession,
    context: KeyContext,
    top: int,
    bottom: int,
    at: datetime,
    episode_id: uuid.UUID | None = None,
) -> Fact:
    """A blood pressure he typed in, the way the readings route writes it."""
    event = await record_event(
        session,
        context=context,
        kind=EventKind.READING,
        occurred_at=at,
        label="blood pressure",
        source_channel=SourceChannel.APP,
        episode_id=episode_id,
    )
    value = {"systolic": top, "diastolic": bottom}
    draft = FactDraft(
        subject="blood_pressure",
        attribute="reading",
        value=value,
        unit="mmHg",
        confidence=1.0,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
        artifact_id=None,
        event_id=event.id,
        episode_id=episode_id,
        supersedes_id=None,
    )
    yes = await confirm(session, context, draft)
    return await assert_fact(
        session,
        context=context,
        subject="blood_pressure",
        attribute="reading",
        value=value,
        unit="mmHg",
        confidence=1.0,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
        confirmation_id=yes.id,
        event_id=event.id,
        episode_id=episode_id,
        valid_from=at,
    )


async def artefact(
    session: AsyncSession,
    context: KeyContext,
    *,
    kind: ArtifactKind = ArtifactKind.PHOTO,
    when: datetime | None = None,
) -> Artifact:
    digest = uuid.uuid4().hex + uuid.uuid4().hex
    return await store_artifact(
        session,
        context=context,
        kind=kind,
        storage_key=f"photos/{context.profile_id}/{digest}",
        content_type="image/png" if kind is ArtifactKind.PHOTO else "application/octet-stream",
        sha256=digest,
        captured_at=when or now(),
        source_channel=SourceChannel.APP,
        region=Region.SG,
        # A voice says whose voices it carries (ADR 0003): here, his own words.
        recording=Recording.OWN_NOTE if kind is ArtifactKind.VOICE else None,
    )


async def lab_paper(session: AsyncSession, context: KeyContext) -> tuple[Artifact, list[Fact]]:
    """A lab paper, photographed today, with two facts read off it, dated on the paper."""
    paper = await artefact(session, context)
    facts = [
        await assert_fact(
            session,
            context=context,
            subject="lipid_panel",
            attribute=attribute,
            value=value,
            unit="mg/dL",
            confidence=0.9,
            artifact_id=paper.id,
            valid_from=PAPER_DAY,
        )
        for attribute, value in (("total_cholesterol", 230), ("ldl", 152))
    ]
    return paper, facts


async def hang_on_episode(
    session: AsyncSession, context: KeyContext, artifact: Artifact, episode: Episode
) -> Attachment:
    draft = AttachDraft(artifact_id=artifact.id, episode_id=episode.id, appointment_id=None)
    yes = await confirm(session, context, draft)
    return await attach_to_episode(
        session,
        context=context,
        artifact_id=artifact.id,
        episode_id=episode.id,
        confirmation_id=yes.id,
    )


async def again(session: AsyncSession, context: KeyContext) -> KeyContext:
    """Resolve the same person afresh: what they may see right now."""
    return await resolve_key_context(
        session, region=Region.SG, person_id=context.person_id, profile_id=context.profile_id
    )


async def keep_only_me(session: AsyncSession, owner: KeyContext, scope: Scope) -> None:
    """The owner marks one part of his record "only me", on his own yes (E12-04)."""
    yes = await confirm(session, owner, only_me_draft(scope, only_me=True))
    await mark_only_me(session, context=owner, scope=scope, confirmation_id=yes.id)


async def trail(session: AsyncSession, context: KeyContext) -> list[AuditEntry]:
    found = await session.scalars(
        select(AuditEntry).where(AuditEntry.profile_id == context.profile_id)
    )
    return list(found)


async def refusals(session: AsyncSession, context: KeyContext) -> list[AuditEntry]:
    return [e for e in await trail(session, context) if e.outcome is Outcome.REFUSED]


@dataclass
class Record:
    owner: KeyContext
    mei: KeyContext
    tan: Provider
    episode: Episode
    checkup: Appointment
    next_visit: Appointment
    readings: list[Fact]
    paper: Artifact
    lab: list[Fact]
    medicine: Reconciled


async def record(session: AsyncSession, *, language: str = "en") -> Record:
    owner = await pa(session, language=language)
    tan = await add_provider(
        session, context=owner, name="Dr Tan", kind=ProviderKind.DOCTOR, region=Region.SG
    )
    start = now()
    episode = await open_episode(
        session,
        context=owner,
        kind=EpisodeKind.ILLNESS,
        label="chest infection",
        opened_at=start - timedelta(days=4),
    )
    checkup = await book(
        session,
        owner,
        tan,
        start - timedelta(days=10),
        "check-up",
        steps=(AppointmentStatus.CONFIRMED, AppointmentStatus.ATTENDED),
    )
    next_visit = await book(
        session, owner, tan, start + timedelta(days=7), "see Dr Tan again", episode_id=episode.id
    )
    readings = [
        await reading(session, owner, 146, 90, start - timedelta(days=6)),
        await reading(session, owner, 138, 84, start - timedelta(days=1), episode.id),
    ]
    paper, lab = await lab_paper(session, owner)
    medicine = await add(session, owner, label("amlodipine", "5 mg"))
    mei = await let_in(
        session, owner, phone=MEI_PHONE, name="Mei", role=KeyRole.CHIEF, scopes=set(ALL_SCOPES)
    )
    await hang_on_episode(session, owner, paper, episode)
    return Record(
        owner=owner,
        mei=mei,
        tan=tan,
        episode=episode,
        checkup=checkup,
        next_visit=next_visit,
        readings=readings,
        paper=paper,
        lab=lab,
        medicine=medicine,
    )
