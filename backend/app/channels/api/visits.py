"""The visit loop over HTTP (E05-01, E05-02, E05-05, E05-06).

    POST /profiles/{id}/providers                                a doctor in the profile's directory
    GET  /profiles/{id}/providers
    POST /profiles/{id}/appointments                             write a visit down, with the yes for it
    GET  /profiles/{id}/appointments                             the visits still to come
    GET  /profiles/{id}/appointments/{appt}/brief                the pre-visit brief, in his language
    GET  /profiles/{id}/appointments/{appt}/questions            the questions, and his one card
    POST /profiles/{id}/appointments/{appt}/questions            add, edit or remove one, with the yes
    POST /profiles/{id}/appointments/{appt}/transcript           the transcript in; the summary card out
    GET  /profiles/{id}/appointments/{appt}/summaries            the cards for this visit
    POST /profiles/{id}/appointments/{appt}/summary/{card}/confirm  the yes: memos, visits, facts, flags
    GET  /profiles/{id}/memos                                    the memo card

Every route takes the key context like every other profile route. Briefs, questions, cards
and memos are under the visits scope; the transcript is an artefact under the record's; a
fact a card writes is held under its own subject's scope. The yes is minted at
`POST /profiles/{id}/confirmations` with subject `appointment`, `question` or `visit_summary`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, status

from app.channels.api.deps import Context, Db, providers_of
from app.channels.api.schemas import (
    AppointmentOut,
    BriefOut,
    FactOut,
    MemoCardOut,
    MemoOut,
    QuestionChangeIn,
    QuestionOut,
    QuestionsOut,
    SummaryConfirmBodyIn,
    SummaryConfirmedOut,
    SummaryOut,
    TranscriptIn,
)
from app.db import utcnow
from app.memory.spine import upcoming_appointments
from app.reasoning.visits.brief import brief_for
from app.reasoning.visits.guard import can_change_visits
from app.reasoning.visits.memos import consolidate_memos, current_memos, memo_card
from app.reasoning.visits.questions import (
    change_questions,
    current_questions,
    patient_card,
    spoken_card,
)
from app.reasoning.visits.summary import (
    NoSuchSummary,
    confirm_summary,
    list_summaries,
    post_visit_summary,
    require_summary,
    store_transcript,
    summary_items,
)

router = APIRouter(prefix="/profiles", tags=["visits"])


@router.get("/{profile_id}/appointments")
async def appointments(context: Context, session: Db) -> list[AppointmentOut]:
    """The visits still to come, soonest first."""
    return [AppointmentOut.of(one) for one in await upcoming_appointments(session, context=context)]


@router.get("/{profile_id}/appointments/{appointment_id}/brief")
async def brief(
    appointment_id: uuid.UUID, request: Request, context: Context, session: Db
) -> BriefOut:
    """The pre-visit brief in the profile's language: purpose, what changed since the last
    visit, the open questions, what to bring. Rebuilt when State has moved past the last
    one. Every line passed the plain-words verifier; a brief that would not is refused
    (`NotPlainEnough`, 400) rather than shown."""
    return BriefOut.of(
        await brief_for(
            session,
            context=context,
            appointment_id=appointment_id,
            registry=providers_of(request).drug_registry,
        )
    )


@router.get("/{profile_id}/appointments/{appointment_id}/questions")
async def questions(appointment_id: uuid.UUID, context: Context, session: Db) -> QuestionsOut:
    """The current questions for this visit, each with its source, and the one card for him
    — the first three by priority. A read: the list is refreshed from gaps, memos and flags
    when the brief is built (`GET …/brief`), and changed by `POST …/questions`."""
    found = await current_questions(session, context=context, appointment_id=appointment_id)
    card = await patient_card(session, context=context, appointment_id=appointment_id)
    return QuestionsOut(
        questions=[QuestionOut.of(one) for one in found], card=card, spoken_card=spoken_card(card)
    )


@router.post("/{profile_id}/appointments/{appointment_id}/questions", status_code=201)
async def change_question(
    appointment_id: uuid.UUID, body: QuestionChangeIn, context: Context, session: Db
) -> QuestionOut:
    """A person adds, edits or removes a question with the yes minted for exactly that. His
    words pass the verifier or are refused (`NotPlainEnough`, 400)."""
    question = await change_questions(
        session,
        context=context,
        appointment_id=appointment_id,
        confirmation_id=body.confirmation_id,
        text=body.text,
        question_id=body.question_id,
        remove=body.remove,
    )
    return QuestionOut.of(question)


@router.post(
    "/{profile_id}/appointments/{appointment_id}/transcript", status_code=status.HTTP_201_CREATED
)
async def transcript(
    appointment_id: uuid.UUID, body: TranscriptIn, request: Request, context: Context, session: Db
) -> SummaryOut:
    """The transcript in: its text goes to the region's store as an artefact, the summariser
    reads it, and the answer is the card — actions, a medicine change as a question for the
    doctor, follow-ups, facts heard — with `red_flag` set and the same-day line first when
    a red-flag word was heard. Nothing is a memo, a booking or a fact yet."""
    served = providers_of(request)
    artifact = await store_transcript(
        session,
        context=context,
        store=served.object_store,
        text=body.as_text(),
        captured_at=body.captured_at or utcnow(),
    )
    summary = await post_visit_summary(
        session,
        context=context,
        appointment_id=appointment_id,
        artifact_id=artifact.id,
        store=served.object_store,
        summariser=served.summariser,
        registry=served.drug_registry,
    )
    return SummaryOut.of(
        summary, await summary_items(session, context=context, summary_id=summary.id)
    )


@router.get("/{profile_id}/appointments/{appointment_id}/summaries")
async def summaries(appointment_id: uuid.UUID, context: Context, session: Db) -> list[SummaryOut]:
    found = await list_summaries(session, context=context, appointment_id=appointment_id)
    return [
        SummaryOut.of(one, await summary_items(session, context=context, summary_id=one.id))
        for one in found
    ]


@router.post("/{profile_id}/appointments/{appointment_id}/summary/{summary_id}/confirm")
async def confirm_card(
    appointment_id: uuid.UUID,
    summary_id: uuid.UUID,
    body: SummaryConfirmBodyIn,
    request: Request,
    context: Context,
    session: Db,
) -> SummaryConfirmedOut:
    """Close the card on the yes minted for exactly these decisions: actions become memos, a
    medicine change becomes a flag and a memo asking the doctor (never a change), follow-ups
    become planned visits, facts heard become facts citing the transcript."""
    # The card must be the visit's in the path: a summary of another visit is not here.
    found = await require_summary(session, context=context, summary_id=summary_id)
    if found.appointment_id != appointment_id:
        raise NoSuchSummary(f"summary {summary_id} is not on appointment {appointment_id}")
    outcome = await confirm_summary(
        session,
        context=context,
        summary_id=summary_id,
        decisions=[one.as_decision() for one in body.decisions],
        confirmation_id=body.confirmation_id,
        registry=providers_of(request).drug_registry,
    )
    return SummaryConfirmedOut(
        summary=SummaryOut.of(outcome.summary, outcome.items),
        memos=[MemoOut.of(one) for one in outcome.memos],
        appointments=[AppointmentOut.of(one) for one in outcome.appointments],
        facts=[FactOut.of(one) for one in outcome.facts],
        flag_ids=[one.id for one in outcome.flags],
    )


@router.get("/{profile_id}/memos")
async def memos(context: Context, session: Db) -> MemoCardOut:
    """The memo card at the end of every conversation: the current memos, duplicates
    collapsed, every line verified on the way out."""
    current = (
        await consolidate_memos(session, context=context)
        if can_change_visits(context)
        else await current_memos(session, context=context)
    )
    card = await memo_card(session, context=context)
    return MemoCardOut(
        memos=[MemoOut.of(one) for one in current], card=card, spoken_card=spoken_card(card)
    )
