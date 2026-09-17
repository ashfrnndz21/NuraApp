"""The family tables (E12): the thread, the roster, the tasks, the scheduled pushes and the
documents behind a basis. The "only me" row lives with the keys (`app.keys.privacy`),
because it is enforced there.

Every table carries `ProfileScoped` and is reached through the audit doors under the family
scope — the thread, the roster and the tasks are the family talking to each other about his
care, which is the family list's business — except that a task is also read and closed by
the person it names, under the footing every key holds (`app.family.roster`).

Free text: the thread message is the one free-text column here, on purpose and short. It is
the family talking to each other, not a fact about him; nothing reads a fact out of it, and
nothing ever will. Everything else is a label (`short_label`), a code or a reference.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, ProfileScoped, as_utc, enum_column, frozen, monotonic, utcnow
from app.keys.scopes import KeyRole
from app.memory.models import LABEL_LENGTH, _row_of_profile, _tied_to_profile
from app.state.models import RenderedFromState

MESSAGE_LENGTH = 280
"""The most a family message may hold: a line to each other, never a document."""


class CardKind(StrEnum):
    """The kinds of health card the thread can carry beside a message. Each is rendered at
    read time from the State it names, never stored as words."""

    READING = "reading"
    TAKEN = "taken"
    VISIT = "visit"
    TASK = "task"


@monotonic
class ThreadMessage(ProfileScoped, Base):
    """One entry in the family thread: a short message from one person, or a card.

    A message row has `text` and no card; a card row names the State snapshot it was
    rendered from and which kind of card it is, and has no text. The table refuses a row
    that is both or neither. A message is the family's own words to each other: it is not
    read for facts, and it is kept under the family scope, not the record's. The first
    unread family message today — `posted_at`, tied by `seq` (#192/#218) — is what a
    presence nudge is built from (`app.delivery.nudges.engine`), which stops at the first
    match.
    """

    __tablename__ = "thread_message"
    __table_args__ = (
        _row_of_profile("thread_message"),
        _tied_to_profile("thread_message", "state_id", "state_snapshot"),
        _tied_to_profile("thread_message", "task_id", "task"),
        CheckConstraint(
            "(text IS NOT NULL AND state_id IS NULL AND card_kind IS NULL)"
            " OR (text IS NULL AND state_id IS NOT NULL AND card_kind IS NOT NULL)",
            name="ck_thread_message_text_or_card",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    author_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"), index=True)
    posted_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    # The one free-text column of the family tables: what one person said to the others.
    text: Mapped[str | None] = mapped_column(String(MESSAGE_LENGTH), default=None)
    state_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("state_snapshot.id"), default=None
    )
    card_kind: Mapped[CardKind | None] = mapped_column(
        enum_column(CardKind, "thread_card_kind"), default=None
    )
    # For a TASK card: which task. Other cards are rendered from the State alone.
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("task.id"), default=None)
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    @property
    def is_card(self) -> bool:
        return self.card_kind is not None


class ThreadPhoto(ProfileScoped, Base):
    """A photo one of the family shared in the thread (E12-02), with the message it came with.

    The photo is an artefact written under the family scope — the family's, like the words
    of the thread, never one of his papers: nothing is read off it, and a key that does not
    hold the family's part does not read it. `on_his_feed` is the poster's own yes, asked when
    the photo is shared, to its being one of his story cards (E21-05); without it the photo
    stays in the thread only. `withdrawn_at` is the poster taking the photo back: from then it
    is not shown, in the thread or on his feed, to anyone. Written once; only the taking back
    is ever set."""

    __tablename__ = "thread_photo"
    __table_args__ = (
        _row_of_profile("thread_photo"),
        _tied_to_profile("thread_photo", "message_id", "thread_message"),
        _tied_to_profile("thread_photo", "artifact_id", "artifact"),
        UniqueConstraint("message_id", name="uq_thread_photo_message"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("thread_message.id"), index=True)
    artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artifact.id"))
    author_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    on_his_feed: Mapped[bool] = mapped_column(Boolean)
    posted_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    withdrawn_at: Mapped[datetime | None] = mapped_column(default=None)


class RosterSlot(ProfileScoped, Base):
    """When one person is on duty: which weekdays or which dates, between which times of
    his day, and as what.

    Times are on the clock on the patient's wall (`app.regions.REGION_TZ`), because "Mei
    on weekday evenings" means his evenings. A slot whose `to_time` is at or before its
    `from_time` runs past midnight: Friday 22:00 to 06:00 is Friday night into Saturday
    morning. A slot with `weekdays` repeats every week; one with `starts_on` and `ends_on`
    and no weekdays covers every day between them; both together means those weekdays
    inside those dates. A slot ends when `ended_at` is set; the row stays.
    """

    __tablename__ = "roster_slot"
    __table_args__ = (_row_of_profile("roster_slot"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"), index=True)
    role: Mapped[KeyRole] = mapped_column(enum_column(KeyRole, "key_role"))
    # 0 is Monday, 6 is Sunday, as `date.weekday()` counts. None means every day in range.
    weekdays: Mapped[list[int] | None] = mapped_column(JSON, default=None)
    starts_on: Mapped[date | None] = mapped_column(default=None)
    ends_on: Mapped[date | None] = mapped_column(default=None)
    from_time: Mapped[time] = mapped_column(Time)
    to_time: Mapped[time] = mapped_column(Time)
    added_by_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    added_at: Mapped[datetime] = mapped_column(default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(default=None)

    def is_open(self, now: datetime) -> bool:
        return self.ended_at is None or as_utc(self.ended_at) > now


class Errand(StrEnum):
    """A task with a purpose Nura knows: driving him to a visit (E05-03), or ordering more of
    a medicine (E04-05). Any other task names no errand."""

    DRIVE = "drive"
    ORDER = "order"
    """More of one medicine, on his yes to "Ask the family to order." (E04-05); the task
    names the medicine line, so one open task a line a day is the most there ever is."""


TASK_DONE_IN_PROGRESS = "task_done"
"""`session.info` key: the id of the one task `roster.mark_task_done` is closing right now."""


def _task_done_is_in_progress(session: Any, row: Any) -> bool:
    return session is not None and session.info.get(TASK_DONE_IN_PROGRESS) == row.id


class Task(ProfileScoped, Base):
    """Something for one person to do for him: what (a label), who, by when; done when the
    person it names taps it, and only then.

    `what` is a label — "buy the water pill" — never instructions and never a fact. The
    one change the row takes is its close, by the doer, through the service. A task that is
    part of a visit's logistics names the visit and the errand (`Errand.DRIVE`: "drive Pa to
    Dr Tan"), so the visit's logistics card can say who is driving (E05-03).
    """

    __tablename__ = "task"
    __table_args__ = (
        _row_of_profile("task"),
        _tied_to_profile("task", "appointment_id", "appointment"),
        _tied_to_profile("task", "medication_line_id", "medication_line"),
        # One open order task a line a day (E04-05; #166 review): a partial unique index,
        # not just the check-then-act in `ask_to_order`, so two yeses at the same moment
        # cannot both write one. `ask_to_order` catches the racing insert's `IntegrityError`
        # and answers with the task this index let win, same as a second yes does today.
        #
        # A day, not forever: `opened_on` is his wall-clock day (`_his_day`) at the moment
        # the task was made, so the index reads "one open order task a line a *day*" — two
        # yeses on the same day cannot both write one, but a task still open from yesterday
        # does not block a fresh yes today (a partial index cannot test "today" itself; the
        # column is what makes the day part of the key, not a computed date at query time).
        Index(
            "uq_task_open_order_per_line_per_day",
            "profile_id",
            "medication_line_id",
            "opened_on",
            unique=True,
            sqlite_where=text("errand = 'order' AND done_at IS NULL"),
            postgresql_where=text("errand = 'order' AND done_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    what: Mapped[str] = mapped_column(String(LABEL_LENGTH))
    assigned_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"), index=True)
    due_at: Mapped[datetime | None] = mapped_column(default=None)
    created_by_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    done_at: Mapped[datetime | None] = mapped_column(default=None)
    done_by_person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("person.id"), default=None
    )
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("appointment.id"), default=None
    )
    errand: Mapped[Errand | None] = mapped_column(enum_column(Errand, "task_errand"), default=None)
    medication_line_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("medication_line.id"), default=None, index=True
    )
    """The medicine line an order task is for (`Errand.ORDER`); else none."""
    opened_on: Mapped[date | None] = mapped_column(default=None)
    """His wall-clock day (`app.medicines.reorder._his_day`) when an order task was made
    (`Errand.ORDER`); else none. What the partial unique index keys on, so a line's task
    resets every day instead of blocking forever while yesterday's is still open."""

    @property
    def is_done(self) -> bool:
        return self.done_at is not None


class PushChannel(StrEnum):
    """Where the chief would like the message to reach him. E11 decides what is possible."""

    APP = "app"
    WHATSAPP = "whatsapp"


class ScheduledPush(RenderedFromState, ProfileScoped, Base):
    """A message to the patient, composed by a chief, waiting for its moment (E12-06).

    `lines` are exactly what he will read or hear, in `language`, already through the
    plain-words verifier; `send_at` is the earliest moment and `expires_at` the last —
    between them E11 picks a State-appropriate time and delivers, and nothing here sends.
    The row names the State the chief composed it against, like every rendered thing.
    """

    __tablename__ = "scheduled_push"
    __table_args__ = (
        _row_of_profile("scheduled_push"),
        _tied_to_profile("scheduled_push", "state_id", "state_snapshot"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    composed_by_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    composed_at: Mapped[datetime] = mapped_column(default=utcnow)
    language: Mapped[str] = mapped_column(String(16))
    template_id: Mapped[str | None] = mapped_column(String(48), default=None)
    lines: Mapped[list[str]] = mapped_column(JSON)
    send_at: Mapped[datetime] = mapped_column(index=True)
    # Named `via_channel` on the row, like the confirmation's: `channel` is the audit door's
    # own keyword, and this is where the chief would like the message to reach him.
    via_channel: Mapped[PushChannel] = mapped_column(
        "channel", enum_column(PushChannel, "push_channel")
    )
    expires_at: Mapped[datetime] = mapped_column()


class DocumentTag(StrEnum):
    """What kind of paper a document is, for the family screen."""

    LPA = "lpa"
    MEDICAL_LETTER = "medical_letter"
    CONSENT_FORM = "consent_form"


class Document(ProfileScoped, Base):
    """A paper kept by reference (E12-09): which artefact, what kind, who added it.

    The bytes are in the region's object store under the artefact; this row is the tag the
    family screen shows. What the paper backs — a consent, a stewardship — is read from the
    rows that cite the artefact, never copied here.
    """

    __tablename__ = "document"
    __table_args__ = (
        _row_of_profile("document"),
        _tied_to_profile("document", "artifact_id", "artifact"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artifact.id"), index=True)
    tag: Mapped[DocumentTag] = mapped_column(enum_column(DocumentTag, "document_tag"))
    added_by_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    added_at: Mapped[datetime] = mapped_column(default=utcnow)


class ScheduledCall(ProfileScoped, Base):
    """A call on the calendar with one family member (design-direction.md, Connect's
    "Upcoming Call"): who, when, and how to join.

    `with_person_id` is a family member — someone who holds a key on this profile — never a
    provider; a call with a doctor is a visit (`app.memory.models.Appointment`), not this. Set
    up by the chief or by him, on the setter's own yes (`app.drafts.CallDraft`), the same way
    booking a visit or asking someone to drive is. `call_link` is what the family provides
    (E: in-app video calling needs a video provider Nura does not have; a family member's own
    Zoom or Google Meet link is what "Join" opens); with none, "Join" rings `with_person_id`'s
    own phone. The one change the row takes is its cancelling.
    """

    __tablename__ = "scheduled_call"
    __table_args__ = (_row_of_profile("scheduled_call"),)
    # `with_person_id`, `added_by_person_id`: plain foreign keys to `person`, like every other
    # person reference on a family row (`Document.added_by_person_id`,
    # `ScheduledPush.composed_by_person_id`) — a person is a global account, never
    # profile-scoped, so there is no `(profile_id, id)` pair on it to tie against.

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    with_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"), index=True)
    scheduled_at: Mapped[datetime] = mapped_column(index=True)
    call_link: Mapped[str | None] = mapped_column(String(300), default=None)
    label: Mapped[str | None] = mapped_column(String(LABEL_LENGTH), default=None)
    added_by_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    added_at: Mapped[datetime] = mapped_column(default=utcnow)
    cancelled_at: Mapped[datetime | None] = mapped_column(default=None)


# What was said was said; a card names the State it named; a push is what was previewed.
frozen(ThreadMessage)
# A shared photo is what was shared; the one who shared it may only take it back.
frozen(ThreadPhoto, except_for=frozenset({"withdrawn_at"}))
frozen(ScheduledPush)
frozen(Document)
# A call takes its cancelling; everything else about it is what was scheduled.
frozen(ScheduledCall, except_for=frozenset({"cancelled_at"}))
# A slot takes its ending; a task takes its close, by the doer, through the service only.
frozen(RosterSlot, except_for=frozenset({"ended_at"}))
frozen(
    Task,
    except_for=frozenset({"done_at", "done_by_person_id"}),
    only_when=_task_done_is_in_progress,
)
