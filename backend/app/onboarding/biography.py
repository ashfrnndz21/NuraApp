"""The health biography (E01-02): one sitting in which the papers of a life become the record.

The owner opens it, or the chief who set the profile up for him, and it walks five steps. The
step is worked out from the session and the record every time it is asked, never stored
twice (`Step`):

    about_you   nothing saved on the settings screen yet (E01-03)
    papers      settings saved; each paper — a photo, or a PDF the way the import path
                takes it — comes with what he says it is
                (`add_paper`), read into a review card through the capture path (E02), and
                confirmed there with one tap
    read_back   at least one paper, and every card confirmed: what he told and what the
                papers said is read back in plain words, one line a fact
    questions   the read-back answered: what the papers did not say, asked of him
    closed      the summary, and the first week's plan (`app.onboarding.plan`)

A person may leave the papers for later — the read-back and the close are open from the
papers step once no card is waiting — and the summary says so.

The read-back is where he checks what was understood. A "yes" is his confirm of that line,
kept on the line. A "no" opens a dispute against the fact (`ConfidenceState.DISPUTED`, under
`ConfirmedFactStands`): the fact stays current, the disagreement is kept beside it for a
person to settle, and nothing anyone confirmed is overwritten. The yes each dispute rests on
is minted and spent in the same request for exactly that dispute, the way the review card
records who confirmed each of its facts. Only facts a person confirmed are read back, and
only the ones this sitting's papers made or he told on the settings screen.

Nothing here infers. The read-back restates confirmed facts; the questions ask him for what
the gap catalogue says is missing (`app.onboarding.gaps`); the summary counts. None of them is
rendered from State, and none is in the register of inferring surfaces
(`app.safety.boundary`) — the visit loop's questions for the doctor are, and carry its line.
Every line is plain words, checked as it is served (`app.onboarding.words`).

Who: the owner, or a chief (the steward, before the claim); anyone else `NotTheirsToSetUp`.
Reading where it stands needs the record, since it reads the record back.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import (
    audited,
    audited_profile_read,
    audited_read,
    audited_write,
    person_display_name,
)
from app.audit.models import Action
from app.audit.trail import record
from app.db import as_utc, utcnow
from app.drafts import FactDraft
from app.errors import Refusal
from app.ingestion.documents import PDF_CONTENT_TYPE, store_pdf
from app.ingestion.extract import DocumentKind, Extractor
from app.ingestion.models import ReviewCard
from app.ingestion.objects import ObjectStore
from app.ingestion.photos import store_photo
from app.ingestion.review import (
    card_fields,
    require_review_card,
    review_artifact,
    review_photo,
)
from app.keys.confirm import confirm
from app.keys.context import KeyContext
from app.keys.scopes import Scope, scope_for_subject
from app.memory.episodic import fact_cites_only_what_is_held_here, record_event
from app.memory.models import ConfidenceState, Event, EventKind, Fact, SourceChannel
from app.memory.semantic import assert_fact, current_facts
from app.onboarding.conditions import graph, name_of
from app.onboarding.gaps import ANTICOAGULANT, open_gaps, questions_for_gaps, what_is_known
from app.onboarding.models import (
    BIOGRAPHY_IN_PROGRESS,
    ActivationPlan,
    Answer,
    BiographyLine,
    BiographyPaper,
    BiographySession,
    PaperKind,
    PlanPrompt,
)
from app.onboarding.plan import make_plan
from app.onboarding.settings import (
    CONDITION,
    DOCTOR,
    a_setter,
    current_settings,
    parse_clock_time,
    settings_language,
)
from app.onboarding.words import (
    Script,
    after_a_no,
    plain_date,
    questions_more,
    read_back,
    script,
    summary,
)
from app.regions import REGION_TZ

BIO_SCOPE = Scope.RECORDS
"""A sitting reads the record back, so it is read and written under the record's scope."""

SESSION = BiographySession.__tablename__
PAPER = BiographyPaper.__tablename__
LINE = BiographyLine.__tablename__

MAX_QUESTIONS = 4
"""The questions shown at once; the rest are a count (docs/gaps-and-unlocks.md §3)."""

LAB_LINES: Mapping[tuple[str, str], str] = {
    ("lipid_panel", "total_cholesterol"): "total_cholesterol",
    ("lipid_panel", "ldl"): "ldl",
    ("lipid_panel", "hdl"): "hdl",
}
"""The results read back from a lab paper, by the read-back line that says each. The rest of
a panel is kept as facts and shown to the caregiver; he is read the numbers he knows."""


class Step(StrEnum):
    ABOUT_YOU = "about_you"
    PAPERS = "papers"
    READ_BACK = "read_back"
    QUESTIONS = "questions"
    CLOSED = "closed"


class NoBiography(Refusal):
    """No biography has been opened on this profile."""


class BiographyAlreadyOpen(Refusal):
    """A biography is already open on this profile: carry on with that one."""


class BiographyClosed(Refusal):
    """This biography is closed. A new sitting is a new biography."""


class NotAtThisStep(Refusal):
    """The biography is not at the step this belongs to: the settings come first."""


class AlreadyReadBack(Refusal):
    """The read-back of this sitting was answered already."""


class CardsStillOpen(Refusal):
    """A paper of this sitting waits for its yes on its review card."""


class NotEveryLineAnswered(Refusal):
    """The read-back is answered whole: every line once, yes or no, and no line it did not read."""


@dataclass(frozen=True, slots=True)
class PaperView:
    paper: BiographyPaper
    card: ReviewCard


@dataclass(frozen=True, slots=True)
class LineView:
    """One read-back line: the fact it reads back, the words, and — once answered — the answer."""

    fact_id: uuid.UUID
    line: str
    answer: Answer | None = None
    dispute_fact_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class Question:
    """A question the papers raised, by the gap it would fill ("dispute" for what follows a
    "no", "more" for the count of the rest)."""

    gap: str
    line: str


@dataclass(frozen=True, slots=True)
class BiographyView:
    """Where a sitting stands, and everything its step shows, in his language."""

    session: BiographySession
    step: Step
    language: str
    script: Script
    papers: tuple[PaperView, ...]
    read_back: tuple[LineView, ...]
    questions: tuple[Question, ...]

    @property
    def open_cards(self) -> int:
        return sum(1 for paper in self.papers if paper.card.is_open)

    @property
    def next(self) -> str | None:
        """The one thing to do next, by the name of the call that does it."""
        if self.step is Step.ABOUT_YOU:
            return "save_settings"
        if self.step is Step.PAPERS:
            return "confirm_cards" if self.open_cards else "add_paper"
        if self.step is Step.READ_BACK:
            return "read_back"
        if self.step is Step.QUESTIONS:
            return "close"
        return None


@dataclass(frozen=True, slots=True)
class Summary:
    """The close of a sitting, counted, and said in his words."""

    papers: int
    facts: int
    conditions: int
    medicines: int
    disputes: int
    questions: int
    prompts: int
    first_prompt_at: datetime | None
    lines: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Closed:
    view: BiographyView
    summary: Summary
    plan: ActivationPlan
    prompts: Sequence[PlanPrompt]


def _step(bio: BiographySession, has_settings: bool, papers: Sequence[PaperView]) -> Step:
    if bio.closed_at is not None:
        return Step.CLOSED
    if bio.read_back_at is not None:
        return Step.QUESTIONS
    if not has_settings:
        return Step.ABOUT_YOU
    if papers and not any(paper.card.is_open for paper in papers):
        return Step.READ_BACK
    return Step.PAPERS


async def latest_biography(
    session: AsyncSession, *, context: KeyContext
) -> BiographySession | None:
    found = await audited_read(session, BiographySession, context, BIO_SCOPE)
    return max(found, key=lambda one: as_utc(one.opened_at)) if found else None


async def _require_open(session: AsyncSession, *, context: KeyContext) -> BiographySession:
    bio = await latest_biography(session, context=context)
    if bio is None:
        raise NoBiography(f"no biography on profile {context.profile_id}")
    if bio.closed_at is not None:
        raise BiographyClosed(f"biography {bio.id} closed at {bio.closed_at}")
    return bio


async def _papers(
    session: AsyncSession, *, context: KeyContext, bio: BiographySession
) -> tuple[PaperView, ...]:
    rows = await audited_read(
        session, BiographyPaper, context, BIO_SCOPE, where=(BiographyPaper.session_id == bio.id,)
    )
    return tuple(
        [
            PaperView(
                paper=row,
                card=await require_review_card(session, context=context, card_id=row.card_id),
            )
            for row in sorted(rows, key=lambda one: one.position)
        ]
    )


# --- the read-back ----------------------------------------------------------------------------


def _number(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _line_for(
    fact: Fact,
    *,
    cards_by_artifact: Mapping[uuid.UUID, ReviewCard],
    language: str,
    context: KeyContext,
) -> str | None:
    """The read-back line for one confirmed fact, or None when it is not one he is read back:
    what he told (a condition, his doctor) or what one of this sitting's papers said."""
    key = (fact.subject, fact.attribute)
    if fact.subject == CONDITION:
        if fact.value is not True or fact.attribute not in graph().conditions:
            return None
        return read_back("condition", language, condition=name_of(fact.attribute, language))
    if key == DOCTOR:
        if not isinstance(fact.value, str) or not fact.value:
            return None
        return read_back("doctor", language, doctor=fact.value)
    card = None if fact.artifact_id is None else cards_by_artifact.get(fact.artifact_id)
    if card is None:
        return None
    if key in LAB_LINES and isinstance(fact.value, int | float):
        day = as_utc(fact.valid_from).astimezone(REGION_TZ[context.region]).date()
        return read_back(
            LAB_LINES[key], language, value=_number(fact.value), date=plain_date(day, language)
        )
    if key == ("medicine", "name") and isinstance(fact.value, str):
        which = "thinner" if card.high_risk_class == ANTICOAGULANT else "medicine"
        return read_back(which, language, medicine=fact.value)
    if key == ("medicine", "dose") and isinstance(fact.value, dict):
        # As printed when he reads Malay (the labels here are); the parse otherwise.
        said = fact.value.get("as_printed") if language == "ms" else None
        said = said or fact.value.get("instruction")
        return read_back("instruction", language, instruction=str(said)) if said else None
    if key == ("medicine", "prescriber") and isinstance(fact.value, str):
        return read_back("prescriber", language, prescriber=fact.value)
    return None


async def _read_back_lines(
    session: AsyncSession,
    *,
    context: KeyContext,
    papers: Sequence[PaperView],
    language: str,
) -> list[tuple[Fact, str]]:
    """What is read back, in order: the conditions he told (the graph's order), his doctor,
    then each paper's facts in the order they were read off the page. Confirmed facts that
    hold now, under subjects this key opens; a line that cannot be said plainly is left out."""
    held = [
        fact
        for fact in await current_facts(session, context=context)
        if fact.confidence_state is ConfidenceState.CONFIRMED_BY_PERSON
        and context.allows(scope_for_subject(fact.subject))
    ]
    told: dict[tuple[str, str], Fact] = {}
    for fact in sorted(held, key=lambda one: as_utc(one.asserted_at)):
        if fact.subject == CONDITION or (fact.subject, fact.attribute) == DOCTOR:
            told[(fact.subject, fact.attribute)] = fact
    ordered = [told[(CONDITION, code)] for code in graph().conditions if (CONDITION, code) in told]
    if DOCTOR in told:
        ordered.append(told[DOCTOR])
    by_id = {fact.id: fact for fact in held}
    for paper in papers:
        for field in await card_fields(session, context=context, card_id=paper.card.id):
            if field.fact_id is not None and field.fact_id in by_id:
                ordered.append(by_id[field.fact_id])
    cards_by_artifact = {paper.card.artifact_id: paper.card for paper in papers}
    lines: list[tuple[Fact, str]] = []
    for fact in ordered:
        line = _line_for(
            fact, cards_by_artifact=cards_by_artifact, language=language, context=context
        )
        if line is not None:
            lines.append((fact, line))
    return lines


async def _answered(
    session: AsyncSession,
    *,
    context: KeyContext,
    bio: BiographySession,
    papers: Sequence[PaperView],
    language: str,
) -> tuple[LineView, ...]:
    """The lines as they were answered, said again from their facts (a fact is never edited,
    so the words are the ones he answered)."""
    rows = await audited_read(
        session, BiographyLine, context, BIO_SCOPE, where=(BiographyLine.session_id == bio.id,)
    )
    if not rows:
        return ()
    facts = await audited_read(
        session,
        Fact,
        context,
        BIO_SCOPE,
        where=(
            Fact.id.in_([row.fact_id for row in rows]),
            fact_cites_only_what_is_held_here(context, BIO_SCOPE),
        ),
    )
    by_id = {fact.id: fact for fact in facts}
    cards_by_artifact = {paper.card.artifact_id: paper.card for paper in papers}
    views: list[LineView] = []
    for row in sorted(rows, key=lambda one: one.position):
        fact = by_id.get(row.fact_id)
        if fact is None or not context.allows(scope_for_subject(fact.subject)):
            continue
        line = _line_for(
            fact, cards_by_artifact=cards_by_artifact, language=language, context=context
        )
        if line is not None:
            views.append(
                LineView(
                    fact_id=fact.id,
                    line=line,
                    answer=row.answer,
                    dispute_fact_id=row.dispute_fact_id,
                )
            )
    return tuple(views)


async def _who_checks(
    session: AsyncSession, *, context: KeyContext, bio: BiographySession
) -> str | None:
    """Who looks at the paper again after a "no": the person who said it, by name, when that
    was not the owner himself; None when it was him (his answer is kept beside the paper), or
    when this key does not open the family list to say who."""
    profile = await audited_profile_read(session, context)
    answerer = bio.read_back_by_person_id
    if answerer is None or answerer == profile.owner_person_id:
        return None
    if not context.allows(Scope.FAMILY):
        return None
    return await person_display_name(session, context, answerer)


async def _questions(
    session: AsyncSession,
    *,
    context: KeyContext,
    bio: BiographySession,
    doctor: str | None,
    language: str,
    answered: Sequence[LineView],
) -> tuple[Question, ...]:
    asked: list[Question] = []
    if any(line.answer is Answer.NO for line in answered):
        after = after_a_no(await _who_checks(session, context=context, bio=bio), language)
        if after is not None:
            asked.append(Question(gap="dispute", line=after))
    gaps = open_gaps(await what_is_known(session, context=context))
    for code, line in questions_for_gaps(gaps[:MAX_QUESTIONS], language=language, doctor=doctor):
        asked.append(Question(gap=code, line=line))
    if len(gaps) > MAX_QUESTIONS:
        more = questions_more(len(gaps) - MAX_QUESTIONS, language)
        if more is not None:
            asked.append(Question(gap="more", line=more))
    return tuple(asked)


async def _view(
    session: AsyncSession, *, context: KeyContext, bio: BiographySession
) -> BiographyView:
    row = await current_settings(session, context=context)
    profile = await audited_profile_read(session, context)
    language = settings_language(row, profile.language)
    papers = await _papers(session, context=context, bio=bio)
    step = _step(bio, row is not None, papers)
    lines: tuple[LineView, ...] = ()
    questions: tuple[Question, ...] = ()
    if step in (Step.PAPERS, Step.READ_BACK) and not any(paper.card.is_open for paper in papers):
        found = await _read_back_lines(session, context=context, papers=papers, language=language)
        lines = tuple(LineView(fact_id=fact.id, line=line) for fact, line in found)
    elif step in (Step.QUESTIONS, Step.CLOSED):
        lines = await _answered(session, context=context, bio=bio, papers=papers, language=language)
        questions = await _questions(
            session,
            context=context,
            bio=bio,
            doctor=None if row is None else row.doctor_name,
            language=language,
            answered=lines,
        )
    return BiographyView(
        session=bio,
        step=step,
        language=language,
        script=script(step.value, language),
        papers=papers,
        read_back=lines,
        questions=questions,
    )


# --- the doors --------------------------------------------------------------------------------


@audited(Action.WRITE, BIO_SCOPE, SESSION)
async def open_biography(session: AsyncSession, *, context: KeyContext) -> BiographyView:
    """Open a sitting. One at a time: while one is open, opening another is refused."""
    a_setter(context)
    latest = await latest_biography(session, context=context)
    if latest is not None and latest.closed_at is None:
        raise BiographyAlreadyOpen(f"biography {latest.id} is open")
    bio = await audited_write(
        session,
        BiographySession,
        context,
        BIO_SCOPE,
        opened_by_person_id=context.person_id,
        opened_at=utcnow(),
    )
    return await _view(session, context=context, bio=bio)


@audited(Action.READ, BIO_SCOPE, SESSION)
async def biography_view(session: AsyncSession, *, context: KeyContext) -> BiographyView:
    """The latest sitting — open or closed — and where it stands."""
    bio = await latest_biography(session, context=context)
    if bio is None:
        raise NoBiography(f"no biography on profile {context.profile_id}")
    return await _view(session, context=context, bio=bio)


@audited(Action.WRITE, BIO_SCOPE, PAPER)
async def add_paper(
    session: AsyncSession,
    *,
    context: KeyContext,
    store: ObjectStore,
    extractor: Extractor,
    data: bytes,
    content_type: str,
    captured_at: datetime,
    paper: PaperKind,
) -> tuple[BiographyPaper, ReviewCard]:
    """One paper of the sitting: the photo through the capture path — stored in the region,
    read into a review card with per-field confidence — and the paper row naming both, with
    what he says it is. The card is confirmed where every card is (E02-07)."""
    a_setter(context)
    bio = await _require_open(session, context=context)
    earlier = await audited_read(
        session, BiographyPaper, context, BIO_SCOPE, where=(BiographyPaper.session_id == bio.id,)
    )
    row = await current_settings(session, context=context)
    profile = await audited_profile_read(session, context)
    language = settings_language(row, profile.language)
    if _is_pdf(content_type):
        # A PDF goes the way `POST /profiles/{id}/imports` takes it (E02-03): kept as a PDF
        # artefact, read page by page, with what he says it is as the hint where it is one.
        artifact = await store_pdf(
            session,
            context=context,
            store=store,
            data=data,
            content_type=content_type,
            captured_at=captured_at,
        )
        card = await review_artifact(
            session,
            context=context,
            artifact_id=artifact.id,
            store=store,
            extractor=extractor,
            language=language,
            asked_as=PDF_HINTS.get(paper),
        )
    else:
        artifact = await store_photo(
            session,
            context=context,
            store=store,
            data=data,
            content_type=content_type,
            captured_at=captured_at,
            source_channel=SourceChannel.APP,
        )
        card = await review_photo(
            session,
            context=context,
            artifact_id=artifact.id,
            store=store,
            extractor=extractor,
            language=language,
        )
    written = await audited_write(
        session,
        BiographyPaper,
        context,
        BIO_SCOPE,
        session_id=bio.id,
        position=len(earlier),
        artifact_id=artifact.id,
        card_id=card.id,
        paper=paper,
        added_by_person_id=context.person_id,
        added_at=utcnow(),
    )
    return written, card


PDF_HINTS: Mapping[PaperKind, DocumentKind] = {
    PaperKind.LAB_RESULT: DocumentKind.LAB_REPORT,
    PaperKind.DISCHARGE_LETTER: DocumentKind.DISCHARGE_LETTER,
    PaperKind.INSURANCE_CARD: DocumentKind.INSURANCE_LETTER,
}
"""What he says a PDF is, as the hint the import path takes (`DOCUMENT_HINTS`, E02-03)."""


def _is_pdf(content_type: str) -> bool:
    return content_type.strip().lower().split(";", 1)[0].strip() == PDF_CONTENT_TYPE


async def _dispute(session: AsyncSession, *, context: KeyContext, fact: Fact, event: Event) -> Fact:
    """A "no" on a line: a dispute against the fact, carrying the value disputed, resting on
    the paper the fact came from and on the moment of the read-back, with his yes to exactly
    this dispute written down and spent. The fact stays current (`ConfirmedFactStands`)."""
    draft = FactDraft(
        subject=fact.subject,
        attribute=fact.attribute,
        value=fact.value,
        unit=fact.unit,
        confidence=1.0,
        confidence_state=ConfidenceState.DISPUTED,
        artifact_id=fact.artifact_id,
        event_id=event.id,
        episode_id=None,
        supersedes_id=fact.id,
    )
    yes = await confirm(session, context, draft)
    return await assert_fact(
        session,
        context=context,
        subject=draft.subject,
        attribute=draft.attribute,
        value=draft.value,
        unit=draft.unit,
        confidence=draft.confidence,
        confidence_state=draft.confidence_state,
        confirmation_id=yes.id,
        artifact_id=draft.artifact_id,
        event_id=event.id,
        supersedes_id=fact.id,
    )


def _stamp(bio: BiographySession, **values: Any) -> None:
    for name, value in values.items():
        setattr(bio, name, value)


async def _stamped(
    session: AsyncSession, *, context: KeyContext, bio: BiographySession, **values: Any
) -> None:
    """The one change a session takes at a time — its read-back, its close — made and written
    down while this service says so."""
    session.info[BIOGRAPHY_IN_PROGRESS] = bio.id
    try:
        _stamp(bio, **values)
        await session.flush()
        await record(
            session,
            context=context,
            action=Action.WRITE,
            scope=BIO_SCOPE,
            target=SESSION,
            target_id=bio.id,
            rows=1,
        )
    finally:
        session.info.pop(BIOGRAPHY_IN_PROGRESS, None)


@audited(Action.WRITE, BIO_SCOPE, LINE)
async def answer_read_back(
    session: AsyncSession, *, context: KeyContext, answers: Sequence[tuple[uuid.UUID, Answer]]
) -> BiographyView:
    """He answers the read-back, every line once: a yes is kept as his confirm of the line;
    a no opens a dispute against its fact. Refused before the settings, while a card of the
    sitting waits for its yes, a second time, or with a line missing or one it did not read."""
    a_setter(context)
    said = dict(answers)
    if len(said) != len(answers):
        raise NotEveryLineAnswered("a line was answered twice")
    bio = await _require_open(session, context=context)
    if bio.read_back_at is not None:
        raise AlreadyReadBack(f"biography {bio.id} was read back at {bio.read_back_at}")
    row = await current_settings(session, context=context)
    if row is None:
        raise NotAtThisStep("the read-back comes after the settings are saved")
    papers = await _papers(session, context=context, bio=bio)
    if any(paper.card.is_open for paper in papers):
        raise CardsStillOpen("a paper of this sitting waits for its yes")
    profile = await audited_profile_read(session, context)
    language = settings_language(row, profile.language)
    lines = await _read_back_lines(session, context=context, papers=papers, language=language)
    if set(said) != {fact.id for fact, _ in lines}:
        raise NotEveryLineAnswered(f"{len(lines)} line(s) to answer, {len(said)} answered")
    moment = utcnow()
    event: Event | None = None
    for position, (fact, _) in enumerate(lines):
        answer = said[fact.id]
        dispute_id = None
        if answer is Answer.NO:
            if event is None:
                event = await record_event(
                    session,
                    context=context,
                    kind=EventKind.ONBOARDING,
                    occurred_at=moment,
                    label="read-back",
                    source_channel=SourceChannel.APP,
                )
            dispute_id = (await _dispute(session, context=context, fact=fact, event=event)).id
        await audited_write(
            session,
            BiographyLine,
            context,
            BIO_SCOPE,
            session_id=bio.id,
            position=position,
            fact_id=fact.id,
            answer=answer,
            dispute_fact_id=dispute_id,
            answered_by_person_id=context.person_id,
            answered_at=moment,
        )
    await _stamped(
        session,
        context=context,
        bio=bio,
        read_back_at=moment,
        read_back_by_person_id=context.person_id,
    )
    return await _view(session, context=context, bio=bio)


def _summary_lines(
    language: str, *, papers: int, facts: int, disputes: int, who: str | None, prompts: int
) -> tuple[str, ...]:
    said: list[str | None] = []
    if papers == 0:
        said.append(summary("papers_none", language))
    elif papers == 1:
        said.append(summary("papers_one", language))
    else:
        said.append(summary("papers_many", language, papers))
    if facts == 1:
        said.append(summary("facts_one", language))
    elif facts > 1:
        said.append(summary("facts_many", language, facts))
    if disputes == 1:
        said.append(summary("disputes_one", language))
    elif disputes > 1:
        said.append(summary("disputes_many", language, disputes))
    if disputes:
        said.append(after_a_no(who, language))
    if prompts:
        said.append(summary("plan_first", language))
        if prompts > 1:
            said.append(summary("plan_count", language, prompts))
    else:
        said.append(summary("plan_none", language))
    said.append(summary("ready", language))
    return tuple(line for line in said if line is not None)


@audited(Action.WRITE, BIO_SCOPE, SESSION)
async def close_biography(session: AsyncSession, *, context: KeyContext) -> Closed:
    """Close the sitting: the gaps it left open become the first week's plan, and the summary
    says what was saved, what he said was not right, and what Nura asks for tomorrow."""
    a_setter(context)
    bio = await _require_open(session, context=context)
    row = await current_settings(session, context=context)
    if row is None:
        raise NotAtThisStep("the biography closes after the settings are saved")
    papers = await _papers(session, context=context, bio=bio)
    if any(paper.card.is_open for paper in papers):
        raise CardsStillOpen("a paper of this sitting waits for its yes")
    profile = await audited_profile_read(session, context)
    language = settings_language(row, profile.language)
    gaps = open_gaps(await what_is_known(session, context=context))
    plan, prompts = await make_plan(
        session,
        context=context,
        session_id=bio.id,
        gaps=gaps,
        breakfast=parse_clock_time(row.breakfast_time),
    )
    answered = await _answered(session, context=context, bio=bio, papers=papers, language=language)
    fields = [
        field
        for paper in papers
        for field in await card_fields(session, context=context, card_id=paper.card.id)
        if field.fact_id is not None
    ]
    disputes = sum(1 for line in answered if line.answer is Answer.NO)
    who = await _who_checks(session, context=context, bio=bio) if disputes else None
    lines = _summary_lines(
        language,
        papers=len(papers),
        facts=len(fields),
        disputes=disputes,
        who=who,
        prompts=len(prompts),
    )
    await _stamped(
        session, context=context, bio=bio, closed_at=utcnow(), closed_by_person_id=context.person_id
    )
    return Closed(
        view=await _view(session, context=context, bio=bio),
        summary=Summary(
            papers=len(papers),
            facts=len(fields),
            conditions=len(row.conditions),
            medicines=sum(
                1 for field in fields if (field.subject, field.attribute) == ("medicine", "name")
            ),
            disputes=disputes,
            questions=len(gaps),
            prompts=len(prompts),
            first_prompt_at=None if not prompts else as_utc(prompts[0].due_at),
            lines=lines,
        ),
        plan=plan,
        prompts=prompts,
    )
