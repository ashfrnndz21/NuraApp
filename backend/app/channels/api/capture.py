"""Capture over HTTP: paper in, review cards out, facts on the person's yes (E02).

    POST /profiles/{id}/photos                        a photo of a page, with the kind he says it is
    POST /profiles/{id}/imports                       a PDF from a portal, an email or a share
    POST /profiles/{id}/readings/photo                a photo of a machine's screen
    GET  /profiles/{id}/review-cards                  the profile's cards, newest first
    GET  /profiles/{id}/review-cards/{card_id}        one card with its fields
    POST /profiles/{id}/review-cards/{card_id}/fields/{field_id}/type
                                                      type in a field Nura could not read
    POST /profiles/{id}/review-cards/{card_id}/confirm  close it with the yes minted for it
    GET  /profiles/{id}/facts?subject=                the current facts, by subject
    POST /profiles/{id}/events/{event_id}/notes       a voice note or a scribble on an event
    GET  /profiles/{id}/events/{event_id}/notes       recall: the notes on it this key opens
    GET  /profiles/{id}/events/{event_id}/notes/{note_id}/content   hear or see it again

Every route takes the key context like every other profile route. Photos, PDFs and cards are
read and written under the record's scope; a fact a card writes is held under its own
subject's scope — a medicine's under the medicines scope, a reading's under the readings
scope — so a key to the record alone cannot confirm a label. A private note is under the
notes scope, a shared one under the record's. The yes is minted at
`POST /profiles/{id}/confirmations` with subject `review_card`.

`POST /profiles/{id}/documents` is the family's (E12-09): a paper behind a basis, tagged and
not read. A PDF to be read goes to `/imports`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_profile_read
from app.channels.api.deps import Context, Db, providers_of
from app.channels.api.schemas import (
    EventNoteIn,
    EventNoteOut,
    FactOut,
    ImportIn,
    PhotoIn,
    ReviewCardOut,
    ReviewConfirmedOut,
    ReviewConfirmIn,
    ScreenPhotoIn,
    TypedIn,
)
from app.ingestion.documents import store_pdf
from app.ingestion.extract import DocumentKind
from app.ingestion.models import NoteKind, ReviewCard
from app.ingestion.notes import add_scribble, add_voice_note, note_content, notes_for
from app.ingestion.photos import store_photo
from app.ingestion.review import (
    card_fields,
    confirm_review_card,
    list_review_cards,
    require_review_card,
    review_artifact,
    type_field,
)
from app.keys.context import KeyContext
from app.memory.models import SourceChannel
from app.memory.semantic import current_facts

router = APIRouter(prefix="/profiles", tags=["capture"])


async def _language(session: AsyncSession, context: KeyContext) -> str:
    """The profile's language: what tells the extractor which words to expect on the page
    and the transcriber which words to listen for. Read under the profile scope every key
    holds."""
    return (await audited_profile_read(session, context)).language


async def _card_out(session: AsyncSession, context: KeyContext, card: ReviewCard) -> ReviewCardOut:
    return ReviewCardOut.of(card, await card_fields(session, context=context, card_id=card.id))


@router.post("/{profile_id}/photos", status_code=status.HTTP_201_CREATED)
async def add_photo(
    body: PhotoIn, request: Request, context: Context, session: Db
) -> ReviewCardOut:
    """A photo of a page: its bytes go to the region's store, one Artifact names them, the
    extractor reads it — told, if he says, what kind of paper it is — and the answer is the
    review card: every field with its confidence, the ones below the threshold marked
    `needs_confirm`, and a field Nura could not read marked `unreadable` with the lines that
    ask for it. Nothing is a fact yet."""
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
    card = await review_artifact(
        session,
        context=context,
        artifact_id=artifact.id,
        store=providers.object_store,
        extractor=providers.extractor,
        language=await _language(session, context),
        asked_as=body.document_kind,
    )
    return await _card_out(session, context, card)


@router.post("/{profile_id}/imports", status_code=status.HTTP_201_CREATED)
async def import_pdf(
    body: ImportIn, request: Request, context: Context, session: Db
) -> ReviewCardOut:
    """A PDF from a portal, an email or a share (E02-03): checked (a PDF, not empty, not too
    big — `NotAPdf` 400, `PdfTooLarge` 413), kept in the region's store as a PDF artefact,
    read page by page with the kind he says it is as a hint, and answered with a review card
    whose fields say the page each was read on. A PDF that is not a health paper is an open
    card with no fields and a `notice` saying so."""
    providers = providers_of(request)
    artifact = await store_pdf(
        session,
        context=context,
        store=providers.object_store,
        data=body.as_bytes(),
        content_type=body.content_type,
        captured_at=body.captured_at,
    )
    card = await review_artifact(
        session,
        context=context,
        artifact_id=artifact.id,
        store=providers.object_store,
        extractor=providers.extractor,
        language=await _language(session, context),
        asked_as=body.document_kind,
        source=body.source,
    )
    return await _card_out(session, context, card)


@router.post("/{profile_id}/readings/photo", status_code=status.HTTP_201_CREATED)
async def add_screen_photo(
    body: ScreenPhotoIn, request: Request, context: Context, session: Db
) -> ReviewCardOut:
    """A photo of a machine's screen (E02-08): kept like any photo, read with the hint that
    it is a device screen, and answered with a review card — the numbers with their units,
    the kind of machine and the time on its screen, each with its confidence. Confirming it
    writes one reading event and its facts, in the shape `POST /readings` writes. A photo
    that is not a machine's screen is an open card with no fields and a `notice`."""
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
    card = await review_artifact(
        session,
        context=context,
        artifact_id=artifact.id,
        store=providers.object_store,
        extractor=providers.extractor,
        language=await _language(session, context),
        asked_as=DocumentKind.DEVICE_SCREEN,
    )
    return await _card_out(session, context, card)


@router.get("/{profile_id}/review-cards")
async def review_cards(
    context: Context,
    session: Db,
    open_only: bool = Query(default=False, alias="open"),
) -> list[ReviewCardOut]:
    """The profile's review cards, newest first, each with its fields; `?open=true` for the
    ones still waiting for a yes. Read under the record's scope."""
    cards = await list_review_cards(session, context=context, open_only=open_only)
    return [await _card_out(session, context, card) for card in cards]


@router.get("/{profile_id}/review-cards/{card_id}")
async def review_card(card_id: uuid.UUID, context: Context, session: Db) -> ReviewCardOut:
    card = await require_review_card(session, context=context, card_id=card_id)
    return await _card_out(session, context, card)


@router.post("/{profile_id}/review-cards/{card_id}/fields/{field_id}/type")
async def type_in(
    card_id: uuid.UUID, field_id: uuid.UUID, body: TypedIn, context: Context, session: Db
) -> ReviewCardOut:
    """Type in what the paper says for one field of an open card — the frequency Nura could
    not read off a clinic slip (E02-02). Anyone holding the record may, before the yes; the
    field names who typed it, and the value read stays beside it. Nothing is a fact until
    the card is confirmed, and the yes binds to the typed value. A closed card is
    `AlreadyConfirmed` (409)."""
    await type_field(session, context=context, card_id=card_id, field_id=field_id, value=body.value)
    card = await require_review_card(session, context=context, card_id=card_id)
    return await _card_out(session, context, card)


@router.post("/{profile_id}/review-cards/{card_id}/confirm")
async def confirm_card(
    card_id: uuid.UUID, body: ReviewConfirmIn, context: Context, session: Db
) -> ReviewConfirmedOut:
    """Close the card on the yes minted for exactly these decisions. Each confirmed or
    corrected field becomes a fact with the photo as provenance and the caller as its
    confirmer; a rejected one writes nothing; State recomputes as each lands. A machine's
    screen becomes one reading event and its facts; a hospital letter or a clinic slip the
    event it records. A yes for other decisions is `NotWhatWasConfirmed` (400); a field Nura
    could not read and nobody typed, confirmed as read, is `UnreadableField` (400); a card
    already closed is `AlreadyConfirmed` (409)."""
    card, fields, facts = await confirm_review_card(
        session,
        context=context,
        card_id=card_id,
        decisions=[decision.as_decision() for decision in body.decisions],
        confirmation_id=body.confirmation_id,
        episode_id=body.episode_id,
    )
    return ReviewConfirmedOut(
        card=ReviewCardOut.of(card, fields),
        facts=[FactOut.of(fact) for fact in facts],
        event_id=next((fact.event_id for fact in facts if fact.event_id is not None), None),
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


# --- notes on an event (E02-06) ------------------------------------------------------------


@router.post("/{profile_id}/events/{event_id}/notes", status_code=status.HTTP_201_CREATED)
async def add_note_on_event(
    event_id: uuid.UUID, body: EventNoteIn, request: Request, context: Context, session: Db
) -> EventNoteOut:
    """A voice note or a scribble on one event. A voice note is kept as a VOICE artefact —
    which rests on the recording consent (E16-02) — and heard by the region's transcriber;
    the words are kept by reference and never become a fact. A scribble is a small image,
    kept as drawn. `private` puts it under the notes scope; otherwise it is shared with
    whoever holds the record."""
    providers = providers_of(request)
    if body.kind is NoteKind.VOICE:
        view = await add_voice_note(
            session,
            context=context,
            store=providers.object_store,
            transcriber=providers.transcriber,
            event_id=event_id,
            data=body.as_bytes(),
            content_type=body.content_type,
            captured_at=body.captured_at,
            private=body.private,
            language=await _language(session, context),
            label=body.label,
        )
    else:
        view = await add_scribble(
            session,
            context=context,
            store=providers.object_store,
            event_id=event_id,
            data=body.as_bytes(),
            content_type=body.content_type,
            captured_at=body.captured_at,
            private=body.private,
            label=body.label,
        )
    return EventNoteOut.of(view)


@router.get("/{profile_id}/events/{event_id}/notes")
async def notes_on_event(
    event_id: uuid.UUID, request: Request, context: Context, session: Db
) -> list[EventNoteOut]:
    """Recall: the notes on one event that this key opens, oldest first — the shared ones
    under the record's scope, the private ones only for a key that opens the notes."""
    views = await notes_for(
        session, context=context, store=providers_of(request).object_store, event_id=event_id
    )
    return [EventNoteOut.of(view) for view in views]


@router.get("/{profile_id}/events/{event_id}/notes/{note_id}/content")
async def note_bytes(
    event_id: uuid.UUID, note_id: uuid.UUID, request: Request, context: Context, session: Db
) -> Response:
    """The recording or the image of one note, as it was kept: hear it again, see it again.
    A note this key does not open is `NoSuchEventNote` (404)."""
    data, content_type = await note_content(
        session,
        context=context,
        store=providers_of(request).object_store,
        event_id=event_id,
        note_id=note_id,
    )
    return Response(content=data, media_type=content_type)
