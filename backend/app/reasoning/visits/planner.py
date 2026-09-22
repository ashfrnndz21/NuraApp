"""The appointment planner (T2): visits Nura proposes from what the record already knows.

`propose_visits` never books anything and never contacts a clinic. It reads the record under
the caller's key, the same way `app.delivery.recommend.broker.slate` does, and returns
deterministic, cited proposals — each a `VisitProposal` naming the evidence it rests on
(`why`, a tuple of `app.delivery.recommend.models.Evidence`, the same shape the recommend
engine already cites with). Nothing here is stored: a proposal is recomputed fresh on every
call, so there is no new table for it (the brief: "declining hides it for 90 days (a Fact, no
new table)"). `proposal_id` is instead a deterministic digest of the source and the evidence
it rests on, stable across calls so a decline (or, later, a booking) can still name it.

Four sources, each producing at most one proposal per piece of evidence:

- **follow_up**: a `subject="follow_up", attribute="date"` fact — the shape a clinic or
  discharge letter's follow-up date is read into (#257, `app/llm/prompts/extract_document.txt`
  §1: "A follow-up date is subject 'follow_up', attribute 'date'."). Read under RECORDS, the
  scope an unnamed subject like this one sits under (`app.keys.scopes.scope_for_subject`).
- **medicine_review**: an active medicine line older than its class's review interval
  (`REVIEW_MONTHS_BY_CLASS`, sourced below) with no visit booked since it started. Read under
  MEDICINES.
- **test_coming**: a lab-report row #257 flagged (`<analyte>_flagged` true — "only when the
  report itself marks the row … never your own judgement") with no visit booked since. This
  is a narrower reading of RE-06's own `test_coming` (`app.delivery.recommend.rules.
  test_coming`), which reads "a paper or a visit names a test" as an *already-booked* lab
  visit and only ever produces a CLIP about it (module doc there: nothing proposes a *next*
  test, a named gap). This story needs the planner to actually propose one, so it reads the
  one fact shape #257 already writes that says a result needs a second look — an abnormal
  flag — rather than inventing a new fact nothing extracts yet. Read under RECORDS.
- **screening_due**: the age/condition guideline table below, `SCREENING_TABLE`. No analyst
  table for this exists on `wave-1` at the time of writing (checked: no commit, no module,
  under either name, `git log --all -i --grep=screening`), so this story adds a small one,
  cited by source, the same way `app.reasoning.ranges`'s own guideline table is. Read under
  RECORDS (a condition fact) or from the birth-year/decade facts `app.reasoning.trends.
  birth_decade` already reads, cited directly rather than through that function so the
  evidence id survives (module doc there is read-only: it returns a decade, not a fact id).

**Suppression.** A source's evidence is skipped once a visit has been booked since the
evidence arrived (`booked_at` or `scheduled_at` on or after it) — a coarse "already acted on"
check, not a match on purpose or provider: any visit booked after a follow-up letter, a stale
medicine line, a flagged result or a screening's due date stands in for that concern having
been raised, because a query for "the visit that was *about* this" would need a purpose match
this story does not add (#257's diagnosis-as-control-word and RE-04's `TopicTagger` are the
two closest things, and a false negative here — a proposal quietly held back forever — is
worse than an occasional found visit that was really about something else). A proposal is
also skipped while a `declined_visit_proposal` fact for its `proposal_id` still holds
(`DECLINE_WINDOW`, 90 days) — RE-07's own `_decline_topic_for_30_days`
(`app.delivery.feed.engagement`) is the model: a Fact with a validity window and a confidence
state (CLAUDE.md), the confirm minted and spent by the same call that writes it, because
tapping "Not now" *is* the yes.

**Booking and declining.** Accepting a proposal is not a call in this module: the surface
opens the existing booking screen with the proposal's own `provider_kind`/`suggested_at`/
`purpose` pre-filled, and books it the way any other visit is booked — `AppointmentDraft`,
`POST /profiles/{id}/confirmations`, `app.memory.spine.book_appointment` — so a booked
proposal is provably the same yes any other booked visit rests on. `decline_proposal` is the
one write this module owns.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum

from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_read
from app.db import as_utc, utcnow
from app.delivery.recommend.models import Evidence
from app.drafts import FactDraft
from app.keys.confirm import confirm
from app.keys.context import KeyContext
from app.keys.scopes import Scope, scope_for_subject
from app.medicines.models import LineStatus, MedicationLine
from app.memory.episodic import record_event
from app.memory.models import Appointment, ConfidenceState, EventKind, ProviderKind, SourceChannel
from app.memory.semantic import assert_fact, current_facts
from app.reasoning.visits.strings import day_and_date, say
from app.regions import Region
from app.state.health_context import age_band

__all__ = [
    "DECLINE_WINDOW",
    "ProposedVisits",
    "VisitProposal",
    "VisitSource",
    "decline_proposal",
    "propose_visits",
]


class VisitSource(StrEnum):
    """Where a proposal's evidence came from (module doc)."""

    FOLLOW_UP = "follow_up"
    MEDICINE_REVIEW = "medicine_review"
    TEST_COMING = "test_coming"
    SCREENING_DUE = "screening_due"


DECLINED_SUBJECT = "declined_visit_proposal"
"""The Fact subject a decline is kept under: `attribute` is the `proposal_id`, `value` says
when, `valid_to` is `DECLINE_WINDOW` out — no new table (module doc)."""

DECLINE_WINDOW = timedelta(days=90)

REVIEW_MONTHS_DEFAULT = 6
"""How long an active line goes between reviews when its class names no interval of its own
— six months, the interval MOH Malaysia's chronic-disease CPGs converge on for a stable
long-term medicine generally (e.g. CPG Management of Hypertension, 5th ed. 2018, §6.3;
CPG Management of Type 2 Diabetes Mellitus, 6th ed. 2020, §5, routine follow-up)."""

REVIEW_MONTHS_BY_CLASS: dict[str, int] = {
    # A newly titrated or higher-risk class is checked more often than the general default.
    "antihypertensive": 3,
    "antidiabetic": 3,
    "anticoagulant": 3,
}
"""Sourced with `REVIEW_MONTHS_DEFAULT` above. Keyed by `MedicationLine.drug_class`; a class
not named here takes the default."""


@dataclass(frozen=True, slots=True)
class ScreeningRule:
    """One row of the guideline table (module doc, `SCREENING_TABLE`)."""

    code: str
    condition_code: str | None
    """A told `condition.<code>` fact this screening needs, or None for an age-only rule."""
    min_age: int | None
    """The age this screening starts at, or None when `condition_code` alone gates it."""
    interval_months: int
    provider_kind: ProviderKind
    purpose_key: str
    """The `app.reasoning.visits.strings` template key for this rule's proposal line."""
    source: str


SCREENING_TABLE: tuple[ScreeningRule, ...] = (
    ScreeningRule(
        code="screening.colorectal",
        condition_code=None,
        min_age=50,
        interval_months=24,
        provider_kind=ProviderKind.CLINIC,
        purpose_key="visit_suggestion_screening",
        source="USPSTF Colorectal Cancer Screening (2021), ages 50-75",
    ),
    ScreeningRule(
        code="screening.diabetic_eye",
        condition_code="diabetes",
        min_age=None,
        interval_months=12,
        provider_kind=ProviderKind.CLINIC,
        purpose_key="visit_suggestion_screening",
        source="MOH Malaysia CPG Management of Type 2 Diabetes Mellitus (6th ed. 2020), "
        "annual retinal (eye) screening",
    ),
)
"""No analyst table for this exists on `wave-1` (module doc): a small one, added here, cited
by source, in `app.reasoning.ranges`'s own shape. Two rows only, kept deliberately small for
this story; a third source (or a licensed guideline feed) is a later story's, behind the same
shape, not a caller-visible change."""

_CONDITION_SUBJECT = "condition"


@dataclass(frozen=True, slots=True)
class VisitProposal:
    """One visit Nura proposes, deterministic and cited (module doc)."""

    proposal_id: str
    source: VisitSource
    purpose: str
    """Plain-words verified, in the profile's own language — the same text a booking screen
    pre-fills `AppointmentDraft.purpose` with."""
    provider_kind: ProviderKind | None
    suggested_at: datetime | None
    why: tuple[Evidence, ...]


class ProposedVisits:
    """One key's proposals, and the scopes it could not read any of the four sources under —
    the same shape `app.delivery.recommend.broker.Slate` reports `withheld` in."""

    __slots__ = ("proposals", "withheld")

    def __init__(self, proposals: Sequence[VisitProposal], withheld: Sequence[Scope]) -> None:
        self.proposals = tuple(proposals)
        self.withheld = tuple(withheld)


def _proposal_id(source: VisitSource, discriminator: str) -> str:
    """A stable id for one piece of evidence under one source — never stored, so it must be
    reconstructible from the same evidence every time (module doc)."""
    return hashlib.sha256(f"{source.value}:{discriminator}".encode()).hexdigest()[:24]


def _parse_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


async def _is_declined(session: AsyncSession, *, context: KeyContext, proposal_id: str) -> bool:
    found = await current_facts(
        session, context=context, subject=DECLINED_SUBJECT, attribute=proposal_id
    )
    return bool(found)


async def _visited_since(session: AsyncSession, *, context: KeyContext, since: datetime) -> bool:
    """Whether any visit was booked, or is scheduled, on or after `since` — the coarse
    "already acted on" suppression the module doc explains."""
    found = await audited_read(
        session,
        Appointment,
        context,
        Scope.VISITS,
        where=(or_(Appointment.booked_at >= since, Appointment.scheduled_at >= since),),
    )
    return len(found) > 0


async def _follow_up_proposals(
    session: AsyncSession, *, context: KeyContext, language: str, region: Region
) -> list[VisitProposal]:
    if not context.allows(Scope.RECORDS):
        return []
    facts = await current_facts(session, context=context, subject="follow_up", attribute="date")
    out: list[VisitProposal] = []
    for fact in facts:
        on = _parse_date(fact.value)
        if on is None:
            continue
        suggested_at = datetime.combine(on, datetime.min.time(), tzinfo=as_utc(fact.asserted_at).tzinfo)
        if await _visited_since(session, context=context, since=as_utc(fact.valid_from)):
            continue
        proposal_id = _proposal_id(VisitSource.FOLLOW_UP, str(fact.id))
        if await _is_declined(session, context=context, proposal_id=proposal_id):
            continue
        purpose = say(
            "visit_suggestion_follow_up_day",
            language,
            day=day_and_date(suggested_at, language, region),
        )
        out.append(
            VisitProposal(
                proposal_id=proposal_id,
                source=VisitSource.FOLLOW_UP,
                purpose=purpose,
                provider_kind=None,
                suggested_at=suggested_at,
                why=(Evidence(kind="fact", id=fact.id, scope=Scope.RECORDS),),
            )
        )
    return out


async def _medicine_review_proposals(
    session: AsyncSession, *, context: KeyContext, now: datetime, language: str
) -> list[VisitProposal]:
    if not context.allows(Scope.MEDICINES):
        return []
    lines = await audited_read(
        session,
        MedicationLine,
        context,
        Scope.MEDICINES,
        where=(MedicationLine.superseded_at.is_(None), MedicationLine.status == LineStatus.ACTIVE),
    )
    out: list[VisitProposal] = []
    for line in lines:
        months = REVIEW_MONTHS_BY_CLASS.get(line.drug_class, REVIEW_MONTHS_DEFAULT)
        started = as_utc(line.started_at)
        due_at = started + timedelta(days=months * 30)
        if now < due_at:
            continue
        if await _visited_since(session, context=context, since=started):
            continue
        proposal_id = _proposal_id(VisitSource.MEDICINE_REVIEW, str(line.id))
        if await _is_declined(session, context=context, proposal_id=proposal_id):
            continue
        purpose = say("visit_suggestion_medicine_review", language)
        out.append(
            VisitProposal(
                proposal_id=proposal_id,
                source=VisitSource.MEDICINE_REVIEW,
                purpose=purpose,
                provider_kind=ProviderKind.CLINIC,
                suggested_at=None,
                why=(Evidence(kind="line", id=line.id, scope=Scope.MEDICINES),),
            )
        )
    return out


async def _test_coming_proposals(
    session: AsyncSession, *, context: KeyContext, language: str
) -> list[VisitProposal]:
    if not context.allows(Scope.RECORDS):
        return []
    facts = await current_facts(session, context=context)
    out: list[VisitProposal] = []
    for fact in facts:
        if not fact.attribute.endswith("_flagged") or fact.value is not True:
            continue
        if scope_for_subject(fact.subject) is not Scope.RECORDS:
            continue
        if await _visited_since(session, context=context, since=as_utc(fact.asserted_at)):
            continue
        proposal_id = _proposal_id(VisitSource.TEST_COMING, str(fact.id))
        if await _is_declined(session, context=context, proposal_id=proposal_id):
            continue
        purpose = say("visit_suggestion_test_coming", language)
        out.append(
            VisitProposal(
                proposal_id=proposal_id,
                source=VisitSource.TEST_COMING,
                purpose=purpose,
                provider_kind=ProviderKind.LAB,
                suggested_at=None,
                why=(Evidence(kind="fact", id=fact.id, scope=Scope.RECORDS),),
            )
        )
    return out


async def _age(session: AsyncSession, *, context: KeyContext, now: datetime) -> tuple[int | None, Evidence | None]:
    """His age today and the fact it rests on. The Health Graph's one age rule (ADR 0019
    point 3, `app.state.health_context.age_band`) does the actual read now — this function
    only adapts its result to the `(age, Evidence)` shape the rest of this module already
    expects, so every caller below is unchanged."""
    result = await age_band(session, context=context, on=now)
    if result.exact is None or result.fact_id is None:
        return None, None
    return result.exact, Evidence(kind="fact", id=result.fact_id, scope=Scope.RECORDS)


async def _screening_proposals(
    session: AsyncSession, *, context: KeyContext, now: datetime, language: str
) -> list[VisitProposal]:
    if not context.allows(Scope.RECORDS):
        return []
    age, age_evidence = await _age(session, context=context, now=now)
    told = await current_facts(session, context=context, subject=_CONDITION_SUBJECT)
    told_by_code = {fact.attribute: fact for fact in told if fact.value is True}
    out: list[VisitProposal] = []
    for rule in SCREENING_TABLE:
        evidence: Evidence | None
        if rule.condition_code is not None:
            fact = told_by_code.get(rule.condition_code)
            evidence = None if fact is None else Evidence(kind="fact", id=fact.id, scope=Scope.RECORDS)
        elif rule.min_age is not None:
            evidence = age_evidence if age is not None and age >= rule.min_age else None
        else:
            evidence = None
        if evidence is None:
            continue
        since = now - timedelta(days=rule.interval_months * 30)
        if await _visited_since(session, context=context, since=since):
            continue
        proposal_id = _proposal_id(VisitSource.SCREENING_DUE, f"{rule.code}:{evidence.id}")
        if await _is_declined(session, context=context, proposal_id=proposal_id):
            continue
        purpose = say(rule.purpose_key, language)
        out.append(
            VisitProposal(
                proposal_id=proposal_id,
                source=VisitSource.SCREENING_DUE,
                purpose=purpose,
                provider_kind=rule.provider_kind,
                suggested_at=None,
                why=(evidence,),
            )
        )
    return out


async def propose_visits(
    session: AsyncSession, *, context: KeyContext, language: str, region: Region
) -> ProposedVisits:
    """Every visit Nura proposes right now, from the four sources (module doc), soonest-dated
    first and undated ones after, withheld entirely for a key without the visits scope — a
    proposal is always a visit not yet on the calendar, so a key that may not see the visits
    may not see one being suggested either."""
    if not context.allows(Scope.VISITS):
        return ProposedVisits((), (Scope.VISITS,))
    now = utcnow()
    proposals = [
        *await _follow_up_proposals(session, context=context, language=language, region=region),
        *await _medicine_review_proposals(session, context=context, now=now, language=language),
        *await _test_coming_proposals(session, context=context, language=language),
        *await _screening_proposals(session, context=context, now=now, language=language),
    ]
    proposals.sort(key=lambda one: (one.suggested_at is None, one.suggested_at or now, one.proposal_id))
    withheld = tuple(
        scope for scope in (Scope.RECORDS, Scope.MEDICINES) if not context.allows(scope)
    )
    return ProposedVisits(proposals, withheld)


async def decline_proposal(session: AsyncSession, *, context: KeyContext, proposal_id: str) -> None:
    """"Not now": hide this proposal for `DECLINE_WINDOW` (module doc). Idempotent — a second
    decline inside the window is a no-op, the way `_decline_topic_for_30_days` already is."""
    now = utcnow()
    if await _is_declined(session, context=context, proposal_id=proposal_id):
        return
    event = await record_event(
        session,
        context=context,
        kind=EventKind.ENGAGEMENT,
        occurred_at=now,
        label="not now: visit suggestion",
        source_channel=SourceChannel.APP,
        scope=Scope.RECORDS,
    )
    draft = FactDraft(
        subject=DECLINED_SUBJECT,
        attribute=proposal_id,
        value={"declined_at": now.isoformat()},
        unit=None,
        confidence=1.0,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
        artifact_id=None,
        event_id=event.id,
        episode_id=None,
        supersedes_id=None,
    )
    yes = await confirm(session, context, draft)
    await assert_fact(
        session,
        context=context,
        subject=draft.subject,
        attribute=draft.attribute,
        value=draft.value,
        confidence=draft.confidence,
        confidence_state=draft.confidence_state,
        confirmation_id=yes.id,
        event_id=event.id,
        valid_from=now,
        valid_to=now + DECLINE_WINDOW,
    )
