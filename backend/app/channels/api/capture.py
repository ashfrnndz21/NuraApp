"""Capture over HTTP: a photo in, a review card out, facts on the person's yes (E02-01, E02-07).

    POST /profiles/{id}/photos                        store the photo, read it, answer the card
    GET  /profiles/{id}/review-cards                  the profile's cards, newest first
    GET  /profiles/{id}/review-cards/{card_id}        one card with its fields
    POST /profiles/{id}/review-cards/{card_id}/confirm  close it with the yes minted for it
    GET  /profiles/{id}/facts?subject=                the current facts, by subject

Every route takes the key context like every other profile route. Photos and cards are read
and written under the record's scope; a fact a card writes is held under its own subject's
scope — a medicine's under the medicines scope — so a key to the record alone cannot confirm
a label. The yes is minted at `POST /profiles/{id}/confirmations` with subject `review_card`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Request, status

from app.audit.access import audited_profile_read
from app.channels.api.deps import Context, Db, providers_of
from app.channels.api.schemas import (
    FactOut,
    PhotoIn,
    ReviewCardOut,
    ReviewConfirmedOut,
    ReviewConfirmIn,
)
from app.ingestion.photos import store_photo
from app.ingestion.review import (
    card_fields,
    confirm_review_card,
    list_review_cards,
    require_review_card,
    review_photo,
)
from app.memory.models import SourceChannel
from app.memory.semantic import current_facts

router = APIRouter(prefix="/profiles", tags=["capture"])


@router.post("/{profile_id}/photos", status_code=status.HTTP_201_CREATED)
async def add_photo(
    body: PhotoIn, request: Request, context: Context, session: Db
) -> ReviewCardOut:
    """A photo of a page: its bytes go to the region's store, one Artifact names them, the
    extractor reads it, and the answer is the review card — every field with its confidence,
    the ones below the threshold marked `needs_confirm`. Nothing is a fact yet."""
    providers = providers_of(request)
    artifact = await store_photo(
        session,
        context=context,
        store=providers.object_store,
        data=body.as_bytes(),
        content_type=body.content_type,
        captured_at=body.captured_at,
        source_channel=SourceChannel.APP,
    )
    card = await review_photo(
        session,
        context=context,
        artifact_id=artifact.id,
        store=providers.object_store,
        extractor=providers.extractor,
        # The profile's language is what tells the extractor which words to expect on the
        # page; read under the profile scope every key holds.
        language=(await audited_profile_read(session, context)).language,
    )
    return ReviewCardOut.of(card, await card_fields(session, context=context, card_id=card.id))


@router.get("/{profile_id}/review-cards")
async def review_cards(
    context: Context,
    session: Db,
    open_only: bool = Query(default=False, alias="open"),
) -> list[ReviewCardOut]:
    """The profile's review cards, newest first, each with its fields; `?open=true` for the
    ones still waiting for a yes. Read under the record's scope."""
    cards = await list_review_cards(session, context=context, open_only=open_only)
    return [
        ReviewCardOut.of(card, await card_fields(session, context=context, card_id=card.id))
        for card in cards
    ]


@router.get("/{profile_id}/review-cards/{card_id}")
async def review_card(card_id: uuid.UUID, context: Context, session: Db) -> ReviewCardOut:
    card = await require_review_card(session, context=context, card_id=card_id)
    return ReviewCardOut.of(card, await card_fields(session, context=context, card_id=card.id))


@router.post("/{profile_id}/review-cards/{card_id}/confirm")
async def confirm_card(
    card_id: uuid.UUID, body: ReviewConfirmIn, context: Context, session: Db
) -> ReviewConfirmedOut:
    """Close the card on the yes minted for exactly these decisions. Each confirmed or
    corrected field becomes a fact with the photo as provenance and the caller as its
    confirmer; a rejected one writes nothing; State recomputes as each lands. A yes for
    other decisions is `NotWhatWasConfirmed` (400); a card already closed is
    `AlreadyConfirmed` (409)."""
    card, fields, facts = await confirm_review_card(
        session,
        context=context,
        card_id=card_id,
        decisions=[decision.as_decision() for decision in body.decisions],
        confirmation_id=body.confirmation_id,
    )
    return ReviewConfirmedOut(
        card=ReviewCardOut.of(card, fields), facts=[FactOut.of(fact) for fact in facts]
    )


@router.get("/{profile_id}/facts")
async def facts(
    context: Context,
    session: Db,
    subject: str | None = Query(default=None, min_length=1, max_length=64),
) -> list[FactOut]:
    """The facts that hold now, with provenance and confirmer, narrowed to one subject. The
    scope is the subject's (`app.keys.scopes.scope_for_subject`): medicines under the
    medicines scope, readings under the readings scope, everything else — or all of it,
    with no subject — under the record's."""
    found = await current_facts(session, context=context, subject=subject)
    return [FactOut.of(fact) for fact in found]
