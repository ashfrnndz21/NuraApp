"""Kept questions go to the visit (E01-02 with E05-02).

A question the papers raised that he keeps is a question for the doctor. When the profile has
a visit coming, keeping it puts it on that visit's list at once — an E05 `Question`, written
by E05's own `change_questions` on the yes of the person keeping it, for exactly that line
(`QuestionDraft`), so it is verified, rendered from State and carries the boundary line like
every question on the list. Keeping it again later changes nothing; saying "not this one"
after it went takes it off the list the same way, as a removal with its own yes.

With no visit on the record — Day 0, for most people — the kept question waits on the sitting
(`BiographyQuestion` with no `question_id`). The moment a visit is booked, by any route (the
timeline, a calendar proposal, a summary's follow-up — all of them go through
`app.memory.spine.book_appointment`), `hand_over_on_booking` puts every waiting kept question
on that visit's list in the same unit of work, under the booker's key, on the booker's yes,
each step on the trail. The row names the question it became.

The hand-over needs what writing a visit's question needs: the record, the visits, and the
scopes a State recompute reads (`RECOMPUTE_SCOPES`). A key without them — a helper's —
leaves the questions waiting for the next booking or the next keep by someone who has them.
A refusal from the visit loop (a line it will not take) leaves that one question waiting, on
the trail; it never refuses the booking.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_read
from app.audit.models import Action
from app.audit.trail import record
from app.db import as_utc, utcnow
from app.errors import Refusal
from app.keys.confirm import confirm
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.memory.models import Appointment
from app.memory.spine import UPCOMING, upcoming_appointments
from app.onboarding.models import QUESTION_IN_PROGRESS, BiographyQuestion
from app.onboarding.words import question
from app.reasoning.visits.models import Question
from app.reasoning.visits.questions import change_questions, question_draft_for, require_visit
from app.state.service import RECOMPUTE_SCOPES

HANDS_OVER = RECOMPUTE_SCOPES | {Scope.RECORDS, Scope.VISITS}
"""What a key must open to put a kept question on a visit's list."""

QUESTION = BiographyQuestion.__tablename__


def can_hand_over(context: KeyContext) -> bool:
    return HANDS_OVER <= context.scopes


async def asked_at(
    session: AsyncSession, *, context: KeyContext, row: BiographyQuestion
) -> Question | None:
    """The visit's question this kept one became, while it is still on that list."""
    if row.question_id is None or not context.allows(Scope.VISITS):
        return None
    found = await audited_read(
        session, Question, context, Scope.VISITS, where=(Question.id == row.question_id,)
    )
    asked = found[0] if found else None
    return (
        asked if asked is not None and asked.superseded_at is None and not asked.removed else None
    )


async def _to_visit(
    session: AsyncSession, *, context: KeyContext, row: BiographyQuestion, appointment_id: object
) -> Question | None:
    visit = await require_visit(session, context=context, appointment_id=appointment_id)  # type: ignore[arg-type]
    line = question(row.gap, visit.language, visit.doctor)
    if line is None:
        return None
    draft = await question_draft_for(
        session,
        context=context,
        appointment_id=visit.appointment.id,
        text=line,
        question_id=None,
        remove=False,
    )
    yes = await confirm(session, context, draft)
    asked = await change_questions(
        session,
        context=context,
        appointment_id=visit.appointment.id,
        confirmation_id=yes.id,
        text=line,
    )
    session.info[QUESTION_IN_PROGRESS] = row.id
    try:
        row.question_id = asked.id
        row.handed_over_at = utcnow()
        await session.flush()
        await record(
            session,
            context=context,
            action=Action.WRITE,
            scope=Scope.RECORDS,
            target=QUESTION,
            target_id=row.id,
            rows=1,
        )
    finally:
        session.info.pop(QUESTION_IN_PROGRESS, None)
    return asked


async def keep_at_visit(
    session: AsyncSession, *, context: KeyContext, row: BiographyQuestion
) -> Question | None:
    """A kept question goes to the next visit now, if there is one and it is not there yet."""
    if not can_hand_over(context) or await asked_at(session, context=context, row=row):
        return None
    coming = await upcoming_appointments(session, context=context, limit=1)
    if not coming:
        return None
    return await _to_visit(session, context=context, row=row, appointment_id=coming[0].id)


async def withdraw(session: AsyncSession, *, context: KeyContext, row: BiographyQuestion) -> None:
    """Not kept any more: off the visit's list, as a removal on the person's own yes."""
    if not can_hand_over(context):
        return
    asked = await asked_at(session, context=context, row=row)
    if asked is None:
        return
    draft = await question_draft_for(
        session,
        context=context,
        appointment_id=asked.appointment_id,
        text=None,
        question_id=asked.id,
        remove=True,
    )
    yes = await confirm(session, context, draft)
    await change_questions(
        session,
        context=context,
        appointment_id=asked.appointment_id,
        confirmation_id=yes.id,
        question_id=asked.id,
        remove=True,
    )


async def hand_over_on_booking(
    session: AsyncSession, context: KeyContext, appointment: Appointment
) -> None:
    """Registered on `app.memory.spine.after_appointment_booked`: every kept question still
    waiting goes on the list of the visit just booked, if it is one still to come."""
    if appointment.status not in UPCOMING or as_utc(appointment.scheduled_at) < utcnow():
        return
    if not can_hand_over(context):
        return
    waiting = await audited_read(
        session,
        BiographyQuestion,
        context,
        Scope.RECORDS,
        where=(BiographyQuestion.kept.is_(True), BiographyQuestion.question_id.is_(None)),
    )
    for row in sorted(waiting, key=lambda one: (as_utc(one.decided_at), one.gap)):
        try:
            await _to_visit(session, context=context, row=row, appointment_id=appointment.id)
        except Refusal:
            # The visit loop would not take this line: it waits, and the refusal is on the
            # trail. A booking is never refused for a question.
            continue
