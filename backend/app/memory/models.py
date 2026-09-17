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
from datetime import datetime, time
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, ImmutableRow, ProfileScoped, enum_column, frozen, monotonic, utcnow
from app.errors import Refusal
from app.keys.rows import RowScoped
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


class Artifact(ProfileScoped, RowScoped, Base):
    """A raw thing that came in, kept where it came in.

    The bytes live in the object store of the profile's region under `storage_key`; this row
    is the reference, the digest and the circumstances. Nothing here holds content.

    `written_scope` is the scope it was kept under (`RowScoped`): a paper, a photo or a voice
    under the record's, the family's WhatsApp message under the family's, the words of a fall
    under the emergency scope, a question asked of Nura under the ask scope. A key reads the
    artefacts written under the scopes it holds, whatever door it reads them through.
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
    ONBOARDING = "onboarding"
    """What a person said while his profile was being set up (E01): the settings he chose, a
    read-back line he answered. The moment a setting fact, or a dispute, rests on."""
    SUPPLY = "supply"
    """A person said there are more of a medicine at home (E04-05, "I have more at home"):
    the moment the count correction's fact rests on, under the medicines' part."""
    FOOD = "food"
    """He (or a key-holder for him) said what he ate, or that he did not have a meal at all:
    the moment a meal fact rests on (`app.lifestyle.food`, `subject="meal"`). Under the
    readings' part, the owner's deliberate call (2026-09-17): whoever can see his readings
    can see whether he has eaten."""
    SETTING = "setting"
    """He (or his chief) changed a preference about how Nura works for him, after setup
    (RE-05, "What Nura uses"): a signal switched on or off. The moment that preference fact
    rests on, the way an onboarding choice rests on ONBOARDING."""


@monotonic
class Event(ProfileScoped, RowScoped, Base):
    """Something that happened: a reading taken, a visit, a message, a dose taken.

    An event comes from somewhere: it names the artefact it was read from, or it says which
    channel it came in on and, in the label, what it was. An event is provenance for a fact,
    so one from nowhere would let a fact rest on nothing. The label is a name for the moment,
    never what was said in it; the artefact is where that is.

    `written_scope` is the part it was written under (`RowScoped`, `episodic.EVENT_SCOPES`):
    the record's, a reading taken the readings', a tablet taken the medicines', the family's
    message the family's, the moment of a fall said on WhatsApp the emergency scope.

    `seq` (#192/#218) is the order events were written in, not when they occurred —
    `occurred_at` can be backdated from a paper or a machine's own clock, so two events
    genuinely at the same clinical instant break their tie by which was recorded more
    recently, the same way every other "newest wins" read here does.
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
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)


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

    A fact sits under the scope of its subject (`scope_for_subject`): every reader of more
    than one subject narrows by it, one held scope at a time (`semantic.fact_is_under`).
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
    panel: Mapped[bool] = mapped_column(Boolean, default=False)
    """A hospital on his insurance (what a family here calls the panel hospital), marked in the
    directory. A red flag's escalation names it (E19-05)."""
    opens_at: Mapped[time | None] = mapped_column(Time, default=None)
    closes_at: Mapped[time | None] = mapped_column(Time, default=None)
    """When the doctor or clinic answers, on his wall clock, where the directory says it. Out
    of these hours a red flag does not say "call the doctor today" (`app.safety.red_flags`)."""


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


# --- what hangs off the spine and the episodes (E03) -----------------------------------------


class AttachedHow(StrEnum):
    """How an artefact came to hang off an episode or a visit: a person's own yes on the
    surface, or the yes on an ingestion card that named the episode as it was confirmed."""

    MANUAL = "manual"
    INGESTION = "ingestion"


class Attachment(ProfileScoped, Base):
    """One artefact hanging off one thing: an episode, or a visit on the spine.

    An artefact is stored once and never changed (`frozen(Artifact)`), and an event names
    its episode when it is written, so the way a paper that came in on its own joins the
    concern it belongs to — or the visit it came from — is this row: who hung it there,
    when, and on whose yes. Exactly one of `episode_id` and `appointment_id` is set; the
    table refuses a row hanging off both or neither. Hanging is a moment: the row is never
    edited, and the same artefact may hang off a visit and off the episode that visit was
    part of.
    """

    __tablename__ = "attachment"
    __table_args__ = (
        _row_of_profile("attachment"),
        _tied_to_profile("attachment", "artifact_id", "artifact"),
        _tied_to_profile("attachment", "episode_id", "episode"),
        _tied_to_profile("attachment", "appointment_id", "appointment"),
        CheckConstraint(
            "(episode_id IS NULL) <> (appointment_id IS NULL)",
            name="ck_attachment_hangs_off_one_thing",
        ),
        UniqueConstraint(
            "profile_id",
            "artifact_id",
            "episode_id",
            "appointment_id",
            name="uq_attachment_once",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artifact.id"), index=True)
    episode_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("episode.id"), default=None)
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("appointment.id"), default=None
    )
    how: Mapped[AttachedHow] = mapped_column(enum_column(AttachedHow, "attached_how"))
    attached_by_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    attached_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


NOTE_LENGTH = 280
"""The most a chief's note about a clinic may hold: a line, never a letter."""


class ProviderNote(ProfileScoped, Base):
    """The chief's own note about a clinic: "parking at B2", "long waits, go early".

    The second free-text column the graph allows, beside the patient's own note
    (`app.notes.models.Note`), and on the same terms: short, the writer's own words, kept
    under a scope only the owner and his chief are preset to (`Scope.FAMILY`). It is a
    note about the *place*, never about his health: `providers.write_chief_note` refuses a
    line that names a medicine or a condition, so nothing clinical ever sits in prose.
    """

    __tablename__ = "provider_note"
    __table_args__ = (
        _row_of_profile("provider_note"),
        _tied_to_profile("provider_note", "provider_id", "provider"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("provider.id"), index=True)
    text: Mapped[str] = mapped_column(String(NOTE_LENGTH))
    written_by_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    written_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


@monotonic
class LastLooked(ProfileScoped, Base):
    """When one person last looked at what changed on this profile (E03-04).

    One row per look, never edited: the newest row for a person — `looked_at`, tied by `seq`
    (#192/#218) — is the moment his next "what changed" counts from. The look is the reader's
    own act, so the row names him and nothing else — nothing of what he saw is written here.
    `appointments` is the spine as he saw it, id to status, so a visit whose status has moved
    since can be told apart from one that has not; a status change leaves no timestamp of its
    own on the visit.
    """

    __tablename__ = "last_looked"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"), index=True)
    looked_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    appointments: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)


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
# Hanging is a moment, a note is a line as written, a look is when it happened.
frozen(Attachment)
frozen(ProviderNote)
frozen(LastLooked)
