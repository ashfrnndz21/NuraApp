"""The AuditEntry: one line for one touch of one profile's data.

An entry says who reached in, how they were allowed to, what kind of thing they touched and
whether they got it. It never says what the thing said. That is the whole discipline of this
table: the trail the owner reads must not become a second copy of the record it guards.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, ProfileScoped, enum_column, monotonic, utcnow
from app.keys.scopes import KeyRole, Scope


class Action(StrEnum):
    """What can happen to profile data. Every one of them is written down."""

    READ = "read"
    WRITE = "write"
    SHARE = "share"
    REVIEW = "review"
    """D3 (ADR 0019 point 7; `docs/design/NURA-BUILD-MASTER-SPEC.md` §39): a model's own
    conclusion was rejected — dropped by a gate before it ever reached a person, or dropped by
    the person himself on a read-back or a review card. `refused_because` names the closed
    reason (`app.audit.conclusions.ConclusionReasonCode` or `ConclusionResponseKind`); never
    the conclusion's own words. See `app.audit.conclusions.record_dropped_conclusion`."""


class Outcome(StrEnum):
    """Whether the reach landed. A refusal is logged as carefully as a success."""

    ALLOWED = "allowed"
    REFUSED = "refused"


class Channel(StrEnum):
    """Where the reach came from, so the owner can tell an app read from a link."""

    APP = "app"
    WHATSAPP = "whatsapp"
    SHARE_LINK = "share_link"
    CLINIC = "clinic"
    SYSTEM = "system"


@monotonic
class AuditEntry(ProfileScoped, Base):
    """One access to one profile, at one moment, by one person.

    `target` is the kind of thing touched — a table of the graph, or for a share the kind of
    copy that went out. `rows` is how many of them. Neither carries any of their content.

    Read newest first, `at` tied by `seq` (#192/#218): the trail's whole purpose is telling
    him, truthfully, what happened and in what order, so a merely stable-but-arbitrary
    tiebreaker is not enough here the way it is for a plain listing — two touches in one
    request, or any frozen clock, must still read back in the order they actually happened.
    """

    __tablename__ = "audit_entry"
    __table_args__ = (
        CheckConstraint(
            "actor_person_id IS NOT NULL OR channel = 'system'",
            name="ck_audit_entry_actor_or_system",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    # None only for Nura's own reach (channel SYSTEM): the delivery engine acting for him.
    actor_person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("person.id"), index=True, default=None
    )
    # The owner reaches his own graph without a key, so there is no role and no key to name.
    actor_role: Mapped[KeyRole | None] = mapped_column(enum_column(KeyRole, "key_role"))
    key_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("key.id"), default=None)
    action: Mapped[Action] = mapped_column(enum_column(Action, "audit_action"))
    scope: Mapped[Scope] = mapped_column(enum_column(Scope, "scope"))
    channel: Mapped[Channel] = mapped_column(enum_column(Channel, "audit_channel"))
    target: Mapped[str] = mapped_column(String(64))
    target_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    rows: Mapped[int] = mapped_column(Integer, default=0)
    outcome: Mapped[Outcome] = mapped_column(enum_column(Outcome, "audit_outcome"))
    # The name of the refusal, never what was held back. See `app.errors.Refusal`.
    refused_because: Mapped[str | None] = mapped_column(String(64), default=None)
    # Who the copy went to: an account for family, a written name for a clinic or a link.
    shared_with_person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("person.id"), default=None
    )
    shared_with_label: Mapped[str | None] = mapped_column(String(120), default=None)
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
