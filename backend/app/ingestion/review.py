"""The review card: from a photo's extraction to a person's yes to facts with provenance.

`review_photo` reads the stored bytes back through the store, runs the extractor, and writes
one card with one field per extracted statement. `confirm_review_card` is the other end: the
person's decisions, bound to a confirmation he minted for exactly them, close the card and
write one Fact per confirmed or corrected field — with the photo as provenance, the person
as confirmer, the unit, and a validity window opening on the date on the paper. A rejected
field writes nothing. State recomputes as each fact lands, through the memory store's hook.

One yes, many facts. The person's tap is a confirmation over the whole card
(`app.drafts.ReviewDraft`): every field and his decision on it. A fact needs a yes of its
own to be CONFIRMED_BY_PERSON, so once the card's yes is spent each fact's yes is written
down and used in the same unit of work, from the same person, for exactly the fact being
written — the way the readings route writes the yes for the number a person typed. The
card's yes is the evidence; the per-fact yes is how the store records who gave it.

What else a card may be (E02-02, E02-03, E02-08). A page is offered with a hint — the kind
the person says it is, or the route's, a machine's screen — and the card keeps it
(`asked_as`) beside what the page was read as; a page that is no health paper, or a photo
sent as a machine's screen that is not one, is an open card with no fields and a notice
(`notice_of`) saying so. A field Nura could not read is typed in — by anyone holding the
record, before the yes (`type_field`) — or rejected; it is never confirmed as read
(`UnreadableField`), and the field names who typed it. A card from a machine's screen is
written as one READING event and the facts of the reading (`app.ingestion.readings`); a
hospital letter or a clinic slip is written as the event it records — a discharge, a visit —
on the date on the paper, and its facts name that event beside the page.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, time
from enum import StrEnum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_read, audited_write
from app.audit.models import Action
from app.audit.trail import record
from app.db import as_utc, utcnow
from app.drafts import DecidedField, FactDraft, ReviewDraft
from app.errors import Refusal
from app.ingestion.extract import DocumentKind, Extraction, Extractor, Hints, check_value
from app.ingestion.models import (
    DECISIONS,
    REVIEW_IN_PROGRESS,
    DocumentSource,
    FieldState,
    ReviewCard,
    ReviewField,
)
from app.ingestion.objects import ObjectStore
from app.ingestion.readings import reading_from
from app.keys.confirm import confirm, consume_confirmation
from app.keys.context import KeyContext
from app.keys.repository import scoped_select
from app.keys.scopes import Scope
from app.memory.attach import attach_from_ingestion
from app.memory.episodic import held_here, record_event, require_artifact
from app.memory.models import Artifact, ConfidenceState, EventKind, Fact
from app.memory.semantic import assert_fact
from app.memory.working import require_open_episode
from app.regions import REGION_TZ
from app.safety.high_risk import high_risk_class

CARD = ReviewCard.__tablename__
FIELD = ReviewField.__tablename__
EXTERNAL_MODEL_PROCESSOR = "external_model_processor"
"""The audit target a reach outside the region is written under: a distinct target from
`CARD`/`FIELD`, so a reader of the trail can tell a page read by an external model processor
(e.g. `ClaudeExtractor.external_processor == "anthropic"`) apart from a fixture read, which
writes no such line at all (`review_artifact`)."""

MEDICINE_NAME = ("medicine", "name")
"""The field a label's drug is named in; what the high-risk lookup reads."""


class NoSuchReviewCard(Refusal):
    """No review card by that id on this profile."""


class NoSuchReviewField(Refusal):
    """A decision named a field that is not on this card."""


class AlreadyConfirmed(Refusal):
    """This card has been confirmed. What it wrote is facts now; a wrong one is superseded."""


class NotEveryFieldDecided(Refusal):
    """One tap saves the whole card, so every field needs a decision, and only one."""


class NotADecision(Refusal):
    """A field is confirmed, corrected or rejected. A correction says what to."""


class UnreadableField(Refusal):
    """A field Nura could not read is typed in, or rejected. It is never confirmed as read."""


class Notice(StrEnum):
    """What a card says about the page as a whole, where the page is not what it was offered
    as. The channel turns the code into his words (`app.channels.strings`)."""

    NOT_A_HEALTH_PAPER = "not_a_health_paper"
    NOT_A_MACHINE_SCREEN = "not_a_machine_screen"
    PHOTO_KIND_NOT_READ = "photo_kind_not_read"
    """A file of a kind the route accepted and this extractor never opened at all (E02-02):
    distinct from a page that was looked at and not made out, so the card does not ask for
    another photo of a kind that will fail again the same way."""


def notice_of(card: ReviewCard) -> Notice | None:
    """The notice a card carries, from what the page was read as and what it was offered as."""
    if card.document_kind is DocumentKind.NOT_HEALTH:
        return Notice.NOT_A_HEALTH_PAPER
    if card.document_kind is DocumentKind.UNSUPPORTED_FILE_TYPE:
        return Notice.PHOTO_KIND_NOT_READ
    if (
        card.asked_as is DocumentKind.DEVICE_SCREEN
        and card.document_kind is not DocumentKind.DEVICE_SCREEN
    ):
        return Notice.NOT_A_MACHINE_SCREEN
    return None


def _nothing_to_take(extraction: Extraction, asked_as: DocumentKind | None) -> bool:
    """A page no field may be taken from: not a health paper, or a photo sent as a machine's
    screen that is not one — its fields belong to another kind of card, not this one."""
    if extraction.document_kind is DocumentKind.NOT_HEALTH:
        return True
    return (
        asked_as is DocumentKind.DEVICE_SCREEN
        and extraction.document_kind is not DocumentKind.DEVICE_SCREEN
    )


DOCUMENT_EVENTS: Mapping[DocumentKind, tuple[EventKind, str]] = {
    DocumentKind.DISCHARGE_LETTER: (EventKind.DISCHARGE, "hospital letter"),
    DocumentKind.CLINIC_SLIP: (EventKind.VISIT, "clinic slip"),
}
"""The papers that record a moment, and the event each is written as on its date: the
discharge a hospital letter records, the visit a clinic slip was written at (E02-03)."""


@dataclass(frozen=True, slots=True)
class Decision:
    """What the person said about one field."""

    field_id: uuid.UUID
    decision: FieldState
    corrected_value: Any = None


def _cards_held_here(context: KeyContext) -> Any:
    """The cards whose photo is held in this region: part of every query returning cards, the
    way `fact_cites_only_what_is_held_here` is for facts."""
    return ReviewCard.artifact_id.in_(
        scoped_select(Artifact, context, Scope.RECORDS)
        .with_only_columns(Artifact.id)
        .where(held_here(context))
    )


@audited(Action.WRITE, Scope.RECORDS, CARD)
async def review_artifact(
    session: AsyncSession,
    *,
    context: KeyContext,
    artifact_id: uuid.UUID,
    store: ObjectStore,
    extractor: Extractor,
    language: str,
    asked_as: DocumentKind | None = None,
    source: DocumentSource | None = None,
) -> ReviewCard:
    """Read a stored photo or PDF into a review card: one field per extracted statement, the
    extractor's confidence on each, the kind and date of the paper, and — from the drug the
    card names — whether the label rule guards it. `asked_as` goes to the extractor as the
    hint and onto the card; `source` is where an imported PDF came from."""
    artifact = await require_artifact(session, context=context, artifact_id=artifact_id)
    data = await store.get(artifact.storage_key)
    if extractor.external_processor is not None:
        # Written before the call, in the same unit of work as the card: a reach that sends
        # the artefact's bytes outside the region is recorded whether or not the call that
        # follows succeeds, distinct from the CARD/FIELD writes below so a reader of the
        # trail can tell an external model processor's read apart from a fixture's.
        await record(
            session,
            context=context,
            action=Action.SHARE,
            scope=Scope.RECORDS,
            target=EXTERNAL_MODEL_PROCESSOR,
            target_id=artifact.id,
            rows=1,
            shared_with_label=extractor.external_processor,
        )
    extraction = await extractor.extract(
        data,
        artifact.content_type,
        Hints(language=language, region=context.region, expected=asked_as),
    )
    return await card_from(
        session,
        context=context,
        artifact=artifact,
        extraction=extraction,
        asked_as=asked_as,
        source=source,
    )


async def review_photo(
    session: AsyncSession,
    *,
    context: KeyContext,
    artifact_id: uuid.UUID,
    store: ObjectStore,
    extractor: Extractor,
    language: str,
    asked_as: DocumentKind | None = None,
) -> ReviewCard:
    """Read a stored photo into a review card (`review_artifact`)."""
    return await review_artifact(
        session,
        context=context,
        artifact_id=artifact_id,
        store=store,
        extractor=extractor,
        language=language,
        asked_as=asked_as,
    )


async def card_from(
    session: AsyncSession,
    *,
    context: KeyContext,
    artifact: Artifact,
    extraction: Extraction,
    asked_as: DocumentKind | None = None,
    source: DocumentSource | None = None,
) -> ReviewCard:
    """Write the card and its fields for an extraction of this artefact. Every field is
    checked (`ExtractedField.checked`) before it is written: codes are codes, values short.
    A page no field may be taken from (`_nothing_to_take`) is a card with no fields."""
    fields = [field.checked() for field in extraction.fields]
    if _nothing_to_take(extraction, asked_as):
        fields = []
    named = next(
        (field.value for field in fields if (field.subject, field.attribute) == MEDICINE_NAME),
        None,
    )
    card = await audited_write(
        session,
        ReviewCard,
        context,
        Scope.RECORDS,
        artifact_id=artifact.id,
        document_kind=extraction.document_kind,
        document_date=extraction.document_date,
        high_risk_class=high_risk_class(named if isinstance(named, str) else None),
        asked_as=asked_as,
        source=source,
        created_at=utcnow(),
    )
    for position, field in enumerate(fields):
        await audited_write(
            session,
            ReviewField,
            context,
            Scope.RECORDS,
            card_id=card.id,
            position=position,
            subject=field.subject,
            attribute=field.attribute,
            value=field.value,
            unit=field.unit,
            confidence=field.confidence,
            span=None if field.span is None else field.span.as_json(),
            state=FieldState.PROPOSED,
        )
    return card


@audited(Action.READ, Scope.RECORDS, CARD)
async def list_review_cards(
    session: AsyncSession, *, context: KeyContext, open_only: bool = False
) -> Sequence[ReviewCard]:
    """The profile's cards, newest first; with `open_only`, the ones still waiting."""
    where: list[Any] = [_cards_held_here(context)]
    if open_only:
        where.append(ReviewCard.confirmed_at.is_(None))
    found = await audited_read(session, ReviewCard, context, Scope.RECORDS, where=where)
    return sorted(found, key=lambda card: (as_utc(card.created_at), str(card.id)), reverse=True)


@audited(Action.READ, Scope.RECORDS, CARD)
async def require_review_card(
    session: AsyncSession, *, context: KeyContext, card_id: uuid.UUID
) -> ReviewCard:
    found = await audited_read(
        session,
        ReviewCard,
        context,
        Scope.RECORDS,
        where=(ReviewCard.id == card_id, _cards_held_here(context)),
    )
    if not found:
        raise NoSuchReviewCard(f"no review card {card_id} on profile {context.profile_id}")
    return found[0]


@audited(Action.READ, Scope.RECORDS, FIELD)
async def card_fields(
    session: AsyncSession, *, context: KeyContext, card_id: uuid.UUID
) -> Sequence[ReviewField]:
    """The fields of one card, in the order they were read off the page."""
    found = await audited_read(
        session, ReviewField, context, Scope.RECORDS, where=(ReviewField.card_id == card_id,)
    )
    return sorted(found, key=lambda field: field.position)


@audited(Action.WRITE, Scope.RECORDS, FIELD)
async def type_field(
    session: AsyncSession,
    *,
    context: KeyContext,
    card_id: uuid.UUID,
    field_id: uuid.UUID,
    value: Any,
) -> ReviewField:
    """Type in the value of one field on an open card: a field Nura could not read, or one
    it read wrong. Anyone holding the record may, before the card is confirmed — a daughter
    typing what her father's slip says — and the field names who did. The value read stays
    beside it; nothing is a fact until the card's yes, which binds to the typed value and to
    who typed it. Typing again replaces the typed value, and names the new typist."""
    card = await require_review_card(session, context=context, card_id=card_id)
    if not card.is_open:
        raise AlreadyConfirmed(f"review card {card_id} was confirmed at {card.confirmed_at}")
    fields = await card_fields(session, context=context, card_id=card_id)
    field = next((one for one in fields if one.id == field_id), None)
    if field is None:
        raise NoSuchReviewField(f"field {field_id} is not on this card")
    typed = check_value(value)
    session.info[REVIEW_IN_PROGRESS] = card.id
    try:
        field.corrected_value = typed
        field.corrected_by_person_id = context.person_id
        await session.flush()
        await record(
            session,
            context=context,
            action=Action.WRITE,
            scope=Scope.RECORDS,
            target=FIELD,
            target_id=field.id,
            rows=1,
        )
    finally:
        session.info.pop(REVIEW_IN_PROGRESS, None)
    return field


def _decided(
    fields: Sequence[ReviewField], decisions: Sequence[Decision], confirmer: uuid.UUID
) -> list[DecidedField]:
    """Every field with exactly one decision on it, or a refusal saying which rule broke.

    The value kept is the confirmer's correction where he made one; otherwise a value typed
    in before the yes, naming who typed it; otherwise what was read. A field Nura could not
    read and nobody typed is never confirmed as read (`UnreadableField`)."""
    by_id = {field.id: field for field in fields}
    said: dict[uuid.UUID, Decision] = {}
    for decision in decisions:
        if decision.field_id not in by_id:
            raise NoSuchReviewField(f"field {decision.field_id} is not on this card")
        if decision.field_id in said:
            raise NotEveryFieldDecided(f"field {decision.field_id} was decided twice")
        if decision.decision not in DECISIONS:
            raise NotADecision("a field is confirmed, corrected or rejected")
        if (decision.decision is FieldState.CORRECTED) != (decision.corrected_value is not None):
            raise NotADecision("a correction says what to, and nothing else does")
        said[decision.field_id] = decision
    missing = set(by_id) - set(said)
    if missing:
        raise NotEveryFieldDecided(f"{len(missing)} field(s) have no decision")
    decided = []
    for field in fields:
        decision = said[field.id]
        typed = field.corrected_value is not None
        corrected_by: uuid.UUID | None = None
        if decision.decision is FieldState.CORRECTED:
            value, corrected_by = decision.corrected_value, confirmer
        elif decision.decision is FieldState.CONFIRMED and typed:
            value, corrected_by = field.corrected_value, field.corrected_by_person_id
        elif decision.decision is FieldState.CONFIRMED and field.unreadable:
            raise UnreadableField(f"field {field.id} could not be read and was not typed in")
        else:
            value = field.value
        decided.append(
            DecidedField(
                field_id=field.id,
                subject=field.subject,
                attribute=field.attribute,
                value=value,
                unit=field.unit,
                decision=decision.decision.value,
                corrected_by=corrected_by,
            )
        )
    return decided


@audited(Action.READ, Scope.RECORDS, CARD)
async def review_draft_for(
    session: AsyncSession,
    *,
    context: KeyContext,
    card_id: uuid.UUID,
    decisions: Sequence[Decision],
    episode_id: uuid.UUID | None = None,
) -> ReviewDraft:
    """What the person is saying yes to: this card, its photo, every field with his
    decision — and, when he named one, the open episode the card goes into (E03-02). The
    surface mints the confirmation over this; the confirm recomputes it."""
    card = await require_review_card(session, context=context, card_id=card_id)
    if not card.is_open:
        raise AlreadyConfirmed(f"review card {card_id} was confirmed at {card.confirmed_at}")
    fields = await card_fields(session, context=context, card_id=card_id)
    return ReviewDraft(
        card_id=card.id,
        artifact_id=card.artifact_id,
        fields=tuple(_decided(fields, decisions, context.person_id)),
        episode_id=episode_id,
    )


def _opens_at(card: ReviewCard, artifact: Artifact, context: KeyContext) -> datetime:
    """When the facts start holding: the day on the paper, on the patient's clock, or the
    moment the photo was taken when the paper has no date."""
    if card.document_date is None:
        return as_utc(artifact.captured_at)
    midnight = datetime.combine(card.document_date, time.min, tzinfo=REGION_TZ[context.region])
    return midnight.astimezone(UTC)


async def _write_fact_for(
    session: AsyncSession,
    *,
    context: KeyContext,
    card: ReviewCard,
    subject: str,
    attribute: str,
    value: Any,
    unit: str | None,
    event_id: uuid.UUID | None,
    valid_from: datetime,
    episode_id: uuid.UUID | None = None,
) -> Fact:
    draft = FactDraft(
        subject=subject,
        attribute=attribute,
        value=value,
        unit=unit,
        confidence=1.0,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
        artifact_id=card.artifact_id,
        event_id=event_id,
        episode_id=episode_id,
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
        event_id=draft.event_id,
        episode_id=draft.episode_id,
        valid_from=valid_from,
    )


@audited(Action.WRITE, Scope.RECORDS, CARD)
async def confirm_review_card(
    session: AsyncSession,
    *,
    context: KeyContext,
    card_id: uuid.UUID,
    decisions: Sequence[Decision],
    confirmation_id: uuid.UUID,
    episode_id: uuid.UUID | None = None,
) -> tuple[ReviewCard, Sequence[ReviewField], Sequence[Fact]]:
    """Close the card on the person's yes and write the facts it decided.

    The yes must be for exactly these decisions on exactly this card (`ReviewDraft`); a
    decision changed since is `NotWhatWasConfirmed`. Then, field by field: a confirmed or
    corrected field becomes a Fact — the photo as provenance, CONFIRMED_BY_PERSON naming
    the confirmer, the unit, valid from the date on the paper — and the field names it; a
    rejected field is marked and writes nothing. A rule under the store (the label rule for
    a high-risk dose) that refuses one fact refuses the whole card: the channel rolls the
    unit back, yes included. The card closes last, naming who confirmed it and when.

    A machine's screen is written as one READING event at the time on the screen and the
    facts of the reading resting on it (`_write_reading`); a hospital letter or a clinic slip
    as the event it records, on the date on the paper, which its facts name beside the page.
    A value typed in before the yes, or corrected in it, leaves the field CORRECTED and
    naming who typed it.

    With `episode_id` the yes was for the card going into that open episode: the event and
    each fact name the episode, and the photo hangs off it (`attach_from_ingestion`, E03-02)
    under the same yes — the automatic way a paper joins the concern it belongs to.
    """
    draft = await review_draft_for(
        session, context=context, card_id=card_id, decisions=decisions, episode_id=episode_id
    )
    if episode_id is not None:
        await require_open_episode(session, context=context, episode_id=episode_id)
    card = await require_review_card(session, context=context, card_id=card_id)
    artifact = await require_artifact(session, context=context, artifact_id=card.artifact_id)
    fields = await card_fields(session, context=context, card_id=card_id)
    yes = await consume_confirmation(session, context, confirmation_id, draft)

    moment = utcnow()
    by_id = {decided.field_id: decided for decided in draft.fields}
    session.info[REVIEW_IN_PROGRESS] = card.id
    try:
        if card.document_kind is DocumentKind.DEVICE_SCREEN:
            fact_of = await _write_reading(
                session,
                context=context,
                card=card,
                artifact=artifact,
                draft=draft,
                now=moment,
                episode_id=episode_id,
            )
        else:
            fact_of = await _write_paper(
                session,
                context=context,
                card=card,
                artifact=artifact,
                draft=draft,
                episode_id=episode_id,
            )
        written = list(dict.fromkeys(fact_of.values()))
        for field in fields:
            decided = by_id[field.id]
            said = FieldState(decided.decision)
            kept = said is not FieldState.REJECTED
            fact = fact_of.get(field.id)
            if fact is not None:
                field.fact_id = fact.id
            if kept and decided.corrected_by is not None:
                field.corrected_value = decided.value
                field.corrected_by_person_id = decided.corrected_by
            field.state = FieldState.CORRECTED if kept and decided.corrected_by else said
            field.decided_at = moment
            await session.flush()
            await record(
                session,
                context=context,
                action=Action.WRITE,
                scope=Scope.RECORDS,
                target=FIELD,
                target_id=field.id,
                rows=1,
            )
        card.confirmed_at = moment
        card.confirmed_by_person_id = yes.person_id
        await session.flush()
        await record(
            session,
            context=context,
            action=Action.WRITE,
            scope=Scope.RECORDS,
            target=CARD,
            target_id=card.id,
            rows=1,
        )
    finally:
        session.info.pop(REVIEW_IN_PROGRESS, None)
    if episode_id is not None:
        await attach_from_ingestion(
            session,
            context=context,
            artifact_id=card.artifact_id,
            episode_id=episode_id,
            by_person_id=yes.person_id,
        )
    return card, fields, written


async def _write_paper(
    session: AsyncSession,
    *,
    context: KeyContext,
    card: ReviewCard,
    artifact: Artifact,
    draft: ReviewDraft,
    episode_id: uuid.UUID | None = None,
) -> dict[uuid.UUID, Fact]:
    """One fact per kept field, valid from the date on the paper; for a paper that records a
    moment (`DOCUMENT_EVENTS`), the event first, on that date, and every fact names it."""
    opens = _opens_at(card, artifact, context)
    kept = [decided for decided in draft.fields if decided.decision != FieldState.REJECTED]
    event_id: uuid.UUID | None = None
    shape = DOCUMENT_EVENTS.get(card.document_kind)
    if shape is not None and kept:
        kind, label = shape
        event = await record_event(
            session,
            context=context,
            kind=kind,
            occurred_at=opens,
            label=label,
            artifact_id=artifact.id,
            episode_id=episode_id,
        )
        event_id = event.id
    fact_of: dict[uuid.UUID, Fact] = {}
    for decided in kept:
        fact_of[decided.field_id] = await _write_fact_for(
            session,
            context=context,
            card=card,
            subject=decided.subject,
            attribute=decided.attribute,
            value=decided.value,
            unit=decided.unit,
            event_id=event_id,
            valid_from=opens,
            episode_id=episode_id,
        )
    return fact_of


async def _write_reading(
    session: AsyncSession,
    *,
    context: KeyContext,
    card: ReviewCard,
    artifact: Artifact,
    draft: ReviewDraft,
    now: datetime,
    episode_id: uuid.UUID | None = None,
) -> dict[uuid.UUID, Fact]:
    """A machine's screen: one READING event at the time on the screen — or when the photo
    was taken, if that was rejected — and the facts of the reading, each naming the event
    and the photo, in the shape a typed reading takes. Every number rejected writes nothing."""
    reading = reading_from(draft.fields, tz=REGION_TZ[context.region], now=now)
    if not reading.facts:
        return {}
    taken_at = reading.taken_at or as_utc(artifact.captured_at)
    event = await record_event(
        session,
        context=context,
        kind=EventKind.READING,
        occurred_at=taken_at,
        label=reading.label,
        artifact_id=artifact.id,
        episode_id=episode_id,
    )
    fact_of: dict[uuid.UUID, Fact] = {}
    for measured in reading.facts:
        fact = await _write_fact_for(
            session,
            context=context,
            card=card,
            subject=measured.subject,
            attribute=measured.attribute,
            value=measured.value,
            unit=measured.unit,
            event_id=event.id,
            valid_from=taken_at,
            episode_id=episode_id,
        )
        for field_id in measured.field_ids:
            fact_of[field_id] = fact
    return fact_of
