"""The medicines service: reconcile a label, take a dose, count what is left, tell the story.

Every function takes the session first and the key context by keyword, stands behind an
`audited` door under `Scope.MEDICINES`, and reaches every row through `app.audit.access`.
Pharmacology comes from the `DrugRegistry` passed in — identification, interactions, the
monograph's rule ids — and from nowhere else. Every write of a line or a supply is a `Fact`
with provenance first (`app.memory.semantic.assert_fact`, which runs the high-risk hook and
spends the person's yes) and a typed row second; the row names the fact.

Who may change the list: the owner, the steward, a chief or a caregiver. A helper, a viewer,
a clinic hold the medicines scope to *read* — the list, the story — and to tap "Taken"; they
do not add or change a line (`NotTheirsToChange`). Nothing here applies a dose change: it
supersedes the line with the person's yes and renders as a question for the doctor.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta, tzinfo
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import ColumnElement
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_profile_read, audited_read, audited_write
from app.audit.models import Action, Channel
from app.audit.trail import record
from app.consent.models import ConsentPurpose
from app.consent.service import require_consent
from app.db import as_utc, utcnow
from app.drafts import FactDraft
from app.drugs.registry import (
    DrugMatch,
    DrugRegistry,
    Interaction,
    LabelFields,
    NotIdentified,
    ReviewState,
)
from app.errors import Refusal
from app.ingestion.models import CONFIDENCE_THRESHOLD
from app.keys.context import KeyContext
from app.keys.scopes import KeyRole, Scope
from app.language.review import queue_pending_interaction
from app.medicines import dose as arithmetic
from app.medicines.dose import Dose
from app.medicines.models import (
    LEAD_TIME_DAYS,
    REORDER_THRESHOLD_DAYS,
    ChangeKind,
    DoseTaken,
    InteractionFlag,
    LineStatus,
    MedicationLine,
    SourceKind,
    Supply,
)
from app.medicines.story import (
    Story,
    count_lines,
    dose_card_line,
    interaction_question,
    medication_story,
    reorder_lines,
)
from app.medicines.strings import (
    PLAIN_NAME,
    REORDER_ACTIONS,
    SOURCE,
    TAKEN,
    language_of,
    say_date,
)
from app.medicines.windows import is_late, window_status
from app.memory.episodic import require_artifact
from app.memory.models import ArtifactKind, ConfidenceState, Event, EventKind, SourceChannel
from app.memory.semantic import assert_fact
from app.regions import REGION_TZ
from app.safety.high_risk import MEDICATION, HighRiskNeedsLabelPhoto

if TYPE_CHECKING:
    from app.routines.service import Day

LINE = MedicationLine.__tablename__

CHANGERS: frozenset[KeyRole] = frozenset({KeyRole.CHIEF, KeyRole.CAREGIVER})
"""The key roles that may add or change a medicine, beside the owner and the steward."""


class NotTheirsToChange(Refusal):
    """A key to read the medicines is not a key to change them. The owner, his steward, a
    chief or a caregiver adds a line; a helper reads the list and taps Taken."""


class NoSuchLine(Refusal):
    """No active medicine line by that id on this profile."""


class AlreadyRecorded(Refusal):
    """This label has already been recorded for this medicine, or it says nothing new."""


class Outcome(StrEnum):
    """What a label means against the list (module doc, section 2, step 5)."""

    NEW_LINE = "new_line"
    REFILL = "refill"
    DOSE_CHANGE = "dose_change"
    DUPLICATE = "duplicate"


@dataclass(frozen=True, slots=True)
class Label:
    """What one label or pack said, as the extractor read it or the person typed it."""

    dose: Dose
    generic: str | None = None
    brand: str | None = None
    strength: str | None = None
    form: str | None = None
    registration_no: str | None = None
    quantity: int | None = None
    prescriber: str | None = None
    dispensed_at: datetime | None = None
    source_kind: SourceKind = SourceKind.RETAIL
    confidence: float = 1.0

    def fields(self) -> LabelFields:
        return LabelFields(
            registration_no=self.registration_no,
            brand=self.brand,
            generic=self.generic,
            strength=self.strength,
            form=self.form,
        )


@dataclass(frozen=True, slots=True)
class Flagged:
    """One interaction the registry flagged between the new medicine and a line already there."""

    interaction: Interaction
    other_line: MedicationLine


@dataclass(frozen=True, slots=True)
class Plan:
    """What reconciling this label would do — shown to the person before he says yes.

    `draft` is exactly what `reconcile` will write and what the yes binds to; it is None for
    a duplicate, which writes nothing. `needs_label_photo` is the high-risk rule, told before
    the write so the card can ask for the photo.
    """

    outcome: Outcome
    match: DrugMatch
    matched_line: MedicationLine | None
    draft: FactDraft | None
    flagged: list[Flagged]
    needs_label_photo: bool
    lead_time_days: int


@dataclass(frozen=True, slots=True)
class Reconciled:
    outcome: Outcome
    line: MedicationLine
    supply: Supply | None
    flags: list[InteractionFlag]


def may_change_medicines(context: KeyContext) -> None:
    if context.is_owner or context.is_steward or context.role in CHANGERS:
        return
    raise NotTheirsToChange(f"a {context.role} key reads the medicines; it does not change them")


def _one_product(matches: Sequence[DrugMatch]) -> DrugMatch:
    """One product, or nothing. Two brands of the same generic and strength agree on
    everything that matters; two strengths do not, and nothing is guessed between them.

    Below `CONFIDENCE_THRESHOLD` the best match is not trusted either (#206): a name match
    whose strength or form does not belong to that product scores low, so a label that
    happens to collide with a real product's name is not silently taken as identifying it —
    the same floor a document field (`app.ingestion.models`) and a WhatsApp voice transcript
    (E19) are already held to before either is trusted.
    """
    if not matches:
        raise NotIdentified("the label matched no product in the register")
    distinct = {(m.generic, m.strength, m.form) for m in matches}
    if len(distinct) > 1:
        raise NotIdentified("the label matched more than one product; the strength decides")
    if matches[0].confidence < CONFIDENCE_THRESHOLD:
        raise NotIdentified(
            f"the label matched {matches[0].generic} at confidence "
            f"{matches[0].confidence:.2f}, below {CONFIDENCE_THRESHOLD}"
        )
    return matches[0]


async def _active_lines(
    session: AsyncSession, *, context: KeyContext, generic: str | None = None
) -> list[MedicationLine]:
    where: list[ColumnElement[bool]] = [
        MedicationLine.superseded_at.is_(None),
        MedicationLine.status == LineStatus.ACTIVE,
    ]
    if generic is not None:
        where.append(MedicationLine.generic == generic)
    found = await audited_read(session, MedicationLine, context, Scope.MEDICINES, where=where)
    return sorted(found, key=lambda line: (as_utc(line.started_at), line.generic))


async def _label_seen_before(
    session: AsyncSession, *, context: KeyContext, artifact_id: uuid.UUID, generic: str
) -> bool:
    lines = await audited_read(
        session,
        MedicationLine,
        context,
        Scope.MEDICINES,
        where=(MedicationLine.source_artifact_id == artifact_id, MedicationLine.generic == generic),
    )
    if lines:
        return True
    supplies = await audited_read(
        session, Supply, context, Scope.MEDICINES, where=(Supply.artifact_id == artifact_id,)
    )
    line_ids = {s.line_id for s in supplies}
    if not line_ids:
        return False
    on = await audited_read(
        session,
        MedicationLine,
        context,
        Scope.MEDICINES,
        where=(MedicationLine.id.in_(line_ids), MedicationLine.generic == generic),
    )
    return bool(on)


def _line_value(match: DrugMatch, label: Label, outcome: Outcome) -> dict[str, Any]:
    """What the fact says: the product the register identified, the dose the label said."""
    return {
        "generic": match.generic,
        "brand": match.brand,
        "strength": match.strength,
        "form": match.form,
        "registration_no": match.registration_no,
        "drug_class": match.drug_class,
        "high_risk": match.high_risk,
        "dose": label.dose.as_json(),
        "prescriber": label.prescriber,
        "source_kind": label.source_kind.value,
        "quantity": label.quantity,
        "dispensed_at": None if label.dispensed_at is None else label.dispensed_at.isoformat(),
        "change": outcome.value,
    }


def _supply_value(line: MedicationLine, label: Label) -> dict[str, Any]:
    return {
        "generic": line.generic,
        "line_id": str(line.id),
        "quantity": label.quantity,
        "dispensed_at": None if label.dispensed_at is None else label.dispensed_at.isoformat(),
        "change": Outcome.REFILL.value,
    }


def _draft(
    *,
    attribute: str,
    value: dict[str, Any],
    label: Label,
    artifact_id: uuid.UUID,
    supersedes: uuid.UUID | None,
) -> FactDraft:
    return FactDraft(
        subject=MEDICATION,
        attribute=attribute,
        value=value,
        unit=None,
        confidence=label.confidence,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
        artifact_id=artifact_id,
        event_id=None,
        episode_id=None,
        supersedes_id=supersedes,
    )


@audited(Action.READ, Scope.MEDICINES, LINE)
async def plan(
    session: AsyncSession,
    *,
    context: KeyContext,
    registry: DrugRegistry,
    label: Label,
    source_artifact_id: uuid.UUID,
) -> Plan:
    """Classify a label against the active lines, without writing anything.

    Identify through the registry; read the artefact; find the line for that generic. Same
    strength and dose with a quantity is a refill; a different strength or dose is a dose
    change; no line is a new line, screened for interactions against everything active; the
    same label twice, or a label that adds nothing, is a duplicate. The draft is what the yes
    will bind to.
    """
    may_change_medicines(context)
    match = _one_product(registry.identify(label.fields()))
    artifact = await require_artifact(session, context=context, artifact_id=source_artifact_id)
    needs_photo = match.high_risk and artifact.kind is not ArtifactKind.PHOTO
    lead = LEAD_TIME_DAYS[label.source_kind]

    if await _label_seen_before(
        session, context=context, artifact_id=source_artifact_id, generic=match.generic
    ):
        return Plan(Outcome.DUPLICATE, match, None, None, [], needs_photo, lead)

    same = await _active_lines(session, context=context, generic=match.generic)
    current = same[-1] if same else None
    if current is None:
        others = await _active_lines(session, context=context)
        by_generic = {line.generic: line for line in others}
        # The pair is told with the new medicine first, however the data orders it.
        flagged = [
            Flagged(
                Interaction(
                    (match.generic, other),
                    interaction.severity,
                    interaction.text_id,
                    source=interaction.source,
                    review_state=interaction.review_state,
                ),
                by_generic[other],
            )
            for interaction in registry.interactions([match.generic, *by_generic])
            for other in interaction.pair
            if match.generic in interaction.pair and other != match.generic and other in by_generic
        ]
        draft = _draft(
            attribute=f"line:{match.generic}",
            value=_line_value(match, label, Outcome.NEW_LINE),
            label=label,
            artifact_id=source_artifact_id,
            supersedes=None,
        )
        return Plan(Outcome.NEW_LINE, match, None, draft, flagged, needs_photo, lead)

    if current.strength == match.strength and Dose.from_json(current.dose).same_as(label.dose):
        if label.quantity is None:
            return Plan(Outcome.DUPLICATE, match, current, None, [], needs_photo, lead)
        draft = _draft(
            attribute=f"supply:{match.generic}",
            value=_supply_value(current, label),
            label=label,
            artifact_id=source_artifact_id,
            supersedes=None,
        )
        return Plan(Outcome.REFILL, match, current, draft, [], needs_photo, lead)

    draft = _draft(
        attribute=f"line:{match.generic}",
        value=_line_value(match, label, Outcome.DOSE_CHANGE),
        label=label,
        artifact_id=source_artifact_id,
        supersedes=current.fact_id,
    )
    return Plan(Outcome.DOSE_CHANGE, match, current, draft, [], needs_photo, lead)


@audited(Action.READ, Scope.MEDICINES, LINE)
async def draft_for(
    session: AsyncSession,
    *,
    context: KeyContext,
    registry: DrugRegistry,
    label: Label,
    source_artifact_id: uuid.UUID,
) -> FactDraft:
    """The draft a yes is minted for: what `reconcile` will write for this label. A label
    that would write nothing has nothing to say yes to, and that refusal is on the trail."""
    what = await plan(
        session,
        context=context,
        registry=registry,
        label=label,
        source_artifact_id=source_artifact_id,
    )
    if what.draft is None:
        raise AlreadyRecorded(f"{what.match.generic}: this label is already on the list")
    return what.draft


async def _write_line(
    session: AsyncSession,
    *,
    context: KeyContext,
    plan: Plan,
    label: Label,
    source_artifact_id: uuid.UUID,
    confirmation_id: uuid.UUID,
    moment: datetime,
) -> MedicationLine:
    assert plan.draft is not None
    fact = await assert_fact(
        session,
        context=context,
        subject=plan.draft.subject,
        attribute=plan.draft.attribute,
        value=plan.draft.value,
        confidence=plan.draft.confidence,
        confidence_state=plan.draft.confidence_state,
        confirmation_id=confirmation_id,
        artifact_id=source_artifact_id,
        supersedes_id=plan.draft.supersedes_id,
    )
    assert fact.confirmed_by_person_id is not None
    old = plan.matched_line
    line = await audited_write(
        session,
        MedicationLine,
        context,
        Scope.MEDICINES,
        fact_id=fact.id,
        generic=plan.match.generic,
        brand=plan.match.brand,
        strength=plan.match.strength,
        form=plan.match.form,
        registration_no=plan.match.registration_no,
        drug_class=plan.match.drug_class,
        high_risk=plan.match.high_risk,
        product_kind=plan.match.product_kind,
        registry_confidence=plan.match.confidence,
        dose=label.dose.as_json(),
        prescriber=label.prescriber,
        source_kind=label.source_kind,
        lead_time_days=plan.lead_time_days,
        reorder_threshold_days=REORDER_THRESHOLD_DAYS,
        source_artifact_id=source_artifact_id,
        source_event_id=None,
        confidence=label.confidence,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
        status=LineStatus.ACTIVE,
        change_kind=(ChangeKind.DOSE_CHANGE if old is not None else ChangeKind.NEW_LINE),
        started_at=old.started_at if old is not None else moment,
        supersedes_id=None if old is None else old.id,
        confirmed_by_person_id=fact.confirmed_by_person_id,
        asserted_at=moment,
    )
    if old is not None:
        old.superseded_at = moment
        await session.flush()
        await record(
            session,
            context=context,
            action=Action.WRITE,
            scope=Scope.MEDICINES,
            target=LINE,
            target_id=old.id,
            rows=1,
        )
    return line


async def _write_supply(
    session: AsyncSession,
    *,
    context: KeyContext,
    line: MedicationLine,
    fact_id: uuid.UUID,
    label: Label,
    source_artifact_id: uuid.UUID,
    confirmed_by: uuid.UUID,
    moment: datetime,
) -> Supply:
    assert label.quantity is not None
    return await audited_write(
        session,
        Supply,
        context,
        Scope.MEDICINES,
        line_id=line.id,
        fact_id=fact_id,
        quantity=label.quantity,
        dispensed_at=label.dispensed_at or moment,
        artifact_id=source_artifact_id,
        confirmed_by_person_id=confirmed_by,
        recorded_at=moment,
    )


@audited(Action.WRITE, Scope.MEDICINES, LINE)
async def reconcile(
    session: AsyncSession,
    *,
    context: KeyContext,
    registry: DrugRegistry,
    label: Label,
    source_artifact_id: uuid.UUID,
    confirmation_id: uuid.UUID,
) -> Reconciled:
    """Write what the label means, with the person's yes for exactly that.

    The plan is computed again here, so the yes binds to what is actually written: a new line
    (and its supply and flags), a supply on the line for a refill, or a new line superseding
    the old for a dose change — the old row stays, marked with when. A high-risk medicine with
    no label photo is refused by class before anything is written; a duplicate is refused too.
    Who may change the list is checked here first, so a helper's try is on the trail as a
    refused write.
    """
    may_change_medicines(context)
    what = await plan(
        session,
        context=context,
        registry=registry,
        label=label,
        source_artifact_id=source_artifact_id,
    )
    if what.needs_label_photo:
        raise HighRiskNeedsLabelPhoto(what.match.drug_class)
    if what.outcome is Outcome.DUPLICATE or what.draft is None:
        raise AlreadyRecorded(f"{what.match.generic}: this label is already on the list")
    moment = utcnow()

    if what.outcome is Outcome.REFILL:
        assert what.matched_line is not None
        fact = await assert_fact(
            session,
            context=context,
            subject=what.draft.subject,
            attribute=what.draft.attribute,
            value=what.draft.value,
            confidence=what.draft.confidence,
            confidence_state=what.draft.confidence_state,
            confirmation_id=confirmation_id,
            artifact_id=source_artifact_id,
        )
        assert fact.confirmed_by_person_id is not None
        refill = await _write_supply(
            session,
            context=context,
            line=what.matched_line,
            fact_id=fact.id,
            label=label,
            source_artifact_id=source_artifact_id,
            confirmed_by=fact.confirmed_by_person_id,
            moment=moment,
        )
        return Reconciled(Outcome.REFILL, what.matched_line, refill, [])

    line = await _write_line(
        session,
        context=context,
        plan=what,
        label=label,
        source_artifact_id=source_artifact_id,
        confirmation_id=confirmation_id,
        moment=moment,
    )
    supply = None
    if label.quantity is not None:
        supply = await _write_supply(
            session,
            context=context,
            line=line,
            fact_id=line.fact_id,
            label=label,
            source_artifact_id=source_artifact_id,
            confirmed_by=line.confirmed_by_person_id,
            moment=moment,
        )
    flags = [
        await audited_write(
            session,
            InteractionFlag,
            context,
            Scope.MEDICINES,
            line_id=line.id,
            other_line_id=each.other_line.id,
            severity=each.interaction.severity,
            text_id=each.interaction.text_id,
            source=each.interaction.source,
            awaiting_review=each.interaction.review_state is ReviewState.AWAITING_REVIEW,
            flagged_at=moment,
        )
        for each in what.flagged
    ]
    for each in what.flagged:
        if each.interaction.review_state is ReviewState.AWAITING_REVIEW:
            await queue_pending_interaction(session, each.interaction)
    return Reconciled(what.outcome, line, supply, flags)


# --- taking a dose ----------------------------------------------------------------------


async def _require_line(
    session: AsyncSession, *, context: KeyContext, line_id: uuid.UUID
) -> MedicationLine:
    found = await audited_read(
        session,
        MedicationLine,
        context,
        Scope.MEDICINES,
        where=(
            MedicationLine.id == line_id,
            MedicationLine.superseded_at.is_(None),
            MedicationLine.status == LineStatus.ACTIVE,
        ),
    )
    if not found:
        raise NoSuchLine(f"no active medicine line {line_id} on profile {context.profile_id}")
    return found[0]


@audited(Action.WRITE, Scope.MEDICINES, DoseTaken.__tablename__)
async def record_dose_taken(
    session: AsyncSession,
    *,
    context: KeyContext,
    line_id: uuid.UUID,
    anchor: str | None = None,
    amount: float | None = None,
    taken_at: datetime | None = None,
    source_channel: SourceChannel = SourceChannel.APP,
    channel: Channel = Channel.APP,
) -> DoseTaken:
    """The person's own tap: this medicine, taken now, by whoever is tapping.

    No confirm — the tap is the yes — and no change to any line. It is a DOSE_TAKEN event
    written under the medicines scope, so the helper who gives him his tablets can tap it
    with the medicines key she holds, and a row naming the line. Audited like every write,
    on the channel the tap came in on: the app, or a "Taken"/"given" reply on WhatsApp.

    `taken_at` is a tap the phone held while it could not reach Nura (E00-08), or a WhatsApp
    reply's own time (the provider's timestamp, #198): written at the moment it says, which
    must be today on the region's clock and not later than now (`TapNotToday`), and written
    once however many times it is sent — the same person, line, moment and anchor is the
    same tap, and the row already written is the answer. The event is recorded now; it
    happened when the tap says it did.

    `late` (#198) is worked out here, once, and stored on the row rather than left for a
    reader to compare `taken_at` against `anchor` itself: whether this tap's own moment came
    after the anchor's window had already closed on his day — the same window the ladder
    climbs from. A tap with no anchor is never late; there is no window to be late against.
    A late "Taken" is still a Taken: nothing here asks a question or holds the tap back.
    """
    line = await _require_line(session, context=context, line_id=line_id)
    dose = Dose.from_json(line.dose)
    if anchor is not None and anchor not in {a.value for a in arithmetic.Anchor}:
        raise arithmetic.NotADose(f"{anchor} is not a moment of the day")
    await require_consent(
        session,
        context=context,
        purpose=ConsentPurpose.HOLD_HEALTH_RECORD,
        scope=Scope.MEDICINES,
        channel=channel,
    )
    moment = utcnow()
    tapped = moment if taken_at is None else _tap_moment(taken_at, moment, context)
    if taken_at is not None:
        earlier = await audited_read(
            session, DoseTaken, context, Scope.MEDICINES, where=(DoseTaken.line_id == line.id,)
        )
        for tap in earlier:
            same = tap.anchor == anchor and tap.by_person_id == context.person_id
            if same and as_utc(tap.taken_at) == tapped:
                return tap
    late = False
    if anchor is not None:
        his = await _his_day(session, context)
        zone = REGION_TZ[context.region]
        late = is_late(anchor, tapped.astimezone(zone), his)
    event = await audited_write(
        session,
        Event,
        context,
        Scope.MEDICINES,
        channel=channel,
        kind=EventKind.DOSE_TAKEN,
        occurred_at=tapped,
        source_channel=source_channel,
        label=f"taken: {line.generic}",
        artifact_id=None,
        episode_id=None,
        recorded_at=moment,
    )
    return await audited_write(
        session,
        DoseTaken,
        context,
        Scope.MEDICINES,
        channel=channel,
        line_id=line.id,
        event_id=event.id,
        anchor=anchor,
        amount=amount if amount is not None else dose.amount,
        taken_at=tapped,
        late=late,
        by_person_id=context.person_id,
    )


TAP_CLOCK_SKEW = timedelta(minutes=2)
"""How far ahead of the backend's clock a phone's clock may run and its tap still be now."""


class TapNotToday(Refusal):
    """A tap the phone held while it could not reach Nura is written at the moment he made it,
    and only when that moment is today on the region's clock: yesterday's tap is not today's
    tablet. The phone drops a held tap at midnight; this is the backend's own guard."""


def _tap_moment(taken_at: datetime, now: datetime, context: KeyContext) -> datetime:
    """The moment of a held tap, in UTC, as the phone wrote it: today on the region's clock, and
    not later than now beyond a phone's clock running a little ahead. Kept exactly as sent, so
    the same tap sent again matches the row it wrote."""
    tapped = as_utc(taken_at).astimezone(UTC)
    zone = REGION_TZ[context.region]
    if tapped > now + TAP_CLOCK_SKEW or tapped.astimezone(zone).date() != now.astimezone(zone).date():
        raise TapNotToday(f"a tap at {tapped.isoformat()} is not today's")
    return tapped


# --- the list, the count, the flags ---------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Count:
    remaining: float
    unit: str
    dispensed: float
    taken: float
    daily_amount: float | None
    days_left: int | None
    reorder_date: date | None
    reorder_due: bool
    lead_time_days: int
    basis: str
    """`taps` when the count rests on dispensed quantity minus Taken taps; `none` when nothing
    was ever dispensed on this line, so there is no count to give."""
    lines: list[str]
    reorder: list[str]
    reorder_actions: dict[str, str]


@dataclass(frozen=True, slots=True)
class FlagView:
    flag: InteractionFlag
    other: MedicationLine
    question: list[str]


@dataclass(frozen=True, slots=True)
class LineView:
    line: MedicationLine
    name: str
    count: Count
    flags: list[FlagView]
    duplicate_of: list[uuid.UUID]
    doctor_question: list[str]
    taken_label: str
    due_now: bool = False
    """One of today's doses of this line is in its window and not yet tapped."""
    missed: bool = False
    """One of today's doses of this line has passed its window untapped."""
    source: str = ""
    """Where the line came from and on which day, in his words: the card's source line."""


async def _his_day(session: AsyncSession, context: KeyContext) -> Day:
    """His day for the dose windows: his settings' breakfast, his routine's other anchors."""
    # Imported here: the routine module reads the medicines, and the medicines read it.
    from app.routines.service import his_day

    return await his_day(session, context=context)


def today_in(context: KeyContext) -> date:
    return utcnow().astimezone(REGION_TZ[context.region]).date()


def now_in(context: KeyContext) -> datetime:
    return utcnow().astimezone(REGION_TZ[context.region])


def source_line(line: MedicationLine, zone: tzinfo, language: str) -> str:
    """The source line under a card that shows this medicine: the label he kept (a photo is
    behind the line) or what was typed in, and the day it started, in his language."""
    kind = "label" if line.source_artifact_id is not None else "typed"
    day = as_utc(line.started_at).astimezone(zone).date()
    return SOURCE[language][kind].format(date=say_date(day, language))


async def _taps_by_generic(
    session: AsyncSession, *, context: KeyContext
) -> tuple[dict[uuid.UUID, str], list[DoseTaken]]:
    """Every tap on every line of the profile, superseded lines included, with the generic
    each line is: a tap belongs to the medicine, not to the version of the line."""
    every = await audited_read(session, MedicationLine, context, Scope.MEDICINES)
    generic_of = {each.id: each.generic for each in every}
    taken = await audited_read(
        session,
        DoseTaken,
        context,
        Scope.MEDICINES,
        where=(DoseTaken.line_id.in_(list(generic_of)),),
    )
    return generic_of, list(taken)


def _tapped(
    anchor: str, generic: str, today_taps: Sequence[DoseTaken], generic_of: dict[uuid.UUID, str]
) -> bool:
    return any(
        generic_of.get(t.line_id) == generic and (t.anchor == anchor or t.anchor is None)
        for t in today_taps
    )


def _tapped_late(
    anchor: str, generic: str, today_taps: Sequence[DoseTaken], generic_of: dict[uuid.UUID, str]
) -> bool:
    """Whether the tap this anchor shows as taken (#198) was itself a late one — his trends
    and the card read this instead of comparing `taken_at` to the window again themselves."""
    return any(
        generic_of.get(t.line_id) == generic
        and (t.anchor == anchor or t.anchor is None)
        and t.late
        for t in today_taps
    )


def count_for(
    *,
    line: MedicationLine,
    supplies: Sequence[Supply],
    taken: Sequence[DoseTaken],
    today: date,
    name: str,
    language: str,
) -> Count:
    dose = Dose.from_json(line.dose)
    dispensed = float(sum(s.quantity for s in supplies))
    used = float(sum(t.amount for t in taken))
    remaining = arithmetic.count_remaining(dispensed, used)
    left = arithmetic.days_left(remaining, dose)
    due_on = arithmetic.reorder_date(today, remaining, dose, line.lead_time_days)
    due = arithmetic.reorder_due(remaining, dose, line.reorder_threshold_days)
    basis = "taps" if supplies else "none"
    return Count(
        remaining=remaining,
        unit=dose.unit,
        dispensed=dispensed,
        taken=used,
        daily_amount=arithmetic.daily_amount(dose),
        days_left=left,
        reorder_date=due_on,
        reorder_due=bool(supplies) and due,
        lead_time_days=line.lead_time_days,
        basis=basis,
        lines=(
            count_lines(
                name=name, remaining=remaining, unit=dose.unit, days=left, language=language
            )
            if supplies
            else []
        ),
        reorder=(
            reorder_lines(name=name, runs_out=today + timedelta(days=left), language=language)
            if supplies and due and left is not None
            else []
        ),
        reorder_actions=dict(REORDER_ACTIONS[language]) if supplies and due else {},
    )


async def language_for(session: AsyncSession, context: KeyContext, asked: str | None) -> str:
    if asked is not None:
        return language_of(asked)
    profile = await audited_profile_read(session, context)
    return language_of(profile.language)


def _names(registry: DrugRegistry, generics: Sequence[str], language: str) -> dict[str, str]:
    return {g: PLAIN_NAME[language][registry.monograph(g).plain_name_id] for g in generics}


@audited(Action.READ, Scope.MEDICINES, LINE)
async def active_lines(
    session: AsyncSession,
    *,
    context: KeyContext,
    registry: DrugRegistry,
    language: str | None = None,
) -> list[LineView]:
    """The reconciled list: each active line with its source, its count, its flags rendered
    as questions for the doctor, and the other active lines of the same generic (two
    strengths in the cupboard) named as duplicates."""
    lang = await language_for(session, context, language)
    lines = await _active_lines(session, context=context)
    if not lines:
        return []
    ids = [line.id for line in lines]
    supplies = await audited_read(
        session, Supply, context, Scope.MEDICINES, where=(Supply.line_id.in_(ids),)
    )
    taken = await audited_read(
        session, DoseTaken, context, Scope.MEDICINES, where=(DoseTaken.line_id.in_(ids),)
    )
    flags = await audited_read(
        session,
        InteractionFlag,
        context,
        Scope.MEDICINES,
        where=(InteractionFlag.line_id.in_(ids),),
    )
    by_id = {line.id: line for line in lines}
    names = _names(registry, sorted({line.generic for line in lines}), lang)
    today = today_in(context)
    now = now_in(context)
    day = await _his_day(session, context)
    generic_of, every_tap = await _taps_by_generic(session, context=context)
    zone = REGION_TZ[context.region]
    today_taps = [t for t in every_tap if as_utc(t.taken_at).astimezone(zone).date() == today]
    views: list[LineView] = []
    for line in lines:
        name = names[line.generic]
        own_flags = [
            FlagView(
                flag=flag,
                other=by_id[flag.other_line_id],
                question=interaction_question(
                    Interaction(
                        (line.generic, by_id[flag.other_line_id].generic),
                        flag.severity,
                        flag.text_id,
                        source=flag.source,
                        review_state=(
                            ReviewState.AWAITING_REVIEW
                            if flag.awaiting_review
                            else ReviewState.REVIEWED
                        ),
                    ),
                    names=names,
                    prescriber=line.prescriber,
                    language=lang,
                ),
            )
            for flag in flags
            if flag.line_id == line.id and flag.other_line_id in by_id
        ]
        views.append(
            LineView(
                line=line,
                name=name,
                count=count_for(
                    line=line,
                    supplies=[s for s in supplies if s.line_id == line.id],
                    taken=[t for t in taken if t.line_id == line.id],
                    today=today,
                    name=name,
                    language=lang,
                ),
                flags=own_flags,
                duplicate_of=[o.id for o in lines if o.generic == line.generic and o.id != line.id],
                doctor_question=(
                    medication_story(
                        generic=line.generic,
                        strength=line.strength,
                        dose=Dose.from_json(line.dose),
                        prescriber=line.prescriber,
                        change_kind=line.change_kind,
                        monograph=registry.monograph(line.generic),
                        language=lang,
                    ).doctor_question
                ),
                taken_label=TAKEN[lang],
                source=source_line(line, zone, lang),
                due_now=any(
                    window_status(a, now, _tapped(a.value, line.generic, today_taps, generic_of), day)[0]
                    for a in Dose.from_json(line.dose).scheduled_anchors
                ),
                missed=any(
                    window_status(a, now, _tapped(a.value, line.generic, today_taps, generic_of), day)[1]
                    for a in Dose.from_json(line.dose).scheduled_anchors
                ),
            )
        )
    return views


@audited(Action.READ, Scope.MEDICINES, LINE)
async def history(session: AsyncSession, *, context: KeyContext) -> list[MedicationLine]:
    """Every line ever written, superseded ones included, oldest first: the change log."""
    found = await audited_read(session, MedicationLine, context, Scope.MEDICINES)
    return sorted(found, key=lambda line: (as_utc(line.asserted_at), line.generic))


@audited(Action.READ, Scope.MEDICINES, InteractionFlag.__tablename__)
async def interaction_flags(
    session: AsyncSession,
    *,
    context: KeyContext,
    registry: DrugRegistry,
    language: str | None = None,
) -> list[FlagView]:
    """Every flag on an active line, worst first, as questions for the doctor."""
    views = await active_lines(session, context=context, registry=registry, language=language)
    order = {"major": 0, "moderate": 1, "minor": 2, "duplicate": 3}
    return sorted(
        (flag for view in views for flag in view.flags),
        key=lambda f: (order[f.flag.severity.value], f.other.generic),
    )


@audited(Action.READ, Scope.MEDICINES, LINE)
async def story(
    session: AsyncSession,
    *,
    context: KeyContext,
    registry: DrugRegistry,
    line_id: uuid.UUID,
    language: str | None = None,
) -> Story:
    """The story of one active line, in the language asked for or the profile's own."""
    line = await _require_line(session, context=context, line_id=line_id)
    lang = await language_for(session, context, language)
    return medication_story(
        generic=line.generic,
        strength=line.strength,
        dose=Dose.from_json(line.dose),
        prescriber=line.prescriber,
        change_kind=line.change_kind,
        monograph=registry.monograph(line.generic),
        language=lang,
    )


@dataclass(frozen=True, slots=True)
class Slot:
    """One dose card at one anchor of his day: the line, the moment, whether it was taken,
    whether its window is open now, whether it has passed untapped — and, for that case,
    the story's own missed-dose lines (E04-07), so no client composes what to do."""

    line: MedicationLine
    anchor: str
    card: str
    taken: bool
    taken_label: str
    due_now: bool = False
    missed: bool = False
    if_forgotten: list[str] = field(default_factory=list)
    source: str = ""
    taken_late: bool = False
    """The tap that took this dose came in after its window had closed (#198): still taken,
    written down late. False when not taken at all."""


@audited(Action.READ, Scope.MEDICINES, LINE)
async def today(
    session: AsyncSession,
    *,
    context: KeyContext,
    registry: DrugRegistry,
    language: str | None = None,
) -> list[Slot]:
    """Today's doses as cards at breakfast, lunch, dinner and bed, with what was tapped."""
    lang = await language_for(session, context, language)
    lines = await _active_lines(session, context=context)
    if not lines:
        return []
    day = today_in(context)
    now = now_in(context)
    his = await _his_day(session, context)
    zone = REGION_TZ[context.region]
    # A tap belongs to the medicine, not to the version of the line: a dose change this
    # afternoon does not undo the tablet he took this morning. So taps are gathered over
    # every line of each generic, superseded ones included, and matched by generic.
    generic_of, taken = await _taps_by_generic(session, context=context)
    today_taps = [t for t in taken if as_utc(t.taken_at).astimezone(zone).date() == day]
    names = _names(registry, sorted({line.generic for line in lines}), lang)
    order = [a.value for a in arithmetic.Anchor]
    slots: list[Slot] = []
    for line in lines:
        dose = Dose.from_json(line.dose)
        if dose.frequency is arithmetic.Frequency.WEEKLY and any(
            as_utc(t.taken_at).astimezone(zone).date() > day - timedelta(days=7)
            for t in taken
            if generic_of.get(t.line_id) == line.generic
        ):
            continue
        forgotten = medication_story(
            generic=line.generic,
            strength=line.strength,
            dose=dose,
            prescriber=line.prescriber,
            change_kind=line.change_kind,
            monograph=registry.monograph(line.generic),
            language=lang,
        ).if_forgotten
        for anchor in dose.scheduled_anchors:
            tapped = _tapped(anchor.value, line.generic, today_taps, generic_of)
            due_now, missed = window_status(anchor, now, tapped, his)
            slots.append(
                Slot(
                    line=line,
                    anchor=anchor.value,
                    card=dose_card_line(
                        name=names[line.generic], dose=dose, anchor=anchor.value, language=lang
                    ),
                    taken=tapped,
                    taken_label=TAKEN[lang],
                    due_now=due_now,
                    missed=missed,
                    if_forgotten=list(forgotten) if missed else [],
                    source=source_line(line, zone, lang),
                    taken_late=tapped
                    and _tapped_late(anchor.value, line.generic, today_taps, generic_of),
                )
            )
    return sorted(slots, key=lambda s: (order.index(s.anchor), s.line.generic))


@dataclass(frozen=True, slots=True)
class Proud:
    """The proud number: how many days of his have a tablet taken on them."""

    days: int
    as_of: datetime


@audited(Action.READ, Scope.MEDICINES, Event.__tablename__)
async def proud_days(session: AsyncSession, *, context: KeyContext) -> Proud:
    """Distinct local days with any DOSE_TAKEN event on the profile, from the memory events
    under the medicines scope, in one audited read — never the audit trail. The days he took
    his tablets, whoever tapped Taken: a helper's "given" is his tablet taken. It is a count
    of days, not a streak: a quiet day takes nothing away, and it never goes down on the same
    record."""
    zone = REGION_TZ[context.region]
    events = await audited_read(
        session, Event, context, Scope.MEDICINES, where=(Event.kind == EventKind.DOSE_TAKEN,)
    )
    days = {as_utc(event.occurred_at).astimezone(zone).date() for event in events}
    return Proud(days=len(days), as_of=utcnow())


__all__ = [
    "AlreadyRecorded",
    "Count",
    "FlagView",
    "Label",
    "LineView",
    "NoSuchLine",
    "NotTheirsToChange",
    "Outcome",
    "Plan",
    "Proud",
    "Reconciled",
    "Slot",
    "active_lines",
    "draft_for",
    "history",
    "interaction_flags",
    "language_for",
    "may_change_medicines",
    "plan",
    "reconcile",
    "record_dose_taken",
    "story",
    "today",
]
