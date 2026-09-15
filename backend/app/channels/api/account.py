"""The account over HTTP (#143): closing it, the closing's status, undoing it, and a key
holder's own yes to WhatsApp.

    POST /profiles/{id}/closure/preview   what closing means, in his words (the owner)
    POST /profiles/{id}/closure           close it, on his yes to exactly those words
    GET  /profiles/{id}/closure           the closing and its day (the owner, while closing)
    POST /profiles/{id}/closure/undo      undo it within the window (the owner, while closing)
    GET  /profiles/{id}/whatsapp-opt-in   the key-accept questions, and his own answers
    POST /profiles/{id}/whatsapp-opt-in   his own yes or no: WhatsApp, and the family's group
    POST /dev/run-erasures                the erasure job, now (a dev run only)

Stopping WhatsApp itself is the one withdraw route W6 (#137) serves; this PR only makes the
family's red-flag notices independent of it.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.channels.api.deps import ClosingContext, Context, Db, providers_of, settings_of
from app.channels.whatsapp.group import sync_group
from app.channels.whatsapp.opt_in import answers_of, record_opt_in
from app.consent.models import ConsentChannel
from app.consent.opt_in_words import OPT_IN_VERSION, opt_in_questions
from app.consent.service import RecordConsent
from app.db import as_utc
from app.identity.closing import (
    GraphEraser,
    close_account,
    close_draft_for,
    closing_status,
    run_erasures,
    undo_closure,
)
from app.identity.closure_models import AccountClosure

router = APIRouter(tags=["account"])


class LanguageIn(BaseModel):
    language: str = Field(min_length=2, max_length=16)


class CloseIn(BaseModel):
    confirmation_id: uuid.UUID
    language: str = Field(min_length=2, max_length=16)


class UndoIn(BaseModel):
    """His yes to keeping his papers again: today's words, in `language`, captured how."""

    wording_version: str = Field(min_length=1, max_length=32)
    language: str = Field(min_length=2, max_length=16)
    captured_via: ConsentChannel = ConsentChannel.APP


class ClosingOut(BaseModel):
    closing: bool
    requested_at: datetime | None = None
    delete_after: datetime | None = None
    lines: list[str] = Field(default_factory=list)
    """What closing means, in his words: the confirm step shows these, and his yes binds to them."""

    @classmethod
    def of(cls, closure: AccountClosure | None) -> ClosingOut:
        if closure is None or closure.undone_at is not None:
            return cls(closing=False)
        return cls(
            closing=True,
            requested_at=as_utc(closure.requested_at),
            delete_after=as_utc(closure.delete_after),
        )


class OptInIn(BaseModel):
    """His two answers, to the words he was shown (`GET`): WhatsApp, and the family's group."""

    messages: bool
    group: bool
    wording_version: str = Field(min_length=1, max_length=32)
    language: str = Field(min_length=2, max_length=16)


class OptInOut(BaseModel):
    wording_version: str
    messages_words: list[str]
    group_words: list[str]
    messages: bool | None = None
    """His newest answer to the first question; none before he has answered."""
    group: bool | None = None
    said_at: datetime | None = None


class ErasedOut(BaseModel):
    profiles: list[uuid.UUID]


@router.post("/profiles/{profile_id}/closure/preview")
async def closure_preview(
    body: LanguageIn, request: Request, context: Context, session: Db
) -> ClosingOut:
    """What closing his account means, in his words, and the day his papers go. His alone."""
    draft = await close_draft_for(
        session,
        context=context,
        language=body.language,
        retention_days=settings_of(request).account_retention_days,
    )
    return ClosingOut(closing=False, lines=list(draft.lines))


@router.post("/profiles/{profile_id}/closure", status_code=status.HTTP_201_CREATED)
async def closure_close(
    body: CloseIn, request: Request, context: Context, session: Db
) -> ClosingOut:
    """Close it on his yes (`POST /confirmations`, subject `close_account`): every key and his
    own reads suspended at once, keeping his papers withdrawn, every push revoked, nothing
    more sent about him but a red flag raised before now."""
    closure = await close_account(
        session,
        context=context,
        confirmation_id=body.confirmation_id,
        language=body.language,
        retention_days=settings_of(request).account_retention_days,
    )
    # The family's WhatsApp group is emptied now, and nothing is mirrored while it stands.
    await sync_group(session, context=context, provider=providers_of(request).whatsapp)
    return ClosingOut.of(closure)


@router.get("/profiles/{profile_id}/closure")
async def closure_now(context: ClosingContext, session: Db) -> ClosingOut:
    """The closing that stands, and the moment his papers go. Open to him while it stands."""
    return ClosingOut.of(await closing_status(session, context=context))


@router.post("/profiles/{profile_id}/closure/undo")
async def closure_undo(
    body: UndoIn, request: Request, context: ClosingContext, session: Db
) -> ClosingOut:
    """His yes within the window: today's words for keeping his papers, and it is as it was."""
    await undo_closure(
        session,
        context=context,
        consent=RecordConsent(
            text_version=body.wording_version,
            language=body.language,
            captured_via=body.captured_via,
        ),
    )
    # Everyone who said yes to the family's group is in it again, now.
    await sync_group(session, context=context, provider=providers_of(request).whatsapp)
    return ClosingOut(closing=False)


def _opt_in_out(language: str, row: object | None) -> OptInOut:
    messages_words, group_words = opt_in_questions(language)
    out = OptInOut(
        wording_version=OPT_IN_VERSION,
        messages_words=list(messages_words),
        group_words=list(group_words),
    )
    if row is not None:
        out.messages = row.said_yes  # type: ignore[attr-defined]
        out.group = row.joins_group  # type: ignore[attr-defined]
        out.said_at = as_utc(row.said_at)  # type: ignore[attr-defined]
    return out


@router.get("/profiles/{profile_id}/whatsapp-opt-in")
async def whatsapp_opt_in_now(context: Context, session: Db, language: str = "en") -> OptInOut:
    """The two questions at the key-accept step, in `language`, and the caller's own newest
    answers to them: none before he has answered."""
    return _opt_in_out(language, await answers_of(session, context=context))


@router.post("/profiles/{profile_id}/whatsapp-opt-in", status_code=status.HTTP_201_CREATED)
async def whatsapp_opt_in(
    body: OptInIn, request: Request, context: Context, session: Db
) -> OptInOut:
    """The caller's own answers at the key-accept step, to today's words. His yes to the
    family's group puts him in it now, and his no takes him out now; nobody but the patient
    is in it without it. The WhatsApp answer decides nothing yet, and never holds back a
    red-flag notice."""
    row = await record_opt_in(
        session,
        context=context,
        messages=body.messages,
        joins_group=body.group,
        wording_version=body.wording_version,
        language=body.language,
    )
    await sync_group(session, context=context, provider=providers_of(request).whatsapp)
    return _opt_in_out(body.language, row)


@router.post("/dev/run-erasures")
async def dev_run_erasures(request: Request, session: Db) -> ErasedOut:
    """The erasure job, now, the way a scheduler calls it. A dev run only."""
    if not settings_of(request).dev_code_sender:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    erased = await run_erasures(session, eraser=GraphEraser(providers_of(request).object_store))
    return ErasedOut(profiles=[row.profile_id for row in erased])
