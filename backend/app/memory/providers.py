"""The providers directory (E03-03): every doctor, clinic, hospital and pharmacy he has used,
with its history, and the chief's own notes about the place.

The directory rows are the spine's (`app.memory.spine.add_provider`, `Scope.VISITS`). Here is
what a provider has to show for itself: every visit with it — and every visit names one, the
table refuses a visit that does not — the papers that hang off those visits or off the
episodes they were part of (the letter, the lab slip), and the medicines whose label names
that doctor. Each part is read under its own scope and withheld by name when the key does
not reach it.

A chief's note is the second short free-text column of the graph beside the family's
messages (E12), and on the same footing: one line, at most 280 characters, the writer's own
words, kept under the family scope and read and written only by the owner and his chief
(`app.family.common.a_chief`). It is about the place — "parking at B2" — and never about him:
a note that names a medicine or a condition is refused (`NoteNamesHealth`, from
`app.safety.health_words`), because health lives in facts, with where they came from.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_read, audited_write
from app.audit.models import Action
from app.db import as_utc, utcnow
from app.drugs.registry import DrugRegistry
from app.errors import Refusal
from app.family.common import a_chief
from app.ingestion.models import ReviewCard
from app.keys.context import KeyContext
from app.keys.scopes import KeyRole, Scope
from app.medicines.models import MedicationLine
from app.memory.models import (
    NOTE_LENGTH,
    Appointment,
    AppointmentStatus,
    Artifact,
    Fact,
    Provider,
    ProviderNote,
)
from app.memory.spine import UPCOMING, NoSuchProvider
from app.memory.timeline import Gathered, gather
from app.safety.health_words import names_health

NOTE_TARGET = ProviderNote.__tablename__


class NotAPlaceNote(Refusal):
    """A note about a place is one line of one to 280 characters."""


class NoteNamesHealth(Refusal):
    """A note about a place named a medicine or a condition. Health is written down as facts,
    with where they came from; a note is about the place. The refusal says which kind of
    word it found, never the word."""

    def __init__(self, kind: str) -> None:
        super().__init__(f"a note about a place named a {kind}")
        self.kind = kind


@dataclass(frozen=True, slots=True)
class Paper:
    """One paper from a provider: hung off one of its visits, or off an episode one of its
    visits was part of, with the kind the reader took it for and the facts resting on it."""

    artifact: Artifact
    kind: str
    via: str
    """`visit` or `episode`: what the paper hangs off."""
    appointment_id: uuid.UUID | None
    episode_id: uuid.UUID | None
    facts: tuple[Fact, ...]


@dataclass(frozen=True, slots=True)
class ProviderSummary:
    provider: Provider
    visits: int
    last_visit: Appointment | None
    next_visit: Appointment | None


@dataclass(frozen=True, slots=True)
class ProviderHistory:
    provider: Provider
    visits: tuple[Appointment, ...]
    papers: tuple[Paper, ...]
    medicines: tuple[MedicationLine, ...]
    notes: tuple[ProviderNote, ...]
    withheld: tuple[Scope, ...]


def is_chief(context: KeyContext) -> bool:
    return context.is_owner or context.role is KeyRole.CHIEF


async def require_provider(
    session: AsyncSession, *, context: KeyContext, provider_id: uuid.UUID
) -> Provider:
    found = await audited_read(
        session, Provider, context, Scope.VISITS, where=(Provider.id == provider_id,)
    )
    if not found:
        raise NoSuchProvider(f"no provider {provider_id} on profile {context.profile_id}")
    return found[0]


def _summary(provider: Provider, visits: Sequence[Appointment]) -> ProviderSummary:
    now = utcnow()
    own = sorted(
        (visit for visit in visits if visit.provider_id == provider.id),
        key=lambda visit: as_utc(visit.scheduled_at),
    )
    happened = [
        v for v in own if v.status == AppointmentStatus.ATTENDED and as_utc(v.scheduled_at) <= now
    ]
    coming = [v for v in own if v.status in UPCOMING and as_utc(v.scheduled_at) >= now]
    return ProviderSummary(
        provider=provider,
        visits=len(own),
        last_visit=happened[-1] if happened else None,
        next_visit=coming[0] if coming else None,
    )


@audited(Action.READ, Scope.VISITS, Provider.__tablename__)
async def directory(session: AsyncSession, *, context: KeyContext) -> list[ProviderSummary]:
    """Every provider he has used, by name, each with how many visits and the last and next."""
    providers = await audited_read(session, Provider, context, Scope.VISITS)
    visits = await audited_read(session, Appointment, context, Scope.VISITS)
    return [_summary(p, visits) for p in sorted(providers, key=lambda p: p.name.lower())]


async def _papers(
    session: AsyncSession, context: KeyContext, found: Gathered, visits: Sequence[Appointment]
) -> list[Paper]:
    visit_ids = {visit.id for visit in visits}
    episode_ids = {visit.episode_id for visit in visits if visit.episode_id is not None}
    papers: dict[uuid.UUID, Paper] = {}
    kinds: dict[uuid.UUID, str] = {}
    if found.artifacts:
        cards = await audited_read(
            session,
            ReviewCard,
            context,
            Scope.RECORDS,
            where=(ReviewCard.artifact_id.in_(list(found.artifacts)),),
        )
        kinds = {card.artifact_id: card.document_kind.value for card in cards}
    for each in sorted(found.attachments, key=lambda a: as_utc(a.attached_at)):
        artifact = found.artifacts.get(each.artifact_id)
        if artifact is None or artifact.id in papers:
            continue
        if each.appointment_id in visit_ids or each.episode_id in episode_ids:
            papers[artifact.id] = Paper(
                artifact=artifact,
                kind=kinds.get(artifact.id, "unknown"),
                via="visit" if each.appointment_id is not None else "episode",
                appointment_id=each.appointment_id,
                episode_id=each.episode_id,
                facts=tuple(f for f in found.facts if f.artifact_id == artifact.id),
            )
    return sorted(papers.values(), key=lambda p: as_utc(p.artifact.captured_at), reverse=True)


@audited(Action.READ, Scope.VISITS, Provider.__tablename__)
async def provider_history(
    session: AsyncSession, *, context: KeyContext, provider_id: uuid.UUID
) -> ProviderHistory:
    """One provider's history: its visits newest first, the papers from them, the medicines
    on its name — and, for the owner and his chief, their notes about the place."""
    provider = await require_provider(session, context=context, provider_id=provider_id)
    found = await gather(session, context=context)
    visits = sorted(
        (visit for visit in found.appointments if visit.provider_id == provider.id),
        key=lambda visit: as_utc(visit.scheduled_at),
        reverse=True,
    )
    papers = await _papers(session, context, found, visits)
    medicines: Sequence[MedicationLine] = ()
    if context.allows(Scope.MEDICINES):
        medicines = await audited_read(
            session,
            MedicationLine,
            context,
            Scope.MEDICINES,
            where=(
                func.lower(MedicationLine.prescriber) == provider.name.strip().lower(),
                MedicationLine.superseded_at.is_(None),
            ),
        )
    else:
        found.withhold(Scope.MEDICINES)
    notes: Sequence[ProviderNote] = ()
    if context.allows(Scope.FAMILY) and is_chief(context):
        notes = await chief_notes(session, context=context, provider_id=provider.id)
    else:
        found.withhold(Scope.FAMILY)
    return ProviderHistory(
        provider=provider,
        visits=tuple(visits),
        papers=tuple(papers),
        medicines=tuple(sorted(medicines, key=lambda line: as_utc(line.started_at), reverse=True)),
        notes=tuple(notes),
        withheld=tuple(found.withheld),
    )


@audited(Action.READ, Scope.FAMILY, NOTE_TARGET)
async def chief_notes(
    session: AsyncSession, *, context: KeyContext, provider_id: uuid.UUID | None = None
) -> list[ProviderNote]:
    """The chief's notes, newest first, about one provider or all of them. The owner's and
    his chief's to read; anyone else is refused and it is written down."""
    a_chief(context)
    where = () if provider_id is None else (ProviderNote.provider_id == provider_id,)
    found = await audited_read(session, ProviderNote, context, Scope.FAMILY, where=where)
    return sorted(found, key=lambda note: (as_utc(note.written_at), str(note.id)), reverse=True)


@audited(Action.WRITE, Scope.FAMILY, NOTE_TARGET)
async def write_chief_note(
    session: AsyncSession,
    *,
    context: KeyContext,
    provider_id: uuid.UUID,
    text: str,
    registry: DrugRegistry | None = None,
) -> ProviderNote:
    """Keep the chief's one line about a place, as written, in her name.

    Refused, and written down: anyone but the owner or a chief (`NotAChief`); an empty line,
    two lines, or more than 280 characters (`NotAPlaceNote`); a line naming a medicine — by the
    licensed registry's answer, the high-risk table or his names for it — or a condition
    (`NoteNamesHealth`).
    """
    a_chief(context)
    line = text.strip()
    if not line or len(line) > NOTE_LENGTH or "\n" in line or "\r" in line:
        raise NotAPlaceNote(f"a note is one line of one to {NOTE_LENGTH} characters")
    provider = await require_provider(session, context=context, provider_id=provider_id)
    kind = names_health(line, registry)
    if kind is not None:
        raise NoteNamesHealth(kind)
    return await audited_write(
        session,
        ProviderNote,
        context,
        Scope.FAMILY,
        provider_id=provider.id,
        text=line,
        written_by_person_id=context.person_id,
        written_at=utcnow(),
    )


__all__ = [
    "NotAPlaceNote",
    "NoteNamesHealth",
    "Paper",
    "ProviderHistory",
    "ProviderSummary",
    "chief_notes",
    "directory",
    "is_chief",
    "provider_history",
    "require_provider",
    "write_chief_note",
]
