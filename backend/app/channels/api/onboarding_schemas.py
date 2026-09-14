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

from pydantic import BaseModel, Field

from app.channels.api.schemas import PhotoIn, ReviewCardOut, utc
from app.onboarding.biography import BiographyView, LineView, PaperView, Question, Summary
from app.onboarding.conditions import Condition
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
    language: str
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
    gap: str
    line: str

    @classmethod
    def of(cls, question: Question) -> QuestionOut:
        return cls(gap=question.gap, line=question.line)


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
        )


class AnswerIn(BaseModel):
    fact_id: uuid.UUID
    answer: Answer


class ReadBackIn(BaseModel):
    """His answer to every read-back line, once each: yes or no."""

    answers: list[AnswerIn]


# --- E01-04: the first week -------------------------------------------------------------------


class PromptOut(BaseModel):
    """One day's prompt: the gap it asks to fill (`prompt`, the code the skip route takes),
    which day, when it is due — in UTC and on his clock — where it stands, and its words."""

    prompt: str
    day: int
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
