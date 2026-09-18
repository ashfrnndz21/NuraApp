"""Care navigation with drafted messages, over HTTP (T3).

    GET  /profiles/{id}/navigation/drafts             every real need, no drafted text yet
    POST /profiles/{id}/navigation/drafts/{need_id}    the drafted message and its link

Nothing here ever sends anything: the POST only ever returns text and a link built from the
provider's own directory contact, for him or his chief to send from their own phone.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from app.channels.api.deps import Context, Db, providers_of
from app.channels.api.navigation_schemas import DraftOut, NeedOut
from app.reasoning.navigation.service import (
    draft_message,
    need_for_id,
    needs_for,
    provider_for_need,
)

router = APIRouter(prefix="/profiles", tags=["navigation"])

Language = Query(default=None, min_length=2, max_length=16)


@router.get("/{profile_id}/navigation/drafts")
async def navigation_needs(context: Context, session: Db) -> list[NeedOut]:
    needs = await needs_for(session, context=context)
    return [NeedOut.of(need) for need in needs]


@router.post("/{profile_id}/navigation/drafts/{need_id}")
async def draft_navigation_message(
    need_id: str,
    request: Request,
    context: Context,
    session: Db,
    language: str | None = Language,
) -> DraftOut:
    need = await need_for_id(session, context=context, need_id=need_id)
    provider = await provider_for_need(session, context=context, need=need)
    draft = await draft_message(
        session,
        context,
        need,
        provider,
        drafter=providers_of(request).drafter,
        language=language,
    )
    return DraftOut.of(draft)
