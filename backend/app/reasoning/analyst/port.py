"""The Health Analyst port (docs/recommendation-engine.md, the Health Analyst backend): one
weekly report, six sections, in a fixed order. `RuleAnalyst` (`app.reasoning.analyst.rule`) is
the default, deterministic adapter; `ClaudeAnalyst` (`app.reasoning.analyst.claude_adapter`) is
the agent behind the same port, gated the same way every other Claude-backed adapter here is
(`app.llm.residency.allow_external_model`) and falling back to the rule report on any doubt.

Nothing above this module assumes which adapter wrote a report: both speak `Report`, built of
`Section`s, built of `Insight`s, each already the plain words a person reads, already cited,
already checked (`app.reasoning.analyst.pipeline.finalize`) — never a row, never a raw value.

`report_stream` is the one method every adapter implements: an async iterator of `Step` events,
one for each real read behind the report — the same shape `app.search.ask.recall_stream`
already promises for Ask's trace — then the finished `Report`, last. `report` (below) is
`report_stream`, drained, for a caller that wants the whole thing at once (the weekly job, the
non-streaming `GET`): the two can never drift apart, the way `recall` and `recall_stream`
cannot (`app/search/ask.py`'s own module doc).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.keys.context import KeyContext
from app.keys.scopes import Scope


class InsightKind(StrEnum):
    """What kind of thing an insight is about — the contract's own vocabulary, never
    extended without the sibling UI builder's own names changing too."""

    TREND = "trend"
    GAP = "gap"
    MEDICINE = "medicine"
    SUPPLEMENT = "supplement"
    COST = "cost"
    COVERAGE = "coverage"
    CHECK = "check"


class AskWho(StrEnum):
    DOCTOR = "doctor"
    PHARMACIST = "pharmacist"
    NOBODY = "nobody"


class Confidence(StrEnum):
    SURE = "sure"
    LIKELY = "likely"
    WORTH_A_LOOK = "worth_a_look"


@dataclass(frozen=True, slots=True)
class Evidence:
    """One id an insight rests on, and the scope it was read under — the same discipline
    `app.reasoning.patterns.series.Evidence` already holds every series point to: never a
    row, never a free-text field that could carry more than the id itself."""

    id: str
    kind: str
    label: str
    scope: Scope | None = None


@dataclass(frozen=True, slots=True)
class Insight:
    insight_id: str
    kind: InsightKind
    text: str
    ask_who: AskWho
    evidence: tuple[Evidence, ...]
    why_plain: str
    confidence: Confidence


@dataclass(frozen=True, slots=True)
class Section:
    key: str
    title: str
    insights: tuple[Insight, ...]


SECTION_TITLES: dict[str, dict[str, str]] = {
    "en": {
        "what_changed": "What changed",
        "worth_a_look": "Worth a look",
        "medicines_and_supplements": "Medicines and supplements",
        "what_you_pay": "What you pay",
        "screenings_due": "Screenings due",
        "questions_for_the_doctor": "Questions for the doctor",
    },
    "ms": {
        "what_changed": "Apa yang berubah",
        "worth_a_look": "Patut dilihat",
        "medicines_and_supplements": "Ubat dan suplemen",
        "what_you_pay": "Apa yang anda bayar",
        "screenings_due": "Pemeriksaan yang perlu",
        "questions_for_the_doctor": "Soalan untuk doktor",
    },
    "zh": {
        "what_changed": "有什么变化",
        "worth_a_look": "值得留意",
        "medicines_and_supplements": "药物和补充品",
        "what_you_pay": "您付的钱",
        "screenings_due": "该做的检查",
        "questions_for_the_doctor": "问医生的问题",
    },
}
"""Section titles, tagged `@patient`: whole words a person reads at the top of each part of
the report, in the fixed order `SECTION_KEYS` names."""

SECTION_KEYS: tuple[str, ...] = (
    "what_changed",
    "worth_a_look",
    "medicines_and_supplements",
    "what_you_pay",
    "screenings_due",
    "questions_for_the_doctor",
)
"""The contract's own order: `POST /profiles/{id}/insights/stream` and every saved report
carry sections in exactly this order, never resorted by a caller."""

SECTION_SCOPE: dict[str, Scope] = {
    "what_changed": Scope.READINGS,
    "worth_a_look": Scope.READINGS,
    "medicines_and_supplements": Scope.MEDICINES,
    "what_you_pay": Scope.MONEY,
    "screenings_due": Scope.RECORDS,
    # Built from what the other five already found (a rollup of every insight whose
    # `ask_who` is "doctor"); it carries no scope of its own. A key holding none of the
    # other scopes gets no questions to roll up, and the section is left out the same way
    # theirs are — not because this key lacks it.
}
"""Which scope each section's own read stands behind, for `RuleAnalyst`'s withholding
(`.claude/rules` — "a key without a scope gets that section withheld, named")."""


@dataclass(frozen=True, slots=True)
class Report:
    report_id: str
    generated_at: datetime
    week_of: date
    language: str
    source: str
    boundary: tuple[str, ...]
    sections: tuple[Section, ...]


class StepKey(StrEnum):
    """One real read behind the report, in the order it happens — the contract's own
    `{"type": "step", "key": ..., "label": ...}` events."""

    RECORDS = "records"
    SERIES = "series"
    MEDICINES = "medicines"
    LEDGER = "ledger"
    COVERAGE = "coverage"


@dataclass(frozen=True, slots=True)
class Step:
    key: StepKey
    label: str


ReportEvent = Step | Report


class Analyst(Protocol):
    """The port. `report_stream` is the one method an adapter implements; `report` (a free
    function below, not part of the port) drains it for a caller that wants the whole thing."""

    def report_stream(
        self,
        session: AsyncSession,
        *,
        context: KeyContext,
        language: str,
        now: datetime | None = None,
    ) -> AsyncIterator[ReportEvent]: ...


async def report(
    analyst: Analyst,
    session: AsyncSession,
    *,
    context: KeyContext,
    language: str,
    now: datetime | None = None,
) -> Report:
    """`report_stream`, drained: every step read and discarded, the finished `Report` kept —
    for the weekly job and the non-streaming `GET`, so the two paths can never say a
    different report for the same input (the same promise `app.search.ask.recall` keeps
    over `recall_stream`)."""
    built: Report | None = None
    async for event in analyst.report_stream(session, context=context, language=language, now=now):
        if isinstance(event, Report):
            built = event
    assert built is not None  # every adapter's stream ends on exactly one Report
    return built


__all__ = [
    "AskWho",
    "Analyst",
    "Confidence",
    "Evidence",
    "Insight",
    "InsightKind",
    "Report",
    "ReportEvent",
    "SECTION_KEYS",
    "SECTION_SCOPE",
    "SECTION_TITLES",
    "Section",
    "Step",
    "StepKey",
    "report",
]
