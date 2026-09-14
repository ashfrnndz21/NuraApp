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

from sqlalchemy import JSON, Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, ProfileScoped, enum_column, frozen, utcnow
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
# A proposal takes one change, its answer, and only while the proposals service is making it.
frozen(
    Proposal,
    except_for=frozenset({"status", "answered_at", "fact_id", "event_id"}),
    only_when=_answer_is_in_progress,
)
