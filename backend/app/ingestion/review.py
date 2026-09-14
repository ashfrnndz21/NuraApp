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
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_read, audited_write
from app.audit.models import Action
from app.audit.trail import record
from app.db import as_utc, utcnow
from app.drafts import DecidedField, FactDraft, ReviewDraft
from app.errors import Refusal
from app.ingestion.extract import Extraction, Extractor, Hints
from app.ingestion.models import (
    DECISIONS,
    REVIEW_IN_PROGRESS,
    FieldState,
    ReviewCard,
    ReviewField,
)
from app.ingestion.objects import ObjectStore
from app.keys.confirm import confirm, consume_confirmation
from app.keys.context import KeyContext
from app.keys.repository import scoped_select
from app.keys.scopes import Scope
from app.memory.episodic import held_here, require_artifact
from app.memory.models import Artifact, ConfidenceState, Fact
from app.memory.semantic import assert_fact
from app.regions import REGION_TZ
from app.safety.high_risk import high_risk_class

CARD = ReviewCard.__tablename__
FIELD = ReviewField.__tablename__

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
async def review_photo(
    session: AsyncSession,
    *,
    context: KeyContext,
    artifact_id: uuid.UUID,
    store: ObjectStore,
    extractor: Extractor,
    language: str,
) -> ReviewCard:
    """Read a stored photo into a review card: one field per extracted statement, the
    extractor's confidence on each, the kind and date of the paper, and — from the drug the
    card names — whether the label rule guards it."""
    artifact = await require_artifact(session, context=context, artifact_id=artifact_id)
    data = await store.get(artifact.storage_key)
    extraction = await extractor.extract(
        data, artifact.content_type, Hints(language=language, region=context.region)
    )
    return await card_from(session, context=context, artifact=artifact, extraction=extraction)


async def card_from(
    session: AsyncSession,
    *,
    context: KeyContext,
    artifact: Artifact,
    extraction: Extraction,
) -> ReviewCard:
    """Write the card and its fields for an extraction of this artefact. Every field is
    checked (`ExtractedField.checked`) before it is written: codes are codes, values short."""
    fields = [field.checked() for field in extraction.fields]
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


def _decided(fields: Sequence[ReviewField], decisions: Sequence[Decision]) -> list[DecidedField]:
    """Every field with exactly one decision on it, or a refusal saying which rule broke."""
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
        value = (
            decision.corrected_value if decision.decision is FieldState.CORRECTED else field.value
        )
        decided.append(
            DecidedField(
                field_id=field.id,
                subject=field.subject,
                attribute=field.attribute,
                value=value,
                unit=field.unit,
                decision=decision.decision.value,
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
) -> ReviewDraft:
    """What the person is saying yes to: this card, its photo, every field with his
    decision. The surface mints the confirmation over this; the confirm recomputes it."""
    card = await require_review_card(session, context=context, card_id=card_id)
    if not card.is_open:
        raise AlreadyConfirmed(f"review card {card_id} was confirmed at {card.confirmed_at}")
    fields = await card_fields(session, context=context, card_id=card_id)
    return ReviewDraft(
        card_id=card.id,
        artifact_id=card.artifact_id,
        fields=tuple(_decided(fields, decisions)),
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
    field: ReviewField,
    value: Any,
    valid_from: datetime,
) -> Fact:
    draft = FactDraft(
        subject=field.subject,
        attribute=field.attribute,
        value=value,
        unit=field.unit,
        confidence=1.0,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
        artifact_id=card.artifact_id,
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
) -> tuple[ReviewCard, Sequence[ReviewField], Sequence[Fact]]:
    """Close the card on the person's yes and write the facts it decided.

    The yes must be for exactly these decisions on exactly this card (`ReviewDraft`); a
    decision changed since is `NotWhatWasConfirmed`. Then, field by field: a confirmed or
    corrected field becomes a Fact — the photo as provenance, CONFIRMED_BY_PERSON naming
    the confirmer, the unit, valid from the date on the paper — and the field names it; a
    rejected field is marked and writes nothing. A rule under the store (the label rule for
    a high-risk dose) that refuses one fact refuses the whole card: the channel rolls the
    unit back, yes included. The card closes last, naming who confirmed it and when.
    """
    draft = await review_draft_for(session, context=context, card_id=card_id, decisions=decisions)
    card = await require_review_card(session, context=context, card_id=card_id)
    artifact = await require_artifact(session, context=context, artifact_id=card.artifact_id)
    fields = await card_fields(session, context=context, card_id=card_id)
    yes = await consume_confirmation(session, context, confirmation_id, draft)

    moment = utcnow()
    opens = _opens_at(card, artifact, context)
    by_id = {decided.field_id: decided for decided in draft.fields}
    written: list[Fact] = []
    session.info[REVIEW_IN_PROGRESS] = card.id
    try:
        for field in fields:
            decided = by_id[field.id]
            state = FieldState(decided.decision)
            if state is not FieldState.REJECTED:
                fact = await _write_fact_for(
                    session,
                    context=context,
                    card=card,
                    field=field,
                    value=decided.value,
                    valid_from=opens,
                )
                written.append(fact)
                field.fact_id = fact.id
            if state is FieldState.CORRECTED:
                field.corrected_value = decided.value
            field.state = state
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
    return card, fields, written
