"""The tables of the memory stores.

Three disciplines run through every table here. Every one carries `ProfileScoped`, so no row
exists without the profile it belongs to, and every reference from one row to another carries
the profile too — `(profile_id, artifact_id)` points at `artifact(profile_id, id)` — so the
table itself refuses a fact that cites another profile's artefact, whatever the service did.
The rows are immutable, or take one change each: what came in is what came in, a fact that
turns out to be wrong is superseded, an episode closes, an appointment changes status. And no
free-text column is wide enough to carry what an artefact said: a label names a thing, the
artefact in the object store is the thing.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, ImmutableRow, ProfileScoped, enum_column, frozen, utcnow
from app.errors import Refusal
from app.regions import Region

LABEL_LENGTH = 80
"""The most a label may hold: a name for a thing, on one line, never the thing itself."""


class NotALabel(Refusal):
    """A label names a thing in a few words. This was empty, or long enough to be the thing."""


def short_label(text: str) -> str:
    """Trim a label, and refuse anything that could be carrying content instead of a name."""
    label = text.strip()
    if not label or len(label) > LABEL_LENGTH or "\n" in label or "\r" in label:
        raise NotALabel(f"a label is one line of at most {LABEL_LENGTH} characters")
    return label


def _row_of_profile(table: str) -> UniqueConstraint:
    """What lets another table point at `(profile_id, id)` here: the pair is unique."""
    return UniqueConstraint("profile_id", "id", name=f"uq_{table}_profile_id_id")


def _tied_to_profile(table: str, column: str, referred: str) -> ForeignKeyConstraint:
    """A reference that carries the profile with it, so it can only land on the same profile.

    The single-column key on the column is the one 0003 shipped and is left standing; this
    is the one that matters. A NULL in `column` leaves the row untied, as a NULL does.
    """
    return ForeignKeyConstraint(
        ["profile_id", column],
        [f"{referred}.profile_id", f"{referred}.id"],
        name=f"fk_{table}_{column.removesuffix('_id')}_profile",
    )


# --- episodic ------------------------------------------------------------------------------


class ArtifactKind(StrEnum):
    PHOTO = "photo"
    PDF = "pdf"
    VOICE = "voice"
    MESSAGE = "message"
    READING = "reading"
    SCREENSHOT = "screenshot"
    TRANSCRIPT = "transcript"
    """The text of a visit as recorded or typed, kept in the object store like any other
    artefact; the post-visit summary (E05-05) is read from it and cites it."""


class Recording(StrEnum):
    """Whose voice a VOICE artefact carries, which decides the consent it rests on (ADR 0003).

    Every writer of a voice says which one it is (`app.memory.episodic.store_artifact`); there
    is no default, so no caller can leave the decision out.
    """

    CONSULT = "consult"
    """A recording that captures people other than the account holder: a visit with the
    doctor (E02-05, E05's consult transcripts). It rests on the RECORDING consent — "When you
    see the doctor, Nura listens" — under the visits scope, as well as on holding the record."""
    OWN_NOTE = "own_note"
    """A person's own words about the patient, said instead of typed: his voice note on an
    event, a not-feeling-well message, a symptom said aloud, or a caregiver's note on his
    event, which is hers. Kept on the consent to hold the record, like typed text, under the
    writer's key."""


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
    __table_args__ = (_row_of_profile("artifact"),)

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
    ENGAGEMENT = "engagement"
    """What a person did with a card on his feed (E21): seen, heard, tapped, not for me,
    shared. The moment a preference fact can rest on."""


class Event(ProfileScoped, Base):
    """Something that happened: a reading taken, a visit, a message, a dose taken.

    An event comes from somewhere: it names the artefact it was read from, or it says which
    channel it came in on and, in the label, what it was. An event is provenance for a fact,
    so one from nowhere would let a fact rest on nothing. The label is a name for the moment,
    never what was said in it; the artefact is where that is.
    """

    __tablename__ = "event"
    __table_args__ = (
        _row_of_profile("event"),
        _tied_to_profile("event", "artifact_id", "artifact"),
        _tied_to_profile("event", "episode_id", "episode"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kind: Mapped[EventKind] = mapped_column(enum_column(EventKind, "event_kind"))
    occurred_at: Mapped[datetime] = mapped_column(index=True)
    source_channel: Mapped[SourceChannel] = mapped_column(
        enum_column(SourceChannel, "source_channel")
    )
    label: Mapped[str | None] = mapped_column(String(LABEL_LENGTH), default=None)
    artifact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("artifact.id"), default=None)
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

    `confidence_state` is not a label the caller picks: CONFIRMED_BY_PERSON and DISPUTED
    name the person who said so in `confirmed_by_person_id`, and the service refuses either
    without one. An EXTRACTED fact is the machine's and names nobody. A DISPUTED fact is an
    open dispute against the fact it `supersedes`: it closes nothing and is never current.

    A `medication.dose` fact here is storage. The label-photo rule for a high-risk drug
    (docs/medications-module.md) is a hook, `semantic.before_fact_write`, that the medicines
    module (E04) registers; until it does, this table accepts a dose whose provenance is a
    WHATSAPP event.
    """

    __tablename__ = "fact"
    __table_args__ = (
        CheckConstraint(
            "artifact_id IS NOT NULL OR event_id IS NOT NULL", name="ck_fact_has_provenance"
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_fact_confidence"),
        _row_of_profile("fact"),
        _tied_to_profile("fact", "artifact_id", "artifact"),
        _tied_to_profile("fact", "event_id", "event"),
        _tied_to_profile("fact", "episode_id", "episode"),
        _tied_to_profile("fact", "supersedes_id", "fact"),
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
    artifact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("artifact.id"), default=None)
    event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("event.id"), default=None)
    episode_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("episode.id"), default=None)
    valid_from: Mapped[datetime] = mapped_column()
    valid_to: Mapped[datetime | None] = mapped_column(default=None)
    asserted_at: Mapped[datetime] = mapped_column(default=utcnow)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fact.id"), default=None)
    superseded_at: Mapped[datetime | None] = mapped_column(default=None)
    # Who confirmed or disputed it. Required by the service for those two states, and
    # refused for an extraction; a nullable column because an extraction names nobody.
    confirmed_by_person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("person.id"), default=None
    )


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

    Events, facts and appointments name the episode they belong to. The one change it takes
    after it is written is to close.
    """

    __tablename__ = "episode"
    __table_args__ = (_row_of_profile("episode"),)

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
    __table_args__ = (_row_of_profile("provider"),)

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

    Nothing is booked without a person's explicit confirm. The surface owes that confirm; the
    row carries who gave it, in `confirmed_by_person_id`. The one change the row takes after
    it is written is its status, along one path (`spine.STATUS_GOES_TO`), each step confirmed
    by a person named in `status_changed_by_person_id`.
    """

    __tablename__ = "appointment"
    __table_args__ = (
        _row_of_profile("appointment"),
        _tied_to_profile("appointment", "provider_id", "provider"),
        _tied_to_profile("appointment", "episode_id", "episode"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("provider.id"), index=True)
    scheduled_at: Mapped[datetime] = mapped_column(index=True)
    status: Mapped[AppointmentStatus] = mapped_column(
        enum_column(AppointmentStatus, "appointment_status")
    )
    purpose: Mapped[str] = mapped_column(String(LABEL_LENGTH))
    episode_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("episode.id"), default=None)
    confirmed_by_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    # Who confirmed the last change of status. The booking confirmer above is never
    # overwritten; a cancellation names its own person here.
    status_changed_by_person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("person.id"), default=None
    )
    booked_at: Mapped[datetime] = mapped_column(default=utcnow)


__all__ = ["ImmutableRow"]

STATUS_CHANGE_IN_PROGRESS = "appointment_status_change"
"""`session.info` key: the id of the one appointment `spine.change_appointment_status` is
changing right now. The only time an appointment's status may change."""


def _status_change_is_in_progress(session: Any, row: Any) -> bool:
    return session is not None and session.info.get(STATUS_CHANGE_IN_PROGRESS) == row.id


frozen(Artifact)
frozen(Event)
# Supersession is the one change a fact takes: the moment it stopped being current.
frozen(Fact, except_for=frozenset({"superseded_at"}))
# Closing is the one change an episode takes, through `working.close_episode`. Status is the
# one an appointment takes, and only while `spine.change_appointment_status` is making it —
# a bare `visit.status = CANCELLED` flushed from anywhere else is refused. Providers are a
# directory and are corrected in place.
frozen(Episode, except_for=frozenset({"closed_at"}))
frozen(
    Appointment,
    except_for=frozenset({"status", "status_changed_by_person_id"}),
    only_when=_status_change_is_in_progress,
)
