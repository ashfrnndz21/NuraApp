"""The medicines routes (E04). Every one takes the key context; none is reachable without it.

    GET  /profiles/{id}/medicines                  the reconciled list, count and flags per line
    POST /profiles/{id}/medicines/draft            what a label would do, before anyone says yes
    POST /profiles/{id}/medicines                  write it, with the yes minted for exactly that
    GET  /profiles/{id}/medicines/history          every line ever written, the change log
    GET  /profiles/{id}/medicines/interactions     every flag on the list, as questions
    GET  /profiles/{id}/medicines/today            today's dose cards at his anchors, due or missed
    GET  /profiles/{id}/proud                      the proud number: days with a tablet taken
    POST /profiles/{id}/medicines/{line}/taken     his tap
    GET  /profiles/{id}/medicines/{line}/story     the story, in his language

The yes for a medicine is minted at `POST /profiles/{id}/confirmations` with subject
`medicine`, in `app.channels.api.profiles`. A label photo is a photo: it comes in through
`POST /profiles/{id}/photos` (E02, `app.channels.api.capture`) and its artefact id is what a
label here names as its source.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Request, status

from app.channels.api.deps import Context, Db, providers_of
from app.channels.api.schemas import (
    LineOut,
    MedicineDraftIn,
    MedicineDraftOut,
    MedicineIn,
    ProudOut,
    ReconciledOut,
    SlotOut,
    StoryOut,
    TakenIn,
    TakenOut,
)
from app.medicines.service import (
    active_lines,
    history,
    interaction_flags,
    plan,
    proud_days,
    reconcile,
    record_dose_taken,
    story,
    today,
)
from app.medicines.story import interaction_question
from app.medicines.strings import PLAIN_NAME, language_of

router = APIRouter(prefix="/profiles", tags=["medicines"])

Language = Query(default=None, min_length=2, max_length=16)


@router.get("/{profile_id}/medicines")
async def medicines(
    request: Request, context: Context, session: Db, language: str | None = Language
) -> list[LineOut]:
    """The reconciled list: each active line with its source and confidence, its running
    count and reorder date, its interaction flags as questions for the doctor, and any other
    active line of the same medicine. In `language`, or the profile's own."""
    views = await active_lines(
        session, context=context, registry=providers_of(request).drug_registry, language=language
    )
    return [LineOut.of(view) for view in views]


@router.post("/{profile_id}/medicines/draft")
async def draft(
    body: MedicineDraftIn, request: Request, context: Context, session: Db
) -> MedicineDraftOut:
    """What this label means against the list — refill, dose change, new line, duplicate —
    with the interactions a new line would be flagged for and whether the high-risk rule
    wants a label photo first. Nothing is written."""
    registry = providers_of(request).drug_registry
    what = await plan(
        session,
        context=context,
        registry=registry,
        label=body.label.as_label(),
        source_artifact_id=body.source_artifact_id,
    )
    lang = language_of(None)
    names = {
        g: PLAIN_NAME[lang][registry.monograph(g).plain_name_id]
        for g in {what.match.generic, *(each.other_line.generic for each in what.flagged)}
    }
    questions = [
        interaction_question(
            each.interaction, names=names, prescriber=body.label.prescriber, language=lang
        )
        for each in what.flagged
    ]
    return MedicineDraftOut.of(what, questions)


@router.post("/{profile_id}/medicines", status_code=status.HTTP_201_CREATED)
async def add(body: MedicineIn, request: Request, context: Context, session: Db) -> ReconciledOut:
    """Write what the label means, with the person's yes for exactly that.

    A new line lands with its supply and its flags; a refill lands as a supply on the line;
    a dose change lands as a new line superseding the old, the old kept. A high-risk
    medicine without a label photo is refused by class (`HighRiskNeedsLabelPhoto`, 400); a
    helper's key is refused (`NotTheirsToChange`, 403); the same label twice is refused
    (`AlreadyRecorded`, 409). Every refusal is on the trail.
    """
    done = await reconcile(
        session,
        context=context,
        registry=providers_of(request).drug_registry,
        label=body.label.as_label(),
        source_artifact_id=body.source_artifact_id,
        confirmation_id=body.confirmation_id,
    )
    return ReconciledOut.of(done)


@router.get("/{profile_id}/medicines/history")
async def change_log(context: Context, session: Db) -> list[LineOut]:
    """Every line ever written, superseded ones included, oldest first."""
    return [LineOut.history_of(line) for line in await history(session, context=context)]


@router.get("/{profile_id}/medicines/interactions")
async def interactions(
    request: Request, context: Context, session: Db, language: str | None = Language
) -> list[dict[str, object]]:
    """Every flag on an active line, worst first: the two medicines named, the severity, and
    the question for the doctor in his words."""
    flags = await interaction_flags(
        session, context=context, registry=providers_of(request).drug_registry, language=language
    )
    return [
        {
            "flag_id": view.flag.id,
            "line_id": view.flag.line_id,
            "other_line_id": view.other.id,
            "other_generic": view.other.generic,
            "severity": view.flag.severity.value,
            "text_id": view.flag.text_id,
            "question": view.question,
        }
        for view in flags
    ]


@router.get("/{profile_id}/medicines/today")
async def doses_today(
    request: Request, context: Context, session: Db, language: str | None = Language
) -> list[SlotOut]:
    """Today's doses as cards at breakfast, lunch, dinner and bed, and which were tapped."""
    slots = await today(
        session, context=context, registry=providers_of(request).drug_registry, language=language
    )
    return [SlotOut.of(slot) for slot in slots]


@router.get("/{profile_id}/proud")
async def proud(context: Context, session: Db) -> ProudOut:
    """The proud number: distinct days with a DOSE_TAKEN event, counted from the memory
    events under the medicines scope in one audited read. The client shows this and never a
    number it worked out or kept for itself."""
    counted = await proud_days(session, context=context)
    return ProudOut(days=counted.days, as_of=counted.as_of)


@router.post("/{profile_id}/medicines/{line_id}/taken", status_code=status.HTTP_201_CREATED)
async def taken(body: TakenIn, line_id: uuid.UUID, context: Context, session: Db) -> TakenOut:
    """His tap: this medicine, taken now. No confirm; the tap is the yes. Anyone whose key
    opens the medicines may tap — the helper who gives him his tablets included."""
    return TakenOut.of(
        await record_dose_taken(
            session,
            context=context,
            line_id=line_id,
            anchor=None if body.anchor is None else body.anchor.value,
            amount=body.amount,
        )
    )


@router.get("/{profile_id}/medicines/{line_id}/story")
async def medication_story(
    line_id: uuid.UUID,
    request: Request,
    context: Context,
    session: Db,
    language: str | None = Language,
) -> StoryOut:
    """The story of one medicine — purpose, how to take, watch-outs, avoid, if forgotten, the
    boundary — as a card and a voice script, in `language` or the profile's own. Rendered
    from templates keyed by the licensed monograph; no model."""
    told = await story(
        session,
        context=context,
        registry=providers_of(request).drug_registry,
        line_id=line_id,
        language=language,
    )
    return StoryOut.of(line_id, told)
