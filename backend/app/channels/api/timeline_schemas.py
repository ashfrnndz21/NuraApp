"""The shapes the timeline routes take and give (E03).

The timeline, an episode, the providers directory, what changed and an answer from Ask, as
the app reads them. Every line meant for a person is already in his words — the anchors, what
changed, the answer — and every one says which ids it rests on, so the app can open the
paper, the visit or the fact behind it. Nothing here holds a question's words: an answer names
the MESSAGE artefact the question was kept as.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from pydantic import AwareDatetime, BaseModel, Field

from app.channels.api.schemas import FactOut, utc
from app.channels.api.voice_schemas import VoiceScriptOut
from app.ingestion.models import EventNote
from app.keys.scopes import Scope
from app.medicines.models import MedicationLine
from app.memory.changes import ChangeLine, Changes
from app.memory.episodic import WITHHELD_ARTIFACT
from app.memory.models import (
    Appointment,
    AppointmentStatus,
    Artifact,
    ArtifactKind,
    AttachedHow,
    Attachment,
    Episode,
    EpisodeKind,
    Event,
    EventKind,
    Provider,
    ProviderKind,
    ProviderNote,
    SourceChannel,
)
from app.memory.providers import Paper, ProviderHistory, ProviderSummary
from app.memory.timeline import Anchor, EpisodeView, TimelineItem, TimelinePage
from app.regions import Region
from app.search.ask import Answer, Mode
from app.search.transcripts import Search

PHONE = r"^\+[1-9][0-9]{7,14}$"


# --- what goes in --------------------------------------------------------------------------


class EpisodeIn(BaseModel):
    """Something going on: its kind and a short name for it ("chest infection")."""

    kind: EpisodeKind
    label: str = Field(min_length=1, max_length=80)


class ProviderIn(BaseModel):
    """A doctor, clinic, hospital or pharmacy for the directory. `region` is where it is,
    which may be across the causeway; the profile's own when not said."""

    name: str = Field(min_length=1, max_length=120)
    kind: ProviderKind
    region: Region | None = None
    phone_e164: str | None = Field(default=None, pattern=PHONE)
    address: str | None = Field(default=None, max_length=300)


class AppointmentIn(BaseModel):
    """A visit a person arranged: with whom, when, why, and the yes minted for exactly that
    (`POST /confirmations`, subject `appointment`). `episode_id` puts it in an open episode."""

    provider_id: uuid.UUID
    scheduled_at: AwareDatetime
    purpose: str = Field(min_length=1, max_length=80)
    confirmation_id: uuid.UUID
    episode_id: uuid.UUID | None = None


class StatusIn(BaseModel):
    """One step of a visit's status, with the yes minted for exactly it."""

    status: AppointmentStatus
    confirmation_id: uuid.UUID


class AttachIn(BaseModel):
    """Hang this artefact off the episode or the visit in the path, on this yes."""

    artifact_id: uuid.UUID
    confirmation_id: uuid.UUID


class PlaceNoteIn(BaseModel):
    """The chief's one line about a place. Its length and its words are the service's to
    refuse, on the trail, so the bound here is only a guard against a page of text."""

    text: str = Field(min_length=1, max_length=1000)


class AskIn(BaseModel):
    """A question, and whether it was said aloud or typed. Voice answers in one line."""

    question: str = Field(min_length=1, max_length=1000)
    mode: Mode = Mode.TEXT
    language: str | None = Field(default=None, min_length=2, max_length=16)


# --- what comes out --------------------------------------------------------------------------


class ProviderOut(BaseModel):
    provider_id: uuid.UUID
    name: str
    kind: ProviderKind
    region: Region
    phone_e164: str | None
    address: str | None

    @classmethod
    def of(cls, provider: Provider) -> ProviderOut:
        return cls(
            provider_id=provider.id,
            name=provider.name,
            kind=provider.kind,
            region=provider.region,
            phone_e164=provider.phone_e164,
            address=provider.address,
        )


class EpisodeOut(BaseModel):
    episode_id: uuid.UUID
    kind: EpisodeKind
    label: str
    opened_at: datetime
    closed_at: datetime | None

    @classmethod
    def of(cls, episode: Episode) -> EpisodeOut:
        return cls(
            episode_id=episode.id,
            kind=episode.kind,
            label=episode.label,
            opened_at=utc(episode.opened_at),
            closed_at=None if episode.closed_at is None else utc(episode.closed_at),
        )


class AppointmentOut(BaseModel):
    appointment_id: uuid.UUID
    provider_id: uuid.UUID
    scheduled_at: datetime
    status: AppointmentStatus
    purpose: str
    episode_id: uuid.UUID | None
    confirmed_by_person_id: uuid.UUID
    status_changed_by_person_id: uuid.UUID | None

    @classmethod
    def of(cls, visit: Appointment) -> AppointmentOut:
        return cls(
            appointment_id=visit.id,
            provider_id=visit.provider_id,
            scheduled_at=utc(visit.scheduled_at),
            status=visit.status,
            purpose=visit.purpose,
            episode_id=visit.episode_id,
            confirmed_by_person_id=visit.confirmed_by_person_id,
            status_changed_by_person_id=visit.status_changed_by_person_id,
        )


class AttachmentOut(BaseModel):
    attachment_id: uuid.UUID
    artifact_id: uuid.UUID
    episode_id: uuid.UUID | None
    appointment_id: uuid.UUID | None
    how: AttachedHow
    attached_by_person_id: uuid.UUID
    attached_at: datetime

    @classmethod
    def of(cls, row: Attachment) -> AttachmentOut:
        return cls(
            attachment_id=row.id,
            artifact_id=row.artifact_id,
            episode_id=row.episode_id,
            appointment_id=row.appointment_id,
            how=row.how,
            attached_by_person_id=row.attached_by_person_id,
            attached_at=utc(row.attached_at),
        )


class ArtifactOut(BaseModel):
    """An artefact by reference: what kind, when, how it came in. Never its content."""

    artifact_id: uuid.UUID
    kind: ArtifactKind
    content_type: str
    captured_at: datetime
    source_channel: SourceChannel

    @classmethod
    def of(cls, artifact: Artifact) -> ArtifactOut:
        return cls(
            artifact_id=artifact.id,
            kind=artifact.kind,
            content_type=artifact.content_type,
            captured_at=utc(artifact.captured_at),
            source_channel=artifact.source_channel,
        )


class EventOut(BaseModel):
    event_id: uuid.UUID
    kind: EventKind
    occurred_at: datetime
    label: str | None
    artifact_id: uuid.UUID | None
    episode_id: uuid.UUID | None
    withheld: list[str] = []
    """`artifact` when the event names an artefact the reader's key may not read: the id is
    left out, and this says so."""

    @classmethod
    def of(cls, event: Event, withheld: Sequence[str] = ()) -> EventOut:
        return cls(
            event_id=event.id,
            kind=event.kind,
            occurred_at=utc(event.occurred_at),
            label=event.label,
            artifact_id=None if WITHHELD_ARTIFACT in withheld else event.artifact_id,
            episode_id=event.episode_id,
            withheld=list(withheld),
        )


class NoteRefOut(BaseModel):
    """A voice note or a scribble on an event, by reference: which note, on which event, what
    kind, whether it is private, whether it has words. The recording and the words are read
    through the notes route (E02-06), never carried here."""

    note_id: uuid.UUID
    event_id: uuid.UUID
    kind: str
    private: bool
    has_words: bool
    written_at: datetime

    @classmethod
    def of(cls, note: EventNote) -> NoteRefOut:
        return cls(
            note_id=note.id,
            event_id=note.event_id,
            kind=note.kind.value,
            private=note.private,
            has_words=note.transcript_key is not None,
            written_at=utc(note.written_at),
        )


class ItemOut(BaseModel):
    """One entry on the timeline and what hangs off it, newest first."""

    kind: str
    id: uuid.UUID
    at: datetime
    appointment: AppointmentOut | None
    provider: ProviderOut | None
    episode: EpisodeOut | None
    visits: list[uuid.UUID]
    artifacts: list[ArtifactOut]
    events: list[EventOut]
    facts: list[FactOut]
    notes: list[NoteRefOut]

    @classmethod
    def of(cls, item: TimelineItem) -> ItemOut:
        return cls(
            kind=item.kind,
            id=item.id,
            at=utc(item.at),
            appointment=None if item.appointment is None else AppointmentOut.of(item.appointment),
            provider=None if item.provider is None else ProviderOut.of(item.provider),
            episode=None if item.episode is None else EpisodeOut.of(item.episode),
            visits=list(item.visits),
            artifacts=[ArtifactOut.of(a) for a in item.hanging.artifacts],
            events=[
                EventOut.of(e, item.hanging.withheld.get(e.id, ())) for e in item.hanging.events
            ],
            facts=[FactOut.of(f, item.hanging.withheld.get(f.id, ())) for f in item.hanging.facts],
            notes=[NoteRefOut.of(n) for n in item.hanging.notes],
        )


class AnchorOut(BaseModel):
    """One anchor of the spine: its line in his words, and the visit it names if any."""

    key: str
    line: str
    appointment_id: uuid.UUID | None
    provider_id: uuid.UUID | None
    at: datetime | None

    @classmethod
    def of(cls, anchor: Anchor) -> AnchorOut:
        visit = anchor.appointment
        return cls(
            key=anchor.key,
            line=anchor.line,
            appointment_id=None if visit is None else visit.id,
            provider_id=None if visit is None else visit.provider_id,
            at=None if visit is None else utc(visit.scheduled_at),
        )


class TimelineOut(BaseModel):
    language: str
    header: list[AnchorOut]
    items: list[ItemOut]
    next_cursor: str | None
    withheld: list[Scope]

    @classmethod
    def of(cls, page: TimelinePage) -> TimelineOut:
        return cls(
            language=page.language,
            header=[AnchorOut.of(anchor) for anchor in page.header],
            items=[ItemOut.of(item) for item in page.items],
            next_cursor=page.next_cursor,
            withheld=list(page.withheld),
        )


class EpisodeViewOut(BaseModel):
    episode: ItemOut
    visits: list[ItemOut]
    withheld: list[Scope]

    @classmethod
    def of(cls, view: EpisodeView) -> EpisodeViewOut:
        return cls(
            episode=ItemOut.of(view.item),
            visits=[ItemOut.of(visit) for visit in view.visits],
            withheld=list(view.withheld),
        )


class ProviderSummaryOut(BaseModel):
    provider: ProviderOut
    visits: int
    last_visit: AppointmentOut | None
    next_visit: AppointmentOut | None

    @classmethod
    def of(cls, summary: ProviderSummary) -> ProviderSummaryOut:
        return cls(
            provider=ProviderOut.of(summary.provider),
            visits=summary.visits,
            last_visit=None
            if summary.last_visit is None
            else AppointmentOut.of(summary.last_visit),
            next_visit=None
            if summary.next_visit is None
            else AppointmentOut.of(summary.next_visit),
        )


class PaperOut(BaseModel):
    artifact: ArtifactOut
    kind: str
    via: str
    appointment_id: uuid.UUID | None
    episode_id: uuid.UUID | None
    fact_ids: list[uuid.UUID]

    @classmethod
    def of(cls, paper: Paper) -> PaperOut:
        return cls(
            artifact=ArtifactOut.of(paper.artifact),
            kind=paper.kind,
            via=paper.via,
            appointment_id=paper.appointment_id,
            episode_id=paper.episode_id,
            fact_ids=[fact.id for fact in paper.facts],
        )


class MedicineRefOut(BaseModel):
    """A medicine on a provider's name, by reference: the line, the register's generic and
    strength as the label named them, and the fact it is the typed view of."""

    line_id: uuid.UUID
    generic: str
    strength: str
    prescriber: str | None
    fact_id: uuid.UUID
    started_at: datetime

    @classmethod
    def of(cls, line: MedicationLine) -> MedicineRefOut:
        return cls(
            line_id=line.id,
            generic=line.generic,
            strength=line.strength,
            prescriber=line.prescriber,
            fact_id=line.fact_id,
            started_at=utc(line.started_at),
        )


class PlaceNoteOut(BaseModel):
    note_id: uuid.UUID
    provider_id: uuid.UUID
    text: str
    written_by_person_id: uuid.UUID
    written_at: datetime

    @classmethod
    def of(cls, note: ProviderNote) -> PlaceNoteOut:
        return cls(
            note_id=note.id,
            provider_id=note.provider_id,
            text=note.text,
            written_by_person_id=note.written_by_person_id,
            written_at=utc(note.written_at),
        )


class ProviderHistoryOut(BaseModel):
    provider: ProviderOut
    visits: list[AppointmentOut]
    papers: list[PaperOut]
    medicines: list[MedicineRefOut]
    notes: list[PlaceNoteOut]
    withheld: list[Scope]

    @classmethod
    def of(cls, history: ProviderHistory) -> ProviderHistoryOut:
        return cls(
            provider=ProviderOut.of(history.provider),
            visits=[AppointmentOut.of(visit) for visit in history.visits],
            papers=[PaperOut.of(paper) for paper in history.papers],
            medicines=[MedicineRefOut.of(line) for line in history.medicines],
            notes=[PlaceNoteOut.of(note) for note in history.notes],
            withheld=list(history.withheld),
        )


CHANGE_TONE: dict[str, str] = {
    "flags": "act",
    "waiting": "watch",
    "medicines": "watch",
    "family": "good",
    "notes": "good",
}
"""The dot beside a line of what changed on the chief's Home (docs/design-system.md, card
grammar: Good / Watch / Act on the figure only), by the part it is in: a red flag is Act, a
changed medicine or something still waiting is Watch, the family's own notes are Good. Visits,
papers and new facts carry no tone. A presentation of the part, never a judgement of a value."""


class ChangeLineOut(BaseModel):
    section: str
    key: str
    text: str
    refs: dict[str, list[str]]
    tone: str | None = None

    @classmethod
    def of(cls, line: ChangeLine) -> ChangeLineOut:
        return cls(
            section=line.section,
            key=line.key,
            text=line.text,
            tone=CHANGE_TONE.get(line.section),
            refs={name: list(ids) for name, ids in line.refs.items() if ids},
        )


class ChangesOut(BaseModel):
    """What changed since the reader last looked, and what is still waiting."""

    language: str
    since: datetime | None
    first_look: bool
    looked_at: datetime
    lines: list[ChangeLineOut]
    waiting: list[ChangeLineOut]
    sections: dict[str, Any]
    withheld: list[Scope]

    @classmethod
    def of(cls, changes: Changes, looked_at: datetime) -> ChangesOut:
        return cls(
            language=changes.language,
            since=None if changes.since is None else utc(changes.since),
            first_look=changes.first_look,
            looked_at=utc(looked_at),
            lines=[ChangeLineOut.of(line) for line in changes.lines],
            waiting=[ChangeLineOut.of(line) for line in changes.waiting],
            sections=dict(changes.sections),
            withheld=list(changes.withheld),
        )


class CiteOut(BaseModel):
    kind: str
    id: uuid.UUID
    start_s: float | None = None
    end_s: float | None = None
    """For a cite of a consult recording: the stretch of it the line is about (E03-05)."""


class ClipOut(BaseModel):
    """What a line's "Hear what Dr Tan said" plays: the recording, from when to when."""

    artifact_id: uuid.UUID
    start_s: float
    end_s: float
    doctor: str


class TranscriptSearchIn(BaseModel):
    """A few words to find in the recordings of his confirmed visits (E02-05). Not kept."""

    words: str = Field(min_length=1, max_length=100)
    language: str | None = Field(default=None, min_length=2, max_length=16)


class FoundOut(BaseModel):
    """One place the words were said: which visit, in his words; the sentence as heard; who
    the separator heard say it; the stretch to play, and what it rests on."""

    appointment_id: uuid.UUID
    summary_id: uuid.UUID
    doctor: str
    line: str
    sentence: str
    heard_in: str | None
    speaker: str | None
    clip: ClipOut
    cites: list[CiteOut]


class TranscriptSearchOut(BaseModel):
    language: str
    found: list[FoundOut]
    honest: list[str]

    @classmethod
    def of(cls, search: Search) -> TranscriptSearchOut:
        return cls(
            language=search.language,
            found=[
                FoundOut(
                    appointment_id=one.appointment_id,
                    summary_id=one.summary_id,
                    doctor=one.doctor,
                    line=one.line,
                    sentence=one.sentence,
                    heard_in=one.heard_in,
                    speaker=one.speaker,
                    clip=ClipOut(
                        artifact_id=one.clip.artifact_id,
                        start_s=one.clip.start_s,
                        end_s=one.clip.end_s,
                        doctor=one.clip.doctor,
                    ),
                    cites=[
                        CiteOut(kind=c.kind, id=c.id, start_s=c.start_s, end_s=c.end_s)
                        for c in one.cites
                    ],
                )
                for one in search.found
            ],
            honest=list(search.honest),
        )


class AnswerLineOut(BaseModel):
    text: str
    cites: list[CiteOut]
    clip: ClipOut | None = None


class AnswerOut(BaseModel):
    """An answer: the cited lines, the honest line when the record does not answer, the
    boundary last, and the whole as he hears it (`spoken`). The question is named by the
    artefact it was kept as, never repeated."""

    question_artifact_id: uuid.UUID
    mode: Mode
    language: str
    answered: bool
    lines: list[AnswerLineOut]
    honest: list[str]
    boundary: list[str]
    spoken: list[str]
    voice_script: VoiceScriptOut
    """`spoken` as it is said (E22-03), the longer pause before the boundary."""
    withheld: list[Scope]

    @classmethod
    def of(cls, answer: Answer) -> AnswerOut:
        return cls(
            question_artifact_id=answer.question_artifact_id,
            mode=answer.mode,
            language=answer.language,
            answered=answer.answered,
            lines=[
                AnswerLineOut(
                    text=line.text,
                    cites=[
                        CiteOut(kind=c.kind, id=c.id, start_s=c.start_s, end_s=c.end_s)
                        for c in line.cites
                    ],
                    clip=None
                    if line.clip is None
                    else ClipOut(
                        artifact_id=line.clip.artifact_id,
                        start_s=line.clip.start_s,
                        end_s=line.clip.end_s,
                        doctor=line.clip.doctor,
                    ),
                )
                for line in answer.lines
            ],
            honest=list(answer.honest),
            boundary=list(answer.boundary),
            spoken=answer.spoken,
            voice_script=VoiceScriptOut.of(
                answer.spoken, answer.language, "\n".join(answer.boundary)
            ),
            withheld=list(answer.withheld),
        )
