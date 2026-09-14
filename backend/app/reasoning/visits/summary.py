"""The post-visit summary: transcript in, a card the person confirms, memos out (E05-05).

    Post-visit summary in Dad's language, action items, medication changes reconciled,
    follow-ups scheduled. — docs/stage1-product-design.md

The transcript is an artefact in the object store, never a column. A `Summariser` reads it
and answers with structure — actions, medicine changes, follow-ups, facts heard, each with
where in the transcript it was heard and how sure — and the templates speak: the model
classifies, the template writes the sentence. A medicine change is rendered as a question
for the doctor and, on the person's yes, becomes a `Flag` and a memo asking about it — never
a change to a medicine line, never a dose. A fact heard about a dose is rerouted to a change
before anything is rendered. A red-flag word among the facts heard writes a `Flag` before the
card is composed and puts "Call Dr Tan today." at the top of it; no ranking sees the card
first. `FixtureSummariser` is what runs in the tests and on a laptop; a model in the
profile's region is a later adapter behind the same protocol.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_read, audited_write, person_display_name
from app.audit.models import Action
from app.audit.trail import record
from app.consent.models import ConsentPurpose
from app.consent.service import require_consent
from app.db import as_utc, utcnow
from app.drafts import AppointmentDraft, DecidedItem, FactDraft, VisitSummaryDraft
from app.drugs.registry import DrugRegistry
from app.errors import Refusal
from app.ingestion.extract import check_code, check_confidence, check_value
from app.ingestion.objects import ObjectStore, sha256_of
from app.keys.confirm import confirm, consume_confirmation
from app.keys.context import KeyContext
from app.keys.grants import list_keys
from app.keys.scopes import KeyRole, Scope
from app.medicines.models import LineStatus, MedicationLine
from app.memory.episodic import require_artifact, store_artifact
from app.memory.models import (
    Appointment,
    AppointmentStatus,
    Artifact,
    ArtifactKind,
    ConfidenceState,
    Fact,
    Provider,
    ProviderKind,
    SourceChannel,
    short_label,
)
from app.memory.semantic import assert_fact
from app.memory.spine import add_provider, book_appointment, list_providers
from app.reasoning.visits.memos import write_memo
from app.reasoning.visits.models import (
    SUMMARY_IN_PROGRESS,
    Flag,
    FlagKind,
    ItemState,
    Memo,
    MemoKind,
    MemoSource,
    SummaryItem,
    SummaryItemKind,
    VisitSummary,
)
from app.reasoning.visits.questions import CHANGE_TEMPLATE, Visit, require_visit
from app.reasoning.visits.strings import (
    day_and_date,
    say,
    subject_words,
)
from app.regions import REGION_TZ, Region, guard_region
from app.safety.high_risk import MEDICINE_SUBJECTS
from app.safety.red_flags import red_flags_in
from app.state.service import StateView, current_state, render_from_state

SUMMARY = VisitSummary.__tablename__
ITEM = SummaryItem.__tablename__

TRANSCRIPT_CONTENT_TYPE = "text/plain; charset=utf-8"
MAX_TRANSCRIPT_BYTES = 1024 * 1024
"""A megabyte of text: an hour's visit with room. Not a recording — that is a VOICE artefact."""

TRANSCRIPT_KINDS = frozenset({ArtifactKind.TRANSCRIPT, ArtifactKind.VOICE})

DOSE_ATTRIBUTES = frozenset({"dose", "start", "stop", "strength", "frequency"})
"""A fact heard about one of these is a medicine change, and is rerouted as a question."""

FOLLOW_UP_HOUR = time(9, 0)
"""When a follow-up with no time is written down: the morning, on the patient's clock."""


class NotATranscript(Refusal):
    """The artefact named is not a transcript or a recording, or the text was empty."""


class TranscriptTooLarge(Refusal):
    """A visit's transcript is not this big."""


class NoSuchSummary(Refusal):
    """No post-visit summary by that id on this profile."""


class NoSuchSummaryItem(Refusal):
    """A decision named an item that is not on this summary."""


class AlreadyConfirmed(Refusal):
    """This summary has been confirmed. What it wrote is memos, visits and facts now."""


class NotEveryItemDecided(Refusal):
    """One tap saves the whole summary, so every item needs a decision, and only one."""


class NotADecision(Refusal):
    """An item is confirmed or rejected. Nothing on a summary is corrected in place."""


class NotAFixture(Refusal):
    """A visit fixture is a JSON file of one shape. This one was not."""


# --- what the summariser answers with --------------------------------------------------------


class ActionKind(StrEnum):
    """What the doctor asked him to do, as a code the templates know. The summariser
    classifies; a thing said that fits none of these is not an action Nura can put in his
    mouth, and is left for the transcript to say."""

    WEIGH_EVERY_MORNING = "weigh_every_morning"
    BP_EVERY_MORNING = "bp_every_morning"
    BRING_BP_BOOK_NEXT_TIME = "bring_bp_book_next_time"
    NO_FOOD_AFTER_MIDNIGHT = "no_food_after_midnight"
    WATER_IS_OK = "water_is_ok"
    LIGHTER_DINNERS = "lighter_dinners"
    TAKE_MEDICINES_AS_BEFORE = "take_medicines_as_before"
    WALK_EVERY_DAY = "walk_every_day"
    BLOOD_TEST_ON = "blood_test_on"


class ChangeHeard(StrEnum):
    """What kind of change to a medicine was heard. Never how much: the amount is the
    label's and the doctor's, and the sentence rendered is a question, not the change."""

    DOSE = "dose"
    START = "start"
    STOP = "stop"
    UNCLEAR = "unclear"


@dataclass(frozen=True, slots=True)
class Span:
    """Where in the transcript something was heard: character offsets."""

    start: int
    end: int

    def as_json(self) -> dict[str, int]:
        return {"start": self.start, "end": self.end}


@dataclass(frozen=True, slots=True)
class ActionHeard:
    kind: ActionKind
    slots: dict[str, Any]
    span: Span
    confidence: float


@dataclass(frozen=True, slots=True)
class MedicationChangeHeard:
    drug: str
    change: ChangeHeard
    span: Span
    confidence: float


@dataclass(frozen=True, slots=True)
class FollowUpHeard:
    on: date
    purpose: str
    span: Span
    confidence: float
    at: time | None = None
    provider: str | None = None


@dataclass(frozen=True, slots=True)
class FactHeard:
    subject: str
    attribute: str
    value: Any
    unit: str | None
    span: Span
    confidence: float


@dataclass(frozen=True, slots=True)
class SummaryDraft:
    """What the summariser heard. Nothing here is a fact, a memo or a booking yet."""

    actions: tuple[ActionHeard, ...] = ()
    medication_changes: tuple[MedicationChangeHeard, ...] = ()
    follow_ups: tuple[FollowUpHeard, ...] = ()
    facts_heard: tuple[FactHeard, ...] = ()

    @classmethod
    def nothing(cls) -> SummaryDraft:
        """The honest answer for a transcript that could not be read."""
        return cls()


@dataclass(frozen=True, slots=True)
class SummaryHints:
    """What the summariser may be told: the language, the region, the doctor's name, and
    the medicines on the record — so it can name a drug it heard, never invent one."""

    language: str
    region: Region
    doctor: str | None = None
    medicines: tuple[str, ...] = ()


class Summariser(Protocol):
    async def summarise(
        self, transcript_text: str, language: str, hints: SummaryHints
    ) -> SummaryDraft: ...


# --- the fixture summariser -------------------------------------------------------------------


def _span(entry: Mapping[str, Any]) -> Span:
    span = entry["span"]
    return Span(int(span["start"]), int(span["end"]))


def draft_from_fixture(fixture: Mapping[str, Any]) -> SummaryDraft:
    """The draft a fixture file describes. Keys the shape does not name — the note, the
    transcript itself — are ignored: a fixture documents itself."""
    try:
        summary = fixture["summary"]
        actions = tuple(
            ActionHeard(
                ActionKind(one["kind"]),
                dict(one.get("slots", {})),
                _span(one),
                check_confidence(one["confidence"]),
            )
            for one in summary.get("actions", [])
        )
        changes = tuple(
            MedicationChangeHeard(
                str(one["drug"]),
                ChangeHeard(one["change"]),
                _span(one),
                check_confidence(one["confidence"]),
            )
            for one in summary.get("medication_changes", [])
        )
        follow_ups = tuple(
            FollowUpHeard(
                on=date.fromisoformat(one["on"]),
                purpose=str(one["purpose"]),
                span=_span(one),
                confidence=check_confidence(one["confidence"]),
                at=None if one.get("at") is None else time.fromisoformat(one["at"]),
                provider=one.get("provider"),
            )
            for one in summary.get("follow_ups", [])
        )
        facts = tuple(
            FactHeard(
                check_code(one["subject"]),
                check_code(one["attribute"]),
                check_value(one["value"]),
                one.get("unit"),
                _span(one),
                check_confidence(one["confidence"]),
            )
            for one in summary.get("facts_heard", [])
        )
    except (KeyError, TypeError, ValueError) as misshapen:
        raise NotAFixture(f"a visit fixture names a summary: {misshapen}") from None
    return SummaryDraft(actions, changes, follow_ups, facts)


class FixtureSummariser:
    """Answers from `tests/fixtures/visits/*.json`, by the sha256 of the transcript text.

    Each fixture carries the transcript, its digest, and the structure a summariser would
    hear in it. A transcript no fixture names is `SummaryDraft.nothing()`.
    """

    def __init__(self, directory: Path) -> None:
        self._directory = Path(directory)
        self._by_digest: dict[str, Path] | None = None

    def _index(self) -> dict[str, Path]:
        if self._by_digest is None:
            found: dict[str, Path] = {}
            for path in sorted(self._directory.glob("*.json")):
                digest = json.loads(path.read_text()).get("sha256")
                if isinstance(digest, str):
                    found[digest.lower()] = path
            self._by_digest = found
        return self._by_digest

    def fixtures(self) -> Sequence[Path]:
        return tuple(self._index().values())

    async def summarise(
        self, transcript_text: str, language: str, hints: SummaryHints
    ) -> SummaryDraft:
        path = self._index().get(hashlib.sha256(transcript_text.encode()).hexdigest())
        if path is None:
            return SummaryDraft.nothing()
        return draft_from_fixture(json.loads(path.read_text()))


# --- storing the transcript -------------------------------------------------------------------


def transcript_key(profile_id: uuid.UUID, digest: str) -> str:
    return f"transcripts/{profile_id}/{digest}"


@audited(Action.WRITE, Scope.RECORDS, Artifact.__tablename__)
async def store_transcript(
    session: AsyncSession,
    *,
    context: KeyContext,
    store: ObjectStore,
    text: str,
    captured_at: datetime,
    source_channel: SourceChannel = SourceChannel.APP,
) -> Artifact:
    """Keep a transcript: the text in the region's store, one Artifact row naming it by key
    and digest. Nothing of what was said goes in the row."""
    guard_region(held_in=store.region, asked_from=context.region)
    data = text.encode("utf-8")
    if not text.strip():
        raise NotATranscript("the transcript was empty")
    if len(data) > MAX_TRANSCRIPT_BYTES:
        raise TranscriptTooLarge(f"a transcript is at most {MAX_TRANSCRIPT_BYTES} bytes")
    await require_consent(
        session, context=context, purpose=ConsentPurpose.HOLD_HEALTH_RECORD, scope=Scope.RECORDS
    )
    digest = sha256_of(data)
    key = transcript_key(context.profile_id, digest)
    await store.put(key, data)
    return await store_artifact(
        session,
        context=context,
        kind=ArtifactKind.TRANSCRIPT,
        storage_key=key,
        content_type=TRANSCRIPT_CONTENT_TYPE,
        sha256=digest,
        captured_at=captured_at,
        source_channel=source_channel,
        region=store.region,
    )


# --- composing the card -----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Item:
    """One item as it goes on the card: kind, structure, span, confidence, template, line."""

    kind: SummaryItemKind
    payload: dict[str, Any]
    span: Span
    confidence: float
    key: str
    text: str


def reroute_medicine_facts(draft: SummaryDraft) -> SummaryDraft:
    """A fact heard about a medicine's dose, start or stop is a medicine change: it is never
    written as a fact from a transcript, it becomes a question for the doctor."""
    kept: list[FactHeard] = []
    changes = list(draft.medication_changes)
    for fact in draft.facts_heard:
        if fact.subject in MEDICINE_SUBJECTS and fact.attribute in DOSE_ATTRIBUTES:
            drug = (
                fact.value.get("drug")
                if isinstance(fact.value, Mapping) and isinstance(fact.value.get("drug"), str)
                else fact.value
                if isinstance(fact.value, str)
                else fact.subject
            )
            change = (
                ChangeHeard(fact.attribute)
                if fact.attribute in {"start", "stop"}
                else ChangeHeard.DOSE
            )
            changes.append(MedicationChangeHeard(str(drug), change, fact.span, fact.confidence))
        else:
            kept.append(fact)
    return SummaryDraft(draft.actions, tuple(changes), draft.follow_ups, tuple(kept))


def _action_slots(action: ActionHeard, visit: Visit, region: Region) -> dict[str, Any]:
    slots = dict(action.slots)
    if "day" in slots:
        slots["day"] = day_and_date(
            _at(date.fromisoformat(str(slots["day"])), None, region), visit.language, region
        )
    slots.setdefault("doctor", visit.doctor)
    return slots


def _at(on: date, at: time | None, region: Region) -> datetime:
    return datetime.combine(on, at or FOLLOW_UP_HOUR, tzinfo=REGION_TZ[region]).astimezone(UTC)


async def _active_lines(
    session: AsyncSession, *, context: KeyContext, generic: str | None = None
) -> Sequence[MedicationLine]:
    """E04's active lines, under the medicines scope; none for a key that does not hold it,
    which is a summariser told less, not a refusal."""
    if not context.allows(Scope.MEDICINES):
        return ()
    where: list[Any] = [
        MedicationLine.superseded_at.is_(None),
        MedicationLine.status == LineStatus.ACTIVE,
    ]
    if generic is not None:
        where.append(MedicationLine.generic == generic)
    return await audited_read(session, MedicationLine, context, Scope.MEDICINES, where=where)


async def _carer(session: AsyncSession, context: KeyContext) -> str | None:
    """The chief's name, when the key reaching can read the family list; else nobody named."""
    if not context.allows(Scope.FAMILY):
        return None
    moment = utcnow()
    for key in await list_keys(session, context=context):
        if key.role is KeyRole.CHIEF and key.is_active(moment):
            return await person_display_name(session, context, key.holder_person_id)
    return None


def compose_items(draft: SummaryDraft, visit: Visit, region: Region) -> list[Item]:
    """Every item rendered through its template — the change as a question, never as the
    change — and the verifier. A line that fails refuses the card."""
    lang = visit.language
    doctor = visit.doctor
    items: list[Item] = []
    for change in draft.medication_changes:
        key = CHANGE_TEMPLATE.get(change.change.value, "ask_medicine_change")
        medicine = visit.medicine(change.drug)
        items.append(
            Item(
                SummaryItemKind.MEDICATION_CHANGE,
                {"generic": change.drug.strip().lower(), "change": change.change.value},
                change.span,
                change.confidence,
                key,
                say(key, lang, doctor=doctor, medicine=medicine),
            )
        )
    for action in draft.actions:
        slots = _action_slots(action, visit, region)
        items.append(
            Item(
                SummaryItemKind.ACTION,
                {"kind": action.kind.value, "slots": dict(action.slots)},
                action.span,
                action.confidence,
                action.kind.value,
                say(action.kind.value, lang, **slots),
            )
        )
    for follow_up in draft.follow_ups:
        when = _at(follow_up.on, follow_up.at, region)
        items.append(
            Item(
                SummaryItemKind.FOLLOW_UP,
                {
                    "on": follow_up.on.isoformat(),
                    "at": None
                    if follow_up.at is None
                    else follow_up.at.isoformat(timespec="minutes"),
                    "provider": follow_up.provider or doctor,
                    "purpose": short_label(follow_up.purpose),
                },
                follow_up.span,
                follow_up.confidence,
                "see_again_on",
                say(
                    "see_again_on",
                    lang,
                    doctor=follow_up.provider or doctor,
                    day=day_and_date(when, lang, region),
                ),
            )
        )
    for fact in draft.facts_heard:
        items.append(
            Item(
                SummaryItemKind.FACT_HEARD,
                {
                    "subject": fact.subject,
                    "attribute": fact.attribute,
                    "value": fact.value,
                    "unit": fact.unit,
                },
                fact.span,
                fact.confidence,
                "doctor_wrote_down",
                say(
                    "doctor_wrote_down",
                    lang,
                    doctor=doctor,
                    thing=subject_words(fact.subject, lang),
                ),
            )
        )
    return items


@audited(Action.WRITE, Scope.VISITS, SUMMARY)
async def post_visit_summary(
    session: AsyncSession,
    *,
    context: KeyContext,
    appointment_id: uuid.UUID,
    artifact_id: uuid.UUID,
    store: ObjectStore,
    summariser: Summariser,
    registry: DrugRegistry | None = None,
) -> VisitSummary:
    """Read the transcript into a card for the person to confirm.

    The red-flag rule runs first: a red-flag word among the facts heard writes a `Flag` and
    puts the same-day lines at the top of the card before anything else is composed. Then
    every item is rendered through its template and the verifier; a medicine change is a
    question for the doctor. The card names the transcript, the visit and the State.
    """
    visit = await require_visit(
        session, context=context, appointment_id=appointment_id, registry=registry
    )
    artifact = await require_artifact(session, context=context, artifact_id=artifact_id)
    if artifact.kind not in TRANSCRIPT_KINDS:
        raise NotATranscript(f"artefact {artifact_id} is a {artifact.kind}, not a transcript")
    text = (await store.get(artifact.storage_key)).decode("utf-8", errors="replace")
    if not text.strip():
        raise NotATranscript("the transcript was empty")
    lines_now = await _active_lines(session, context=context)
    heard = reroute_medicine_facts(
        await summariser.summarise(
            text,
            visit.language,
            SummaryHints(
                language=visit.language,
                region=context.region,
                doctor=visit.doctor,
                medicines=tuple(sorted({line.generic for line in lines_now})),
            ),
        )
    )
    state = await current_state(session, context=context)
    lang = visit.language
    lines: list[dict[str, Any]] = []

    # The red-flag rule, before anything is ranked: a flag row per word heard, naming where
    # in the transcript the fact that carries it was heard, then the same-day lines.
    found: dict[str, tuple[str, Span]] = {}
    for fact in heard.facts_heard:
        for hit in red_flags_in(fact.value):
            found.setdefault(hit.code, (hit.word, fact.span))
    red_flag = bool(found)
    flags: list[Flag] = []
    for code, (word, span) in found.items():
        flags.append(
            await audited_write(
                session,
                Flag,
                context,
                Scope.RECORDS,
                kind=FlagKind.RED_FLAG,
                code=code,
                subject="symptom",
                fact_ids=[],
                payload={"word": word, "span": span.as_json()},
                artifact_id=artifact.id,
                appointment_id=appointment_id,
                raised_at=utcnow(),
            )
        )
    if red_flag:
        lines.append(
            {
                "key": "call_doctor_today",
                "text": say("call_doctor_today", lang, doctor=visit.doctor),
            }
        )
        carer = await _carer(session, context)
        if carer:
            lines.append(
                {"key": "tell_carer_today", "text": say("tell_carer_today", lang, carer=carer)}
            )

    items = compose_items(heard, visit, context.region)
    when = day_and_date(visit.appointment.scheduled_at, lang, context.region)
    lines.append(
        {
            "key": "doctor_said_on",
            "text": say("doctor_said_on", lang, doctor=visit.doctor, day=when),
        }
    )
    lines.extend({"key": item.key, "text": item.text} for item in items)

    summary = await render_from_state(
        session,
        VisitSummary,
        context,
        Scope.VISITS,
        state=state,
        appointment_id=appointment_id,
        artifact_id=artifact.id,
        language=lang,
        red_flag=red_flag,
        lines=lines,
        created_at=utcnow(),
    )
    for position, item in enumerate(items):
        await audited_write(
            session,
            SummaryItem,
            context,
            Scope.VISITS,
            summary_id=summary.id,
            position=position,
            kind=item.kind,
            payload=item.payload,
            span=item.span.as_json(),
            confidence=item.confidence,
            key=item.key,
            text=item.text,
            state=ItemState.PROPOSED,
        )
    return summary


# --- reading it back --------------------------------------------------------------------------


@audited(Action.READ, Scope.VISITS, SUMMARY)
async def require_summary(
    session: AsyncSession, *, context: KeyContext, summary_id: uuid.UUID
) -> VisitSummary:
    found = await audited_read(
        session, VisitSummary, context, Scope.VISITS, where=(VisitSummary.id == summary_id,)
    )
    if not found:
        raise NoSuchSummary(f"no summary {summary_id} on profile {context.profile_id}")
    return found[0]


@audited(Action.READ, Scope.VISITS, SUMMARY)
async def list_summaries(
    session: AsyncSession, *, context: KeyContext, appointment_id: uuid.UUID
) -> Sequence[VisitSummary]:
    found = await audited_read(
        session,
        VisitSummary,
        context,
        Scope.VISITS,
        where=(VisitSummary.appointment_id == appointment_id,),
    )
    return sorted(found, key=lambda one: (as_utc(one.created_at), str(one.id)), reverse=True)


@audited(Action.READ, Scope.VISITS, ITEM)
async def summary_items(
    session: AsyncSession, *, context: KeyContext, summary_id: uuid.UUID
) -> Sequence[SummaryItem]:
    found = await audited_read(
        session, SummaryItem, context, Scope.VISITS, where=(SummaryItem.summary_id == summary_id,)
    )
    return sorted(found, key=lambda item: item.position)


# --- the person's yes -------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Decision:
    item_id: uuid.UUID
    decision: ItemState


DECISIONS = frozenset({ItemState.CONFIRMED, ItemState.REJECTED})


def _decided(items: Sequence[SummaryItem], decisions: Sequence[Decision]) -> list[DecidedItem]:
    by_id = {item.id: item for item in items}
    said: dict[uuid.UUID, Decision] = {}
    for decision in decisions:
        if decision.item_id not in by_id:
            raise NoSuchSummaryItem(f"item {decision.item_id} is not on this summary")
        if decision.item_id in said:
            raise NotEveryItemDecided(f"item {decision.item_id} was decided twice")
        if decision.decision not in DECISIONS:
            raise NotADecision("an item is confirmed or rejected")
        said[decision.item_id] = decision
    missing = set(by_id) - set(said)
    if missing:
        raise NotEveryItemDecided(f"{len(missing)} item(s) have no decision")
    return [DecidedItem(item.id, item.kind.value, said[item.id].decision.value) for item in items]


@audited(Action.READ, Scope.VISITS, SUMMARY)
async def summary_draft_for(
    session: AsyncSession,
    *,
    context: KeyContext,
    summary_id: uuid.UUID,
    decisions: Sequence[Decision],
) -> VisitSummaryDraft:
    """What the person is saying yes to: this card, its transcript, every item decided."""
    summary = await require_summary(session, context=context, summary_id=summary_id)
    if not summary.is_open:
        raise AlreadyConfirmed(f"summary {summary_id} was confirmed at {summary.confirmed_at}")
    items = await summary_items(session, context=context, summary_id=summary_id)
    return VisitSummaryDraft(summary.id, summary.artifact_id, tuple(_decided(items, decisions)))


@dataclass(slots=True)
class Outcome:
    """What the yes wrote: memos, visits, facts and flags. Never a medicine."""

    summary: VisitSummary
    items: Sequence[SummaryItem]
    memos: list[Memo] = field(default_factory=list)
    appointments: list[Appointment] = field(default_factory=list)
    facts: list[Fact] = field(default_factory=list)
    flags: list[Flag] = field(default_factory=list)


async def _provider_named(
    session: AsyncSession, *, context: KeyContext, name: str, fallback: Provider
) -> Provider:
    wanted = name.strip().lower()
    for provider in await list_providers(session, context=context):
        if provider.name.strip().lower() == wanted:
            return provider
    if wanted == fallback.name.strip().lower() or not wanted:
        return fallback
    return await add_provider(
        session, context=context, name=name, kind=ProviderKind.DOCTOR, region=context.region
    )


async def _book_follow_up(
    session: AsyncSession, *, context: KeyContext, item: SummaryItem, visit: Visit
) -> Appointment:
    """A follow-up heard becomes a PLANNED visit, on the person's yes to the card: the yes
    for exactly this booking is written and used in the same unit of work, the way the
    review card does for each fact."""
    payload = item.payload
    at = None if payload.get("at") is None else time.fromisoformat(str(payload["at"]))
    when = _at(date.fromisoformat(str(payload["on"])), at, context.region)
    provider = await _provider_named(
        session, context=context, name=str(payload.get("provider") or ""), fallback=visit.provider
    )
    purpose = short_label(str(payload["purpose"]))
    yes = await confirm(
        session,
        context,
        AppointmentDraft(provider_id=provider.id, scheduled_at=when, purpose=purpose),
    )
    return await book_appointment(
        session,
        context=context,
        provider_id=provider.id,
        scheduled_at=when,
        purpose=purpose,
        confirmation_id=yes.id,
        status=AppointmentStatus.PLANNED,
    )


async def _write_fact_heard(
    session: AsyncSession,
    *,
    context: KeyContext,
    item: SummaryItem,
    summary: VisitSummary,
    visit: Visit,
) -> Fact:
    payload = item.payload
    draft = FactDraft(
        subject=str(payload["subject"]),
        attribute=str(payload["attribute"]),
        value=payload["value"],
        unit=payload.get("unit"),
        confidence=1.0,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
        artifact_id=summary.artifact_id,
        event_id=None,
        episode_id=None,
        supersedes_id=None,
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
        valid_from=as_utc(visit.appointment.scheduled_at),
    )


@audited(Action.WRITE, Scope.VISITS, SUMMARY)
async def confirm_summary(
    session: AsyncSession,
    *,
    context: KeyContext,
    summary_id: uuid.UUID,
    decisions: Sequence[Decision],
    confirmation_id: uuid.UUID,
    registry: DrugRegistry | None = None,
) -> Outcome:
    """Close the card on the person's yes and write what it decided.

    Follow-ups first, so memos can be filed against the next visit. Then, item by item: an
    action becomes a memo; a medicine change becomes a `Flag` for E04's reconcile and a memo
    asking the doctor — no medicine line changes, no dose is written; a fact heard becomes a
    Fact with the transcript as provenance and the person as confirmer. A rejected item
    writes nothing. The card closes last, naming who confirmed it and when.
    """
    draft = await summary_draft_for(
        session, context=context, summary_id=summary_id, decisions=decisions
    )
    summary = await require_summary(session, context=context, summary_id=summary_id)
    visit = await require_visit(
        session, context=context, appointment_id=summary.appointment_id, registry=registry
    )
    items = await summary_items(session, context=context, summary_id=summary_id)
    yes = await consume_confirmation(session, context, confirmation_id, draft)
    state: StateView = await current_state(session, context=context)
    decided = {one.item_id: ItemState(one.decision) for one in draft.items}
    moment = utcnow()
    outcome = Outcome(summary=summary, items=items)

    session.info[SUMMARY_IN_PROGRESS] = summary.id
    try:
        kept = [item for item in items if decided[item.id] is ItemState.CONFIRMED]
        for item in kept:
            if item.kind is SummaryItemKind.FOLLOW_UP:
                booked = await _book_follow_up(session, context=context, item=item, visit=visit)
                item.appointment_id = booked.id
                outcome.appointments.append(booked)
        # State moved with the bookings; memos are rendered from what it is now.
        state = await current_state(session, context=context)
        filed_against = (
            outcome.appointments[0].id if outcome.appointments else summary.appointment_id
        )
        for item in kept:
            if item.kind is SummaryItemKind.ACTION:
                memo = await write_memo(
                    session,
                    context=context,
                    kind=MemoKind.ACTION,
                    key=item.key,
                    slots=_action_slots(
                        ActionHeard(
                            ActionKind(item.payload["kind"]),
                            dict(item.payload.get("slots", {})),
                            Span(**item.span) if item.span else Span(0, 0),
                            item.confidence,
                        ),
                        visit,
                        context.region,
                    ),
                    source=MemoSource.VISIT,
                    source_id=item.id,
                    appointment_id=filed_against,
                    state=state,
                    language=summary.language,
                )
                item.memo_id = memo.id
                outcome.memos.append(memo)
            elif item.kind is SummaryItemKind.MEDICATION_CHANGE:
                # The change as E04's reconcile picks it up, with the person's OK on a plan:
                # the generic, the kind of change, the active line it is about — no amount.
                generic = str(item.payload["generic"])
                lines = await _active_lines(session, context=context, generic=generic)
                flag = await audited_write(
                    session,
                    Flag,
                    context,
                    Scope.RECORDS,
                    kind=FlagKind.MEDICINE_CHANGE_HEARD,
                    code=str(item.payload["change"]),
                    subject=generic,
                    fact_ids=[str(line.fact_id) for line in lines],
                    payload={
                        "generic": generic,
                        "change": str(item.payload["change"]),
                        "line_id": str(lines[0].id) if lines else None,
                        "span": item.span,
                        "ask_the_doctor": True,
                    },
                    artifact_id=summary.artifact_id,
                    appointment_id=summary.appointment_id,
                    raised_at=moment,
                )
                memo = await write_memo(
                    session,
                    context=context,
                    kind=MemoKind.ASK,
                    key=item.key,
                    slots={"doctor": visit.doctor, "medicine": visit.medicine(generic)},
                    source=MemoSource.VISIT,
                    source_id=item.id,
                    appointment_id=filed_against,
                    state=state,
                    language=summary.language,
                )
                item.flag_id = flag.id
                item.memo_id = memo.id
                outcome.flags.append(flag)
                outcome.memos.append(memo)
            elif item.kind is SummaryItemKind.FACT_HEARD:
                fact = await _write_fact_heard(
                    session, context=context, item=item, summary=summary, visit=visit
                )
                item.fact_id = fact.id
                outcome.facts.append(fact)
                # A fact landing moved State; the next memo is rendered from the new one.
                state = await current_state(session, context=context)
        for item in items:
            item.state = decided[item.id]
            item.decided_at = moment
            await session.flush()
            await record(
                session,
                context=context,
                action=Action.WRITE,
                scope=Scope.VISITS,
                target=ITEM,
                target_id=item.id,
                rows=1,
            )
        summary.confirmed_at = moment
        summary.confirmed_by_person_id = yes.person_id
        await session.flush()
        await record(
            session,
            context=context,
            action=Action.WRITE,
            scope=Scope.VISITS,
            target=SUMMARY,
            target_id=summary.id,
            rows=1,
        )
    finally:
        session.info.pop(SUMMARY_IN_PROGRESS, None)
    return outcome
