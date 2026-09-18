"""`Conversation` and `Turn` (W2): Ask becomes a thread.

One `Conversation` per person per profile — the chief's thread and a caregiver's thread are
never the same row, because `person_id` names whose thread it is (a caregiver's is hers, about
him by name; the patient's own is his). It is reused across days
(`app.search.conversation.current_conversation`) until that person starts a new one
(`closed_at`, set only by `app.search.conversation.start_new_conversation`).

Each question and its answer is one `Turn` on a conversation. Neither table holds the words
themselves: a question was already kept as a MESSAGE `Artifact`, by reference, before this
story (`app.search.ask._keep_question`, "No row holds the words"); the answer becomes one the
same way (`app.search.conversation._keep_answer`), and a `Turn` only ever points at the two
artefact ids — the rule `app.memory.models`'s own module doc already states for every table
here: "no free-text column is wide enough to carry what an artefact said."

Both tables are `RowScoped` under `Scope.ASK`, the same door a question was already kept
behind, and both carry `ProfileScoped`. `Conversation.summary` is the one exception to "no
free text": a short, deterministic, rule-written run of "he asked about X; Nura found Y
(cites)" lines for turns already folded out of the last `KEPT_VERBATIM`
(`app.search.conversation.summarize_turn`) — never a turn's own words, and never written by a
model outside the existing dev/demo gate (`app.llm.residency.allow_external_model`).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, ProfileScoped, enum_column, monotonic, utcnow
from app.keys.rows import RowScoped
from app.memory.models import _row_of_profile, _tied_to_profile
from app.search.ask import Mode

CONVERSATION_TARGET = "conversation"
TURN_TARGET = "turn"

SUMMARY_LENGTH = 4000


@monotonic
class Conversation(ProfileScoped, RowScoped, Base):
    """One person's thread with Nura about one profile. See the module docstring."""

    __tablename__ = CONVERSATION_TARGET
    __table_args__ = (_row_of_profile(CONVERSATION_TARGET),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    last_turn_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(default=None)
    turn_count: Mapped[int] = mapped_column(Integer, default=0)
    summarized_through: Mapped[int] = mapped_column(Integer, default=0)
    """How many of this thread's oldest turns are already folded into `summary` — never more
    than `turn_count` minus `app.search.conversation.KEPT_VERBATIM`."""
    summary: Mapped[str | None] = mapped_column(String(SUMMARY_LENGTH), default=None)
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)


@monotonic
class Turn(ProfileScoped, RowScoped, Base):
    """One question and its answer, on one conversation. See the module docstring — the words
    are never here, only the two artefacts' ids."""

    __tablename__ = TURN_TARGET
    __table_args__ = (
        _row_of_profile(TURN_TARGET),
        _tied_to_profile(TURN_TARGET, "conversation_id", CONVERSATION_TARGET),
        _tied_to_profile(TURN_TARGET, "question_artifact_id", "artifact"),
        _tied_to_profile(TURN_TARGET, "answer_artifact_id", "artifact"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{CONVERSATION_TARGET}.id"), index=True
    )
    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"), index=True)
    mode: Mapped[Mode] = mapped_column(enum_column(Mode, "ask_mode"))
    language: Mapped[str] = mapped_column(String(16))
    question_artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artifact.id"))
    answer_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("artifact.id"), default=None
    )
    answered: Mapped[bool] = mapped_column(default=False)
    line_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)


__all__ = ["CONVERSATION_TARGET", "SUMMARY_LENGTH", "TURN_TARGET", "Conversation", "Turn"]
