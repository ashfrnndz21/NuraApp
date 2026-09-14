"""The feeling cloud, feeling inference, the smart nudges and the Me page over HTTP (E17).

    GET  /profiles/{id}/feelings/cloud?language=         the words, weighed from State, and whether they show
    POST /profiles/{id}/feelings                         a tap; a red word takes the red-flag path first
    POST /profiles/{id}/feelings/{tap}/answer            his one answer; a note, or the red-flag path
    GET  /profiles/{id}/feelings/notes                   the notes, newest first
    GET  /profiles/{id}/nudges/plan?day=                 the day's nudges: what goes, what is held and why
    POST /profiles/{id}/nudges/plan?day=                 hand the day's nudge to delivery (sends nothing)
    POST /profiles/{id}/nudges/{nudge}/response          seen, accepted, dismissed
    GET  /profiles/{id}/nudge-metrics?weeks=             counts per week, for the owner and his chief
    GET  /profiles/{id}/me-summary?language=             the Me page: the number that only goes up

Every route takes the key context. The tap moved here from the feed's routes (E21) and keeps
their promise: a red word is written, flagged and escalated before anything else happens.
"""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Query, Request, status

from app.audit.access import audited_profile_read
from app.channels.api.deps import Context, Db, providers_of
from app.channels.api.feelings_schemas import (
    AnsweredOut,
    AnswerIn,
    CloudOut,
    FeelingIn,
    FeelingOut,
    HandedOverOut,
    MeSummaryOut,
    NoteOut,
    NudgeMetricsOut,
    NudgeOut,
    NudgePlanOut,
    NudgeResponseIn,
    NudgeResponseOut,
)
from app.delivery.nudges.engine import hand_over, plan_nudges, respond
from app.delivery.nudges.metrics import nudge_metrics
from app.delivery.nudges.strings import recognition_lines
from app.medicines.service import proud_days
from app.reasoning.feelings.cloud import compose_cloud
from app.reasoning.feelings.service import answer_tap, recent_notes, record_tap
from app.reasoning.feelings.strings import language_of

router = APIRouter(prefix="/profiles", tags=["feelings"])

Language = Query(default=None, min_length=2, max_length=16)


@router.get("/{profile_id}/feelings/cloud")
async def cloud(
    request: Request, context: Context, session: Db, language: str | None = Language
) -> CloudOut:
    """The feeling cloud now: base words, what State brings forward and why (by code and id),
    whether the strip shows (only after a change, at most once a day), and the question."""
    registry = providers_of(request).drug_registry
    return CloudOut.of(
        await compose_cloud(session, context=context, registry=registry, language=language)
    )


@router.post("/{profile_id}/feelings", status_code=status.HTTP_201_CREATED)
async def feeling(body: FeelingIn, request: Request, context: Context, session: Db) -> FeelingOut:
    """A tap on the feeling cloud. A red word is written as the moment it was said, flagged —
    the family holding the emergency scope told — and the ladder written, before anything
    else; it asks nothing and no note follows. Any other word asks one thing back."""
    tapped = await record_tap(
        session,
        context=context,
        word=body.word,
        registry=providers_of(request).drug_registry,
        store=providers_of(request).object_store,
        transcriber=providers_of(request).transcriber,
        language=body.language,
    )
    return FeelingOut.of(tapped)


@router.post("/{profile_id}/feelings/{tap_id}/answer", status_code=status.HTTP_201_CREATED)
async def answer(
    tap_id: uuid.UUID, body: AnswerIn, request: Request, context: Context, session: Db
) -> AnsweredOut:
    """His one answer. Read against his medicines, his blood pressure and this week into a
    note ending on the boundary line — or, a yes that makes the word red, the red-flag path."""
    answered = await answer_tap(
        session,
        context=context,
        tap_id=tap_id,
        answer=body.answer,
        registry=providers_of(request).drug_registry,
        store=providers_of(request).object_store,
        transcriber=providers_of(request).transcriber,
        language=body.language,
    )
    return AnsweredOut.of(answered)


@router.get("/{profile_id}/feelings/notes")
async def notes(context: Context, session: Db) -> list[NoteOut]:
    return [NoteOut.of(note) for note in await recent_notes(session, context=context)]


@router.get("/{profile_id}/nudges/plan")
async def nudge_plan(
    request: Request, context: Context, session: Db, day: date | None = None
) -> NudgePlanOut:
    """The nudges for `day` (today by default): the one that goes, and every one held with
    why — one a day, resting after two ignored, or none at all on a red-flag day or at night."""
    plan = await plan_nudges(
        session, context=context, registry=providers_of(request).drug_registry, day=day
    )
    return NudgePlanOut.of(plan)


@router.post("/{profile_id}/nudges/plan", status_code=status.HTTP_201_CREATED)
async def nudge_hand_over(
    request: Request, context: Context, session: Db, day: date | None = None
) -> HandedOverOut:
    """Write the day's nudge down and hand it to delivery (E11). Nothing is sent from here."""
    plan, nudge = await hand_over(
        session, context=context, registry=providers_of(request).drug_registry, day=day
    )
    return HandedOverOut(plan=NudgePlanOut.of(plan), nudge=NudgeOut.of(nudge))


@router.post("/{profile_id}/nudges/{nudge_id}/response", status_code=status.HTTP_201_CREATED)
async def nudge_response(
    nudge_id: uuid.UUID, body: NudgeResponseIn, context: Context, session: Db
) -> NudgeResponseOut:
    return NudgeResponseOut.of(
        await respond(session, context=context, nudge_id=nudge_id, kind=body.kind)
    )


@router.get("/{profile_id}/nudge-metrics")
async def metrics(
    context: Context, session: Db, weeks: int = Query(default=4, ge=1, le=12)
) -> NudgeMetricsOut:
    """Counts per week for the owner and his chief: taps, "Fine today" and its share, and
    acceptance by kind of nudge. No health content; every read is on his trail."""
    return NudgeMetricsOut.of(await nudge_metrics(session, context=context, weeks=weeks))


@router.get("/{profile_id}/me-summary")
async def me_summary(
    context: Context, session: Db, language: str | None = Language
) -> MeSummaryOut:
    """The Me page: the number that only goes up — days with a tablet taken, counted by the
    backend from the DOSE_TAKEN events (`GET /profiles/{id}/proud`) — in his words."""
    profile = await audited_profile_read(session, context)
    code = language_of(language or profile.language)
    counted = await proud_days(session, context=context)
    return MeSummaryOut(
        name=profile.display_name,
        language=code,
        proud_days=counted.days,
        as_of=counted.as_of,
        lines=list(recognition_lines(counted.days, code)),
    )
