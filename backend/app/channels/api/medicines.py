"""The medicines routes (E04). Every one takes the key context; none is reachable without it.

    GET  /profiles/{id}/medicines                  the reconciled list, count and flags per line
    POST /profiles/{id}/medicines/draft            what a label would do, before anyone says yes
    POST /profiles/{id}/medicines                  write it, with the yes minted for exactly that
    GET  /profiles/{id}/medicines/history          every line ever written, the change log
    GET  /profiles/{id}/medicines/interactions     every flag on the list, as questions
    GET  /profiles/{id}/medicines/today            today's dose cards at his anchors, due or missed
    GET  /profiles/{id}/medicines/now              the one big number on his Today, and its words
    GET  /profiles/{id}/proud                      the proud number: days with a tablet taken
    POST /profiles/{id}/medicines/{line}/taken     his tap
    GET  /profiles/{id}/medicines/{line}/story     the story, in his language
    GET  /profiles/{id}/medicines/{line}/story/voice?part=   one part of it, as a voice note
    POST /profiles/{id}/medicines/{line}/ask-to-order  the reorder card: a task for the family
    POST /profiles/{id}/medicines/{line}/more      the reorder card: more found at home, on a yes

The yes for a medicine is minted at `POST /profiles/{id}/confirmations` with subject
`medicine` (and for tablets found at home, subject `count_correction`), in `app.channels.api.profiles`. A label photo is a photo: it comes in through
`POST /profiles/{id}/photos` (E02, `app.channels.api.capture`) and its artefact id is what a
label here names as its source.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Literal

from fastapi import APIRouter, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.about_him import reader_of
from app.channels.api.deps import Context, Db, providers_of
from app.channels.api.schemas import (
    AskedOut,
    CountOut,
    LineOut,
    MedicineDraftIn,
    MedicineDraftOut,
    MedicineIn,
    MoreIn,
    MoreOut,
    NowOut,
    ProudOut,
    ReconciledOut,
    SlotOut,
    StoryOut,
    TakenIn,
    TakenOut,
)
from app.delivery.voice import voiced
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.medicines.models import MedicationLine
from app.medicines.reorder import ask_to_order, found_more
from app.medicines.service import (
    active_lines,
    history,
    interaction_flags,
    now_count,
    plan,
    proud_days,
    reconcile,
    record_dose_taken,
    story,
    today,
)
from app.medicines.story import STORY_PARTS, interaction_question, story_part
from app.medicines.strings import PLAIN_NAME, language_of
from app.memory.episodic import withheld_references

router = APIRouter(prefix="/profiles", tags=["medicines"])

Language = Query(default=None, min_length=2, max_length=16)


async def _sources_withheld(
    session: AsyncSession, context: KeyContext, lines: Sequence[MedicationLine]
) -> dict[uuid.UUID, tuple[str, ...]]:
    """What each line came from that this key may not read: a line is the medicines' and its
    label photo the record's, so a helper sees the line and is told the photo is withheld."""
    return await withheld_references(
        session,
        context=context,
        cited=[
            (line.id, Scope.MEDICINES, line.source_artifact_id, line.source_event_id)
            for line in lines
        ],
    )


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
    withheld = await _sources_withheld(session, context, [view.line for view in views])
    reader = await reader_of(session, context, language)
    return [reader.model(LineOut.of(view, withheld.get(view.line.id, ()))) for view in views]


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
    lines = await history(session, context=context)
    withheld = await _sources_withheld(session, context, lines)
    return [LineOut.history_of(line, withheld.get(line.id, ())) for line in lines]


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
    reader = await reader_of(session, context, language)
    return [reader.model(SlotOut.of(slot)) for slot in slots]


@router.get("/{profile_id}/medicines/now")
async def medicines_now(
    request: Request, context: Context, session: Db, language: str | None = Language
) -> NowOut:
    """The one big number on his Today (the hero, docs/design-system.md §4): how many tablets
    at the moment of the day that is open now, or the next one still to come today, and his
    words for what it counts — counted from today's cards, under the medicines scope."""
    found = await now_count(
        session, context=context, registry=providers_of(request).drug_registry, language=language
    )
    if found is None:
        return NowOut(count=None, anchor=None, words=None)
    return NowOut(count=found.count, anchor=found.anchor, words=found.words)


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


StoryPart = Literal[STORY_PARTS]  # type: ignore[valid-type]


@router.get("/{profile_id}/medicines/{line_id}/story/voice")
async def medication_story_voice(
    line_id: uuid.UUID,
    request: Request,
    context: Context,
    session: Db,
    part: StoryPart = "purpose",
    language: str | None = Language,
) -> Response:
    """One part of the story as a voice note (E04-06): what it is for, how to take it, what to
    watch for, what to avoid, what to do if he forgot — each but the first ending on the
    story's boundary, since each plays on its own. Each is under thirty seconds, said once through the voice port and kept in the
    region's store under the digest of its script, the same cache every card's spoken twin is
    kept in (E11-04), so every later play is a read. Played on a tap; nothing plays by itself.
    404 when the part says nothing for this medicine, has no voice in the language yet, or
    would run too long: the phone then says the words with its own voice."""
    providers = providers_of(request)
    told = await story(
        session,
        context=context,
        registry=providers.drug_registry,
        line_id=line_id,
        language=language,
    )
    lines, boundary = story_part(told, part)
    said = await voiced(
        providers.object_store,
        providers.voice,
        profile_id=context.profile_id,
        region=context.region,
        lines=lines,
        language=told.language,
        boundary=boundary,
    )
    return Response(
        content=said.spoken.audio,
        media_type=said.spoken.content_type,
        headers={
            "X-Duration-Seconds": f"{said.spoken.duration_seconds:.1f}",
            "X-Voice-Cache": "hit" if said.cached else "miss",
            "Cache-Control": "private, no-store",
        },
    )


@router.post("/{profile_id}/medicines/{line_id}/ask-to-order", status_code=status.HTTP_201_CREATED)
async def ask_the_family(
    line_id: uuid.UUID,
    request: Request,
    context: Context,
    session: Db,
    language: str | None = Language,
) -> AskedOut:
    """His tap on the reorder card's "Ask the family to order." (E04-05): a task on the
    family's list for whoever is on duty now, else his chief, and a notice to his chief. The
    tap is the yes, as Taken is. Nobody to ask is `NobodyToAsk` (409); a key that does not
    arrange the family's list is refused by it (`NotAChief`, or `OutOfScope` family)."""
    asked = await ask_to_order(
        session,
        context=context,
        registry=providers_of(request).drug_registry,
        line_id=line_id,
        language=language,
    )
    return AskedOut(
        line_id=asked.line.id,
        task_id=asked.task.id,
        asked_person_id=asked.asked.id,
        told_person_ids=[person.id for person in asked.told],
        language=asked.language,
        lines=list(asked.lines),
    )


@router.post("/{profile_id}/medicines/{line_id}/more", status_code=status.HTTP_201_CREATED)
async def more_at_home(
    line_id: uuid.UUID,
    body: MoreIn,
    request: Request,
    context: Context,
    session: Db,
    language: str | None = Language,
) -> MoreOut:
    """ "I have more at home.": the tablets found, added to the count on the person's yes for
    exactly this line and number (subject `count_correction`). A helper's key is refused
    (`NotTheirsToChange`, 403); a yes for another number is `NotWhatWasConfirmed` (400)."""
    done = await found_more(
        session,
        context=context,
        registry=providers_of(request).drug_registry,
        line_id=line_id,
        quantity=body.quantity,
        confirmation_id=body.confirmation_id,
        language=language,
    )
    return MoreOut(
        line_id=done.line.id,
        supply_id=done.supply.id,
        fact_id=done.fact.id,
        event_id=done.event.id,
        quantity=done.supply.quantity,
        count=None if done.count is None else CountOut.of(done.count),
    )
