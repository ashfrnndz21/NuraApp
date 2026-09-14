"""The day's routine over HTTP (E10-01).

    GET /profiles/{id}/routine?persona=&language=   the day, for him or for the caregiver
    PUT /profiles/{id}/routine                      set it, with the yes minted for exactly it

The yes is minted at `POST /profiles/{id}/confirmations` with subject `routine` and the same
day. `persona` is `patient` (one line per moment, in his words) or `caregiver` (a dense
table); without it the owner reads his lines and anyone else the table.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from app.channels.api.daily_schemas import RoutineIn, RoutineOut
from app.channels.api.deps import Context, Db, providers_of
from app.routines.service import Persona, render_routine, set_routine

router = APIRouter(prefix="/profiles", tags=["routine"])

Language = Query(default=None, min_length=2, max_length=16)


@router.get("/{profile_id}/routine")
async def the_routine(
    request: Request,
    context: Context,
    session: Db,
    persona: Persona | None = None,
    language: str | None = Language,
) -> RoutineOut:
    view = await render_routine(
        session,
        context=context,
        registry=providers_of(request).drug_registry,
        persona=persona,
        language=language,
    )
    return RoutineOut.of(view)


@router.put("/{profile_id}/routine")
async def set_the_routine(
    body: RoutineIn,
    request: Request,
    context: Context,
    session: Db,
    persona: Persona | None = None,
    language: str | None = Language,
) -> RoutineOut:
    """Set the day. Refused without the yes for exactly this day (`NotWhatWasConfirmed`),
    for a key that reads the day but does not set it (`NotTheirsToSet`, 403), and for a day
    that is not one (`NotARoutine`); every refusal is on the trail."""
    await set_routine(
        session,
        context=context,
        anchors=body.anchors,
        reading_prompts=body.reading_prompts,
        walks=body.walks,
        morning_card_at=body.morning_card_at,
        confirmation_id=body.confirmation_id,
    )
    view = await render_routine(
        session,
        context=context,
        registry=providers_of(request).drug_registry,
        persona=persona,
        language=language,
    )
    return RoutineOut.of(view)
