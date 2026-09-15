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
    GET  /profiles/{id}/appointments/{appt}/logistics            time, place, parking, driver, bring (E05-03)
    POST /profiles/{id}/appointments/{appt}/driver               the chief's yes: who drives him
    GET  /profiles/{id}/appointments/{appt}/recording/notice     the gate, then the notice (E16-02)
    POST /profiles/{id}/appointments/{appt}/recording            the recording's bytes, on Stop (E02-05)
    GET  /profiles/{id}/appointments/{appt}/recordings           the recordings kept, who spoke when
    GET  /profiles/{id}/artifacts/{artifact}/clip?start=&end=    a stretch of one (E03-05)
    POST /profiles/{id}/transcripts/search                       words said at a confirmed visit (E02-05)

Every route takes the key context like every other profile route. Briefs, questions, cards
and memos are under the visits scope; the transcript is an artefact under the record's; a
fact a card writes is held under its own subject's scope. The yes is minted at
`POST /profiles/{id}/confirmations` with subject `appointment`, `question` or `visit_summary`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Request, Response, status
from pydantic import AwareDatetime

from app.audit.access import audited_guard, audited_read
from app.audit.models import Action
from app.channels.api.delivery import via_of
from app.channels.api.deps import Context, CurrentPerson, Db, providers_of
from app.channels.api.schemas import (
    AppointmentOut,
    BriefOut,
    ConsultOut,
    DriverIn,
    FactOut,
    LogisticsOut,
    MemoCardOut,
    MemoOut,
    NoticeOut,
    QuestionChangeIn,
    QuestionOut,
    QuestionsOut,
    RecordingOut,
    SummaryConfirmBodyIn,
    SummaryConfirmedOut,
    SummaryOut,
    TaskOut,
    TranscriptIn,
)
from app.channels.api.timeline_schemas import TranscriptSearchIn, TranscriptSearchOut
from app.channels.api.uploads import Cap, read_capped
from app.db import utcnow
from app.ingestion.consult import (
    CONSULT,
    MAX_CONSULT_BYTES,
    ConsultTooLong,
    consult_clip,
    notice_for,
    record_consult,
    recordings_for,
)
from app.keys.scopes import Scope
from app.memory.models import Provider
from app.memory.spine import upcoming_appointments
from app.reasoning.visits.brief import brief_for
from app.reasoning.visits.guard import can_change_visits
from app.reasoning.visits.logistics import assign_driver, logistics_for
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
from app.search.transcripts import search_transcripts

router = APIRouter(prefix="/profiles", tags=["visits"])


@router.get("/{profile_id}/appointments")
async def appointments(context: Context, session: Db) -> list[AppointmentOut]:
    """The visits still to come, soonest first, each with its doctor's name as the family wrote
    it — read under the visits scope, as the visits are."""
    upcoming = await upcoming_appointments(session, context=context)
    if not upcoming:
        return []
    names = {
        one.id: one.name for one in await audited_read(session, Provider, context, Scope.VISITS)
    }
    return [AppointmentOut.of(one, doctor=names.get(one.provider_id)) for one in upcoming]


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
        via=via_of(request),
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


# --- the visit day (E05-03, E05-04, E02-05, E03-05) ------------------------------------------


@router.get("/{profile_id}/appointments/{appointment_id}/logistics")
async def logistics(
    appointment_id: uuid.UUID, request: Request, context: Context, session: Db
) -> LogisticsOut:
    """The logistics card: when (his day, his clock), where (the doctor's address), the
    chief's note about the place under her name, who drives him — the task given, or the
    roster's person on duty then as a suggestion waiting for the chief's yes — and what to
    bring. Every line he reads passed the verifier; the card names the State it came from."""
    return LogisticsOut.of(
        await logistics_for(
            session,
            context=context,
            appointment_id=appointment_id,
            registry=providers_of(request).drug_registry,
        )
    )


@router.post(
    "/{profile_id}/appointments/{appointment_id}/driver", status_code=status.HTTP_201_CREATED
)
async def driver(
    appointment_id: uuid.UUID, body: DriverIn, context: Context, session: Db
) -> TaskOut:
    """On the chief's yes (subject `drive`), the family task "drive Pa to Dr Tan", given to
    that person and naming the visit. Refused to anyone but the owner and his chief."""
    return TaskOut.of(
        await assign_driver(
            session,
            context=context,
            appointment_id=appointment_id,
            person_id=body.person_id,
            confirmation_id=body.confirmation_id,
        )
    )


@router.get("/{profile_id}/appointments/{appointment_id}/recording/notice")
async def recording_notice(
    appointment_id: uuid.UUID, person: CurrentPerson, context: Context, session: Db
) -> NoticeOut:
    """What the Start button asks first. A key that does not change the visits is refused;
    then the gate — the RECORDING consent in force, the records scope held — refuses on the
    trail (`ConsentWithheld`, 403) before the room is told anything; only then the notice,
    to the doctor by name, the printed card, and the words for a no."""
    writer = None if context.is_owner else person.display_name
    return NoticeOut.of(
        await notice_for(session, context=context, appointment_id=appointment_id, writer=writer)
    )


@router.post(
    "/{profile_id}/appointments/{appointment_id}/recording", status_code=status.HTTP_201_CREATED
)
async def recording(
    appointment_id: uuid.UUID,
    request: Request,
    context: Context,
    session: Db,
    duration_s: float = Query(),
    started_at: AwareDatetime | None = None,
) -> ConsultOut:
    """The recording, sent once on Stop: the body is the recorder's own bytes (`audio/webm`,
    `audio/ogg` or `audio/mp4`), `duration_s` how long the phone listened, `started_at` when it
    began, with its offset (a time without one is a 422, ADR 0009). Kept as a consult
    VOICE artefact in the region, heard, separated by speaker, and read into the post-visit
    card with each line's place in the recording. A body declared bigger than a visit is
    refused before it is read, and one that runs past the cap is refused as it arrives, with
    nothing of it kept (#133); both on the trail."""
    # Refused on the trail where the recording would have been kept: a visit's (ADR 0004).
    async with audited_guard(session, context, Action.WRITE, Scope.VISITS, CONSULT):
        data = await read_capped(
            request.stream(),
            Cap(MAX_CONSULT_BYTES, ConsultTooLong),
            declared=request.headers.get("content-length"),
        )
    served = providers_of(request)
    outcome = await record_consult(
        session,
        context=context,
        appointment_id=appointment_id,
        data=data,
        content_type=request.headers.get("content-type", ""),
        duration_s=duration_s,
        started_at=started_at,
        store=served.object_store,
        transcriber=served.transcriber,
        separator=served.speaker_separator,
        summariser=served.summariser,
        registry=served.drug_registry,
    )
    return ConsultOut(
        recording=RecordingOut.of(outcome.recording, outcome.segments),
        summary=None if outcome.summary is None else SummaryOut.of(outcome.summary, outcome.items),
        summary_refused=outcome.summary_refused,
    )


@router.get("/{profile_id}/appointments/{appointment_id}/recordings")
async def recordings(
    appointment_id: uuid.UUID, context: Context, session: Db
) -> list[RecordingOut]:
    """Every recording of this visit, newest first, with who spoke when. No words."""
    found = await recordings_for(session, context=context, appointment_id=appointment_id)
    return [RecordingOut.of(recording, segments) for recording, segments in found]


@router.get("/{profile_id}/artifacts/{artifact_id}/clip")
async def clip(
    artifact_id: uuid.UUID,
    request: Request,
    context: Context,
    session: Db,
    start: float = Query(ge=0),
    end: float = Query(gt=0),
) -> Response:
    """The stretch `start`–`end` of a consult recording that a summary line or an answer
    cites. The whole recording comes back — a phone's webm or mp4 is not cut at a byte offset
    without a demuxer — with the stretch in `X-Clip-Start`/`X-Clip-End` and as the media
    fragment the phone plays (`#t=start,end`, `X-Media-Fragment`); the phone stops at the end.
    Under the visits scope, where a consult recording and its bytes are written (ADR 0004):
    a key that reads the visits hears it; any other is refused at the door, on the trail."""
    found = await consult_clip(
        session,
        context=context,
        store=providers_of(request).object_store,
        artifact_id=artifact_id,
        start_s=start,
        end_s=end,
    )
    fragment = f"t={found.start_s:g},{found.end_s:g}"
    return Response(
        content=found.data,
        media_type=found.artifact.content_type,
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": "inline",
            "X-Clip-Start": f"{found.start_s:g}",
            "X-Clip-End": f"{found.end_s:g}",
            "X-Media-Fragment": fragment,
        },
    )


@router.post("/{profile_id}/transcripts/search")
async def transcript_search(
    body: TranscriptSearchIn, request: Request, context: Context, session: Db
) -> TranscriptSearchOut:
    """Where these words were said in the recording of a visit whose card he confirmed: the
    sentence as heard, which visit in his words, and the stretch of the recording to play
    (`…/artifacts/{artifact}/clip`). For him and the family he let in; a viewer, a clinic or
    a helper is refused by name, on the trail. The words searched are not kept (E02-05)."""
    found = await search_transcripts(
        session,
        context=context,
        store=providers_of(request).object_store,
        searched=body.words,
        language=body.language,
    )
    return TranscriptSearchOut.of(found)
