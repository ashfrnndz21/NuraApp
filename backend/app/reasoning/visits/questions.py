"""Questions to ask the doctor, generated from gaps, memos and flags; editable; one card for him.

    Questions to ask, generated from gaps, memos and State; editable by Ash; one card for
    Dad. — docs/stage1-product-design.md (E05-02)

Every question carries its source: the gap kind and the facts it rests on, the memo, the
flag, or the person who typed it. A dose change or an interaction becomes a question for the
doctor — "Ask Dr Tan about the new amount of the water pill." — never advice about what to
take. Rows are immutable: a person's edit or removal is a new row with his yes, superseding
the old. His card is the first three by priority, rendered through the templates and the
verifier like everything else he reads.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_profile_read, audited_read
from app.audit.models import Action
from app.audit.trail import record
from app.db import as_utc, utcnow
from app.drafts import QuestionDraft
from app.drugs.registry import DrugRegistry
from app.errors import Refusal
from app.keys.confirm import consume_confirmation
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.memory.models import Appointment, Provider
from app.reasoning.visits.gaps import Gap, GapKind, NoSuchAppointment, find_gaps
from app.reasoning.visits.guard import may_change_visits
from app.reasoning.visits.memos import current_memos
from app.reasoning.visits.models import (
    LINE_LENGTH,
    Memo,
    MemoKind,
    Question,
    QuestionSource,
)
from app.reasoning.visits.strings import (
    has_subject_words,
    language_for,
    medicine_words,
    red_flag_words,
    render,
    say,
    spoken,
    subject_words,
    verified,
)
from app.safety.boundary import Surface, boundary_line, boundary_lines
from app.safety.red_flags import Flag, FlagKind
from app.state.service import StateView, current_state, render_from_state

QUESTION = Question.__tablename__

CARD_SIZE = 3
"""One card for him: the first three questions by priority, one screen."""

PRIORITY_RED_FLAG = 0
PRIORITY_MEDICINE_CHANGE = 1
PRIORITY_PERSON = 2
PRIORITY_MEDICINE_GAP = 3
PRIORITY_RECORD_GAP = 4
PRIORITY_MEMO = 5

GAP_PRIORITY: Mapping[GapKind, int] = {
    GapKind.INTERACTION_FLAGGED: PRIORITY_MEDICINE_GAP,
    GapKind.MEDICINE_NO_PURPOSE: PRIORITY_MEDICINE_GAP,
    GapKind.OPEN_DISPUTE: PRIORITY_MEDICINE_GAP,
    GapKind.FACT_EXPIRED: PRIORITY_RECORD_GAP,
    GapKind.READING_STALE: PRIORITY_RECORD_GAP,
    GapKind.APPOINTMENT_NO_PURPOSE: PRIORITY_RECORD_GAP,
}

CHANGE_TEMPLATE: Mapping[str, str] = {
    "dose": "ask_new_amount",
    "start": "ask_starting",
    "stop": "ask_stopping",
}
"""A medicine change heard, as the question it becomes. Anything else is `ask_medicine_change`."""


class NoSuchQuestion(Refusal):
    """No current question by that id on this visit."""


class NotAQuestion(Refusal):
    """A question is one line of at most 120 characters. This was empty, or longer."""


class GapWithoutItsOther(Refusal):
    """An interaction is between two medicines. This gap named only one, so no line is
    rendered with an empty slot in it."""


class NoRegistry(Refusal):
    """Questions about medicines need the licensed drug data behind its port; none was given."""


@dataclass(frozen=True, slots=True)
class Visit:
    """The appointment and the doctor it is with, read once for the whole loop."""

    appointment: Appointment
    provider: Provider
    language: str
    registry: DrugRegistry | None = None
    """The licensed drug data, for his name for a medicine; None where no medicine is named."""

    @property
    def doctor(self) -> str:
        return self.provider.name

    def medicine(self, generic: str) -> str:
        return medicine_words(generic, self.language, self.registry)


@dataclass(frozen=True, slots=True)
class Proposed:
    """A question the loop proposes: which template, with what, from where, how urgent."""

    key: str
    slots: dict[str, Any]
    source: QuestionSource
    source_kind: str
    source_ids: tuple[str, ...]
    priority: int

    def same_as(self, question: Question) -> bool:
        return question.key == self.key and _slots_json(question.slots) == _slots_json(self.slots)


def _slots_json(slots: Mapping[str, Any]) -> str:
    return json.dumps(slots, sort_keys=True, default=str)


@audited(Action.READ, Scope.VISITS, Appointment.__tablename__)
async def require_visit(
    session: AsyncSession,
    *,
    context: KeyContext,
    appointment_id: uuid.UUID,
    registry: DrugRegistry | None = None,
) -> Visit:
    """The visit, its doctor and the language to speak in, or a refusal."""
    found = await audited_read(
        session, Appointment, context, Scope.VISITS, where=(Appointment.id == appointment_id,)
    )
    if not found:
        raise NoSuchAppointment(f"no appointment {appointment_id} on profile {context.profile_id}")
    appointment = found[0]
    providers = await audited_read(
        session, Provider, context, Scope.VISITS, where=(Provider.id == appointment.provider_id,)
    )
    profile = await audited_profile_read(session, context)
    return Visit(appointment, providers[0], language_for(profile.language), registry)


def question_from_gap(gap: Gap, visit: Visit) -> Proposed:
    """The question a gap becomes: what to ask the doctor, never what to do about it."""
    lang = visit.language
    doctor = {"doctor": visit.doctor}
    priority = GAP_PRIORITY[gap.kind]
    if gap.kind is GapKind.FACT_EXPIRED:
        # A subject with no words of his: the whole fallback line, never the code (F7).
        if not has_subject_words(gap.subject):
            key, slots = "ask_visit_purpose", doctor
        else:
            key, slots = "ask_fact_expired", {**doctor, "thing": subject_words(gap.subject, lang)}
    elif gap.kind is GapKind.READING_STALE:
        key, slots = "ask_reading_stale", doctor
    elif gap.kind is GapKind.MEDICINE_NO_PURPOSE:
        key, slots = (
            "ask_medicine_purpose",
            {
                **doctor,
                "medicine": visit.medicine(gap.medicine or gap.subject),
            },
        )
    elif gap.kind is GapKind.INTERACTION_FLAGGED:
        if not gap.other:
            raise GapWithoutItsOther(f"interaction gap on {gap.subject} names no other medicine")
        key, slots = (
            "ask_interaction",
            {
                **doctor,
                "medicine": visit.medicine(gap.medicine or gap.subject),
                "other": visit.medicine(gap.other),
            },
        )
    elif gap.kind is GapKind.OPEN_DISPUTE:
        if not has_subject_words(gap.subject):
            key, slots = "ask_visit_purpose", doctor
        else:
            key, slots = "tell_dispute", {**doctor, "thing": subject_words(gap.subject, lang)}
    else:
        key, slots = "ask_visit_purpose", doctor
    return Proposed(key, slots, QuestionSource.GAP, gap.kind.value, gap.source_ids(), priority)


def question_from_flag(flag: Flag, visit: Visit) -> Proposed | None:
    """A red flag becomes "tell the doctor"; a change heard becomes "ask the doctor". An
    interaction is E04's `InteractionFlag`, read as a gap (`gaps.py`), not a kind here."""
    lang = visit.language
    doctor = visit.doctor
    if flag.kind is FlagKind.RED_FLAG:
        return Proposed(
            "tell_doctor_about",
            {"doctor": doctor, "what": red_flag_words(flag.code, lang)},
            QuestionSource.FLAG,
            flag.kind.value,
            (str(flag.id),),
            PRIORITY_RED_FLAG,
        )
    if flag.kind is FlagKind.MEDICINE_CHANGE_HEARD:
        if flag.subject == "unknown_drug" or not flag.payload.get("generic"):
            # A change to a drug the register did not know: the question names no drug.
            return Proposed(
                "ask_medicines_change",
                {"doctor": doctor},
                QuestionSource.FLAG,
                flag.kind.value,
                (str(flag.id),),
                PRIORITY_MEDICINE_CHANGE,
            )
        return Proposed(
            CHANGE_TEMPLATE.get(flag.code, "ask_medicine_change"),
            {"doctor": doctor, "medicine": visit.medicine(flag.subject)},
            QuestionSource.FLAG,
            flag.kind.value,
            (str(flag.id),),
            PRIORITY_MEDICINE_CHANGE,
        )
    return None


def question_from_memo(memo: Memo) -> Proposed:
    return Proposed(
        memo.key,
        dict(memo.slots),
        QuestionSource.MEMO,
        memo.kind.value,
        (str(memo.id),),
        PRIORITY_MEMO,
    )


async def propose_questions(
    session: AsyncSession, *, context: KeyContext, visit: Visit
) -> list[Proposed]:
    """Every question the record suggests for this visit, by priority, without duplicates.

    Flags first — a red flag before anything else, then a medicine change heard — then the
    gaps, then the memos that ask the doctor something.
    """
    # The flags a visit wrote — a red-flag word heard, a medicine change heard. A flag from
    # the feeling cloud (no transcript, a feeling) is the feed's to escalate (E21), not a
    # question here.
    flags = await audited_read(
        session,
        Flag,
        context,
        Scope.RECORDS,
        where=(Flag.resolved_at.is_(None), Flag.feeling.is_(None)),
    )
    if visit.registry is None:
        raise NoRegistry("proposing questions needs the licensed drug data for his names")
    gaps = await find_gaps(
        session, context=context, registry=visit.registry, appointment_id=visit.appointment.id
    )
    memos = await current_memos(session, context=context)
    proposed: list[Proposed] = []
    for flag in sorted(flags, key=lambda f: (as_utc(f.raised_at), str(f.id))):
        one = question_from_flag(flag, visit)
        if one is not None:
            proposed.append(one)
    proposed.extend(question_from_gap(gap, visit) for gap in gaps)
    proposed.extend(
        question_from_memo(memo)
        for memo in memos
        if memo.kind is MemoKind.ASK and memo.language == visit.language
    )
    seen: set[tuple[str, str]] = set()
    unique: list[Proposed] = []
    for one in sorted(proposed, key=lambda p: p.priority):
        mark = (one.key, _slots_json(one.slots))
        if mark not in seen:
            seen.add(mark)
            unique.append(one)
    return unique


def render_proposed(one: Proposed, language: str) -> str:
    return say(one.key, language, **one.slots)


async def _rows(
    session: AsyncSession, *, context: KeyContext, appointment_id: uuid.UUID
) -> Sequence[Question]:
    return await audited_read(
        session, Question, context, Scope.VISITS, where=(Question.appointment_id == appointment_id,)
    )


def _current(rows: Sequence[Question]) -> list[Question]:
    return sorted(
        (q for q in rows if q.superseded_at is None and not q.removed),
        key=lambda q: (q.priority, as_utc(q.created_at), str(q.id)),
    )


@audited(Action.READ, Scope.VISITS, QUESTION)
async def current_questions(
    session: AsyncSession, *, context: KeyContext, appointment_id: uuid.UUID
) -> Sequence[Question]:
    """The current questions as they stand: the unsuperseded rows, by priority. A read and
    nothing else — what `GET …/questions` answers with. The list is refreshed from the
    record when the brief is built (`brief.build_brief`) and changed by a person."""
    await require_visit(session, context=context, appointment_id=appointment_id)
    return _current(await _rows(session, context=context, appointment_id=appointment_id))


@audited(Action.WRITE, Scope.VISITS, QUESTION)
async def questions_for(
    session: AsyncSession,
    *,
    context: KeyContext,
    appointment_id: uuid.UUID,
    registry: DrugRegistry,
) -> Sequence[Question]:
    """The current questions for this visit, refreshed from the record.

    A generated question already on the list stands; a new one is written, rendered through
    its template and the verifier; one whose source has gone is superseded. One a person
    removed is not proposed again. The person's own questions stand as he wrote them. A
    write: only a key that may change the visits refreshes the list.
    """
    may_change_visits(context)
    visit = await require_visit(
        session, context=context, appointment_id=appointment_id, registry=registry
    )
    state = await current_state(session, context=context)
    rows = await _rows(session, context=context, appointment_id=appointment_id)
    current = _current(rows)
    removed_marks = {(q.key, _slots_json(q.slots)) for q in rows if q.removed}
    proposed = await propose_questions(session, context=context, visit=visit)
    moment = utcnow()

    generated = [q for q in current if q.source is not QuestionSource.PERSON]
    for question in generated:
        if not any(one.same_as(question) for one in proposed):
            question.superseded_at = moment
            await session.flush()
            await record(
                session,
                context=context,
                action=Action.WRITE,
                scope=Scope.VISITS,
                target=QUESTION,
                target_id=question.id,
                rows=1,
            )
    for one in proposed:
        if (one.key, _slots_json(one.slots)) in removed_marks:
            continue
        if any(one.same_as(question) for question in generated):
            continue
        await _write(session, context=context, visit=visit, state=state, proposed=one)
    return _current(await _rows(session, context=context, appointment_id=appointment_id))


async def _write(
    session: AsyncSession,
    *,
    context: KeyContext,
    visit: Visit,
    state: StateView,
    proposed: Proposed,
    text: str | None = None,
    added_by_person_id: uuid.UUID | None = None,
    supersedes_id: uuid.UUID | None = None,
    removed: bool = False,
) -> Question:
    line = text if text is not None else render_proposed(proposed, visit.language)
    # A question about two medicines together is the interaction surface; every other one
    # is the questions surface (E16-01). Each row carries its line.
    surface = (
        Surface.INTERACTION_FLAG
        if proposed.source_kind == GapKind.INTERACTION_FLAGGED.value
        else Surface.QUESTIONS
    )
    return await render_from_state(
        session,
        Question,
        context,
        Scope.VISITS,
        state=state,
        surface=surface,
        boundary=boundary_line(surface, visit.language, doctor=visit.doctor),
        appointment_id=visit.appointment.id,
        language=visit.language,
        source=proposed.source,
        source_kind=proposed.source_kind,
        source_ids=list(proposed.source_ids),
        key=proposed.key,
        slots=proposed.slots,
        text=line,
        priority=proposed.priority,
        added_by_person_id=added_by_person_id,
        removed=removed,
        supersedes_id=supersedes_id,
        created_at=utcnow(),
    )


def _own_words(text: str) -> str:
    line = " ".join(text.split())
    if not line or len(line) > LINE_LENGTH:
        raise NotAQuestion(f"a question is one line of at most {LINE_LENGTH} characters")
    return line


async def _current_question(
    session: AsyncSession, *, context: KeyContext, appointment_id: uuid.UUID, question_id: uuid.UUID
) -> Question:
    rows = await _rows(session, context=context, appointment_id=appointment_id)
    for question in _current(rows):
        if question.id == question_id:
            return question
    raise NoSuchQuestion(f"no current question {question_id} on appointment {appointment_id}")


async def question_draft_for(
    session: AsyncSession,
    *,
    context: KeyContext,
    appointment_id: uuid.UUID,
    text: str | None,
    question_id: uuid.UUID | None,
    remove: bool,
) -> QuestionDraft:
    """What the person is saying yes to: this visit, these words (or a removal), and the
    question it replaces. The surface mints the confirmation over this."""
    visit = await require_visit(session, context=context, appointment_id=appointment_id)
    if question_id is not None:
        await _current_question(
            session, context=context, appointment_id=appointment_id, question_id=question_id
        )
    if remove:
        if question_id is None:
            raise NoSuchQuestion("a removal names the question it removes")
        return QuestionDraft(appointment_id, "", visit.language, question_id, True)
    if text is None:
        raise NotAQuestion("a question says something")
    return QuestionDraft(appointment_id, _own_words(text), visit.language, question_id, False)


@audited(Action.WRITE, Scope.VISITS, QUESTION)
async def change_questions(
    session: AsyncSession,
    *,
    context: KeyContext,
    appointment_id: uuid.UUID,
    confirmation_id: uuid.UUID,
    text: str | None = None,
    question_id: uuid.UUID | None = None,
    remove: bool = False,
) -> Question:
    """A person adds a question, edits one, or removes one, with his yes for exactly that.

    His words go through the verifier like every other line: a question that is not plain
    is refused (`NotPlainEnough`) before anything is written or spent. An edit or a removal
    is a new row superseding the old, so the list is always the unsuperseded rows.
    """
    may_change_visits(context)
    draft = await question_draft_for(
        session,
        context=context,
        appointment_id=appointment_id,
        text=text,
        question_id=question_id,
        remove=remove,
    )
    visit = await require_visit(session, context=context, appointment_id=appointment_id)
    if not draft.removed:
        verified(draft.text, visit.language)
    state = await current_state(session, context=context)
    old = None
    if draft.supersedes_id is not None:
        old = await _current_question(
            session, context=context, appointment_id=appointment_id, question_id=draft.supersedes_id
        )
    yes = await consume_confirmation(session, context, confirmation_id, draft)
    proposed = Proposed(
        key="own_words" if not draft.removed else (old.key if old else "own_words"),
        slots={} if not draft.removed else (dict(old.slots) if old else {}),
        source=QuestionSource.PERSON,
        source_kind="removed" if draft.removed else "typed",
        source_ids=(str(yes.person_id),),
        priority=PRIORITY_PERSON if old is None else old.priority,
    )
    new = await _write(
        session,
        context=context,
        visit=visit,
        state=state,
        proposed=proposed,
        text=draft.text if not draft.removed else (old.text if old else ""),
        added_by_person_id=yes.person_id,
        supersedes_id=draft.supersedes_id,
        removed=draft.removed,
    )
    if old is not None:
        old.superseded_at = utcnow()
        await session.flush()
        await record(
            session,
            context=context,
            action=Action.WRITE,
            scope=Scope.VISITS,
            target=QUESTION,
            target_id=old.id,
            rows=1,
        )
    return new


@audited(Action.READ, Scope.VISITS, QUESTION)
async def patient_card(
    session: AsyncSession, *, context: KeyContext, appointment_id: uuid.UUID
) -> list[str]:
    """One card for him: the first three questions by priority, the line that says he need
    not remember them, and the boundary line the questions carry (E16-01). Every line
    verified again on the way out."""
    visit = await require_visit(session, context=context, appointment_id=appointment_id)
    current = _current(await _rows(session, context=context, appointment_id=appointment_id))
    lines = [verified(q.text, q.language) for q in current[:CARD_SIZE]]
    lines.append(say("no_need_to_remember", visit.language))
    lines.extend(boundary_lines(Surface.QUESTIONS, visit.language, doctor=visit.doctor))
    return lines


def spoken_card(lines: Sequence[str]) -> list[str]:
    """The card as it is read aloud: the same lines, the bracketed chemical names dropped."""
    return [spoken(line) for line in lines]


__all__ = [
    "CARD_SIZE",
    "GapWithoutItsOther",
    "NoRegistry",
    "NoSuchQuestion",
    "NotAQuestion",
    "Proposed",
    "Visit",
    "change_questions",
    "current_questions",
    "patient_card",
    "propose_questions",
    "question_draft_for",
    "questions_for",
    "render",
    "require_visit",
]
