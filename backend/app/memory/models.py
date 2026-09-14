"""The tables of the memory stores.

Three disciplines run through every table here. Every one carries `ProfileScoped`, so no row
exists without the profile it belongs to. The episodic and semantic rows are immutable: what
came in is what came in, and a fact that turns out to be wrong is superseded, never edited.
And no free-text column is wide enough to carry what an artefact said: a label names a thing,
the artefact in the object store is the thing.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, CheckConstraint, Float, ForeignKey, String, event, inspect
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, ProfileScoped, enum_column, utcnow
from app.errors import Refusal
from app.regions import Region

LABEL_LENGTH = 80
"""The most a label may hold: a name for a thing, on one line, never the thing itself."""


class NotALabel(Refusal):
    """A label names a thing in a few words. This was empty, or long enough to be the thing."""


class ImmutableRow(Refusal):
    """What came in is what came in. A wrong fact is superseded, never edited."""


def short_label(text: str) -> str:
    """Trim a label, and refuse anything that could be carrying content instead of a name."""
    label = text.strip()
    if not label or len(label) > LABEL_LENGTH or "\n" in label or "\r" in label:
        raise NotALabel(f"a label is one line of at most {LABEL_LENGTH} characters")
    return label


def _frozen(model: type[Any], *, except_for: frozenset[str] = frozenset()) -> None:
    """Refuse any update to a row of this table beyond the columns named."""

    @event.listens_for(model, "before_update")
    def _refuse(mapper: Any, connection: Any, target: Any) -> None:
        changed = {
            attribute.key
            for attribute in inspect(target).attrs
            if attribute.history.has_changes()
        }
        if changed - except_for:
            raise ImmutableRow(f"{model.__tablename__} rows are not edited")


# --- episodic ------------------------------------------------------------------------------


class ArtifactKind(StrEnum):
    PHOTO = "photo"
    PDF = "pdf"
    VOICE = "voice"
    MESSAGE = "message"
    READING = "reading"
    SCREENSHOT = "screenshot"


class SourceChannel(StrEnum):
    """Where an artefact came in from."""

    APP = "app"
    WHATSAPP = "whatsapp"
    CONNECTOR = "connector"
    DEVICE = "device"
    CLINIC = "clinic"


class Artifact(ProfileScoped, Base):
    """A raw thing that came in, kept where it came in.

    The bytes live in the object store of the profile's region under `storage_key`; this row
    is the reference, the digest and the circumstances. Nothing here holds content.
    """

    __tablename__ = "artifact"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kind: Mapped[ArtifactKind] = mapped_column(enum_column(ArtifactKind, "artifact_kind"))
    storage_key: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str] = mapped_column(String(128))
    sha256: Mapped[str] = mapped_column(String(64))
    captured_at: Mapped[datetime] = mapped_column(index=True)
    source_channel: Mapped[SourceChannel] = mapped_column(
        enum_column(SourceChannel, "source_channel")
    )
    # The region the bytes are stored in. It is the profile's, and the service checks it.
    region: Mapped[Region] = mapped_column(enum_column(Region, "region"))
    stored_at: Mapped[datetime] = mapped_column(default=utcnow)


class EventKind(StrEnum):
    READING = "reading"
    VISIT = "visit"
    MESSAGE = "message"
    DOSE_TAKEN = "dose_taken"
    SYMPTOM = "symptom"
    DISCHARGE = "discharge"


class Event(ProfileScoped, Base):
    """Something that happened: a reading taken, a visit, a message, a dose taken.

    An event that came from an artefact names it. The label is a name for the moment, never
    what was said in it; the artefact is where that is.
    """

    __tablename__ = "event"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kind: Mapped[EventKind] = mapped_column(enum_column(EventKind, "event_kind"))
    occurred_at: Mapped[datetime] = mapped_column(index=True)
    label: Mapped[str | None] = mapped_column(String(LABEL_LENGTH), default=None)
    artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("artifact.id"), default=None
    )
    episode_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("episode.id"), default=None)
    recorded_at: Mapped[datetime] = mapped_column(default=utcnow)


# --- semantic ------------------------------------------------------------------------------


class ConfidenceState(StrEnum):
    """How sure, in words. `confidence` is how sure in a number; both travel with the fact."""

    EXTRACTED = "extracted"
    CONFIRMED_BY_PERSON = "confirmed_by_person"
    DISPUTED = "disputed"


class Fact(ProfileScoped, Base):
    """A statement about the profile, with where it came from and how sure we are.

    `subject` and `attribute` are short codes ("blood_pressure", "systolic"); `value` is
    JSON with `unit` beside it where one applies. A fact names the artefact or the event it
    was read from, and the table refuses one that names neither. It holds for the window
    `valid_from` to `valid_to`, and once superseded it stays, marked with when.
    """

    __tablename__ = "fact"
    __table_args__ = (
        CheckConstraint(
            "artifact_id IS NOT NULL OR event_id IS NOT NULL", name="ck_fact_has_provenance"
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_fact_confidence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    subject: Mapped[str] = mapped_column(String(64), index=True)
    attribute: Mapped[str] = mapped_column(String(64))
    value: Mapped[Any] = mapped_column(JSON)
    unit: Mapped[str | None] = mapped_column(String(32), default=None)
    confidence: Mapped[float] = mapped_column(Float)
    confidence_state: Mapped[ConfidenceState] = mapped_column(
        enum_column(ConfidenceState, "confidence_state")
    )
    artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("artifact.id"), default=None
    )
    event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("event.id"), default=None)
    episode_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("episode.id"), default=None)
    valid_from: Mapped[datetime] = mapped_column()
    valid_to: Mapped[datetime | None] = mapped_column(default=None)
    asserted_at: Mapped[datetime] = mapped_column(default=utcnow)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fact.id"), default=None)
    superseded_at: Mapped[datetime | None] = mapped_column(default=None)


# --- working -------------------------------------------------------------------------------


class EpisodeKind(StrEnum):
    """The kinds of thing that can be going on. One of each may be open at a time."""

    ILLNESS = "illness"
    ADMISSION = "admission"
    RECOVERY = "recovery"
    TRAVEL = "travel"
    FASTING = "fasting"
    OTHER = "other"


class Episode(ProfileScoped, Base):
    """The current thing going on: "chest infection, started 3 September".

    Events, facts and appointments name the episode they belong to. It is the one row in
    memory that changes after it is written, and only to close.
    """

    __tablename__ = "episode"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kind: Mapped[EpisodeKind] = mapped_column(enum_column(EpisodeKind, "episode_kind"))
    label: Mapped[str] = mapped_column(String(LABEL_LENGTH))
    opened_at: Mapped[datetime] = mapped_column(index=True)
    closed_at: Mapped[datetime | None] = mapped_column(default=None)


# --- the spine -----------------------------------------------------------------------------


class ProviderKind(StrEnum):
    DOCTOR = "doctor"
    CLINIC = "clinic"
    HOSPITAL = "hospital"
    PHARMACY = "pharmacy"
    LAB = "lab"
    OTHER = "other"


class Provider(ProfileScoped, Base):
    """A doctor, clinic, hospital or pharmacy this profile has used.

    The directory is the profile's own: two profiles seeing the same doctor hold two rows,
    so that nothing about one graph can be learned from another. `region` is where the
    provider is, which may be across the causeway; the row itself lives with the profile.
    """

    __tablename__ = "provider"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[ProviderKind] = mapped_column(enum_column(ProviderKind, "provider_kind"))
    phone_e164: Mapped[str | None] = mapped_column(String(20), default=None)
    address: Mapped[str | None] = mapped_column(String(300), default=None)
    region: Mapped[Region] = mapped_column(enum_column(Region, "region"))
    added_at: Mapped[datetime] = mapped_column(default=utcnow)


class AppointmentStatus(StrEnum):
    PLANNED = "planned"
    CONFIRMED = "confirmed"
    ATTENDED = "attended"
    NOT_ATTENDED = "not_attended"
    CANCELLED = "cancelled"


class Appointment(ProfileScoped, Base):
    """One visit on the timeline: with whom, when, why, and which episode it belongs to.

    Appointments are the spine: the last check-up, the last visit, the next visit. The visit
    loop (E05) hangs its brief, its questions and its summary off this row.
    """

    __tablename__ = "appointment"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("provider.id"), index=True)
    scheduled_at: Mapped[datetime] = mapped_column(index=True)
    status: Mapped[AppointmentStatus] = mapped_column(
        enum_column(AppointmentStatus, "appointment_status")
    )
    purpose: Mapped[str] = mapped_column(String(LABEL_LENGTH))
    episode_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("episode.id"), default=None)
    booked_at: Mapped[datetime] = mapped_column(default=utcnow)


_frozen(Artifact)
_frozen(Event)
# Supersession is the one change a fact takes: the moment it stopped being current.
_frozen(Fact, except_for=frozenset({"superseded_at"}))
