"""The WhatsApp tables: the thread, the messages in it by reference, and the proposal.

A thread is one number talking to one profile: who, since when, and the two moments the
24-hour window turns on. A message row is a pointer and a classification, never the words:
what was said lives as an artefact in the region's object store, and the row names it. A
proposal is a health event the classifier heard, waiting for the poster's yes — the one row
here that carries a value, because the value is exactly what the poster is asked to confirm,
and it is written under the scope of its subject the way the fact it becomes will be.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, ProfileScoped, enum_column, frozen, monotonic, utcnow
from app.memory.models import EventKind, _row_of_profile, _tied_to_profile


class Direction(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageKind(StrEnum):
    """What a kept message was: how the classifier read it, or what the number sent."""

    DOCUMENT = "document"
    HEALTH_EVENT = "health_event"
    COORDINATION = "coordination"
    RED_FLAG = "red_flag"
    ANSWER = "answer"
    CHECK_IN_ANSWER = "check_in_answer"
    REPLY = "reply"
    TEMPLATE = "template"
    VOICE_NOTE = "voice_note"
    """A card's spoken twin, sent inside the window (E11-04)."""
    TAKEN = "taken"
    """A "Taken" or "given" reply that wrote a Taken tap (E11-01)."""


class WhatsAppThread(ProfileScoped, Base):
    """One number's private thread with one profile.

    `is_patient` marks the profile owner's own thread: his Level 0 app, where the morning
    card goes and where a feeling word is his own answer rather than a proposal. The two
    moments are what the 24-hour rule is checked against; they are the one thing here that
    moves after the row is written.
    """

    __tablename__ = "whatsapp_thread"
    __table_args__ = (
        _row_of_profile("whatsapp_thread"),
        UniqueConstraint("profile_id", "person_id", name="uq_whatsapp_thread_person"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"), index=True)
    is_patient: Mapped[bool] = mapped_column(Boolean, default=False)
    opened_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_inbound_at: Mapped[datetime | None] = mapped_column(default=None)
    last_outbound_at: Mapped[datetime | None] = mapped_column(default=None)


class WhatsAppMessage(ProfileScoped, Base):
    """One kept message, by reference: which thread, which way, what kind, and what it names.

    An inbound row names the artefact its words or its photo became; an outbound row names
    the template or the catalogue key it was rendered from and, for a template, the State
    snapshot it was composed from. Nothing here is text a person wrote.
    """

    __tablename__ = "whatsapp_message"
    __table_args__ = (
        _row_of_profile("whatsapp_message"),
        _tied_to_profile("whatsapp_message", "thread_id", "whatsapp_thread"),
        _tied_to_profile("whatsapp_message", "artifact_id", "artifact"),
        _tied_to_profile("whatsapp_message", "flag_id", "red_flag"),
        _tied_to_profile("whatsapp_message", "state_id", "state_snapshot"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    thread_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("whatsapp_thread.id"), index=True)
    direction: Mapped[Direction] = mapped_column(enum_column(Direction, "whatsapp_direction"))
    kind: Mapped[MessageKind] = mapped_column(enum_column(MessageKind, "whatsapp_message_kind"))
    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    """Who sent it, or who it went to."""
    at: Mapped[datetime] = mapped_column(index=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(80), default=None)
    artifact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("artifact.id"), default=None)
    flag_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("red_flag.id"), default=None)
    template_name: Mapped[str | None] = mapped_column(String(32), default=None)
    catalogue_key: Mapped[str | None] = mapped_column(String(48), default=None)
    state_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("state_snapshot.id"), default=None
    )
    asks_feeling: Mapped[bool] = mapped_column(Boolean, default=False)
    """Set on an outbound row when its words put the feeling question to him (#205) — the
    plain check-in, the day's check-in nudge, or anything later that carries the same words
    (`app.reasoning.feelings.strings.asks_about_feeling`, read once at `send`). Never set by
    template name: a name is a list a future asker can be written outside of, and this is
    what his "OK" is checked against for an open feeling question (`inbound._check_in_open`)."""


class WhatsAppGroup(ProfileScoped, Base):
    """The family's group on WhatsApp (E11-01): the thread of the family (E12-02), mirrored.

    One per profile, named by the provider's handle for the group. Who is in it is never
    stored: it is the people who read the family thread — the patient, and every live key that
    holds the family's part — worked out from the keys every time the group is used, and told
    to the provider then (`app.channels.whatsapp.group`). A key closed is a person out of the
    group at the next message, whichever side it comes from."""

    __tablename__ = "whatsapp_group"
    __table_args__ = (
        _row_of_profile("whatsapp_group"),
        UniqueConstraint("profile_id", name="uq_whatsapp_group_profile"),
        UniqueConstraint("provider_group_id", name="uq_whatsapp_group_provider"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider_group_id: Mapped[str] = mapped_column(String(80))
    opened_by_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    opened_at: Mapped[datetime] = mapped_column(default=utcnow)
    members_digest: Mapped[str | None] = mapped_column(String(64), default=None)
    """A digest of the numbers last told to the provider — never the numbers (#143): a sync
    that would tell it the same says nothing, and one the provider failed is tried again."""


class WhatsAppReceipt(Base):
    """One inbound message the provider delivered, by the provider's own id and never its words
    (#158): whether it has been handled, and how often handling it failed.

    A provider sends a webhook delivery again until it is answered with a 2xx. The webhook
    handles each message in a savepoint of its own and answers 5xx when any message failed, so
    the whole delivery comes again; a message whose row says it was handled is acknowledged and
    skipped, and only the one that failed is tried again. A row that keeps counting failures is
    what the operator reads: an id, a moment and the name of what went wrong, nothing else.
    It names no profile — a message is received before it is known whose it is — so it holds
    nothing about a person.
    """

    __tablename__ = "whatsapp_receipt"
    __table_args__ = (
        UniqueConstraint("provider_message_id", name="uq_whatsapp_receipt_provider_message"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider_message_id: Mapped[str] = mapped_column(String(128))
    """The provider's id for the message (`InboundMessage.provider_message_id`): its handle."""
    first_seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    handled_at: Mapped[datetime | None] = mapped_column(default=None)
    """When it was handled, all the way; a redelivery after this is skipped."""
    failures: Mapped[int] = mapped_column(Integer, default=0)
    last_failed_at: Mapped[datetime | None] = mapped_column(default=None)
    last_failure: Mapped[str | None] = mapped_column(String(64), default=None)
    """The class name of what went wrong the last time, never its message."""


@monotonic
class DoseQuestion(ProfileScoped, Base):
    """ "Which tablet?" — asked when a "Taken" or "given" reply could be about more than one
    tablet at that moment (#162). Nothing is written down until the poster answers with one
    that says exactly which: a number from the list, "both", or the tablet's own word.

    `doses` is the list exactly as it was asked, in its order — each tablet's line and the
    moment of his day it was due at — so "1" means the first line that was read to him, not
    the first one of a list worked out again later. Written under the medicines scope, which
    the helper's key holds, on the thread it was asked in; it takes one change, its answer.
    The open question a reply answers is the newest one — `asked_at`, tied by `seq`
    (#192/#218) — for that thread.
    """

    __tablename__ = "whatsapp_dose_question"
    __table_args__ = (
        _row_of_profile("whatsapp_dose_question"),
        _tied_to_profile("whatsapp_dose_question", "thread_id", "whatsapp_thread"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    thread_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("whatsapp_thread.id"), index=True)
    asked_at: Mapped[datetime] = mapped_column()
    expires_at: Mapped[datetime] = mapped_column()
    doses: Mapped[list[dict[str, str]]] = mapped_column(JSON)
    """`[{"line_id": …, "anchor": …}, …]`, in the order the question read them out."""
    answered_at: Mapped[datetime | None] = mapped_column(default=None)
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)


class ProposalStatus(StrEnum):
    OPEN = "open"
    CONFIRMED = "confirmed"
    DECLINED = "declined"
    EXPIRED = "expired"


ANSWER_IN_PROGRESS = "whatsapp_proposal_answer"
"""`session.info` key: the id of the one proposal `proposals.answer` is closing right now."""


def _answer_is_in_progress(session: Any, row: Any) -> bool:
    return session is not None and session.info.get(ANSWER_IN_PROGRESS) == row.id


class Proposal(ProfileScoped, Base):
    """What the classifier heard, waiting for the poster's yes.

    The draft the yes binds to is recomputed from these columns at the moment of the yes:
    the subject, the attribute, the value and the unit of the fact, and the kind and moment
    of the event it will rest on. `message_id` is the message it was heard in, whose
    artefact becomes the provenance. Only the poster answers, and only once.
    """

    __tablename__ = "whatsapp_proposal"
    __table_args__ = (
        _row_of_profile("whatsapp_proposal"),
        _tied_to_profile("whatsapp_proposal", "thread_id", "whatsapp_thread"),
        _tied_to_profile("whatsapp_proposal", "message_id", "whatsapp_message"),
        _tied_to_profile("whatsapp_proposal", "fact_id", "fact"),
        _tied_to_profile("whatsapp_proposal", "event_id", "event"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    thread_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("whatsapp_thread.id"), index=True)
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("whatsapp_message.id"))
    poster_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"), index=True)
    subject: Mapped[str] = mapped_column(String(64))
    attribute: Mapped[str] = mapped_column(String(64))
    value: Mapped[Any] = mapped_column(JSON)
    unit: Mapped[str | None] = mapped_column(String(32), default=None)
    event_kind: Mapped[EventKind] = mapped_column(enum_column(EventKind, "event_kind"))
    occurred_at: Mapped[datetime] = mapped_column()
    said: Mapped[str] = mapped_column(String(32))
    """Which read-back was sent (`strings.REPLIES` key suffix): what the poster was asked."""
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime] = mapped_column()
    status: Mapped[ProposalStatus] = mapped_column(
        enum_column(ProposalStatus, "whatsapp_proposal_status"), default=ProposalStatus.OPEN
    )
    answered_at: Mapped[datetime | None] = mapped_column(default=None)
    fact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fact.id"), default=None)
    event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("event.id"), default=None)

    @property
    def is_open(self) -> bool:
        return self.status is ProposalStatus.OPEN


frozen(WhatsAppMessage)
# A group is opened once; who is in it is never a column, only the digest of what the
# provider was last told, which is the one thing a sync changes.
frozen(WhatsAppGroup, except_for=frozenset({"members_digest"}))
# A question about which tablet takes one change: its answer (#162).
frozen(DoseQuestion, except_for=frozenset({"answered_at"}))
# A proposal takes one change, its answer, and only while the proposals service is making it.
frozen(
    Proposal,
    except_for=frozenset({"status", "answered_at", "fact_id", "event_id"}),
    only_when=_answer_is_in_progress,
)
