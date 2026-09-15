"""The review card: the one thing a person edits.

A card is made from one photo's extraction and names that photo. Each of its fields is a
proposed statement — subject, attribute, value, unit — with the extractor's confidence and,
below the threshold, a mark that it needs the person's eye. A person decides every field:
confirmed as proposed, corrected to what the paper says, or rejected. On his yes the card
closes and each kept field names the Fact it became; a rejected one names nothing.

Facts are never edited (`app.memory.models`), so this is where editing happens instead, and
it happens once: a field takes its decision, a card takes its close, and neither takes a
second — `frozen`, and only while `review.confirm_review_card` is the one making the change.
Every row is the profile's and is tied to its photo on the same profile, the way provenance
is tied in memory.

A field Nura could not read (E02-02) carries no value — JSON null, never a guess — and is
never confirmed as read: someone types it, and the field names who did
(`corrected_by_person_id`), which may be a daughter typing before the patient says yes.

`EventNote` is a voice note or a scribble attached to one event (E02-06): the recording or
the image is an artefact, the words heard in a voice note are kept by reference in the
object store, and neither is ever a fact. A private note is read under the notes scope, a
shared one under the record's.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, ProfileScoped, enum_column, frozen, utcnow
from app.ingestion.extract import DocumentKind
from app.memory.models import LABEL_LENGTH, _row_of_profile, _tied_to_profile

CONFIDENCE_THRESHOLD = 0.8
"""Below this a field is shown dotted and asked, never assumed (docs/medications-module.md §9)."""


class FieldState(StrEnum):
    """Where a field stands. PROPOSED until the person decides; then one of the other three."""

    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    CORRECTED = "corrected"
    REJECTED = "rejected"


DECISIONS = frozenset({FieldState.CONFIRMED, FieldState.CORRECTED, FieldState.REJECTED})
"""What a person may say about a field. PROPOSED is where it starts, not something he says."""

class DocumentSource(StrEnum):
    """Where an imported PDF came from, in the person's word (E02-03)."""

    PORTAL = "portal"
    EMAIL = "email"
    SHARE = "share"


REVIEW_IN_PROGRESS = "review_card_confirm"
"""`session.info` key: the id of the one card `review.confirm_review_card` is closing right
now. The only time a card or its fields may change."""


def _review_is_in_progress(session: Any, row: Any) -> bool:
    card_id = getattr(row, "card_id", None) or row.id
    return session is not None and session.info.get(REVIEW_IN_PROGRESS) == card_id


class ReviewCard(ProfileScoped, Base):
    """One photo, read into fields, waiting for — or closed by — a person's yes.

    `high_risk_class` is not something the extractor proposed and not the person's to
    reject: it is looked up in `app.safety.high_risk` from the drug the card names, and
    shown so that the person knows the dose he is about to confirm is one the label rule
    guards. `document_date` is the date on the paper, and becomes `valid_from` on the facts.
    `asked_as` is the kind the page was offered as — by the person, or by the route (a
    machine's screen) — beside `document_kind`, what it was read as; where the two disagree
    in a way that matters the card says so. `source` is where an imported PDF came from.
    """

    __tablename__ = "review_card"
    __table_args__ = (
        _row_of_profile("review_card"),
        _tied_to_profile("review_card", "artifact_id", "artifact"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artifact.id"), index=True)
    document_kind: Mapped[DocumentKind] = mapped_column(enum_column(DocumentKind, "document_kind"))
    document_date: Mapped[date | None] = mapped_column(default=None)
    high_risk_class: Mapped[str | None] = mapped_column(String(32), default=None)
    asked_as: Mapped[DocumentKind | None] = mapped_column(
        enum_column(DocumentKind, "document_kind"), default=None
    )
    source: Mapped[DocumentSource | None] = mapped_column(
        enum_column(DocumentSource, "document_source"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(default=None)
    confirmed_by_person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("person.id"), default=None
    )

    @property
    def is_open(self) -> bool:
        return self.confirmed_at is None


class ReviewField(ProfileScoped, Base):
    """One proposed statement on a card, and what the person said about it.

    `value` is what the extractor proposed and is never overwritten: a correction goes in
    `corrected_value`, so the card shows both what was read and what the person said. The
    value is JSON like a fact's, and short (`extract.VALUE_LENGTH`): a name for a thing on
    the page, never the page. It is JSON null for a field Nura could not read.
    `corrected_by_person_id` is who typed or corrected the value kept: the person who typed
    it in before the card was confirmed, or the confirmer who corrected it in his yes.
    """

    __tablename__ = "review_field"
    __table_args__ = (
        _row_of_profile("review_field"),
        _tied_to_profile("review_field", "card_id", "review_card"),
        _tied_to_profile("review_field", "fact_id", "fact"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    card_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("review_card.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    subject: Mapped[str] = mapped_column(String(64))
    attribute: Mapped[str] = mapped_column(String(64))
    value: Mapped[Any] = mapped_column(JSON)
    unit: Mapped[str | None] = mapped_column(String(32), default=None)
    confidence: Mapped[float] = mapped_column(Float)
    span: Mapped[dict[str, float | int] | None] = mapped_column(
        JSON(none_as_null=True), default=None
    )
    state: Mapped[FieldState] = mapped_column(
        enum_column(FieldState, "review_field_state"), default=FieldState.PROPOSED
    )
    corrected_value: Mapped[Any | None] = mapped_column(JSON(none_as_null=True), default=None)
    corrected_by_person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("person.id"), default=None
    )
    fact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fact.id"), default=None)
    decided_at: Mapped[datetime | None] = mapped_column(default=None)

    @property
    def unreadable(self) -> bool:
        """Nura saw the field and could not read it: no value was proposed (E02-02)."""
        return self.value is None

    @property
    def typed(self) -> bool:
        """Someone typed a value in before the card was confirmed."""
        return self.corrected_value is not None and self.state is FieldState.PROPOSED

    @property
    def page(self) -> int | None:
        """The page of a document of several it was read on, counting from 1."""
        found = (self.span or {}).get("page")
        return None if found is None else int(found)

    @property
    def needs_confirm(self) -> bool:
        """Shown dotted: the extractor was not sure enough for this to pass on a glance, or
        could not read it at all."""
        return self.unreadable or self.confidence < CONFIDENCE_THRESHOLD

    @property
    def decided_value(self) -> Any:
        """What the person kept: his correction where he made one, the proposal otherwise."""
        return self.corrected_value if self.state is FieldState.CORRECTED else self.value


# A card takes one change, its close; a field takes one, its decision. Both only while the
# review service is making them.
frozen(
    ReviewCard,
    except_for=frozenset({"confirmed_at", "confirmed_by_person_id"}),
    only_when=_review_is_in_progress,
)
frozen(
    ReviewField,
    except_for=frozenset(
        {"state", "corrected_value", "corrected_by_person_id", "fact_id", "decided_at"}
    ),
    only_when=_review_is_in_progress,
)


class NoteKind(StrEnum):
    """What a note on an event is: something said, or something drawn or written by hand."""

    VOICE = "voice"
    SCRIBBLE = "scribble"


class EventNote(ProfileScoped, Base):
    """A voice note or a scribble attached to one event (E02-06).

    The recording or the image is the artefact the row names; the row holds no content.
    For a voice note, the words the transcriber heard are bytes in the region's object store
    under `transcript_key` — text by reference, like everything an artefact says — with how
    sure it was and in which language. They are never a fact: nothing is inferred from a
    note. `label` is an optional name for it, one short line. `private` puts the note under
    the notes scope, which only the patient and a chief preset to it open; a shared note is
    under the record's, with the event it is attached to. Written once, never edited.
    """

    __tablename__ = "event_note"
    __table_args__ = (
        _row_of_profile("event_note"),
        _tied_to_profile("event_note", "event_id", "event"),
        _tied_to_profile("event_note", "artifact_id", "artifact"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("event.id"), index=True)
    artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artifact.id"))
    kind: Mapped[NoteKind] = mapped_column(enum_column(NoteKind, "event_note_kind"))
    private: Mapped[bool] = mapped_column(Boolean, default=False)
    label: Mapped[str | None] = mapped_column(String(LABEL_LENGTH), default=None)
    transcript_key: Mapped[str | None] = mapped_column(String(512), default=None)
    transcript_sha256: Mapped[str | None] = mapped_column(String(64), default=None)
    transcript_confidence: Mapped[float | None] = mapped_column(Float, default=None)
    transcript_language: Mapped[str | None] = mapped_column(String(16), default=None)
    written_by_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    written_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


frozen(EventNote)


# --- a consult recording (E02-05, E05-04) ------------------------------------------------------


class Speaker(StrEnum):
    """Who a stretch of a consult recording is, as the separator heard it. Never a name: the
    doctor is the visit's provider, the patient is the profile, the family is whoever came.
    `unknown` is honest — the notice the phone spoke, or a voice the separator could not
    place."""

    PATIENT = "patient"
    DOCTOR = "doctor"
    FAMILY = "family"
    UNKNOWN = "unknown"


class ConsultRecording(ProfileScoped, Base):
    """One recording of one visit, as kept: the VOICE artefact (`Recording.CONSULT`), the
    transcript the region's transcriber heard in it (a TRANSCRIPT artefact, when it heard
    anything), and the RECORDING consent it rested on when the bytes landed.

    The row holds no words. `duration_s` is how long the phone says it listened; the notice
    was spoken in `notice_language`, to the doctor by name (`doctor_named`), and the doctor's
    answer is the first seconds of the artefact — nothing is trimmed from its start, ever.
    Written once, never edited (docs/trust/recording-consent.md §1)."""

    __tablename__ = "consult_recording"
    __table_args__ = (
        _row_of_profile("consult_recording"),
        _tied_to_profile("consult_recording", "appointment_id", "appointment"),
        _tied_to_profile("consult_recording", "artifact_id", "artifact"),
        _tied_to_profile("consult_recording", "transcript_artifact_id", "artifact"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    appointment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("appointment.id"), index=True)
    artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artifact.id"), index=True)
    transcript_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("artifact.id"), default=None
    )
    consent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("consent.id"))
    duration_s: Mapped[float] = mapped_column(Float)
    started_at: Mapped[datetime] = mapped_column(index=True)
    notice_language: Mapped[str] = mapped_column(String(16))
    doctor_named: Mapped[bool] = mapped_column(Boolean)
    heard_confidence: Mapped[float | None] = mapped_column(Float, default=None)
    recorded_by_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    stored_at: Mapped[datetime] = mapped_column(default=utcnow)


class ConsultSegment(ProfileScoped, Base):
    """One stretch of a consult: who spoke, from when to when in the recording, and where in
    the transcript those words are (`char_start`, `char_end`). The words themselves are only
    in the transcript artefact; a segment is a pointer into it and a time in the audio, so a
    line of the summary can play exactly what was said (E03-05)."""

    __tablename__ = "consult_segment"
    __table_args__ = (
        _row_of_profile("consult_segment"),
        _tied_to_profile("consult_segment", "recording_id", "consult_recording"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    recording_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("consult_recording.id"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    speaker: Mapped[Speaker] = mapped_column(enum_column(Speaker, "consult_speaker"))
    start_s: Mapped[float] = mapped_column(Float)
    end_s: Mapped[float] = mapped_column(Float)
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)


frozen(ConsultRecording)
frozen(ConsultSegment)


class ConsultUpload(ProfileScoped, Base):
    """A consult recording on its way in, in chunks (#129, `app.ingestion.chunks`).

    Opened as the microphone opens, on the RECORDING consent in force then (`consent_id`), by
    the person holding the phone (`started_by_person_id`), in the recorder's own container.
    The chunks are bytes in the region's object store, never a column; the row counts them
    (`chunks`, `received_bytes`), so the phone knows where to start again after a dropped
    connection. `doctor_said_yes_at` is the doctor's answer; nothing is kept as a recording
    before it. The row ends one of two ways: put together into a `consult_recording`
    (`finished_at`, `recording_id`), or thrown away with every chunk (`discarded_at`,
    `discarded_because`: no, left, no_answer, unfinished, no_consent). No words, no audio."""

    __tablename__ = "consult_upload"
    __table_args__ = (
        _row_of_profile("consult_upload"),
        _tied_to_profile("consult_upload", "appointment_id", "appointment"),
        _tied_to_profile("consult_upload", "recording_id", "consult_recording"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    appointment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("appointment.id"), index=True)
    consent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("consent.id"))
    started_by_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    content_type: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column()
    opened_at: Mapped[datetime] = mapped_column(default=utcnow)
    chunks: Mapped[int] = mapped_column(Integer, default=0)
    received_bytes: Mapped[int] = mapped_column(Integer, default=0)
    doctor_said_yes_at: Mapped[datetime | None] = mapped_column(default=None)
    discarded_at: Mapped[datetime | None] = mapped_column(default=None)
    discarded_because: Mapped[str | None] = mapped_column(String(16), default=None)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)
    recording_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("consult_recording.id"), default=None
    )


frozen(
    ConsultUpload,
    except_for=frozenset(
        {
            "chunks",
            "received_bytes",
            "doctor_said_yes_at",
            "discarded_at",
            "discarded_because",
            "finished_at",
            "recording_id",
        }
    ),
)
