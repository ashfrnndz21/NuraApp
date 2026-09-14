"""The shapes of the feeling cloud, a tap and its answer, a note, a nudge plan, the metrics and
the Me page (E17). Every patient line in them was written from a template and verified before
it got here; the reasons are codes and ids, and the metrics are counts."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.db import as_utc
from app.delivery.nudges.handoff import Held, NudgeDraft, NudgePlan
from app.delivery.nudges.metrics import Metrics
from app.delivery.nudges.models import Nudge, NudgeKind, NudgeResponse, ResponseKind
from app.reasoning.feelings.cloud import Cloud
from app.reasoning.feelings.models import FeelingNote, NoteOutcome
from app.reasoning.feelings.service import Answered, RedPath, Tapped
from app.reasoning.feelings.words import Answer, FollowUp
from app.safety.red_flags import Feeling

LanguageField = Field(default=None, min_length=2, max_length=16)


class FeelingIn(BaseModel):
    """A tap on the feeling cloud: one word from its fixed set."""

    word: Feeling
    language: str | None = LanguageField


class CloudWordOut(BaseModel):
    """One word on the cloud. `reasons` is why it is there, by code and id — for the audit
    and the metrics, never for his screen."""

    word: Feeling
    label: str
    weight: int
    red: bool
    reasons: list[dict[str, Any]]


class CloudOut(BaseModel):
    """The strip on Today: whether it shows now and why (a code), the question, the words
    biggest first with "Fine today" last, and the State they were weighed from."""

    state_id: uuid.UUID | None
    language: str
    show: bool
    because: str
    prompt: list[str]
    words: list[CloudWordOut]

    @classmethod
    def of(cls, cloud: Cloud) -> CloudOut:
        return cls(
            state_id=cloud.state_id,
            language=cloud.language,
            show=cloud.show,
            because=cloud.because,
            prompt=list(cloud.prompt),
            words=[
                CloudWordOut(
                    word=word.word,
                    label=word.label,
                    weight=word.weight,
                    red=word.red,
                    reasons=[reason.as_json() for reason in word.reasons],
                )
                for word in cloud.words
            ],
        )


class ChoiceOut(BaseModel):
    answer: Answer
    label: str


class QuestionOut(BaseModel):
    """The one thing a tap asks back, and the buttons under it."""

    follow_up: FollowUp
    words: str
    answers: list[ChoiceOut]


def _red(red: RedPath | None) -> dict[str, Any]:
    flag = None if red is None else red.flag
    return {
        "red_flag": red is not None,
        "flag_id": None if flag is None else flag.id,
        "told": [] if flag is None else [uuid.UUID(one) for one in flag.told],
        "suppressed_because": None if flag is None else flag.suppressed_because,
        "escalation_id": None if red is None or red.escalation is None else red.escalation.id,
        "opens": None if red is None else red.opens,
    }


class FeelingOut(BaseModel):
    """What a tap did. A red word: the flag, who was told, the ladder written for delivery,
    and the not-feeling-well card's words with the flow to open — no question, no note. Any
    other word: its one question, or, for "Fine today", what it says back."""

    event_id: uuid.UUID
    word: Feeling
    tap_id: uuid.UUID
    language: str
    red_flag: bool
    flag_id: uuid.UUID | None
    told: list[uuid.UUID]
    suppressed_because: str | None
    escalation_id: uuid.UUID | None
    opens: str | None
    question: QuestionOut | None
    lines: list[str]

    @classmethod
    def of(cls, tapped: Tapped) -> FeelingOut:
        question = tapped.question
        return cls(
            event_id=tapped.tap.event_id,
            word=tapped.tap.word,
            tap_id=tapped.tap.id,
            language=tapped.language,
            question=None
            if question is None
            else QuestionOut(
                follow_up=question.follow_up,
                words=question.words,
                answers=[ChoiceOut(answer=a, label=label) for a, label in question.answers],
            ),
            lines=list(tapped.lines),
            **_red(tapped.red),
        )


class AnswerIn(BaseModel):
    answer: Answer
    language: str | None = LanguageField


class NoteOut(BaseModel):
    """A note: the headline, at most two things to tell the doctor, who does the next thing,
    the spoken twin, and the boundary line it ends on; the reasons by id; the State."""

    note_id: uuid.UUID
    tap_id: uuid.UUID
    word: Feeling
    answer: Answer
    language: str
    headline: str
    lines: list[str]
    then: str
    voice: list[str]
    boundary: str
    reasons: list[dict[str, Any]]
    outcome: NoteOutcome
    appointment_id: uuid.UUID | None
    rendered_from_state: uuid.UUID
    created_at: datetime

    @classmethod
    def of(cls, note: FeelingNote) -> NoteOut:
        return cls(
            note_id=note.id,
            tap_id=note.tap_id,
            word=note.word,
            answer=note.answer,
            language=note.language,
            headline=note.headline,
            lines=list(note.lines),
            then=note.then,
            voice=list(note.voice),
            boundary=note.boundary or "",
            reasons=list(note.reasons),
            outcome=note.outcome,
            appointment_id=note.appointment_id,
            rendered_from_state=note.state_id,
            created_at=as_utc(note.created_at),
        )


class AnsweredOut(BaseModel):
    """What his answer did: a note, or — a yes that made the word red — the red-flag path."""

    tap_id: uuid.UUID
    answer: Answer
    red_flag: bool
    flag_id: uuid.UUID | None
    told: list[uuid.UUID]
    suppressed_because: str | None
    escalation_id: uuid.UUID | None
    opens: str | None
    lines: list[str]
    note: NoteOut | None
    note_withheld_because: str | None

    @classmethod
    def of(cls, answered: Answered) -> AnsweredOut:
        assert answered.tap.answer is not None
        return cls(
            tap_id=answered.tap.id,
            answer=answered.tap.answer,
            lines=[] if answered.red is None else list(answered.red.lines),
            note=None if answered.note is None else NoteOut.of(answered.note),
            note_withheld_because=answered.note_withheld_because,
            **_red(answered.red),
        )


class NudgeDraftOut(BaseModel):
    kind: NudgeKind
    lines: list[str]
    voice: list[str]
    language: str
    why: str
    reason: dict[str, Any]
    cap_class: str
    scope: str
    day: date
    send_after: datetime
    expires_at: datetime
    state_id: uuid.UUID
    priority: int
    dedupe_key: str
    memo_id: uuid.UUID | None

    @classmethod
    def of(cls, draft: NudgeDraft) -> NudgeDraftOut:
        return cls(
            kind=draft.kind,
            lines=list(draft.lines),
            voice=list(draft.voice),
            language=draft.language,
            why=draft.why,
            reason=dict(draft.reason),
            cap_class=draft.cap_class.value,
            scope=draft.scope.value,
            day=draft.day,
            send_after=draft.send_after,
            expires_at=draft.expires_at,
            state_id=draft.state_id,
            priority=draft.priority,
            dedupe_key=draft.dedupe_key,
            memo_id=draft.memo_id,
        )


class HeldOut(BaseModel):
    kind: NudgeKind
    because: str
    priority: int | None
    reason: dict[str, Any]

    @classmethod
    def of(cls, held: Held) -> HeldOut:
        return cls(
            kind=held.kind, because=held.because, priority=held.priority, reason=dict(held.reason)
        )


class NudgePlanOut(BaseModel):
    """The day's plan: what goes (at most one), what was held and why, or why nothing may."""

    day: date
    drafts: list[NudgeDraftOut]
    held: list[HeldOut]
    none_because: str | None

    @classmethod
    def of(cls, plan: NudgePlan) -> NudgePlanOut:
        return cls(
            day=plan.day,
            drafts=[NudgeDraftOut.of(d) for d in plan.drafts],
            held=[HeldOut.of(h) for h in plan.held],
            none_because=plan.none_because,
        )


class NudgeOut(BaseModel):
    nudge_id: uuid.UUID
    kind: NudgeKind
    day: str
    lines: list[str]
    why: str
    reason: dict[str, Any]
    cap_class: str
    send_after: datetime
    expires_at: datetime
    rendered_from_state: uuid.UUID
    handed_over_at: datetime

    @classmethod
    def of(cls, nudge: Nudge) -> NudgeOut:
        return cls(
            nudge_id=nudge.id,
            kind=nudge.kind,
            day=nudge.day,
            lines=list(nudge.lines),
            why=nudge.why,
            reason=dict(nudge.reason),
            cap_class=nudge.cap_class.value,
            send_after=as_utc(nudge.send_after),
            expires_at=as_utc(nudge.expires_at),
            rendered_from_state=nudge.state_id,
            handed_over_at=as_utc(nudge.handed_over_at),
        )


class HandedOverOut(BaseModel):
    plan: NudgePlanOut
    nudge: NudgeOut


class NudgeResponseIn(BaseModel):
    kind: ResponseKind


class NudgeResponseOut(BaseModel):
    response_id: uuid.UUID
    nudge_id: uuid.UUID
    kind: ResponseKind
    at: datetime

    @classmethod
    def of(cls, response: NudgeResponse) -> NudgeResponseOut:
        return cls(
            response_id=response.id,
            nudge_id=response.nudge_id,
            kind=response.kind,
            at=as_utc(response.at),
        )


class KindCountsOut(BaseModel):
    handed_over: int
    accepted: int
    dismissed: int
    seen: int
    ignored: int
    acceptance: float | None


class WeekOut(BaseModel):
    week: str
    starts_on: date
    taps: int
    fine_today: int
    fine_share: float | None
    nudges: dict[NudgeKind, KindCountsOut]


class NudgeMetricsOut(BaseModel):
    """Counts only, per week on his wall: taps, "Fine today" and its share, and each kind of
    nudge handed over, accepted, dismissed, seen and ignored. No word, no line, no id."""

    weeks: list[WeekOut]
    ignored_streaks: dict[NudgeKind, int]
    resting: list[NudgeKind]
    as_of: datetime

    @classmethod
    def of(cls, metrics: Metrics) -> NudgeMetricsOut:
        return cls(
            weeks=[
                WeekOut(
                    week=week.week,
                    starts_on=week.starts_on,
                    taps=week.taps,
                    fine_today=week.fine_today,
                    fine_share=week.fine_share,
                    nudges={
                        kind: KindCountsOut(
                            handed_over=counts.handed_over,
                            accepted=counts.accepted,
                            dismissed=counts.dismissed,
                            seen=counts.seen,
                            ignored=counts.ignored,
                            acceptance=counts.acceptance,
                        )
                        for kind, counts in week.nudges.items()
                    },
                )
                for week in metrics.weeks
            ],
            ignored_streaks=dict(metrics.ignored_streaks),
            resting=list(metrics.resting),
            as_of=metrics.as_of,
        )


class MeSummaryOut(BaseModel):
    """The Me page: whose it is, and the number that only goes up, in his words."""

    name: str
    language: str
    proud_days: int
    as_of: datetime
    lines: list[str]
