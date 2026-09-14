"""Gaps (docs/gaps-and-unlocks.md): what the record does not hold yet, what having it would
let Nura do, and the one thing that fills it.

A gap exists only where a capability needs the fact — no capability, no gap — so the
catalogue here is the part of the document's v1 catalogue this backend can act on today, each
with the rule that makes it apply to a profile and the rule that closes it, in the document's
order of tiers. Both rules read a `Known`: what the record holds, as codes and yes-or-no,
never what any of it says. `Known` is read under the caller's key context; a part the key
does not open reads as not there, so a narrow key can leave a gap open but never close one it
could not see.

The biography's questions (`app.onboarding.biography`) and the first week's prompts
(`app.onboarding.plan`) both come from here: the questions are the open gaps asked of him in
the one sitting, the prompts are the same gaps asked one a day. A gap closes itself the
moment its fact arrives by any route (§4). The stop rule of the first week is here too:
once the record has his medicines, his last visit and his next visit, the prompts stop.

The seam: questions for the doctor, generated from the record, are E05's
(`app.reasoning.visits.questions_for`, not on main when this was written). These are
questions for him, about what the papers did not say, and `questions_for_gaps` is the one
call the biography makes for them — the place the visit loop's renderer plugs in.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_read
from app.db import as_utc, utcnow
from app.ingestion.review import list_review_cards
from app.keys.context import KeyContext
from app.keys.grants import list_keys
from app.keys.scopes import Scope, scope_for_subject
from app.memory.models import Appointment, AppointmentStatus, Event, EventKind, Fact
from app.memory.semantic import current_facts
from app.memory.spine import UPCOMING
from app.onboarding.models import BiographyPaper, PaperKind
from app.onboarding.settings import BREAKFAST, CONDITION
from app.onboarding.words import question

ANTICOAGULANT = "anticoagulant"
"""The high-risk class a blood thinner's label is looked up as (`app.safety.high_risk`)."""

MEDICINE_SUBJECTS = frozenset({"medicine", "medication"})
CHOLESTEROL_SUBJECTS = frozenset({"lipid_panel", "cholesterol"})
SUGAR_SUBJECTS = frozenset({"hba1c", "sugar_test"})
KIDNEY_SUBJECTS = frozenset({"kidney_panel", "kidney_function", "creatinine", "egfr"})
INSURANCE_SUBJECTS = frozenset({"insurance", "policy"})
HAPPENED = frozenset(
    {AppointmentStatus.ATTENDED, AppointmentStatus.PLANNED, AppointmentStatus.CONFIRMED}
)
"""A visit on the spine that is in the past and was not cancelled or missed is a last visit."""


@dataclass(frozen=True, slots=True)
class Known:
    """What the record holds, as the gap rules read it: codes and yes-or-no, nothing it says."""

    conditions: frozenset[str] = frozenset()
    """The conditions he told, from the `condition.<code>` facts that hold."""
    subjects: frozenset[str] = frozenset()
    attributes: frozenset[str] = frozenset()
    papers: frozenset[str] = frozenset()
    """What the person said the papers he added were (`PaperKind`)."""
    documents: frozenset[str] = frozenset()
    """What the confirmed review cards were read as (`DocumentKind`)."""
    anticoagulant_named: bool = False
    medicines: bool = False
    last_visit: bool = False
    next_visit: bool = False
    breakfast_set: bool = False
    someone_holds_a_key: bool = False


Rule = Callable[[Known], bool]


def _told(*codes: str) -> Rule:
    wanted = frozenset(codes)
    return lambda known: bool(known.conditions & wanted)


def _holds(subjects: frozenset[str]) -> Rule:
    return lambda known: bool(known.subjects & subjects)


def _always(known: Known) -> bool:
    return True


def _any_condition(known: Known) -> bool:
    return bool(known.conditions) or known.medicines


def _clinic_paper(known: Known) -> bool:
    """A clinic card or an appointment slip arrived. Until the extractor reads the date off
    it, one slip answers both the last visit and the next."""
    return PaperKind.CLINIC_CARD.value in known.papers or "clinic_slip" in known.documents


@dataclass(frozen=True, slots=True)
class Gap:
    """One gap: its code, its tier, when it applies to a profile and when it is closed."""

    code: str
    tier: int
    applies: Rule
    closed: Rule
    capture: str = "photo"
    """What doing it now opens: the camera ("photo"), a tap ("tap"), or nothing yet ("none")."""


CATALOGUE: tuple[Gap, ...] = (
    Gap("medicines", 1, _always, lambda k: k.medicines),
    Gap(
        "bp_numbers",
        1,
        _told("high_blood_pressure", "bp_tablets", "bp_at_home"),
        _holds(frozenset({"blood_pressure"})),
    ),
    Gap(
        "weight",
        1,
        _told("weak_heart", "weigh_myself", "water_pill"),
        _holds(frozenset({"weight"})),
    ),
    Gap(
        "allergy_which",
        1,
        _told("allergies", "medicine_allergy"),
        lambda k: "allergy" in k.attributes,
        capture="tap",
    ),
    Gap(
        # "Thinner tapped, kind unknown": only when he said he takes one, never assumed from
        # a heartbeat or a stroke tapped beside it.
        "thinner_which",
        1,
        _told("blood_thinner"),
        lambda k: k.anticoagulant_named,
    ),
    Gap(
        "discharge_letter",
        1,
        _told("hospital_last_year", "have_hospital_letter"),
        lambda k: PaperKind.DISCHARGE_LETTER.value in k.papers or "discharge_letter" in k.documents,
    ),
    Gap(
        "cholesterol_result",
        2,
        _told("cholesterol", "cholesterol_tablet"),
        _holds(CHOLESTEROL_SUBJECTS),
    ),
    Gap(
        "sugar_result",
        2,
        _told("diabetes", "sugar_tablets", "insulin", "sugar_at_home"),
        _holds(SUGAR_SUBJECTS),
    ),
    Gap(
        "kidney_result",
        2,
        lambda k: _told("kidneys", "kidney_watched", "dialysis")(k) or k.medicines,
        _holds(KIDNEY_SUBJECTS),
    ),
    Gap("next_visit", 2, _any_condition, lambda k: k.next_visit or _clinic_paper(k)),
    Gap("last_visit", 2, _any_condition, lambda k: k.last_visit or _clinic_paper(k)),
    Gap(
        "insurance",
        2,
        _always,
        lambda k: PaperKind.INSURANCE_CARD.value in k.papers or _holds(INSURANCE_SUBJECTS)(k),
    ),
    Gap("meal_times", 2, _always, lambda k: k.breakfast_set, capture="tap"),
    Gap("someone_to_see", 3, _always, lambda k: k.someone_holds_a_key, capture="none"),
)
"""The document's catalogue, in its order, for what this backend can act on today."""

BY_CODE = {gap.code: gap for gap in CATALOGUE}


def open_gaps(known: Known) -> list[Gap]:
    """The gaps that apply and are not closed, tier first, then the catalogue's order."""
    order = {gap.code: index for index, gap in enumerate(CATALOGUE)}
    found = [gap for gap in CATALOGUE if gap.applies(known) and not gap.closed(known)]
    return sorted(found, key=lambda gap: (gap.tier, order[gap.code]))


CLOSING_SUBJECTS = (
    MEDICINE_SUBJECTS
    | CHOLESTEROL_SUBJECTS
    | SUGAR_SUBJECTS
    | KIDNEY_SUBJECTS
    | INSURANCE_SUBJECTS
    | frozenset({"blood_pressure", "weight"})
)
"""The subjects a fact may be about and close a gap by landing."""


def closes_a_gap(fact: Fact) -> bool:
    """Whether a fact could close any gap on its own: the hook's cheap first question."""
    return (
        fact.subject in CLOSING_SUBJECTS
        or fact.attribute == "allergy"
        or (fact.subject, fact.attribute) == BREAKFAST
    )


STOP_PARTS: tuple[str, ...] = ("medicines", "last_visit", "next_visit")


def what_stops(known: Known) -> tuple[str, ...]:
    """Which of the three the record holds: the prompts stop when it holds all of them."""
    held = {"medicines": known.medicines, "last_visit": known.last_visit}
    held["next_visit"] = known.next_visit
    return tuple(part for part in STOP_PARTS if held[part])


def stopped(known: Known) -> bool:
    return len(what_stops(known)) == len(STOP_PARTS)


async def what_is_known(session: AsyncSession, *, context: KeyContext) -> Known:
    """Read `Known` from the record under this key context. The record's facts and papers
    need `Scope.RECORDS`; the visits and the keys are read only when the key opens them."""
    moment = utcnow()
    facts = [
        fact
        for fact in await current_facts(session, context=context)
        if context.allows(scope_for_subject(fact.subject))
    ]
    subjects = frozenset(fact.subject for fact in facts)
    confirmed = [
        card for card in await list_review_cards(session, context=context) if not card.is_open
    ]
    papers = await audited_read(session, BiographyPaper, context, Scope.RECORDS)
    visit_events = await audited_read(
        session,
        Event,
        context,
        Scope.RECORDS,
        where=(Event.kind == EventKind.VISIT, Event.occurred_at <= moment),
    )
    last_visit, next_visit = bool(visit_events), False
    if context.allows(Scope.VISITS):
        booked = await audited_read(
            session,
            Appointment,
            context,
            Scope.VISITS,
            where=(Appointment.status.in_(HAPPENED | UPCOMING),),
        )
        for visit in booked:
            if as_utc(visit.scheduled_at) < moment and visit.status in HAPPENED:
                last_visit = True
            elif as_utc(visit.scheduled_at) >= moment and visit.status in UPCOMING:
                next_visit = True
    keys = await list_keys(session, context=context) if context.allows(Scope.FAMILY) else ()
    return Known(
        conditions=frozenset(
            fact.attribute for fact in facts if fact.subject == CONDITION and fact.value is True
        ),
        subjects=subjects,
        attributes=frozenset(fact.attribute for fact in facts),
        papers=frozenset(paper.paper.value for paper in papers),
        documents=frozenset(card.document_kind.value for card in confirmed),
        anticoagulant_named=any(card.high_risk_class == ANTICOAGULANT for card in confirmed),
        medicines=bool(subjects & MEDICINE_SUBJECTS),
        last_visit=last_visit,
        next_visit=next_visit,
        breakfast_set=any(
            (fact.subject, fact.attribute) == BREAKFAST and fact.value for fact in facts
        ),
        someone_holds_a_key=any(key.is_active(moment) for key in keys),
    )


def questions_for_gaps(
    gaps: Sequence[Gap], *, language: str, doctor: str | None
) -> list[tuple[str, str]]:
    """The open gaps as questions for him, each with its gap code, in his language: the seam
    E05's questions-from-the-record plugs into. A line that does not pass plain words is
    left out, never served."""
    asked: list[tuple[str, str]] = []
    for gap in gaps:
        line = question(gap.code, language, doctor)
        if line is not None:
            asked.append((gap.code, line))
    return asked
