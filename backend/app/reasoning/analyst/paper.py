"""Checkpoint 3, "What it means for you" (`docs/design/experience-blueprint.html`, scene
`insight`): the moment a paper is confirmed, Nura connects it to the person's own record —
his medicines, his other results of the same analytes, his next visit — and offers back
questions for the doctor, never advice.

This reuses the Health Analyst's own machinery start to finish, the same gate every weekly
candidate already passes: `app.reasoning.analyst.pipeline.Candidate`/`finalize` is the one
safety check every candidate here goes through too, and a candidate that would touch a
medicine and fails it is rerouted through `app.reasoning.analyst.rule.ask_the_doctor` — the
same reroute the weekly report uses, never a second safety path. The Claude path (`app.
channels.api.analyst`) reuses `app.reasoning.analyst.claude_adapter.ClaudeAnalyst`'s own
`_ask_claude`/`_rebuild` unchanged: this module only builds a `Report`-shaped pool of
already rule-finalised candidates for that adapter to choose and rephrase from, so the cite
check and the `EXTERNAL_MODEL_PROCESSOR` audit line stay the analyst's own.

Values are compared only with the range printed on the paper itself (`_printed_range`),
never a guideline table: a fact's own embedded `range` where a sibling builder's shape has
landed, else the legacy sibling fact `{attribute}_reference_range` this backend writes today
(`app.llm.prompts.extract_document.txt`) — both shapes are read, so this module does not
care which one is on a given profile.

`read_phase` is the one half of this module that touches the database; it never calls a
model. The caller (`app.channels.api.analyst`) is the one that structures the three short
units of work a stream needs — reads, then the model call with no session open at all, then
the rebuild and the save — so no database transaction is ever open while a model call is in
flight (the defect `app.delivery.feed.background`'s own docstring describes: a synchronous
model call blocking the one event loop, and by extension a connection, for as long as it
takes).
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_read
from app.db import as_utc, utcnow
from app.delivery import analyst_strings as words
from app.drugs.registry import DrugRegistry, UnknownDrug
from app.errors import Refusal
from app.ingestion.models import ReviewCard, ReviewField
from app.ingestion.review import card_fields
from app.keys.context import KeyContext
from app.keys.scopes import Scope, scope_for_subject
from app.medicines.models import LineStatus, MedicationLine
from app.medicines.strings import PLAIN_NAME
from app.memory.models import Appointment
from app.memory.semantic import current_facts
from app.memory.spine import upcoming_appointments
from app.reasoning.analyst.pipeline import Candidate, finalize
from app.reasoning.analyst.port import AskWho, Confidence, Evidence, Insight, InsightKind
from app.reasoning.analyst.rule import ask_the_doctor
from app.safety.boundary import Surface, boundary_lines

REPORT_KEY = "questions_for_the_doctor"
"""The one section name a *saved* paper-scoped insight carries (`app.reasoning.analyst.
paper_service._section_json`) — cosmetic, read back by `questions_of` alone."""

CANDIDATE_SECTION_KEY = "paper_candidates"
"""The section key `app.channels.api.analyst._paper_events` puts the rule-finalised
candidates under before handing them to `ClaudeAnalyst`'s own `_ask_claude`/`_rebuild`
(`app.reasoning.analyst.claude_adapter`) — deliberately never
`app.reasoning.analyst.rule.QUESTIONS_KEY`: `_rebuild` treats that one key as the weekly
report's own rollup and always skips it, rebuilding it instead from what its other five
sections kept (its own docstring). A paper-scoped run has no other sections to roll up from,
so its own candidates must sit under an ordinary key `_rebuild` actually rebuilds."""


class NotAConfirmedPaper(Refusal):
    """No confirmed paper by this id on this profile — an unconfirmed card and another
    profile's artifact both refuse in these same words (404), the same standing `NoKey`
    already holds to (`app.keys.context`): neither should be told apart by what comes back.
    A key without RECORDS is turned away earlier and differently: `audited_read` requires
    the scope before it ever runs the query, so that case is `OutOfScope` (403), from
    `app.keys.context.KeyContext.require`, never this refusal."""


class PaperStepKey(StrEnum):
    """One real read behind a paper-scoped insight, in the order it happens."""

    PAPER = "paper"
    MEDICINES = "medicines"
    HISTORY = "history"
    VISIT = "visit"


@dataclass(frozen=True, slots=True)
class PaperStep:
    key: PaperStepKey
    label: str


@dataclass(frozen=True, slots=True)
class LookedAt:
    kind: str
    id: str
    label: str


@dataclass(frozen=True, slots=True)
class ReadResult:
    """Everything the read phase produced: finalised candidates (`pipeline.finalize` and,
    where a medicine one failed, `ask_the_doctor` already ran), ready either to become the
    insight as-is (rule mode) or to be shown to Claude to choose and rephrase from."""

    paper_label: str
    questions: tuple[Insight, ...]
    looked_at: tuple[LookedAt, ...]
    withheld: tuple[str, ...]


PaperReadEvent = PaperStep | ReadResult


@dataclass(frozen=True, slots=True)
class PaperInsight:
    """The finished, paper-scoped insight: a headline, what was actually read, and 1-4
    questions for the doctor — never a diagnosis, never advice."""

    report_id: str
    generated_at: datetime
    language: str
    source: str
    boundary: tuple[str, ...]
    headline: str
    looked_at: tuple[LookedAt, ...]
    questions: tuple[Insight, ...]
    withheld: tuple[str, ...]


_RANGE_RE = re.compile(
    r"^\s*(?:"
    r"(?P<le><=|<)\s*(?P<hi1>-?\d+(?:\.\d+)?)"
    r"|(?P<ge>>=|>)\s*(?P<lo1>-?\d+(?:\.\d+)?)"
    r"|(?P<lo2>-?\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(?P<hi2>-?\d+(?:\.\d+)?)"
    r")\s*$"
)
"""A printed lab range, as a lab prints it: "<130", ">=40", "3.5-5.5", "3.5 to 5.5". Whatever
does not match this small, literal set is read as no range at all — never guessed at."""


def _parse_printed_range(text: str) -> tuple[float | None, float | None] | None:
    match = _RANGE_RE.match(text)
    if match is None:
        return None
    if match.group("hi1") is not None:
        return (None, float(match.group("hi1")))
    if match.group("lo1") is not None:
        return (float(match.group("lo1")), None)
    if match.group("lo2") is not None and match.group("hi2") is not None:
        return (float(match.group("lo2")), float(match.group("hi2")))
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _printed_range(value: Any, sibling: Any) -> tuple[float | None, float | None] | None:
    """The range printed beside one value on the paper, in whichever of the two shapes this
    profile's facts carry: a `range` already embedded on the value itself (a sibling
    builder's shape, `{"value": 140, "range": "<130"}`), or the legacy sibling fact this
    backend writes today (`{attribute}_reference_range`, a plain string). Both are read, so
    neither shape needs to have landed for the other to work."""
    if isinstance(value, Mapping) and "range" in value:
        embedded = value.get("range")
        if isinstance(embedded, str):
            return _parse_printed_range(embedded)
        return None
    if isinstance(sibling, str):
        return _parse_printed_range(sibling)
    return None


def _band(value: float, bounds: tuple[float | None, float | None]) -> str | None:
    low, high = bounds
    if low is not None and value < low:
        return "below"
    if high is not None and value > high:
        return "above"
    return None


ANALYTE_DRUG_CLASS_HINTS: dict[str, tuple[str, ...]] = {
    "ldl": ("statin",),
    "cholesterol": ("statin",),
    "hdl": ("statin",),
    "triglycerides": ("statin", "fibrate"),
    "hba1c": ("biguanide", "sulfonylurea", "insulin"),
    "glucose": ("biguanide", "sulfonylurea", "insulin"),
    "potassium": ("ace_inhibitor", "arb", "diuretic"),
    "tsh": ("thyroid",),
}
"""A small heuristic, not a clinical claim, the same standing `app.reasoning.analyst.rule.
SUPPLEMENT_INDICATIONS` already holds: which drug classes are commonly relevant to a lab
analyte, used only to decide whether a value worth asking about is also worth citing a
medicine beside — never to say the medicine is right or wrong."""


def _plain_name(registry: DrugRegistry | None, generic: str, language: str) -> str:
    if registry is not None:
        try:
            return PLAIN_NAME[language][registry.monograph(generic).plain_name_id]
        except (UnknownDrug, KeyError):
            pass
    return generic


def _analyte_label(subject: str, attribute: str) -> str:
    return attribute.replace("_", " ") or subject.replace("_", " ")


async def _confirmed_paper(
    session: AsyncSession, *, context: KeyContext, artifact_id: uuid.UUID
) -> ReviewCard:
    """The confirmed review card for this artifact, on this profile — or `NotAConfirmedPaper`
    for an unconfirmed card, another profile's artifact, or a key without RECORDS: all three
    read the same way an `audited_read` under RECORDS scoped to this profile already reads
    them, so none is told apart from another (`NoKey`'s own reasoning)."""
    found = await audited_read(
        session,
        ReviewCard,
        context,
        Scope.RECORDS,
        where=(ReviewCard.artifact_id == artifact_id,),
    )
    confirmed = [card for card in found if not card.is_open]
    if not confirmed:
        raise NotAConfirmedPaper(
            f"no confirmed paper {artifact_id} on profile {context.profile_id}"
        )
    return confirmed[0]


def _page_of(fields: Sequence[ReviewField], *, subject: str, attribute: str) -> int | None:
    for field in fields:
        if field.subject == subject and field.attribute == attribute:
            span = field.span
            if isinstance(span, Mapping):
                page = span.get("page")
                if isinstance(page, int):
                    return page
    return None


def _evidence_label(paper_label: str, page: int | None) -> str:
    return f"{paper_label} (page {page})" if page is not None else paper_label


async def _value_candidates(
    session: AsyncSession,
    *,
    context: KeyContext,
    language: str,
    card: ReviewCard,
    paper_label: str,
    medicines: Sequence[MedicationLine],
    registry: DrugRegistry | None,
    moment: datetime,
) -> list[Candidate]:
    """One candidate for every value on this paper found outside its own printed range.
    Never compared with a guideline table — only the range printed on this paper itself.

    A paper can carry more than one kind of fact — a lab row under RECORDS beside a vital
    the confirm route turned into a READINGS reading (`app.ingestion.review`, the module
    doc's own example) — so each subject is read only where this key holds the scope it
    sits under (`scope_for_subject`); a subject outside the key's scopes is skipped, never a
    reason to refuse the whole insight."""
    fields = await card_fields(session, context=context, card_id=card.id)
    subjects = sorted(
        {
            field.subject
            for field in fields
            if context.allows(scope_for_subject(field.subject))
        }
    )
    candidates: list[Candidate] = []
    seen_facts: set[uuid.UUID] = set()
    for subject in subjects:
        facts = await current_facts(session, context=context, subject=subject, at=moment)
        by_attribute = {fact.attribute: fact for fact in facts if fact.artifact_id == card.artifact_id}
        for attribute, fact in by_attribute.items():
            if attribute.endswith(("_reference_range", "_flagged", "_date")):
                continue
            number = _number(fact.value)
            if number is None or fact.id in seen_facts:
                continue
            sibling = by_attribute.get(f"{attribute}_reference_range")
            bounds = _printed_range(fact.value, sibling.value if sibling is not None else None)
            if bounds is None or (bounds[0] is None and bounds[1] is None):
                continue
            band = _band(number, bounds)
            if band is None:
                continue
            seen_facts.add(fact.id)
            name = _analyte_label(subject, attribute)
            page = _page_of(fields, subject=subject, attribute=attribute)
            evidence = [Evidence(kind="fact", id=str(fact.id), label=name, scope=Scope.RECORDS)]
            evidence.append(
                Evidence(
                    kind="artifact",
                    id=str(card.artifact_id),
                    label=_evidence_label(paper_label, page),
                    scope=Scope.RECORDS,
                )
            )
            related_line: MedicationLine | None = None
            for line in medicines:
                hints = ANALYTE_DRUG_CLASS_HINTS.get(attribute, ())
                if line.drug_class in hints or line.generic.lower() in hints:
                    related_line = line
                    break
            if related_line is not None:
                evidence.append(
                    Evidence(
                        kind="medication_line",
                        id=str(related_line.id),
                        label=_plain_name(registry, related_line.generic, language),
                    )
                )
                kind = InsightKind.MEDICINE
                ask_who = AskWho.DOCTOR
            else:
                kind = InsightKind.CHECK
                ask_who = AskWho.DOCTOR
            candidates.append(
                Candidate(
                    insight_id=f"paper_value:{fact.id}",
                    kind=kind,
                    text=words.fill(words.PAPER_VALUE_LINE[language], name=name),
                    ask_who=ask_who,
                    evidence=tuple(evidence),
                    why_plain=words.PAPER_VALUE_WHY[language],
                    confidence=Confidence.WORTH_A_LOOK,
                )
            )
    return candidates


def _repeat_candidate(
    language: str, *, artifact_id: uuid.UUID, paper_label: str, out_of_range: list[Candidate]
) -> Candidate | None:
    if not out_of_range:
        return None
    evidence = tuple(
        e for candidate in out_of_range for e in candidate.evidence if e.kind == "fact"
    )
    return Candidate(
        insight_id=f"paper_repeat:{artifact_id}",
        kind=InsightKind.CHECK,
        text=words.PAPER_REPEAT_LINE[language],
        ask_who=AskWho.DOCTOR,
        evidence=evidence,
        why_plain=words.PAPER_REPEAT_WHY[language],
        confidence=Confidence.WORTH_A_LOOK,
    )


async def read_phase(
    session: AsyncSession,
    *,
    context: KeyContext,
    artifact_id: uuid.UUID,
    language: str,
    registry: DrugRegistry | None = None,
    now: datetime | None = None,
) -> Any:
    """An async generator: a `PaperStep` the instant each real read finishes, then one
    `ReadResult`, last. Never calls a model — see the module docstring."""
    moment = now if now is not None else utcnow()
    card = await _confirmed_paper(session, context=context, artifact_id=artifact_id)
    paper_label = words.LOOKED_AT_LABEL[language]["paper"]
    yield PaperStep(PaperStepKey.PAPER, words.PAPER_STEP_LABEL[language]["paper"])

    looked_at = [LookedAt(kind="artifact", id=str(artifact_id), label=paper_label)]
    withheld: list[str] = []

    medicines: list[MedicationLine] = []
    if context.allows(Scope.MEDICINES):
        medicines = list(
            await audited_read(
                session,
                MedicationLine,
                context,
                Scope.MEDICINES,
                where=(
                    MedicationLine.superseded_at.is_(None),
                    MedicationLine.status == LineStatus.ACTIVE,
                ),
            )
        )
        yield PaperStep(PaperStepKey.MEDICINES, words.PAPER_STEP_LABEL[language]["medicines"])
        if medicines:
            looked_at.append(
                LookedAt(
                    kind="medicines",
                    id=",".join(str(line.id) for line in medicines),
                    label=words.fill(
                        words.LOOKED_AT_LABEL[language]["medicines"], count=len(medicines)
                    ),
                )
            )
    else:
        withheld.append("medicines_and_supplements")

    value_candidates = await _value_candidates(
        session,
        context=context,
        language=language,
        card=card,
        paper_label=paper_label,
        medicines=medicines,
        registry=registry,
        moment=moment,
    )
    yield PaperStep(PaperStepKey.HISTORY, words.PAPER_STEP_LABEL[language]["history"])

    next_visit: Appointment | None = None
    if context.allows(Scope.VISITS):
        upcoming = await upcoming_appointments(session, context=context, at=moment)
        ordered = sorted(upcoming, key=lambda visit: (as_utc(visit.scheduled_at), str(visit.id)))
        next_visit = ordered[0] if ordered else None
        yield PaperStep(PaperStepKey.VISIT, words.PAPER_STEP_LABEL[language]["visit"])
        if next_visit is not None:
            looked_at.append(
                LookedAt(
                    kind="appointment",
                    id=str(next_visit.id),
                    label=words.LOOKED_AT_LABEL[language]["visit"],
                )
            )

    candidates = list(value_candidates)
    repeat = _repeat_candidate(
        language, artifact_id=artifact_id, paper_label=paper_label, out_of_range=value_candidates
    )
    if repeat is not None:
        candidates.append(repeat)

    async def reroute(candidate: Candidate) -> Insight | None:
        return await ask_the_doctor(session, context, language, candidate)

    questions = [
        insight
        for candidate in candidates
        if (insight := await finalize(candidate, language=language, reroute=reroute)) is not None
    ]

    yield ReadResult(
        paper_label=paper_label,
        questions=tuple(questions),
        looked_at=tuple(looked_at),
        withheld=tuple(withheld),
    )


def build_insight(
    *,
    language: str,
    source: str,
    questions: Sequence[Insight],
    looked_at: Sequence[LookedAt],
    withheld: Sequence[str],
    now: datetime,
) -> PaperInsight:
    headline = (
        words.PAPER_HEADLINE[language] if questions else words.PAPER_NOTHING_LINE[language]
    )
    return PaperInsight(
        report_id=str(uuid.uuid4()),
        generated_at=now,
        language=language,
        source=source,
        boundary=boundary_lines(Surface.INSIGHT, language, doctor=None),
        headline=headline,
        looked_at=tuple(looked_at),
        questions=tuple(questions[:4]),
        withheld=tuple(withheld),
    )


__all__ = [
    "ANALYTE_DRUG_CLASS_HINTS",
    "CANDIDATE_SECTION_KEY",
    "REPORT_KEY",
    "LookedAt",
    "NotAConfirmedPaper",
    "PaperInsight",
    "PaperReadEvent",
    "PaperStep",
    "PaperStepKey",
    "ReadResult",
    "build_insight",
    "read_phase",
]
