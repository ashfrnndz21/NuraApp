"""Notes on any event: a voice note or a scribble, attached to the moment it is about (E02-06).

A person picks an event — this morning's blood pressure, Tuesday's visit — and leaves a note
on it: something said, or something drawn or written by hand. The recording or the image is
stored like a photo (`app.ingestion.photos`): bytes in the region's object store under a
content-addressed key, one Artifact naming them, after the agreement to hold the record is
checked. A voice note is the writer's own words — the patient's about himself, or a
caregiver's on his event — so it is stored as `Recording.OWN_NOTE` and rests on that
agreement alone; the RECORDING consent is for consults, which capture other people (ADR 0003). A voice note is then heard by the region's transcriber (`app.ingestion.transcribe`),
and the words it heard are kept the way everything an artefact says is kept — as bytes in the
store, named by key and digest on the note's row. They are text by reference, and never a
fact: nothing here writes one, and nothing is inferred from a note. A note that was not heard
is kept all the same, and says so.

A scribble is kept as drawn: the image is the note, and nothing is read off it.

A note is private — under the notes scope, which only the patient and a chief preset to it
open, and which his "only me" closes to everyone else (E12-04) — or shared with whoever holds
the record, beside the event. `notes_for(event)` is recall: the notes on one event that the
reader's key opens, oldest first, each with its words where there are any.
`recallable_notes` is the same for every event at once, for Ask (E03-05): a note is found by
recall only when the key opens the note and reads the event it hangs off. `notes_written_since`
is what changed (E03-04): the notes others left, as rows, never their words.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_read, audited_write
from app.audit.models import Action
from app.consent.models import ConsentPurpose
from app.consent.service import require_consent
from app.db import as_utc, utcnow
from app.errors import Refusal
from app.ingestion.models import EventNote, NoteKind
from app.ingestion.objects import ObjectStore, sha256_of
from app.ingestion.photos import PHOTO_CONTENT_TYPES
from app.ingestion.transcribe import Transcriber, Transcript
from app.keys.context import KeyContext
from app.keys.repository import scoped_select
from app.keys.scopes import Scope
from app.memory.episodic import (
    held_here,
    readable_event_ids,
    require_artifact,
    require_event,
    store_artifact,
)
from app.memory.models import Artifact, ArtifactKind, Recording, SourceChannel, short_label
from app.regions import guard_region

NOTE = EventNote.__tablename__

VOICE_CONTENT_TYPES = frozenset(
    {"audio/m4a", "audio/mp4", "audio/aac", "audio/mpeg", "audio/wav", "audio/webm", "audio/ogg"}
)
"""What a voice note may be. The app records AAC in an m4a; WhatsApp sends ogg."""

MAX_VOICE_BYTES = 5 * 1024 * 1024
"""Five megabytes: a minute or two of speech with room; not a recording of a whole visit."""

MAX_SCRIBBLE_BYTES = 1024 * 1024
"""One megabyte: a small image of a few words or a drawing, not a photo of a page."""

TRANSCRIPT_CONTENT_TYPE = "text/plain; charset=utf-8"


class NotAVoiceNote(Refusal):
    """The bytes offered as a voice note were empty, or of a kind that is not sound."""


class NotAScribble(Refusal):
    """The bytes offered as a scribble were empty, or of a kind that is not an image."""


class NoteTooLarge(Refusal):
    """A note on an event is small: a minute of speech, or a small image."""


class NoSuchEventNote(Refusal):
    """No note by that id on this event that this key opens."""


def voice_key(profile_id: uuid.UUID, digest: str) -> str:
    return f"voice/{profile_id}/{digest}"


def scribble_key(profile_id: uuid.UUID, digest: str) -> str:
    return f"scribbles/{profile_id}/{digest}"


def transcript_key(profile_id: uuid.UUID, digest: str) -> str:
    return f"transcripts/{profile_id}/{digest}"


def note_scope(private: bool) -> Scope:
    """A private note is read and written under the notes scope, a shared one the record's."""
    return Scope.NOTES if private else Scope.RECORDS


def _kind_of(content_type: str) -> str:
    return content_type.strip().lower().split(";", 1)[0].strip()


def check_voice(data: bytes, content_type: str) -> str:
    kind = _kind_of(content_type)
    if kind not in VOICE_CONTENT_TYPES:
        raise NotAVoiceNote(f"{content_type} is not a voice note")
    if not data:
        raise NotAVoiceNote("the voice note was empty")
    if len(data) > MAX_VOICE_BYTES:
        raise NoteTooLarge(f"a voice note is at most {MAX_VOICE_BYTES} bytes")
    return kind


def check_scribble(data: bytes, content_type: str) -> str:
    kind = _kind_of(content_type)
    if kind not in PHOTO_CONTENT_TYPES:
        raise NotAScribble(f"{content_type} is not an image")
    if not data:
        raise NotAScribble("the scribble was empty")
    if len(data) > MAX_SCRIBBLE_BYTES:
        raise NoteTooLarge(f"a scribble is at most {MAX_SCRIBBLE_BYTES} bytes")
    return kind


@dataclass(frozen=True, slots=True)
class NoteView:
    """One note as it is read back: the row, the artefact it names, and — for a voice note
    that was heard — the words, read back from the store."""

    note: EventNote
    artifact: Artifact
    transcript: Transcript | None


async def _keep(
    session: AsyncSession,
    *,
    context: KeyContext,
    store: ObjectStore,
    kind: ArtifactKind,
    key: str,
    data: bytes,
    content_type: str,
    captured_at: datetime,
    recording: Recording | None,
) -> Artifact:
    """Bytes into the region's store and the artefact naming them, after the agreement to hold
    the record: a refusal leaves nothing behind."""
    await require_consent(
        session,
        context=context,
        purpose=ConsentPurpose.HOLD_HEALTH_RECORD,
        scope=Scope.RECORDS,
    )
    await store.put(key, data)
    return await store_artifact(
        session,
        context=context,
        kind=kind,
        storage_key=key,
        content_type=content_type,
        sha256=sha256_of(data),
        captured_at=captured_at,
        source_channel=SourceChannel.APP,
        region=store.region,
        recording=recording,
    )


async def _write_note(
    session: AsyncSession,
    *,
    context: KeyContext,
    event_id: uuid.UUID,
    artifact: Artifact,
    kind: NoteKind,
    private: bool,
    label: str | None,
    heard: Transcript | None,
    words_key: str | None,
    words_digest: str | None,
) -> EventNote:
    return await audited_write(
        session,
        EventNote,
        context,
        note_scope(private),
        event_id=event_id,
        artifact_id=artifact.id,
        kind=kind,
        private=private,
        label=label,
        transcript_key=words_key,
        transcript_sha256=words_digest,
        transcript_confidence=None if heard is None else heard.confidence,
        transcript_language=None if heard is None else heard.language,
        written_by_person_id=context.person_id,
        written_at=utcnow(),
    )


@audited(Action.WRITE, lambda call: note_scope(call["private"]), NOTE)
async def add_voice_note(
    session: AsyncSession,
    *,
    context: KeyContext,
    store: ObjectStore,
    transcriber: Transcriber,
    event_id: uuid.UUID,
    data: bytes,
    content_type: str,
    captured_at: datetime,
    private: bool,
    language: str,
    label: str | None = None,
) -> NoteView:
    """Leave a voice note on one event: the recording kept as a VOICE artefact, heard by the
    region's transcriber, and the words — if it heard any — kept in the store by reference.
    Nothing here is a fact."""
    guard_region(held_in=store.region, asked_from=context.region)
    guard_region(held_in=transcriber.region, asked_from=context.region)
    kind = check_voice(data, content_type)
    named = None if label is None else short_label(label)
    event = await require_event(session, context=context, event_id=event_id)
    artifact = await _keep(
        session,
        context=context,
        store=store,
        kind=ArtifactKind.VOICE,
        key=voice_key(context.profile_id, sha256_of(data)),
        data=data,
        content_type=kind,
        captured_at=captured_at,
        # His own words about himself, or a caregiver's own on his event: kept on the record
        # consent, like typed text; the recording consent is for consults (ADR 0003).
        recording=Recording.OWN_NOTE,
    )
    transcript = await transcriber.transcribe(data, kind, language, context.region)
    heard = transcript if transcript.heard else None
    words_key = words_digest = None
    if heard is not None:
        words = heard.text.strip().encode("utf-8")
        words_digest = sha256_of(words)
        words_key = transcript_key(context.profile_id, words_digest)
        await store.put(words_key, words)
    note = await _write_note(
        session,
        context=context,
        event_id=event.id,
        artifact=artifact,
        kind=NoteKind.VOICE,
        private=private,
        label=named,
        heard=heard,
        words_key=words_key,
        words_digest=words_digest,
    )
    return NoteView(note=note, artifact=artifact, transcript=heard)


@audited(Action.WRITE, lambda call: note_scope(call["private"]), NOTE)
async def add_scribble(
    session: AsyncSession,
    *,
    context: KeyContext,
    store: ObjectStore,
    event_id: uuid.UUID,
    data: bytes,
    content_type: str,
    captured_at: datetime,
    private: bool,
    label: str | None = None,
) -> NoteView:
    """Leave a scribble on one event: a small image, kept as drawn, with an optional label of
    one short line. Nothing is read off it."""
    guard_region(held_in=store.region, asked_from=context.region)
    kind = check_scribble(data, content_type)
    named = None if label is None else short_label(label)
    event = await require_event(session, context=context, event_id=event_id)
    artifact = await _keep(
        session,
        context=context,
        store=store,
        kind=ArtifactKind.PHOTO,
        key=scribble_key(context.profile_id, sha256_of(data)),
        data=data,
        content_type=kind,
        captured_at=captured_at,
        recording=None,
    )
    note = await _write_note(
        session,
        context=context,
        event_id=event.id,
        artifact=artifact,
        kind=NoteKind.SCRIBBLE,
        private=private,
        label=named,
        heard=None,
        words_key=None,
        words_digest=None,
    )
    return NoteView(note=note, artifact=artifact, transcript=None)


def _notes_held_here(context: KeyContext) -> ColumnElement[bool]:
    """The notes whose artefact is held in this region: part of every query returning notes."""
    return EventNote.artifact_id.in_(
        scoped_select(Artifact, context, Scope.RECORDS)
        .with_only_columns(Artifact.id)
        .where(held_here(context))
    )


async def _notes_on(
    session: AsyncSession, context: KeyContext, where: Sequence[ColumnElement[bool]]
) -> list[EventNote]:
    """The shared notes matching `where`, and the private ones when the key opens the notes.
    A key without the notes scope is not refused here: the private notes are simply not its
    to see, and asking for them would write a refusal for a reach the reader did not make."""
    held = [*where, _notes_held_here(context)]
    found: list[EventNote] = list(
        await audited_read(
            session, EventNote, context, Scope.RECORDS, where=[*held, EventNote.private.is_(False)]
        )
    )
    if context.allows(Scope.NOTES):
        found.extend(
            await audited_read(
                session,
                EventNote,
                context,
                Scope.NOTES,
                where=[*held, EventNote.private.is_(True)],
            )
        )
    return sorted(found, key=lambda note: (as_utc(note.written_at), str(note.id)))


async def _view(
    session: AsyncSession, *, context: KeyContext, store: ObjectStore, note: EventNote
) -> NoteView:
    artifact = await require_artifact(session, context=context, artifact_id=note.artifact_id)
    transcript = None
    if note.transcript_key is not None:
        words = (await store.get(note.transcript_key)).decode("utf-8")
        transcript = Transcript(
            text=words,
            confidence=note.transcript_confidence or 0.0,
            language=note.transcript_language,
        )
    return NoteView(note=note, artifact=artifact, transcript=transcript)


@audited(Action.READ, Scope.RECORDS, NOTE)
async def notes_for(
    session: AsyncSession,
    *,
    context: KeyContext,
    store: ObjectStore,
    event_id: uuid.UUID,
) -> list[NoteView]:
    """Recall: the notes on one event that this key opens, oldest first, each with its words
    where it has any. The event is read first, so a note is only ever found through it."""
    guard_region(held_in=store.region, asked_from=context.region)
    event = await require_event(session, context=context, event_id=event_id)
    notes = await _notes_on(session, context, [EventNote.event_id == event.id])
    return [await _view(session, context=context, store=store, note=note) for note in notes]


@audited(Action.READ, Scope.RECORDS, NOTE)
async def note_content(
    session: AsyncSession,
    *,
    context: KeyContext,
    store: ObjectStore,
    event_id: uuid.UUID,
    note_id: uuid.UUID,
) -> tuple[bytes, str]:
    """The recording or the image of one note, and its content type: what makes a voice note
    something a person can hear again. Only a note this key opens, on this event."""
    guard_region(held_in=store.region, asked_from=context.region)
    event = await require_event(session, context=context, event_id=event_id)
    found = await _notes_on(
        session, context, [EventNote.event_id == event.id, EventNote.id == note_id]
    )
    if not found:
        raise NoSuchEventNote(f"no note {note_id} on event {event_id} for this key")
    artifact = await require_artifact(session, context=context, artifact_id=found[0].artifact_id)
    return await store.get(artifact.storage_key), artifact.content_type


async def _on_events_it_reads(
    session: AsyncSession, context: KeyContext, notes: Sequence[EventNote]
) -> list[EventNote]:
    """The notes whose event this key reads: a note is only ever found through its event."""
    readable = await readable_event_ids(
        session, context=context, event_ids=[note.event_id for note in notes]
    )
    return [note for note in notes if note.event_id in readable]


@audited(Action.READ, Scope.RECORDS, NOTE)
async def recallable_notes(
    session: AsyncSession, *, context: KeyContext, store: ObjectStore
) -> list[NoteView]:
    """Recall over the notes (E02-06, E03-05): every note this key opens — a shared one under
    the record's scope, a private one only under the notes' — on an event it reads, oldest
    first, each with its words where it has any. What `notes_for` gives for one event, for
    every event; the words are read back from the region's store, never from a row."""
    guard_region(held_in=store.region, asked_from=context.region)
    notes = await _on_events_it_reads(session, context, await _notes_on(session, context, []))
    return [await _view(session, context=context, store=store, note=note) for note in notes]


@audited(Action.READ, Scope.RECORDS, NOTE)
async def notes_written_since(
    session: AsyncSession, *, context: KeyContext, after: datetime | None
) -> list[EventNote]:
    """What changed (E03-04): the notes someone other than the reader left after `after`
    (from the beginning when None) that this key opens, on events it reads, oldest first. The
    rows only — who, when, on which event — and never the words."""
    where: list[ColumnElement[bool]] = [EventNote.written_by_person_id != context.person_id]
    if after is not None:
        where.append(EventNote.written_at > after)
    return await _on_events_it_reads(session, context, await _notes_on(session, context, where))


__all__: Sequence[Any] = (
    "NoteView",
    "add_scribble",
    "add_voice_note",
    "note_content",
    "notes_for",
    "notes_written_since",
    "recallable_notes",
)
