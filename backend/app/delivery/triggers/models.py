"""The delivery tables: the settings a profile's deliveries follow, one row per attempt to
reach a person, and the ladder an unanswered action climbs.

`Delivery` is the log the acceptance lines rest on: every trigger that fired writes its rule
on every row it makes ("every trigger logs its rule"), and a row says who it was for, by
which channel, from which template, and what became of it — sent, held by the cap, held by
the quiet hours, nobody's key covering it, no channel that could carry it, skipped on a quiet
day. The words sent are not here: a WhatsApp row names the message, which names the template
and the State it was composed from. `Ladder` is one unanswered action: whom it will ask, in
order and after how long, how far it has climbed, and who answered. The settings are a
history: a change is a new row, and the newest one is in force.
"""

from __future__ import annotations

import uuid
from datetime import datetime, time
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, ProfileScoped, enum_column, frozen, utcnow
from app.keys.scopes import Scope
from app.memory.models import _row_of_profile, _tied_to_profile


class TriggerKind(StrEnum):
    RULE = "rule"
    """A date or an hour reached: the reorder date, breakfast, the end of a dose's window."""
    PATTERN = "pattern"
    """Arithmetic on events over a window: a count, never a diagnosis."""
    EVENT = "event"
    """Something new: a red flag, a paper waiting, a visit tomorrow, a family message due."""


class TriggerType(StrEnum):
    MORNING = "morning"
    DOSE = "dose"
    REORDER = "reorder"
    DOSES_UNTAPPED = "doses_untapped"
    FLAG = "flag"
    VISIT_TOMORROW = "visit_tomorrow"
    PAPERS = "papers"
    FAMILY_MESSAGE = "family_message"
    CHECK_IN = "check_in"
    """The feeling check-in at his check-in time, once a day (E11-01, E19-03)."""
    FAMILY_NOTICE = "family_notice"
    """The evening count to each chief of what was written down this week (E11-01, E19-03)."""
    FIRST_WEEK_PROMPT = "first_week_prompt"
    """The first week's prompt due today (E01-04), carried as one line of the morning card."""
    NUDGE = "nudge"
    """The day's smart nudge (E17-03), handed over by its planner; the `nudge` row is the queue."""
    VOICE_NOTE_UNHEARD = "voice_note_unheard"
    """His voice note that Nura could not hear (#158): a red word in it could not be read, so
    his chief is told to listen. An alert, like a red flag: never capped, never quiet."""

    BRIEF = "visit_brief"
    """The pre-visit brief, rendered three days before a visit and its card sent (E05-01)."""


class Category(StrEnum):
    """How a type is routed and held: an alert is never capped and never quiet."""

    ALERT = "alert"
    REMINDER = "reminder"
    CONTEXT = "context"


class DeliveryChannel(StrEnum):
    APP_PUSH = "app_push"
    WHATSAPP = "whatsapp"
    CAREGIVER = "caregiver"
    """The patient could not be reached, so the one standing in for him was."""
    IN_APP = "in_app"
    """The notice on their family page: an open red flag and its one button, "I'm on it".
    Written for every alert, whatever else carried it, so a person no phone can reach still
    has it where they look (#162)."""


PHONE: frozenset[DeliveryChannel] = frozenset(
    {DeliveryChannel.APP_PUSH, DeliveryChannel.WHATSAPP, DeliveryChannel.CAREGIVER}
)
"""The channels that reach a person's phone. The in-app notice waits until they look."""


class DeliveryOutcome(StrEnum):
    SENT = "sent"
    CAPPED = "capped"
    QUIET = "quiet"
    NO_CHANNEL = "no_channel"
    NO_SCOPE = "no_scope"
    SKIPPED = "skipped"


class Subject(StrEnum):
    DOSE = "dose"
    FLAG = "flag"
    UNHEARD_NOTE = "unheard_note"
    """A voice note Nura could not hear (#173). It climbs the way a flag's ladder climbs —
    the chief, then whoever is on duty, then everyone else whose key holds the emergency
    card — and one person saying they have it stops it for the rest."""


ANSWERED_BY_A_PERSON: frozenset[Subject] = frozenset({Subject.FLAG, Subject.UNHEARD_NOTE})
"""The ladders someone stops by saying they have it, rather than by doing the thing (a dose's
ladder stops on the Taken tap). Both are alerts, and both lapse after `FLAG_WINDOW`."""


class DeliverySettings(ProfileScoped, Base):
    """What a profile changed of the delivery defaults (`rules.RULES`): whether a quiet day's
    morning card is skipped, the quiet hours, and per type the channel list and the cap. The
    times of his day are E10-01's routine, not kept here. A change is a new row."""

    __tablename__ = "delivery_settings"
    __table_args__ = (_row_of_profile("delivery_settings"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    skip_quiet_days: Mapped[bool] = mapped_column(Boolean, default=False)
    quiet_from: Mapped[time | None] = mapped_column(Time, default=None)
    quiet_until: Mapped[time | None] = mapped_column(Time, default=None)
    channels: Mapped[dict[str, list[str]]] = mapped_column(JSON, default=dict)
    caps: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    set_by_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    set_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


LADDER_STEP = "delivery_ladder_step"
"""`session.info` key: the id of the one ladder `ladder` is moving right now."""


def _ladder_is_moving(session: Any, row: Any) -> bool:
    return session is not None and session.info.get(LADDER_STEP) == row.id


class Ladder(ProfileScoped, Base):
    """One unanswered action, climbing.

    `rungs` is the calling order, fixed when the ladder starts: `{"rung", "person_id",
    "standing", "after_minutes"}` — person ids only, no names. `started_at` is the moment the
    action went unanswered (the end of the dose's window, the moment the flag was raised);
    each rung is due `after_minutes` after it. `next_rung` is how far it has climbed. It
    closes when someone answers (a Taken tap for a dose, an acknowledgement for a flag) or
    when its day is over; the rung, the answer and the close change only through `ladder`.
    """

    __tablename__ = "delivery_ladder"
    __table_args__ = (
        _row_of_profile("delivery_ladder"),
        UniqueConstraint("profile_id", "dedupe_key", name="uq_delivery_ladder_dedupe"),
        _tied_to_profile("delivery_ladder", "line_id", "medication_line"),
        _tied_to_profile("delivery_ladder", "flag_id", "red_flag"),
        _tied_to_profile("delivery_ladder", "note_id", "event_note"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    subject: Mapped[Subject] = mapped_column(enum_column(Subject, "ladder_subject"))
    scope: Mapped[Scope] = mapped_column(enum_column(Scope, "scope"))
    dedupe_key: Mapped[str] = mapped_column(String(160))
    day: Mapped[str] = mapped_column(String(10), index=True)
    line_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("medication_line.id"), default=None
    )
    anchor: Mapped[str | None] = mapped_column(String(16), default=None)
    flag_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("red_flag.id"), default=None)
    note_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("event_note.id"), default=None)
    """The note an unheard-note ladder is about, when there is one to listen to (#173): what
    decides, for each person it asks, whether she is told to listen or to call him. None
    where the audio never arrived, and on every other ladder."""
    note_from_person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("person.id"), default=None
    )
    """Who sent that voice note (#173). The notice never says the patient sent it when he did
    not: a note from the helper names her and says to call her. None on every other ladder."""
    rungs: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    started_at: Mapped[datetime] = mapped_column()
    next_rung: Mapped[int] = mapped_column(Integer, default=0)
    acknowledged_at: Mapped[datetime | None] = mapped_column(default=None)
    acknowledged_by_person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("person.id"), default=None
    )
    closed_at: Mapped[datetime | None] = mapped_column(default=None)
    closed_because: Mapped[str | None] = mapped_column(String(32), default=None)

    @property
    def is_open(self) -> bool:
        return self.closed_at is None


class Delivery(ProfileScoped, Base):
    """One attempt to reach one person, and what became of it.

    `rule` is the rule that fired, by name; `why` the ids it fired on. `for_person_id` is set
    when a stand-in received what was meant for someone else (the caregiver channel). `via`
    is the channel (the column is `channel`; the attribute is `via` so it does not collide
    with the audit door's own keyword). `passed_over` is the channels tried first and why
    they could not carry it. `due_at` is the moment the engine was evaluating; `day` his
    local date then, which is what the caps count.
    """

    __tablename__ = "delivery"
    __table_args__ = (
        _row_of_profile("delivery"),
        _tied_to_profile("delivery", "ladder_id", "delivery_ladder"),
        _tied_to_profile("delivery", "message_id", "whatsapp_message"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    trigger_kind: Mapped[TriggerKind] = mapped_column(enum_column(TriggerKind, "trigger_kind"))
    trigger_type: Mapped[TriggerType] = mapped_column(enum_column(TriggerType, "trigger_type"))
    category: Mapped[Category] = mapped_column(enum_column(Category, "delivery_category"))
    scope: Mapped[Scope] = mapped_column(enum_column(Scope, "scope"))
    rule: Mapped[str] = mapped_column(String(64))
    dedupe_key: Mapped[str] = mapped_column(String(160), index=True)
    why: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    to_person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("person.id"), default=None, index=True
    )
    for_person_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("person.id"), default=None)
    standing: Mapped[str | None] = mapped_column(String(16), default=None)
    rung: Mapped[int | None] = mapped_column(Integer, default=None)
    ladder_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("delivery_ladder.id"), default=None
    )
    via: Mapped[DeliveryChannel | None] = mapped_column(
        "channel", enum_column(DeliveryChannel, "delivery_channel"), default=None
    )
    template_name: Mapped[str | None] = mapped_column(String(32), default=None)
    outcome: Mapped[DeliveryOutcome] = mapped_column(
        enum_column(DeliveryOutcome, "delivery_outcome")
    )
    reason: Mapped[str | None] = mapped_column(String(64), default=None)
    passed_over: Mapped[list[str]] = mapped_column(JSON, default=list)
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("whatsapp_message.id"), default=None
    )
    day: Mapped[str] = mapped_column(String(10), index=True)
    due_at: Mapped[datetime] = mapped_column()
    recorded_at: Mapped[datetime] = mapped_column(default=utcnow)


frozen(DeliverySettings)
frozen(Delivery)
frozen(
    Ladder,
    except_for=frozenset(
        {"next_rung", "acknowledged_at", "acknowledged_by_person_id", "closed_at", "closed_because"}
    ),
    only_when=_ladder_is_moving,
)


class PushSubscription(ProfileScoped, Base):
    """One browser a person asked to get reminders on, for this profile (Web Push, ADR 0001):
    the push service's endpoint and the browser's two keys, from one login session. Revoked
    when he stops reminders on it; `gone_at` when the push service said the endpoint no longer
    exists (404, 410). A push goes only to one whose login session still stands, so a phone
    signed out gets nothing. Nothing else about the row changes."""

    __tablename__ = "push_subscription"
    __table_args__ = (_row_of_profile("push_subscription"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"), index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("session.id"))
    endpoint: Mapped[str] = mapped_column(String(1024))
    p256dh: Mapped[str] = mapped_column(String(128))
    auth: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(default=None)
    gone_at: Mapped[datetime | None] = mapped_column(default=None)


frozen(PushSubscription, except_for=frozenset({"revoked_at", "gone_at"}))
