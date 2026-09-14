"""The safety tables: the flag, the notice, the what-to-do-now card, the emergency card.

Every row is the profile's (`ProfileScoped`) and is reached through `app.audit.access`. The
two cards carry `RenderedFromState`: neither can reach the database without the snapshot it
was rendered from (`app.state.models`). No column here holds prose. A flag is a code from the
red-flag table; a notice is a template id and the codes that fill it; a card is the ids of
the lines it showed, in which language, from which State. The words themselves are rendered
from the templates in `app.channels.safety_strings` when the row is read back, so a card
read tomorrow says exactly what it said today and a template that is corrected corrects
every card at once.

A flag is written before anything else about the moment it belongs to (`app.safety.not_feeling_well`),
so it names the artefact — the voice note, the typed words — and not the event, which comes
after it. The notice names the flag; the card names the flag and the event.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, ProfileScoped, enum_column, frozen, utcnow
from app.state.models import Posture, RenderedFromState


def _row_of_profile(table: str) -> UniqueConstraint:
    return UniqueConstraint("profile_id", "id", name=f"uq_{table}_profile_id_id")


def _tied_to_profile(table: str, column: str, referred: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["profile_id", column],
        [f"{referred}.profile_id", f"{referred}.id"],
        name=f"fk_{table}_{column.removesuffix('_id')}_profile",
    )


class FlagKind(StrEnum):
    RED_FLAG = "red_flag"


class Flag(ProfileScoped, Base):
    """One red flag heard in a person's words: which one, when, from which artefact.

    "This one we do not wait for." The row is the first thing written when a red flag is
    heard, before the event, the fact, the notices and the card, and it is written through
    `app.safety.red_flags.write_flag_kept`, whose keeper writes it again if a refusal later in
    the same request rolls the unit of work back: whatever else fails, the flag is on the
    record. `posture` is what the flag asks of the day: always ACT for a
    red flag. Nothing here is a diagnosis; the code names the words in the table.
    """

    __tablename__ = "flag"
    __table_args__ = (
        _row_of_profile("flag"),
        _tied_to_profile("flag", "artifact_id", "artifact"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kind: Mapped[FlagKind] = mapped_column(enum_column(FlagKind, "flag_kind"))
    code: Mapped[str] = mapped_column(String(48), index=True)
    posture: Mapped[Posture] = mapped_column(enum_column(Posture, "posture"))
    artifact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("artifact.id"), default=None)
    raised_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    raised_by_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    # The flags the table held back this time, by code, so the caregiver sees the suppression.
    suppressed: Mapped[list[str]] = mapped_column(JSON, default=list)


class NoticeKind(StrEnum):
    """Who a notice is for and why."""

    FAMILY_ALERT = "family_alert"
    """To a key holder: he is not feeling well, this is what he said, call him."""
    CHECK_IN = "check_in"
    """To the person himself, later: how do you feel now."""


class Notice(ProfileScoped, Base):
    """One message owed to one person, to be delivered by a channel (E11 push, E19 WhatsApp).

    The row is the template id and the codes that fill it — the profile's name is read at
    delivery, the words he said are a code from the red-flag or symptom table — in the
    language the person reads. `deliver_after` is when it may go (now for an alert, two
    hours on for a check-in); `delivered_at` is the one change the row takes, by the
    channel that sent it. Nothing here is free text, so nothing a person said travels in a
    row a channel reads.
    """

    __tablename__ = "notice"
    __table_args__ = (
        _row_of_profile("notice"),
        _tied_to_profile("notice", "flag_id", "flag"),
        _tied_to_profile("notice", "event_id", "event"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kind: Mapped[NoticeKind] = mapped_column(enum_column(NoticeKind, "notice_kind"))
    to_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"), index=True)
    template: Mapped[str] = mapped_column(String(48))
    slots: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    language: Mapped[str] = mapped_column(String(16))
    flag_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("flag.id"), default=None)
    event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("event.id"), default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    deliver_after: Mapped[datetime] = mapped_column(index=True)
    delivered_at: Mapped[datetime | None] = mapped_column(default=None)


class WhatToDoKind(StrEnum):
    """Which row of the decision table the card came from."""

    RED_FLAG = "red_flag"
    MISSED_DOSE = "missed_dose"
    REST = "rest"


class WhatToDoCard(RenderedFromState, ProfileScoped, Base):
    """The card he is shown after "I'm not feeling well": which row of the table, which
    lines, in which language, from which State — and the event and flag it belongs to."""

    __tablename__ = "what_to_do_card"
    __table_args__ = (
        _row_of_profile("what_to_do_card"),
        _tied_to_profile("what_to_do_card", "flag_id", "flag"),
        _tied_to_profile("what_to_do_card", "event_id", "event"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kind: Mapped[WhatToDoKind] = mapped_column(enum_column(WhatToDoKind, "what_to_do_kind"))
    language: Mapped[str] = mapped_column(String(16))
    # The template ids of the lines shown, in order. The words come from the templates.
    line_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    flag_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("flag.id"), default=None)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("event.id"))
    check_in_at: Mapped[datetime | None] = mapped_column(default=None)
    rendered_at: Mapped[datetime] = mapped_column(default=utcnow)
    rendered_for_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))


class CardFormat(StrEnum):
    JSON = "json"
    HTML = "html"


class EmergencyCard(RenderedFromState, ProfileScoped, Base):
    """One rendering of the emergency card: for whom, in which format and language, from
    which State, resting on which facts and lines. The offline story: the app caches the
    last render, and this row is the record of what it holds."""

    __tablename__ = "emergency_card"
    __table_args__ = (_row_of_profile("emergency_card"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    format: Mapped[CardFormat] = mapped_column(enum_column(CardFormat, "card_format"))
    language: Mapped[str] = mapped_column(String(16))
    fact_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    line_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    rendered_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    rendered_for_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))


frozen(Flag)
# Delivery is the one change a notice takes: the channel that sent it says when.
frozen(Notice, except_for=frozenset({"delivered_at"}))
frozen(WhatToDoCard)
frozen(EmergencyCard)
