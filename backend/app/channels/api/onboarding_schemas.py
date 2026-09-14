"""The shapes onboarding puts on the wire (E01-02, E01-03, E01-04).

Plain JSON for the screens of docs/onboarding.html: the word cloud, the settings, where a
biography stands with the words of its step, the papers and their review cards, the
read-back lines and the questions, the close's summary and the first week's plan. Every
sentence in them is his, in his language, checked against docs/plain-words.md before it got
here; ids and codes are for the client, never shown.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator

from app.channels.api.schemas import PhotoIn, ReviewCardOut, utc
from app.onboarding.biography import BiographyView, LineView, PaperView, Question, Summary
from app.onboarding.conditions import Condition, name_of
from app.onboarding.gaps import BY_CODE
from app.onboarding.models import Answer, Density, PaperKind, PlanPrompt, PromptStatus
from app.onboarding.plan import PlanView
from app.onboarding.settings import (
    SettingsValues,
    SettingsView,
    clock_time,
    parse_clock_time,
)
from app.onboarding.words import prompt as prompt_words
from app.regions import REGION_TZ, Region

CLOCK = r"^([01][0-9]|2[0-3]):[0-5][0-9]$"
"""A time of day on his wall clock, "07:30"."""


# --- E01-03: the word cloud and the settings ---------------------------------------------------


class ConditionOut(BaseModel):
    """One word of the cloud: its code, his name for it, how large it sits, what appears
    beside it once tapped, and whether the cloud shows it first."""

    code: str
    name: str
    weight: int
    related: list[str]
    top: bool

    @classmethod
    def of(cls, condition: Condition, language: str) -> ConditionOut:
        return cls(
            code=condition.code,
            name=condition.name(language),
            weight=condition.weight,
            related=list(condition.related),
            top=condition.top,
        )


class ConditionsOut(BaseModel):
    """The cloud: the graph's version, the words it shows first (`top`), and every word. A
    word that is not `top` appears once a word naming it in `related` is picked."""

    language: str
    version: int
    top: list[str]
    conditions: list[ConditionOut]


class SettingsIn(BaseModel):
    """The settings screen, whole (a PUT replaces it). Everything but the language has a
    default: nothing tapped, detailed, every help off, no names, no breakfast time."""

    language: str = Field(min_length=2, max_length=16)
    conditions: list[str] = Field(default_factory=list, max_length=80)
    density: Density = Density.DETAILED
    large_text: bool = False
    high_contrast: bool = False
    voice_on: bool = False
    big_targets: bool = False
    one_thing_per_screen: bool = False
    read_back: bool = False
    repeat_prompts: bool = False
    preferred_name: str | None = Field(default=None, max_length=80)
    doctor_name: str | None = Field(default=None, max_length=80)
    breakfast_time: str | None = Field(default=None, pattern=CLOCK)
    checkin_time: str | None = Field(default=None, pattern=CLOCK)
    """When he is asked how he is (E17), "HH:MM" on his clock."""
    birth_decade: int | None = None
    """The decade he was born in, by its first year: 1950. Never the year."""

    def as_values(self) -> SettingsValues:
        return SettingsValues(
            language=self.language,
            conditions=tuple(self.conditions),
            density=self.density,
            large_text=self.large_text,
            high_contrast=self.high_contrast,
            voice_on=self.voice_on,
            big_targets=self.big_targets,
            one_thing_per_screen=self.one_thing_per_screen,
            read_back=self.read_back,
            repeat_prompts=self.repeat_prompts,
            preferred_name=self.preferred_name,
            doctor_name=self.doctor_name,
            breakfast_time=parse_clock_time(self.breakfast_time),
            checkin_time=parse_clock_time(self.checkin_time),
            birth_decade=self.birth_decade,
        )


class SettingsOut(BaseModel):
    """The settings as the caller's key reads them. `withheld` names the parts his key does
    not open — `conditions` and `doctor_name` without the record — and those are null.
    `settings_id` is null until the first save; the values are then the defaults, in the
    profile's language."""

    settings_id: uuid.UUID | None
    profile_id: uuid.UUID
    language: str
    conditions: list[str] | None
    density: Density
    large_text: bool
    high_contrast: bool
    voice_on: bool
    big_targets: bool
    one_thing_per_screen: bool
    read_back: bool
    repeat_prompts: bool
    preferred_name: str | None
    doctor_name: str | None
    breakfast_time: str | None
    checkin_time: str | None
    birth_decade: int | None
    set_by_person_id: uuid.UUID | None
    set_at: datetime | None
    withheld: list[str]

    @classmethod
    def of(cls, view: SettingsView, profile_id: uuid.UUID) -> SettingsOut:
        values = view.values
        return cls(
            settings_id=None if view.row is None else view.row.id,
            profile_id=profile_id,
            language=values.language,
            conditions=None if "conditions" in view.withheld else list(values.conditions),
            density=values.density,
            large_text=values.large_text,
            high_contrast=values.high_contrast,
            voice_on=values.voice_on,
            big_targets=values.big_targets,
            one_thing_per_screen=values.one_thing_per_screen,
            read_back=values.read_back,
            repeat_prompts=values.repeat_prompts,
            preferred_name=values.preferred_name,
            doctor_name=None if "doctor_name" in view.withheld else values.doctor_name,
            breakfast_time=clock_time(values.breakfast_time),
            checkin_time=clock_time(values.checkin_time),
            birth_decade=None if "birth_decade" in view.withheld else values.birth_decade,
            set_by_person_id=None if view.row is None else view.row.set_by_person_id,
            set_at=None if view.row is None else utc(view.row.set_at),
            withheld=list(view.withheld),
        )


# --- E01-02: the biography ------------------------------------------------------------------


class ScriptOut(BaseModel):
    """The words of the step he is at: a headline and a few lines, in his language."""

    headline: str
    lines: list[str]


class PaperOut(BaseModel):
    paper_id: uuid.UUID
    position: int
    paper: PaperKind
    artifact_id: uuid.UUID
    card_id: uuid.UUID
    document_kind: str
    confirmed: bool

    @classmethod
    def of(cls, view: PaperView) -> PaperOut:
        return cls(
            paper_id=view.paper.id,
            position=view.paper.position,
            paper=view.paper.paper,
            artifact_id=view.paper.artifact_id,
            card_id=view.card.id,
            document_kind=view.card.document_kind.value,
            confirmed=not view.card.is_open,
        )


class PaperIn(PhotoIn):
    """A paper of the sitting: the photo, as for `POST /profiles/{id}/photos`, and what he
    says it is."""

    paper: PaperKind


class AttachIn(BaseModel):
    """A paper already photographed through capture, joining the sitting by its review card;
    what he says it is, or what it was read as."""

    card_id: uuid.UUID
    paper: PaperKind | None = None


class PaperAddedOut(BaseModel):
    """The paper, and the review card it was read into: confirm the card where every card is
    confirmed (`POST /profiles/{id}/confirmations`, then `…/review-cards/{card}/confirm`)."""

    paper: PaperOut
    card: ReviewCardOut


class LineOut(BaseModel):
    """A read-back line: the fact it reads back, the words, and once answered the answer and,
    for a "no", the dispute it opened."""

    fact_id: uuid.UUID
    line: str
    answer: Answer | None
    dispute_fact_id: uuid.UUID | None

    @classmethod
    def of(cls, line: LineView) -> LineOut:
        return cls(
            fact_id=line.fact_id,
            line=line.line,
            answer=line.answer,
            dispute_fact_id=line.dispute_fact_id,
        )


class QuestionOut(BaseModel):
    """A question the papers raised: its id (the gap it would fill — what `POST …/questions`
    takes), the line, and what he said: kept, not this one (false), or nothing yet (null).
    `state_id` is the State it was worked out under; `source` says where it came from, in his
    words (what he told, which paper, or the papers together); `handed_over_to` is the visit
    whose list a kept one is on (E05), null while it waits for a visit to be booked."""

    question_id: str
    line: str
    kept: bool | None
    state_id: uuid.UUID | None
    source: str | None
    handed_over_to: uuid.UUID | None

    @classmethod
    def of(cls, question: Question) -> QuestionOut:
        return cls(
            question_id=question.gap,
            line=question.line,
            kept=question.kept,
            state_id=question.state_id,
            source=question.source,
            handed_over_to=question.handed_over_to,
        )


class QuestionIn(BaseModel):
    """Keep this question, or not this one."""

    question_id: str = Field(min_length=1, max_length=32)
    keep: bool


class BiographyOut(BaseModel):
    """Where the sitting stands. `step` is one of about_you, papers, read_back, questions,
    closed; `next` names the one call to make next (save_settings, add_paper, confirm_cards,
    read_back, close) or null once closed; `prompt` is the step's words."""

    biography_id: uuid.UUID
    profile_id: uuid.UUID
    step: str
    next: str | None
    language: str
    opened_at: datetime
    opened_by_person_id: uuid.UUID
    read_back_at: datetime | None
    closed_at: datetime | None
    prompt: ScriptOut
    papers: list[PaperOut]
    open_cards: int
    read_back: list[LineOut]
    questions: list[QuestionOut]
    after_no: str | None
    """After a "no" on the read-back: who looks at the paper again."""
    more: str | None
    """How many more questions wait for later, past the ones shown."""

    @classmethod
    def of(cls, view: BiographyView) -> BiographyOut:
        bio = view.session
        return cls(
            biography_id=bio.id,
            profile_id=bio.profile_id,
            step=view.step.value,
            next=view.next,
            language=view.language,
            opened_at=utc(bio.opened_at),
            opened_by_person_id=bio.opened_by_person_id,
            read_back_at=None if bio.read_back_at is None else utc(bio.read_back_at),
            closed_at=None if bio.closed_at is None else utc(bio.closed_at),
            prompt=ScriptOut(headline=view.script.headline, lines=list(view.script.lines)),
            papers=[PaperOut.of(paper) for paper in view.papers],
            open_cards=view.open_cards,
            read_back=[LineOut.of(line) for line in view.read_back],
            questions=[QuestionOut.of(question) for question in view.questions],
            after_no=view.after_no,
            more=view.more,
        )


class AnswerIn(BaseModel):
    fact_id: uuid.UUID
    answer: Answer


class ReadBackIn(BaseModel):
    """His answer to the read-back: every line still waiting at once (`answers`), or one line
    (`line_id`, the line's `fact_id`, and `answer`) — one thing a screen."""

    answers: list[AnswerIn] | None = None
    line_id: uuid.UUID | None = None
    answer: Answer | None = None

    @model_validator(mode="after")
    def _one_way(self) -> ReadBackIn:
        whole = self.answers is not None
        one = self.line_id is not None and self.answer is not None
        if whole == one or (not whole and (self.line_id is None) != (self.answer is None)):
            raise ValueError("answer every line (`answers`) or one line (`line_id` and `answer`)")
        return self


# --- E01-04: the first week -------------------------------------------------------------------


def _word_of(gap: str, language: str) -> str | None:
    found = BY_CODE.get(gap)
    return None if found is None or not found.words else name_of(found.words[0], language)


class PromptOut(BaseModel):
    """One day's prompt: the gap it asks to fill (`prompt`, the code the skip route takes),
    which day, when it is due — in UTC and on his clock — where it stands, and its words."""

    prompt: str
    day: int
    tier: int
    capture: str
    """How it is filled: "photo" (the camera), "pdf" (an import), "tap" (a follow-up
    question), or "invite" (letting someone in)."""
    word: str | None
    """The word of the cloud the gap is about, in his language, or null when it is about none."""
    deferred: int
    """How many times he said Later: once sends it to the back of the week, twice retires it."""
    due_at: datetime
    due_local: str
    status: PromptStatus
    done_at: datetime | None
    done_by_fact_id: uuid.UUID | None
    skipped_at: datetime | None
    headline: str | None
    line: str | None
    action: str | None

    @classmethod
    def of(
        cls, prompt: PlanPrompt, *, region: Region, language: str, doctor: str | None
    ) -> PromptOut:
        words = prompt_words(prompt.gap, language, doctor)
        due = utc(prompt.due_at)
        return cls(
            prompt=prompt.gap,
            day=prompt.day,
            tier=BY_CODE[prompt.gap].tier if prompt.gap in BY_CODE else 3,
            capture=BY_CODE[prompt.gap].capture if prompt.gap in BY_CODE else "photo",
            word=_word_of(prompt.gap, language),
            deferred=prompt.deferred,
            due_at=due,
            due_local=due.astimezone(REGION_TZ[region]).isoformat(),
            status=prompt.status,
            done_at=None if prompt.done_at is None else utc(prompt.done_at),
            done_by_fact_id=prompt.done_by_fact_id,
            skipped_at=None if prompt.skipped_at is None else utc(prompt.skipped_at),
            headline=None if words is None else words.headline,
            line=None if words is None else words.line,
            action=None if words is None else words.action,
        )


class LaterIn(BaseModel):
    """Later, on one prompt of the week, by its gap."""

    gap_id: str = Field(min_length=1, max_length=32)


class PlanOut(BaseModel):
    """The first week. `stopped` once the record holds his medicines, his last visit and his
    next visit (`stopped_because` lists which of the three it holds); `due` is the one prompt
    due at the moment asked about (`?at=`, now by default), or none."""

    plan_id: uuid.UUID
    profile_id: uuid.UUID
    biography_id: uuid.UUID | None
    created_at: datetime
    first_day: date
    breakfast_time: str
    timezone: str
    stopped: bool
    stopped_because: list[str]
    prompts: list[PromptOut]
    due: list[PromptOut]

    @classmethod
    def of(
        cls,
        view: PlanView,
        due: Sequence[PlanPrompt],
        *,
        region: Region,
        language: str,
        doctor: str | None,
    ) -> PlanOut:
        plan = view.plan

        def out(prompt: PlanPrompt) -> PromptOut:
            return PromptOut.of(prompt, region=region, language=language, doctor=doctor)

        return cls(
            plan_id=plan.id,
            profile_id=plan.profile_id,
            biography_id=plan.session_id,
            created_at=utc(plan.created_at),
            first_day=plan.first_day,
            breakfast_time=plan.breakfast_time,
            timezone=str(REGION_TZ[region]),
            stopped=view.stopped,
            stopped_because=list(view.stopped_because),
            prompts=[out(prompt) for prompt in view.prompts],
            due=[out(prompt) for prompt in due],
        )


class SummaryOut(BaseModel):
    """The close of a sitting: the counts, and `lines`, the summary in his words."""

    papers: int
    facts: int
    conditions: int
    medicines: int
    disputes: int
    questions: int
    prompts: int
    first_prompt_at: datetime | None
    lines: list[str]

    @classmethod
    def of(cls, summary: Summary) -> SummaryOut:
        return cls(
            papers=summary.papers,
            facts=summary.facts,
            conditions=summary.conditions,
            medicines=summary.medicines,
            disputes=summary.disputes,
            questions=summary.questions,
            prompts=summary.prompts,
            first_prompt_at=summary.first_prompt_at,
            lines=list(summary.lines),
        )


class ClosedOut(BaseModel):
    biography: BiographyOut
    summary: SummaryOut
    plan: PlanOut
