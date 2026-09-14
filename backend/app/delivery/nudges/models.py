"""The nudge tables: a nudge handed to delivery, and what he did with it.

A `Nudge` is a `NudgeDraft` (`app.delivery.nudges.handoff`) at the moment it was handed to
delivery: its kind, its lines and spoken twin in his language, why he is seeing it (a plain
line, and the ids it rests on), its cap class, the earliest moment it may go and when it
stops being worth sending. It names the State it was rendered from, like every rendered row.
The nudges infer nothing — they say back what the record holds (a visit tomorrow, days with
a tablet taken, his own words) or ask how he is — so they carry no boundary line.

A `NudgeResponse` is one thing a person did with one nudge: seen, accepted (the one tap), or
dismissed ("Not today"). It rests on a memory Event of kind ENGAGEMENT, the way a card's
engagement does (`app.delivery.feed.engagement`), so a preference can later rest on it. A
nudge with no response by the time it stopped being worth sending was ignored; that is read
from the two tables, never written.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, ProfileScoped, enum_column, frozen, utcnow
from app.delivery.feed.models import CapsClass
from app.keys.scopes import Scope
from app.memory.models import _row_of_profile, _tied_to_profile
from app.state.models import RenderedFromState

LINE_LENGTH = 200


class NudgeKind(StrEnum):
    """The smart nudges this engine makes (docs/smart-nudges.md §1). Curiosity and context
    need the self-search jobs and the environmental jobs; they are not made here yet."""

    ANTICIPATION = "anticipation"
    CHECK_IN = "check_in"
    PATTERN = "pattern"
    COMMITMENT = "commitment"
    RECOGNITION = "recognition"
    PRESENCE = "presence"


class ResponseKind(StrEnum):
    SEEN = "seen"
    ACCEPTED = "accepted"
    """He tapped the nudge's one action: "Went well", a word on the cloud, "Thank you"."""
    DISMISSED = "dismissed"
    """"Not today". Feeds ranking: that kind comes later in his plan for a week."""


class Nudge(RenderedFromState, ProfileScoped, Base):
    """One nudge, as it was handed to delivery. Never edited; never sent from here."""

    __tablename__ = "nudge"
    __table_args__ = (
        _row_of_profile("nudge"),
        UniqueConstraint("profile_id", "dedupe_key", name="uq_nudge_dedupe"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kind: Mapped[NudgeKind] = mapped_column(enum_column(NudgeKind, "nudge_kind"))
    scope: Mapped[Scope] = mapped_column(enum_column(Scope, "scope"))
    day: Mapped[str] = mapped_column(String(10), index=True)
    language: Mapped[str] = mapped_column(String(16))
    lines: Mapped[list[str]] = mapped_column(JSON)
    voice: Mapped[list[str]] = mapped_column(JSON)
    why: Mapped[str] = mapped_column(String(LINE_LENGTH))
    reason: Mapped[dict[str, Any]] = mapped_column(JSON)
    cap_class: Mapped[CapsClass] = mapped_column(enum_column(CapsClass, "caps_class"))
    priority: Mapped[int] = mapped_column(Integer)
    send_after: Mapped[datetime] = mapped_column()
    expires_at: Mapped[datetime] = mapped_column()
    dedupe_key: Mapped[str] = mapped_column(String(120))
    memo_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    """For a commitment: the memo his words were quoted from (E05's table, when it is here)."""
    handed_over_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    handed_over_by_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))


class NudgeResponse(ProfileScoped, Base):
    """One person, one nudge, one thing done with it, at one moment."""

    __tablename__ = "nudge_response"
    __table_args__ = (
        _row_of_profile("nudge_response"),
        _tied_to_profile("nudge_response", "nudge_id", "nudge"),
        _tied_to_profile("nudge_response", "event_id", "event"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    nudge_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("nudge.id"), index=True)
    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    kind: Mapped[ResponseKind] = mapped_column(enum_column(ResponseKind, "nudge_response_kind"))
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("event.id"))
    at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


frozen(Nudge)
frozen(NudgeResponse)
