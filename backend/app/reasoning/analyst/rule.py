"""`RuleAnalyst`: the default, deterministic `Analyst` (`app.reasoning.analyst.port`).

Five real reads, in the fixed order `StepKey` names, each yielded as a `Step` the instant it
finishes — the same "a step is real work that already happened" discipline `app.search.ask.
recall_stream` holds to:

1. `records` — his conditions and the decade he was born in (`ProfileSettings`, under
   RECORDS): feeds `screenings_due` (age/condition against a sourced table,
   `app.reasoning.analyst.screenings`, each already-done screening found by its newest
   matching fact, `_last_screening_dates`, held against the table's own interval) and the
   supplement check below.
2. `series` — his blood-pressure series (RE-03, `app.reasoning.patterns.series.reading_
   series`, under READINGS): feeds `what_changed` against a small sourced band
   (`app.reasoning.analyst.trend_ranges`).
3. `medicines` — his active medicine lines (under MEDICINES): feeds `medicines_and_
   supplements` — duplicate therapy (two lines sharing a `drug_class`) and a supplement
   line (`category == "supplement"`) no condition on file explains.
4. `ledger` — his insurance ledger (`app.insurance.ledger.insurance_ledger`, under MONEY):
   feeds `what_you_pay` — cost concentration, one policy carrying most of this year's spend.
5. `coverage` — his policies (`app.insurance.policy.current_policies`, under MONEY): feeds
   `worth_a_look` — a policy that has lapsed or is past its renewal date.

A section whose scope this key does not hold is never read and never appears in `sections`
(withheld, by construction, the way `app.search.ask._corpus_stream` already keeps that rule).
`questions_for_the_doctor` is built last, from every insight above whose `ask_who` is
"doctor" — no read of its own, and left out only when every one of the five was itself
withheld (nothing to roll up).

Every candidate goes through `app.reasoning.analyst.pipeline.finalize` before it is shown:
plain words, the conclusion-or-advice blocklist, and a cite or it is dropped. A medicine or
supplement candidate that fails either check is rerouted as a real question for the doctor
(`ask_the_doctor`, #236) and its own words are never printed.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_read
from app.db import as_utc, utcnow
from app.delivery import analyst_strings as words
from app.delivery.strings import YOUR_DOCTOR
from app.drugs.registry import DrugRegistry, UnknownDrug
from app.insurance.ledger import insurance_ledger
from app.insurance.policy import Policy, PolicyStatus, current_policies
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.medicines.models import LineStatus, MedicationLine
from app.medicines.strings import PLAIN_NAME, say_date
from app.memory.semantic import current_facts
from app.onboarding.models import ProfileSettings
from app.reasoning.analyst import screenings as screening_table
from app.reasoning.analyst import trend_ranges
from app.reasoning.analyst.pipeline import Candidate, finalize
from app.reasoning.analyst.port import (
    SECTION_KEYS,
    SECTION_SCOPE,
    AskWho,
    Confidence,
    Evidence,
    Insight,
    InsightKind,
    Report,
    ReportEvent,
    Section,
    Step,
    StepKey,
)
from app.reasoning.analyst.port import SECTION_TITLES as TITLES
from app.reasoning.patterns.series import SeriesKind, reading_series
from app.reasoning.trends import doctor_to_ask
from app.reasoning.visits.memos import write_memo
from app.reasoning.visits.models import MemoKind, MemoSource
from app.regions import REGION_TZ
from app.safety.boundary import Surface, boundary_lines

log = logging.getLogger("nura.reasoning.analyst.rule")

QUESTIONS_KEY = "questions_for_the_doctor"

SUPPLEMENT_INDICATIONS: dict[str, tuple[str, ...]] = {
    "glucosamine": ("joints", "knees"),
    "chondroitin": ("joints", "knees"),
    "fish_oil": ("cholesterol", "heart"),
    "omega_3": ("cholesterol", "heart"),
    "coq10": ("heart",),
    "magnesium": ("sleep",),
    "probiotic": ("stomach",),
    "iron": ("fatty_liver",),
}
"""A small heuristic seed, not a clinical claim: what a supplement is commonly taken for, by
condition code (`app.onboarding.conditions`). A generic not in this table, or one whose
listed conditions share nothing with his own, is "no condition on file explains it" — a
prompt to ask the pharmacist, never a verdict that the supplement is wrong."""


@dataclass(frozen=True, slots=True)
class _Settings:
    conditions: tuple[str, ...]
    age: int | None


def _week_of(now: datetime, region: object) -> date:
    """The Monday of the week `now` falls in, on the region's own clock (`REGION_TZ`)."""
    local = as_utc(now).astimezone(REGION_TZ[region]).date()  # type: ignore[index]
    return local - timedelta(days=local.weekday())


def _plain_name(registry: DrugRegistry | None, generic: str, language: str) -> str:
    if registry is not None:
        try:
            return PLAIN_NAME[language][registry.monograph(generic).plain_name_id]
        except (UnknownDrug, KeyError):
            pass
    return generic


async def _read_settings(
    session: AsyncSession, context: KeyContext, *, now: datetime
) -> _Settings | None:
    if not context.allows(Scope.RECORDS):
        return None
    row = await audited_read(
        session,
        ProfileSettings,
        context,
        Scope.RECORDS,
        where=(ProfileSettings.superseded_at.is_(None),),
    )
    current = max(row, key=lambda one: as_utc(one.set_at)) if row else None
    if current is None:
        return _Settings(conditions=(), age=None)
    age = None
    if current.birth_decade is not None:
        on = as_utc(now).astimezone(REGION_TZ[context.region]).date()  # type: ignore[index]
        age = on.year - (current.birth_decade + 5)
    return _Settings(conditions=tuple(current.conditions), age=age)


async def ask_the_doctor(
    session: AsyncSession, context: KeyContext, language: str, candidate: Candidate
) -> Insight | None:
    """The reroute (#236): file a real question for the doctor and show a safe, fixed line
    instead of the candidate's own words, which are never printed. `None` — the candidate is
    dropped — only when the filing itself could not be done (an out-of-scope key, a database
    hiccup): the report must never cost him the section over a filing failure it did not
    cause, the same resilience `app.delivery.feed.search._file_question` already keeps."""
    try:
        doctor = await doctor_to_ask(session, context)
        await write_memo(
            session,
            context=context,
            kind=MemoKind.ASK,
            key="ask_medicines_change",
            slots={"doctor": doctor or YOUR_DOCTOR[language]},
            source=MemoSource.ANALYST,
            language=language,
        )
    except Exception:
        log.warning("analyst reroute: filing a doctor question failed", exc_info=True)
        return None
    return Insight(
        insight_id=f"reroute:{candidate.insight_id}",
        kind=candidate.kind,
        text=words.ASK_THE_DOCTOR_LINE[language],
        ask_who=AskWho.DOCTOR,
        evidence=candidate.evidence,
        why_plain=words.ASK_THE_DOCTOR_WHY[language],
        confidence=Confidence.WORTH_A_LOOK,
    )


def _trend_candidates(
    language: str,
    systolic_points: Sequence[object],
    diastolic_points: Sequence[object],
) -> list[Candidate]:
    candidates: list[Candidate] = []
    for key, points, band in (
        ("systolic", systolic_points, trend_ranges.SYSTOLIC),
        ("diastolic", diastolic_points, trend_ranges.DIASTOLIC),
    ):
        if not points:
            continue
        latest = points[-1]  # `reading_series` returns points oldest first
        value = latest.value  # type: ignore[attr-defined]
        if not isinstance(value, int | float) or isinstance(value, bool):
            continue
        if trend_ranges.band_of(float(value), band) is not trend_ranges.Band.ABOVE:
            continue
        name = words.BP_NAME[language][key]
        day = say_date(latest.day, language)  # type: ignore[attr-defined]
        evidence = tuple(
            Evidence(kind=one.kind, id=str(one.id), label=name, scope=one.scope)
            for one in latest.ids  # type: ignore[attr-defined]
        )
        candidates.append(
            Candidate(
                insight_id=f"trend:{key}:{latest.ids[0].id}",  # type: ignore[attr-defined]
                kind=InsightKind.TREND,
                text=words.fill(words.TREND_LINE[language], name=name, day=day),
                ask_who=AskWho.DOCTOR,
                evidence=evidence,
                why_plain=words.TREND_WHY[language],
                confidence=Confidence.WORTH_A_LOOK,
            )
        )
    return candidates


async def _last_screening_dates(
    session: AsyncSession, context: KeyContext
) -> dict[str, date]:
    """The newest `valid_from` among this key's own facts under each screening's
    `fact_subjects` (`app.reasoning.analyst.screenings.SCREENINGS`) — read under RECORDS, the
    same door `_read_settings` already opens. A screening this table names no subject for
    (today, only `eye_check`) never gets an entry here and stays due, the reading this module
    already held to before this fix."""
    dates: dict[str, date] = {}
    for row in screening_table.SCREENINGS:
        newest: date | None = None
        for subject in row.fact_subjects:
            for fact in await current_facts(session, context=context, subject=subject):
                on = as_utc(fact.valid_from).date()
                if newest is None or on > newest:
                    newest = on
        if newest is not None:
            dates[row.key] = newest
    return dates


def _screening_candidates(
    language: str, settings: _Settings, last_done: Mapping[str, date], today: date
) -> list[Candidate]:
    due = screening_table.screenings_due(
        age=settings.age, conditions=settings.conditions, last_done=last_done, today=today
    )
    candidates: list[Candidate] = []
    for row in due:
        name = words.SCREENING_NAME[language][row.key]
        candidates.append(
            Candidate(
                insight_id=f"screening:{row.key}",
                kind=InsightKind.CHECK,
                text=words.fill(words.SCREENING_LINE[language], name=name),
                ask_who=AskWho.DOCTOR,
                evidence=(Evidence(kind="guideline", id=row.source_id, label=name),),
                why_plain=words.SCREENING_WHY[language],
                confidence=Confidence.SURE,
            )
        )
    return candidates


def _medicine_candidates(
    language: str,
    lines: Sequence[MedicationLine],
    settings: _Settings | None,
    registry: DrugRegistry | None,
) -> list[Candidate]:
    candidates: list[Candidate] = []
    by_class: dict[str, list[MedicationLine]] = {}
    for line in lines:
        by_class.setdefault(line.drug_class, []).append(line)
    for drug_class, group in sorted(by_class.items()):
        if len({line.generic for line in group}) < 2:
            continue
        ordered = sorted(group, key=lambda one: one.generic)
        name = _plain_name(registry, ordered[0].generic, language)
        candidates.append(
            Candidate(
                insight_id=f"duplicate:{drug_class}",
                kind=InsightKind.MEDICINE,
                text=words.fill(words.DUPLICATE_LINE[language], name=name),
                ask_who=AskWho.PHARMACIST,
                evidence=tuple(
                    Evidence(kind="medication_line", id=str(one.id), label=one.generic)
                    for one in ordered
                ),
                why_plain=words.DUPLICATE_WHY[language],
                confidence=Confidence.LIKELY,
            )
        )
    if settings is not None:
        held = set(settings.conditions)
        for line in sorted(lines, key=lambda one: one.generic):
            if line.category != "supplement":
                continue
            indications = SUPPLEMENT_INDICATIONS.get(line.generic.lower(), ())
            if held & set(indications):
                continue
            name = _plain_name(registry, line.generic, language)
            candidates.append(
                Candidate(
                    insight_id=f"supplement:{line.id}",
                    kind=InsightKind.SUPPLEMENT,
                    text=words.fill(words.SUPPLEMENT_LINE[language], name=name),
                    ask_who=AskWho.PHARMACIST,
                    evidence=(Evidence(kind="medication_line", id=str(line.id), label=name),),
                    why_plain=words.SUPPLEMENT_WHY[language],
                    confidence=Confidence.WORTH_A_LOOK,
                )
            )
    return candidates


def _cost_candidate(language: str, ledger: object) -> Candidate | None:
    by_policy = ledger.by_policy  # type: ignore[attr-defined]
    total = ledger.total_paid_by_patient_cents  # type: ignore[attr-defined]
    if total <= 0 or len(by_policy) < 2:
        return None
    top = max(by_policy, key=lambda one: (one.paid_by_patient_cents, one.policy_name))
    if top.paid_by_patient_cents / total < 0.5:
        return None
    return Candidate(
        insight_id=f"cost:{top.policy_id}",
        kind=InsightKind.COST,
        text=words.fill(
            words.COST_LINE[language], amount=top.paid_by_patient_said, policy=top.policy_name
        ),
        ask_who=AskWho.NOBODY,
        evidence=(Evidence(kind="policy", id=str(top.policy_id), label=top.policy_name),),
        why_plain=words.COST_WHY[language],
        confidence=Confidence.LIKELY,
    )


def _coverage_candidates(
    language: str, policies: Sequence[Policy], today: date
) -> list[Candidate]:
    candidates: list[Candidate] = []
    for policy in sorted(policies, key=lambda one: one.insurer_name):
        status_key: str | None = None
        if policy.status is PolicyStatus.LAPSED:
            status_key = "lapsed"
        elif policy.status is PolicyStatus.CANCELLED:
            status_key = "cancelled"
        elif policy.renewal_date is not None and policy.renewal_date < today:
            status_key = "renewal_due"
        if status_key is None:
            continue
        status = words.STATUS_WORDS[language][status_key]
        candidates.append(
            Candidate(
                insight_id=f"coverage:{policy.id}",
                kind=InsightKind.COVERAGE,
                text=words.fill(
                    words.COVERAGE_LINE[language], policy=policy.insurer_name, status=status
                ),
                ask_who=AskWho.NOBODY,
                evidence=(Evidence(kind="policy", id=str(policy.id), label=policy.insurer_name),),
                why_plain=words.COVERAGE_WHY[language],
                confidence=Confidence.SURE,
            )
        )
    return candidates


class RuleAnalyst:
    """The default `Analyst`. `registry` resolves a plain medicine name where one is known;
    without it (no adapter configured) the generic string is shown instead."""

    def __init__(self, *, registry: DrugRegistry | None = None) -> None:
        self._registry = registry

    async def report_stream(
        self,
        session: AsyncSession,
        *,
        context: KeyContext,
        language: str,
        now: datetime | None = None,
    ) -> AsyncIterator[ReportEvent]:
        moment = now if now is not None else utcnow()
        sections: dict[str, Section] = {}
        any_scope_held = False

        async def reroute(candidate: Candidate) -> Insight | None:
            return await ask_the_doctor(session, context, language, candidate)

        # 1. records — conditions and age, feeding screenings_due.
        settings: _Settings | None = None
        if context.allows(SECTION_SCOPE["screenings_due"]):
            any_scope_held = True
            settings = await _read_settings(session, context, now=moment)
            last_screened = await _last_screening_dates(session, context)
            today = as_utc(moment).astimezone(REGION_TZ[context.region]).date()  # type: ignore[index]
            yield Step(StepKey.RECORDS, words.STEP_LABEL[language]["records"])
            candidates = (
                _screening_candidates(language, settings, last_screened, today) if settings else []
            )
            insights = [i for c in candidates if (i := await finalize(c, language=language, reroute=reroute)) is not None]
            sections["screenings_due"] = Section(
                "screenings_due", TITLES[language]["screenings_due"], tuple(insights)
            )

        # 2. series — blood-pressure trend.
        if context.allows(SECTION_SCOPE["what_changed"]):
            any_scope_held = True
            systolic = await reading_series(session, context=context, kind=SeriesKind.BP_SYSTOLIC, now=moment)
            diastolic = await reading_series(session, context=context, kind=SeriesKind.BP_DIASTOLIC, now=moment)
            yield Step(StepKey.SERIES, words.STEP_LABEL[language]["series"])
            candidates = _trend_candidates(language, systolic.points, diastolic.points)
            insights = [i for c in candidates if (i := await finalize(c, language=language, reroute=reroute)) is not None]
            sections["what_changed"] = Section(
                "what_changed", TITLES[language]["what_changed"], tuple(insights)
            )

        # 3. medicines — duplicate therapy, supplements with no indication on file.
        if context.allows(SECTION_SCOPE["medicines_and_supplements"]):
            any_scope_held = True
            lines = await audited_read(
                session,
                MedicationLine,
                context,
                Scope.MEDICINES,
                where=(
                    MedicationLine.superseded_at.is_(None),
                    MedicationLine.status == LineStatus.ACTIVE,
                ),
            )
            yield Step(StepKey.MEDICINES, words.STEP_LABEL[language]["medicines"])
            candidates = _medicine_candidates(language, lines, settings, self._registry)
            insights = [i for c in candidates if (i := await finalize(c, language=language, reroute=reroute)) is not None]
            sections["medicines_and_supplements"] = Section(
                "medicines_and_supplements",
                TITLES[language]["medicines_and_supplements"],
                tuple(insights),
            )

        # 4. ledger — cost concentration.
        if context.allows(SECTION_SCOPE["what_you_pay"]):
            any_scope_held = True
            ledger = await insurance_ledger(session, context=context, language=language)
            yield Step(StepKey.LEDGER, words.STEP_LABEL[language]["ledger"])
            cost = _cost_candidate(language, ledger)
            cost_insights = (
                [i] if cost is not None and (i := await finalize(cost, language=language, reroute=reroute)) is not None else []
            )
            sections["what_you_pay"] = Section(
                "what_you_pay", TITLES[language]["what_you_pay"], tuple(cost_insights)
            )

        # 5. coverage — lapsed or overdue policies.
        if context.allows(SECTION_SCOPE["worth_a_look"]):
            any_scope_held = True
            policies = await current_policies(session, context=context)
            yield Step(StepKey.COVERAGE, words.STEP_LABEL[language]["coverage"])
            today = as_utc(moment).astimezone(REGION_TZ[context.region]).date()  # type: ignore[index]
            candidates = _coverage_candidates(language, policies, today)
            insights = [i for c in candidates if (i := await finalize(c, language=language, reroute=reroute)) is not None]
            sections["worth_a_look"] = Section(
                "worth_a_look", TITLES[language]["worth_a_look"], tuple(insights)
            )

        # 6. questions_for_the_doctor — a rollup, no read of its own.
        if any_scope_held:
            doctor_insights: list[Insight] = []
            for key in ("what_changed", "worth_a_look", "medicines_and_supplements", "what_you_pay", "screenings_due"):
                section = sections.get(key)
                if section is None:
                    continue
                doctor_insights.extend(one for one in section.insights if one.ask_who is AskWho.DOCTOR)
            sections[QUESTIONS_KEY] = Section(
                QUESTIONS_KEY, TITLES[language][QUESTIONS_KEY], tuple(doctor_insights)
            )

        ordered = tuple(sections[key] for key in SECTION_KEYS if key in sections)
        doctor = await doctor_to_ask(session, context) if context.allows(Scope.VISITS) or context.allows(Scope.MEDICINES) else None
        yield Report(
            report_id=str(uuid.uuid4()),
            generated_at=moment,
            week_of=_week_of(moment, context.region),
            language=language,
            source="rule",
            boundary=boundary_lines(Surface.INSIGHT, language, doctor=doctor),
            sections=ordered,
        )


__all__ = ["QUESTIONS_KEY", "RuleAnalyst", "ask_the_doctor"]
