"""Onboarding over HTTP (E01-02, E01-03, E01-04): the routes docs/onboarding.html is built on.

    GET  /onboarding/conditions?language=          the word cloud; public, no profile data
    GET  /profiles/{id}/settings                   the settings, as the caller's key reads them
    PUT  /profiles/{id}/settings                   save them (owner or chief)
    POST /profiles/{id}/biography                  open a sitting
    GET  /profiles/{id}/biography                  where it stands, and the words of its step
    POST /profiles/{id}/biography/papers           a paper: a photo or a PDF in, or a card
    POST /profiles/{id}/biography/read-back        yes or no: every line, or one line
    POST /profiles/{id}/biography/questions        keep a question the papers raised, or not
    POST /profiles/{id}/biography/close            the summary and the first week's plan
    GET  /profiles/{id}/plan?at=                   the first week, and the prompt due at `at`
    POST /profiles/{id}/plan/later                 Later: to the back of the week, then retired
    POST /profiles/{id}/plan/{prompt}/skip         not this one: retired at once

Every profile route takes the key context like every other. Settings are read under the face
of the graph, which every key opens, with the record's parts withheld from a key without the
record (`app.onboarding.settings`); the biography and the plan are read and written under the
record's scope; writing any of it is the owner's and his chief's (`NotTheirsToSetUp`, 403).
A paper's review card is confirmed where every card is: `POST /profiles/{id}/confirmations`
with subject `review_card`, then `POST /profiles/{id}/review-cards/{card}/confirm`.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query, Request, status
from pydantic import AwareDatetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_profile_read
from app.channels.api.capture import capture_language
from app.channels.api.deps import Context, Db, providers_of
from app.channels.api.onboarding_schemas import (
    AttachIn,
    BiographyOut,
    ClosedOut,
    ConditionOut,
    ConditionsOut,
    LaterIn,
    PaperAddedOut,
    PaperIn,
    PaperOut,
    PlanOut,
    PromptOut,
    QuestionIn,
    ReadBackIn,
    SettingsIn,
    SettingsOut,
    SummaryOut,
)
from app.channels.api.schemas import ReviewCardOut
from app.db import utcnow
from app.ingestion.review import card_fields
from app.keys.context import KeyContext
from app.onboarding.biography import (
    PaperView,
    add_paper,
    answer_read_back,
    attach_paper,
    biography_view,
    close_biography,
    keep_question,
    open_biography,
)
from app.onboarding.conditions import graph
from app.onboarding.plan import PlanView, current_plan, due_in, later_prompt, skip_prompt
from app.onboarding.settings import (
    current_settings,
    read_settings,
    save_settings,
    settings_language,
)
from app.onboarding.strings import language_for

router = APIRouter(tags=["onboarding"])


@router.get("/onboarding/conditions")
async def conditions(
    language: str = Query(default="en", min_length=2, max_length=16),
) -> ConditionsOut:
    """The word cloud: every condition in the fixed graph, named in `language` (en, ms or
    zh; English for anything else), with its weight and what appears beside it once tapped.
    Public: it is the same for everyone and says nothing about anyone."""
    code = language_for(language)
    held = graph()
    return ConditionsOut(
        language=code,
        version=held.version,
        top=list(held.top),
        conditions=[ConditionOut.of(one, code) for one in held.conditions.values()],
    )


@router.get("/profiles/{profile_id}/settings")
async def get_settings(context: Context, session: Db) -> SettingsOut:
    """The settings as this key reads them: how to talk to him for every key; the
    conditions and the doctor's name only for a key to the record (else `withheld`)."""
    return SettingsOut.of(await read_settings(session, context=context), context.profile_id)


@router.put("/profiles/{profile_id}/settings")
async def put_settings(body: SettingsIn, context: Context, session: Db) -> SettingsOut:
    """Save the settings screen whole. The owner or a chief (the steward before the claim);
    anyone else `NotTheirsToSetUp` (403), on the trail. What changed is written as facts, his
    yes on each, and State folds them at once; the language becomes the profile's own. An
    unknown condition is `NotACondition` (400), a language Nura does not speak `NotALanguage`."""
    await save_settings(session, context=context, values=body.as_values())
    return SettingsOut.of(await read_settings(session, context=context), context.profile_id)


@router.post("/profiles/{profile_id}/biography", status_code=status.HTTP_201_CREATED)
async def open_sitting(context: Context, session: Db) -> BiographyOut:
    """Open a sitting of the health biography. One at a time: `BiographyAlreadyOpen` (409)."""
    return BiographyOut.of(await open_biography(session, context=context))


@router.get("/profiles/{profile_id}/biography")
async def get_sitting(context: Context, session: Db, language: str | None = None) -> BiographyOut:
    """The latest sitting, open or closed: its step, the one call to make next, the words
    of the step in his language (or `?language=`), its papers, the read-back and the
    questions."""
    return BiographyOut.of(await biography_view(session, context=context, language=language))


@router.post("/profiles/{profile_id}/biography/papers", status_code=status.HTTP_201_CREATED)
async def add_sitting_paper(
    body: PaperIn | AttachIn, request: Request, context: Context, session: Db
) -> PaperAddedOut:
    """A paper of the sitting, one of two ways. A photo or a PDF with what he says it is:
    stored in the region and read into a review card, as `POST /profiles/{id}/photos` or
    `/imports` does. Or `card_id`: a card already made through capture joins the sitting.
    Nothing is a fact until the card is confirmed. `PaperAlreadyAdded` (409) for a card
    that is already one of its papers."""
    if isinstance(body, AttachIn):
        paper, card = await attach_paper(
            session, context=context, card_id=body.card_id, paper=body.paper
        )
    else:
        providers = providers_of(request)
        paper, card = await add_paper(
            session,
            context=context,
            store=providers.object_store,
            extractor=providers.extractor,
            data=body.as_bytes(),
            content_type=body.content_type,
            captured_at=body.captured_at,
            paper=body.paper,
        )
    return PaperAddedOut(
        paper=PaperOut.of(PaperView(paper=paper, card=card)),
        card=ReviewCardOut.of(
            card,
            await card_fields(session, context=context, card_id=card.id),
            language=await capture_language(session, context),
        ),
    )


@router.post("/profiles/{profile_id}/biography/read-back")
async def read_back(body: ReadBackIn, context: Context, session: Db) -> BiographyOut:
    """His answer to the read-back: every line still waiting (`answers`), or one line
    (`line_id` and `answer`). A yes is his confirm of the line; a no opens a dispute against
    its fact, which stays current; the read-back is done when every line is answered.
    `NotAtThisStep` (409) before the settings, `CardsStillOpen` (409) while a card waits,
    `AlreadyReadBack` (409) once done, `NotEveryLineAnswered` (400) for a whole answer with a
    line missing, twice or not read, `NoSuchReadBackLine` (404) for a line not waiting."""
    if body.answers is not None:
        view = await answer_read_back(
            session,
            context=context,
            answers=[(answer.fact_id, answer.answer) for answer in body.answers],
        )
    else:
        assert body.line_id is not None and body.answer is not None
        view = await answer_read_back(
            session, context=context, answers=[(body.line_id, body.answer)], whole=False
        )
    return BiographyOut.of(view)


@router.post("/profiles/{profile_id}/biography/questions")
async def keep_or_not(body: QuestionIn, context: Context, session: Db) -> BiographyOut:
    """Keep a question the papers raised (`keep: true`), or not this one (`keep: false`);
    he may change his mind until the sitting closes. A kept question is the seam to the
    visit loop (E05); one he did not keep is left out of the first week. `NotAtThisStep`
    (409) before the read-back, `NoSuchQuestion` (404) for a question it did not raise."""
    return BiographyOut.of(
        await keep_question(session, context=context, question_id=body.question_id, keep=body.keep)
    )


async def _plan_out(
    session: AsyncSession,
    *,
    context: KeyContext,
    view: PlanView,
    at: datetime,
    language: str | None = None,
) -> PlanOut:
    row = await current_settings(session, context=context)
    profile = await audited_profile_read(session, context)
    return PlanOut.of(
        view,
        due_in(view, at),
        region=context.region,
        language=language_for(language) if language else settings_language(row, profile.language),
        doctor=None if row is None else row.doctor_name,
    )


@router.post("/profiles/{profile_id}/biography/close")
async def close_sitting(context: Context, session: Db) -> ClosedOut:
    """Close the sitting: the summary in his words, and the first week's plan — the gaps it
    left open, one a day from tomorrow at his breakfast time."""
    closed = await close_biography(session, context=context)
    view = PlanView(plan=closed.plan, prompts=closed.prompts, stopped_because=())
    return ClosedOut(
        biography=BiographyOut.of(closed.view),
        summary=SummaryOut.of(closed.summary),
        plan=await _plan_out(session, context=context, view=view, at=utcnow()),
    )


@router.get("/profiles/{profile_id}/plan")
async def get_plan(
    context: Context, session: Db, at: AwareDatetime | None = None, language: str | None = None
) -> PlanOut:
    """The first week, reconciled with the record first, and the one prompt due at `at`
    (now by default), its words in his language (or `?language=`). `NoPlan` (404) before a
    biography has closed."""
    view = await current_plan(session, context=context)
    return await _plan_out(
        session, context=context, view=view, at=at or utcnow(), language=language
    )


@router.post("/profiles/{profile_id}/plan/later")
async def later(body: LaterIn, context: Context, session: Db) -> PlanOut:
    """Later, on one prompt (docs/gaps-and-unlocks.md §4): the first sends it to the back of
    the week, to be asked once more; the second retires it. The plan as it stands after.
    `NoSuchPrompt` (404), `PromptAlreadySettled` (409) for one done or retired."""
    await later_prompt(session, context=context, gap=body.gap_id)
    view = await current_plan(session, context=context)
    return await _plan_out(session, context=context, view=view, at=utcnow())


@router.post("/profiles/{profile_id}/plan/{prompt}/skip")
async def skip(prompt: str, context: Context, session: Db) -> PromptOut:
    """Later: the prompt is skipped, and stays in the plan. `NoSuchPrompt` (404),
    `PromptAlreadySettled` (409) for one done or skipped."""
    skipped = await skip_prompt(session, context=context, gap=prompt)
    row = await current_settings(session, context=context)
    profile = await audited_profile_read(session, context)
    return PromptOut.of(
        skipped,
        region=context.region,
        language=settings_language(row, profile.language),
        doctor=None if row is None else row.doctor_name,
    )
