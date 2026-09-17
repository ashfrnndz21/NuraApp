"""The feeling tables: a tap on the cloud, and the note a tap and its one answer became.

A `FeelingTap` is one tap: his word, the SYMPTOM event it was written as, the one question it
asked back, and — once — his answer. It carries no words of his beyond the word he tapped,
which is a code (`Feeling`). `reasons` is why that word was on the cloud at that moment, by
code and id (a medicine line, an episode, a fact), never by what they say; `cloud_state_id`
is the State the cloud was read from. A red word is a tap too, with the flag it raised, so a
week's taps can be counted without reading anything else.

A `FeelingNote` is what a tap and its answer were read into: at most two lines of things to
tell the doctor — plus, right after a line that names a medicine, the two lines that keep it
as it is and hand the decision to him (`DO_NOT_STOP`, #157) — who does the next thing, and
the boundary last. It is a rendered row of an
inferring surface (`Surface.FEELING_INFERENCE`): it names the State it was rendered from and
carries the boundary line, or it is not written (`app.state.service.render_from_state`).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, ProfileScoped, enum_column, frozen, monotonic, utcnow
from app.memory.models import _row_of_profile, _tied_to_profile
from app.reasoning.feelings.words import Answer, FollowUp
from app.safety.red_flags import Feeling
from app.state.models import RenderedFromState

LINE_LENGTH = 200
"""One line of a note, in his words: never a document."""


@monotonic
class FeelingTap(ProfileScoped, Base):
    """One tap on the feeling cloud, and the one answer it asked for.

    The row takes one change: the answer, with when it came and — when a yes to the question
    that tells a red variant apart made it red — the flag that yes raised. The reader's own
    last tap — `tapped_at`, tied by `seq` (#192/#218) — gates whether a watched feeling note
    is still worth checking in on (`app.delivery.nudges.engine`).
    """

    __tablename__ = "feeling_tap"
    __table_args__ = (
        _row_of_profile("feeling_tap"),
        _tied_to_profile("feeling_tap", "event_id", "event"),
        _tied_to_profile("feeling_tap", "flag_id", "red_flag"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("event.id"))
    word: Mapped[Feeling] = mapped_column(enum_column(Feeling, "feeling"))
    red: Mapped[bool] = mapped_column(Boolean)
    flag_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("red_flag.id"), default=None)
    follow_up: Mapped[FollowUp | None] = mapped_column(
        enum_column(FollowUp, "feeling_follow_up"), default=None
    )
    answer: Mapped[Answer | None] = mapped_column(
        enum_column(Answer, "feeling_answer"), default=None
    )
    answered_at: Mapped[datetime | None] = mapped_column(default=None)
    emphasised: Mapped[bool] = mapped_column(Boolean, default=False)
    reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    cloud_state_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("state_snapshot.id"), default=None
    )
    by_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    tapped_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)


class NoteOutcome(StrEnum):
    """What happens next with what he said (E17-02): kept for the doctor, or watched."""

    FOR_THE_DOCTOR = "for_the_doctor"
    """The tap was read against something on the record; the note is kept for the visit."""
    WATCH = "watch"
    """Nothing on the record to read it against; Nura asks again in a week."""


@monotonic
class FeelingNote(RenderedFromState, ProfileScoped, Base):
    """What one tap and its answer were read into, as he was shown it.

    `lines` are the things to tell the doctor (at most two) — plus, right after a line that
    names a medicine, the two lines that keep it as it is and hand the decision to him
    (`DO_NOT_STOP`, #157) — `then` who does the next thing, and `voice` the spoken twin —
    headline, lines, then, and the boundary. `reasons` names
    what the tap was read against by id: the medicine line and the monograph rule, the facts
    of a direction in his blood pressure, the event of a visit or a discharge. A watched note
    still worth checking in on is picked newest first — `created_at`, tied by `seq`
    (#192/#218) — by `app.delivery.nudges.engine`, which stops at the first match.
    """

    __tablename__ = "feeling_note"
    __table_args__ = (
        _row_of_profile("feeling_note"),
        _tied_to_profile("feeling_note", "tap_id", "feeling_tap"),
        _tied_to_profile("feeling_note", "appointment_id", "appointment"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tap_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("feeling_tap.id"), index=True)
    word: Mapped[Feeling] = mapped_column(enum_column(Feeling, "feeling"))
    answer: Mapped[Answer] = mapped_column(enum_column(Answer, "feeling_answer"))
    language: Mapped[str] = mapped_column(String(16))
    headline: Mapped[str] = mapped_column(String(LINE_LENGTH))
    lines: Mapped[list[str]] = mapped_column(JSON)
    then: Mapped[str] = mapped_column(String(LINE_LENGTH))
    voice: Mapped[list[str]] = mapped_column(JSON)
    reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    outcome: Mapped[NoteOutcome] = mapped_column(enum_column(NoteOutcome, "feeling_outcome"))
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("appointment.id"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)


frozen(FeelingTap, except_for=frozenset({"answer", "answered_at", "flag_id"}))
frozen(FeelingNote)
