"""The tables of onboarding: the profile's settings (E01-03), the biography session with its
papers and read-back lines (E01-02), and the first week's plan with its prompts (E01-04).

The disciplines of the memory tables hold here too. Every table carries `ProfileScoped`, and
every reference to another row carries the profile with it (`_tied_to_profile`), so a paper
cannot name another profile's photo, nor a read-back line another profile's fact, whatever a
service did. Rows are immutable or take one named change each: settings are superseded by
the next settings, never edited; a session takes its read-back and its close; a prompt takes
its done or its skip — each only while the service that owns the change is making it.
Nothing here holds what a paper said: a paper row names the photo and the card, a line names
the fact and the answer, and the facts are where the words are.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, ProfileScoped, enum_column, frozen, utcnow
from app.memory.models import LABEL_LENGTH, _row_of_profile, _tied_to_profile

CLOCK_TIME_LENGTH = 5
"""A time of day on his wall clock, "07:30": the region's zone says whose clock."""


class Density(StrEnum):
    """How much goes on a screen (docs/onboarding.html: "Detailed" or "Simple, one thing at a
    time"). The web client's two densities read this."""

    DETAILED = "detailed"
    SIMPLE = "simple"


# --- E01-03: the settings --------------------------------------------------------------------


class ProfileSettings(ProfileScoped, Base):
    """What the profile's settings screen says, as it stood from `set_at` until superseded.

    One row per save. The next save writes a new row naming this one in `supersedes_id` and
    stamps this one's `superseded_at` — the one change a row takes. The settings are also
    written as facts (`app.onboarding.settings`), each resting on `event_id`, the moment of
    the save, so State folds them; this row is what the screen reads back whole.
    """

    __tablename__ = "profile_settings"
    __table_args__ = (
        _row_of_profile("profile_settings"),
        _tied_to_profile("profile_settings", "event_id", "event"),
        _tied_to_profile("profile_settings", "supersedes_id", "profile_settings"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    conditions: Mapped[list[str]] = mapped_column(JSON)
    language: Mapped[str] = mapped_column(String(16))
    density: Mapped[Density] = mapped_column(enum_column(Density, "density"))
    large_text: Mapped[bool] = mapped_column(Boolean)
    high_contrast: Mapped[bool] = mapped_column(Boolean)
    voice_on: Mapped[bool] = mapped_column(Boolean)
    big_targets: Mapped[bool] = mapped_column(Boolean)
    one_thing_per_screen: Mapped[bool] = mapped_column(Boolean)
    read_back: Mapped[bool] = mapped_column(Boolean)
    repeat_prompts: Mapped[bool] = mapped_column(Boolean)
    preferred_name: Mapped[str | None] = mapped_column(String(LABEL_LENGTH), default=None)
    doctor_name: Mapped[str | None] = mapped_column(String(LABEL_LENGTH), default=None)
    breakfast_time: Mapped[str | None] = mapped_column(String(CLOCK_TIME_LENGTH), default=None)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("event.id"))
    set_by_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    set_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profile_settings.id"), default=None
    )
    superseded_at: Mapped[datetime | None] = mapped_column(default=None)


# --- E01-02: the biography session -----------------------------------------------------------


class PaperKind(StrEnum):
    """What the person said a paper is, as he photographs it — the five records
    docs/onboarding.html asks for. His tag, beside the extractor's own guess on the card."""

    DISCHARGE_LETTER = "discharge_letter"
    LAB_RESULT = "lab_result"
    MEDICINE = "medicine"
    """A prescription, a dispensing label, or the medicine bag."""
    CLINIC_CARD = "clinic_card"
    """A clinic card or an appointment slip."""
    INSURANCE_CARD = "insurance_card"


class Answer(StrEnum):
    """What he said to a read-back line."""

    YES = "yes"
    NO = "no"


BIOGRAPHY_IN_PROGRESS = "biography_change"
"""`session.info` key: the id of the one biography session a service is moving on right now.
The only time a session's read-back or close may be stamped."""


def _biography_is_in_progress(session: Any, row: Any) -> bool:
    return session is not None and session.info.get(BIOGRAPHY_IN_PROGRESS) == row.id


class BiographySession(ProfileScoped, Base):
    """One sitting of the health biography: who opened it, and — once each — when the
    read-back was answered and when it closed. Where it stands (`app.onboarding.biography.Step`)
    is worked out from these and from the record, never stored twice."""

    __tablename__ = "biography_session"
    __table_args__ = (_row_of_profile("biography_session"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    opened_by_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    opened_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    read_back_at: Mapped[datetime | None] = mapped_column(default=None)
    read_back_by_person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("person.id"), default=None
    )
    closed_at: Mapped[datetime | None] = mapped_column(default=None)
    closed_by_person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("person.id"), default=None
    )


class BiographyPaper(ProfileScoped, Base):
    """One paper added in a sitting: the photo, the review card it was read into, and what
    the person said it is."""

    __tablename__ = "biography_paper"
    __table_args__ = (
        _row_of_profile("biography_paper"),
        _tied_to_profile("biography_paper", "session_id", "biography_session"),
        _tied_to_profile("biography_paper", "artifact_id", "artifact"),
        _tied_to_profile("biography_paper", "card_id", "review_card"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("biography_session.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    """The order the papers were added in, from 0: the order the read-back follows."""
    artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artifact.id"))
    card_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("review_card.id"))
    paper: Mapped[PaperKind] = mapped_column(enum_column(PaperKind, "paper_kind"))
    added_by_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    added_at: Mapped[datetime] = mapped_column(default=utcnow)


class BiographyLine(ProfileScoped, Base):
    """One read-back line as it was answered: which fact it read back, in what place, and
    what he said. A "no" names the dispute it opened against that fact."""

    __tablename__ = "biography_line"
    __table_args__ = (
        _row_of_profile("biography_line"),
        _tied_to_profile("biography_line", "session_id", "biography_session"),
        _tied_to_profile("biography_line", "fact_id", "fact"),
        _tied_to_profile("biography_line", "dispute_fact_id", "fact"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("biography_session.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    fact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("fact.id"))
    answer: Mapped[Answer] = mapped_column(enum_column(Answer, "read_back_answer"))
    dispute_fact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fact.id"), default=None)
    answered_by_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    answered_at: Mapped[datetime] = mapped_column(default=utcnow)


# --- E01-04: the first week -------------------------------------------------------------------


class PromptStatus(StrEnum):
    PENDING = "pending"
    DONE = "done"
    """What it asked for arrived, by any route."""
    SKIPPED = "skipped"
    """He said Later. It stays in the caregiver's list; it is not asked for again this week."""


PLAN_IN_PROGRESS = "activation_plan_change"
"""`session.info` key: the id of the one plan whose prompts a service is settling right now.
The only time a prompt's status may change."""


def _plan_is_in_progress(session: Any, row: Any) -> bool:
    return session is not None and session.info.get(PLAN_IN_PROGRESS) == row.plan_id


class ActivationPlan(ProfileScoped, Base):
    """The first week after a biography: which day it starts, at what time on his clock."""

    __tablename__ = "activation_plan"
    __table_args__ = (
        _row_of_profile("activation_plan"),
        _tied_to_profile("activation_plan", "session_id", "biography_session"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("biography_session.id"), default=None
    )
    breakfast_time: Mapped[str] = mapped_column(String(CLOCK_TIME_LENGTH))
    first_day: Mapped[date] = mapped_column()
    created_by_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


class PlanPrompt(ProfileScoped, Base):
    """One day's prompt: which gap it asks to fill (`app.onboarding.gaps`), when it is due,
    and where it stands. `done_by_fact_id` names the fact that closed it, when one did."""

    __tablename__ = "plan_prompt"
    __table_args__ = (
        _row_of_profile("plan_prompt"),
        _tied_to_profile("plan_prompt", "plan_id", "activation_plan"),
        _tied_to_profile("plan_prompt", "done_by_fact_id", "fact"),
        UniqueConstraint("plan_id", "gap", name="uq_plan_prompt_plan_id_gap"),
        UniqueConstraint("plan_id", "day", name="uq_plan_prompt_plan_id_day"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("activation_plan.id"), index=True)
    day: Mapped[int] = mapped_column(Integer)
    gap: Mapped[str] = mapped_column(String(32))
    due_at: Mapped[datetime] = mapped_column()
    status: Mapped[PromptStatus] = mapped_column(
        enum_column(PromptStatus, "plan_prompt_status"), default=PromptStatus.PENDING
    )
    done_at: Mapped[datetime | None] = mapped_column(default=None)
    done_by_fact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fact.id"), default=None)
    skipped_at: Mapped[datetime | None] = mapped_column(default=None)
    skipped_by_person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("person.id"), default=None
    )


# Settings are superseded, never edited. A session takes its read-back and its close, a
# prompt its done or its skip, each only through its service. Papers, lines and plans take
# nothing.
frozen(ProfileSettings, except_for=frozenset({"superseded_at"}))
frozen(
    BiographySession,
    except_for=frozenset(
        {"read_back_at", "read_back_by_person_id", "closed_at", "closed_by_person_id"}
    ),
    only_when=_biography_is_in_progress,
)
frozen(BiographyPaper)
frozen(BiographyLine)
frozen(ActivationPlan)
frozen(
    PlanPrompt,
    except_for=frozenset(
        {"status", "done_at", "done_by_fact_id", "skipped_at", "skipped_by_person_id"}
    ),
    only_when=_plan_is_in_progress,
)
