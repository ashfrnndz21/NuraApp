"""The rows of the visit loop: the brief, the questions, the summary, the memos and the flags.

Four of them are things a person is shown, so they carry `RenderedFromState`: the brief, a
question, a summary and a memo each name the State snapshot they were rendered from, and the
schema refuses one that does not. Every row is the profile's, and every reference to another
row carries the profile with it (`_tied_to_profile`), the way memory's do.

Text here is rendered from a template in `strings.py` and checked by the plain-words verifier
before the row is written; the columns are short — a line, never a page. The transcript a
summary was read from is an artefact in the object store, never a column. A `Flag` is not
shown to anyone as it stands: it is a safety row the sentences are rendered from, written
before anything is ranked.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, ProfileScoped, enum_column, frozen, utcnow
from app.memory.models import _row_of_profile, _tied_to_profile
from app.state.models import RenderedFromState

LINE_LENGTH = 120
"""The most a rendered patient line may hold. A template line with names and a date."""

MEMO_LENGTH = 80
"""A memo is one line in his words, short enough to be read aloud in one breath."""


# --- flags -----------------------------------------------------------------------------------


class FlagKind(StrEnum):
    """What a flag is. None of these is a diagnosis; each is a thing that bypasses planning
    (a red flag) or becomes a question for the doctor (a change heard, an interaction)."""

    RED_FLAG = "red_flag"
    MEDICINE_CHANGE_HEARD = "medicine_change_heard"
    INTERACTION = "interaction"


class Flag(ProfileScoped, Base):
    """A safety row: what was found, in which facts or artefact, and when.

    `code` is the entry in the red-flag table (`app.safety.red_flags`), the kind of change
    heard, or the interaction the licensed data client named. `payload` is structured — a
    drug name, a span in the transcript — never a sentence. A flag takes one change: it is
    resolved, by a person, when the doctor has been asked.
    """

    __tablename__ = "flag"
    __table_args__ = (
        _row_of_profile("flag"),
        _tied_to_profile("flag", "artifact_id", "artifact"),
        _tied_to_profile("flag", "appointment_id", "appointment"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kind: Mapped[FlagKind] = mapped_column(enum_column(FlagKind, "flag_kind"))
    code: Mapped[str] = mapped_column(String(64))
    subject: Mapped[str] = mapped_column(String(64))
    fact_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    artifact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("artifact.id"), default=None)
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("appointment.id"), default=None
    )
    raised_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(default=None)


# --- the brief -------------------------------------------------------------------------------


class Brief(RenderedFromState, ProfileScoped, Base):
    """The pre-visit brief for one appointment, as rendered: purpose, what changed since the
    last visit, the open questions, what to bring.

    `lines` is the rendered lines in order, each `{"section", "key", "text", "sources"}`:
    the template it came from, the text the verifier passed, and the ids (facts, memos,
    flags) it rests on. `since_state_id` is the snapshot "what changed" was measured from.
    A brief is never edited: a later one for the same visit supersedes it by being newer.
    """

    __tablename__ = "brief"
    __table_args__ = (
        _row_of_profile("brief"),
        _tied_to_profile("brief", "appointment_id", "appointment"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    appointment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("appointment.id"), index=True)
    language: Mapped[str] = mapped_column(String(16))
    since_state_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("state_snapshot.id"), default=None
    )
    lines: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    sources: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    built_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


# --- questions -------------------------------------------------------------------------------


class QuestionSource(StrEnum):
    """Where a question came from. Every question carries its source (E05-02)."""

    GAP = "gap"
    MEMO = "memo"
    FLAG = "flag"
    PERSON = "person"


class Question(RenderedFromState, ProfileScoped, Base):
    """One question to ask the doctor at one visit.

    Generated ones come from a gap, a memo or a flag, through a template; a person's own
    comes typed, with his yes. Rows are immutable: an edit is a new row naming the one it
    supersedes, a removal is a new row with `removed` set, and the old row takes the one
    change of being superseded. The current list is the unsuperseded rows not removed.
    """

    __tablename__ = "question"
    __table_args__ = (
        _row_of_profile("question"),
        _tied_to_profile("question", "appointment_id", "appointment"),
        _tied_to_profile("question", "supersedes_id", "question"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    appointment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("appointment.id"), index=True)
    language: Mapped[str] = mapped_column(String(16))
    source: Mapped[QuestionSource] = mapped_column(enum_column(QuestionSource, "question_source"))
    source_kind: Mapped[str | None] = mapped_column(String(64), default=None)
    source_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    key: Mapped[str] = mapped_column(String(64))
    slots: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    text: Mapped[str] = mapped_column(String(LINE_LENGTH))
    priority: Mapped[int] = mapped_column(Integer)
    added_by_person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("person.id"), default=None
    )
    removed: Mapped[bool] = mapped_column(Boolean, default=False)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("question.id"), default=None)
    superseded_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


# --- memos -----------------------------------------------------------------------------------


class MemoKind(StrEnum):
    """What a memo asks of him: do a thing, ask the doctor a thing, bring a thing, tell
    someone a thing."""

    ACTION = "action"
    ASK = "ask"
    BRING = "bring"
    TELL = "tell"


class MemoSource(StrEnum):
    VISIT = "visit"
    CONVERSATION = "conversation"
    PERSON = "person"


class Memo(RenderedFromState, ProfileScoped, Base):
    """One line in his words, filed against the next appointment.

    The line is rendered from a template (`key`, `slots`) and is at most `MEMO_LENGTH`
    characters. `source_id` names the summary item or the artefact it came from. A memo is
    superseded, never edited: consolidation marks the older of two that say the same thing.
    """

    __tablename__ = "memo"
    __table_args__ = (
        _row_of_profile("memo"),
        _tied_to_profile("memo", "appointment_id", "appointment"),
        _tied_to_profile("memo", "supersedes_id", "memo"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("appointment.id"), default=None
    )
    kind: Mapped[MemoKind] = mapped_column(enum_column(MemoKind, "memo_kind"))
    source: Mapped[MemoSource] = mapped_column(enum_column(MemoSource, "memo_source"))
    source_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    key: Mapped[str] = mapped_column(String(64))
    slots: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    text: Mapped[str] = mapped_column(String(MEMO_LENGTH))
    language: Mapped[str] = mapped_column(String(16))
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("memo.id"), default=None)
    superseded_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


# --- the post-visit summary ------------------------------------------------------------------


class SummaryItemKind(StrEnum):
    ACTION = "action"
    MEDICATION_CHANGE = "medication_change"
    FOLLOW_UP = "follow_up"
    FACT_HEARD = "fact_heard"


class ItemState(StrEnum):
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


SUMMARY_IN_PROGRESS = "visit_summary_confirm"
"""`session.info` key: the id of the one summary `summary.confirm_summary` is closing right
now. The only time a summary or its items may change."""


def _summary_confirm_in_progress(session: Any, row: Any) -> bool:
    summary_id = getattr(row, "summary_id", None) or row.id
    return session is not None and session.info.get(SUMMARY_IN_PROGRESS) == summary_id


class VisitSummary(RenderedFromState, ProfileScoped, Base):
    """What the doctor said at one visit, read from the transcript, waiting for the person's
    yes. `artifact_id` is the transcript in the object store; `red_flag` says a red-flag
    word was heard and a `Flag` was written before the card was composed; `lines` is the
    card as rendered for him. The card takes one change: its close."""

    __tablename__ = "visit_summary"
    __table_args__ = (
        _row_of_profile("visit_summary"),
        _tied_to_profile("visit_summary", "appointment_id", "appointment"),
        _tied_to_profile("visit_summary", "artifact_id", "artifact"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    appointment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("appointment.id"), index=True)
    artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artifact.id"), index=True)
    language: Mapped[str] = mapped_column(String(16))
    red_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    lines: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(default=None)
    confirmed_by_person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("person.id"), default=None
    )

    @property
    def is_open(self) -> bool:
        return self.confirmed_at is None


class SummaryItem(ProfileScoped, Base):
    """One thing heard: an action, a medicine change, a follow-up, a fact. `payload` is the
    summariser's structured answer, `span` where in the transcript it was heard, `text` the
    line rendered for him. On the person's yes each kept item names what it became: a memo,
    an appointment, a fact, or — for a medicine change — a flag and a memo asking the doctor,
    never a change to a medicine."""

    __tablename__ = "summary_item"
    __table_args__ = (
        _row_of_profile("summary_item"),
        _tied_to_profile("summary_item", "summary_id", "visit_summary"),
        _tied_to_profile("summary_item", "memo_id", "memo"),
        _tied_to_profile("summary_item", "appointment_id", "appointment"),
        _tied_to_profile("summary_item", "fact_id", "fact"),
        _tied_to_profile("summary_item", "flag_id", "flag"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    summary_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("visit_summary.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    kind: Mapped[SummaryItemKind] = mapped_column(enum_column(SummaryItemKind, "summary_item_kind"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    span: Mapped[dict[str, int] | None] = mapped_column(JSON(none_as_null=True), default=None)
    confidence: Mapped[float] = mapped_column(Float)
    key: Mapped[str] = mapped_column(String(64))
    text: Mapped[str] = mapped_column(String(LINE_LENGTH))
    state: Mapped[ItemState] = mapped_column(
        enum_column(ItemState, "summary_item_state"), default=ItemState.PROPOSED
    )
    decided_at: Mapped[datetime | None] = mapped_column(default=None)
    memo_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("memo.id"), default=None)
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("appointment.id"), default=None
    )
    fact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fact.id"), default=None)
    flag_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("flag.id"), default=None)


# A flag takes one change, being resolved. A brief takes none. A question and a memo take one,
# being superseded. A summary takes its close, an item its decision, and only while the
# summary service is making it.
frozen(Flag, except_for=frozenset({"resolved_at"}))
frozen(Brief)
frozen(Question, except_for=frozenset({"superseded_at"}))
frozen(Memo, except_for=frozenset({"superseded_at"}))
frozen(
    VisitSummary,
    except_for=frozenset({"confirmed_at", "confirmed_by_person_id"}),
    only_when=_summary_confirm_in_progress,
)
frozen(
    SummaryItem,
    except_for=frozenset(
        {"state", "decided_at", "memo_id", "appointment_id", "fact_id", "flag_id"}
    ),
    only_when=_summary_confirm_in_progress,
)
