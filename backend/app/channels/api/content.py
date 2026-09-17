"""The content library over HTTP (docs/design-direction.md's Reference B growth).

    GET /profiles/{id}/activities(/{item})            Stay engaged
    GET /profiles/{id}/care-services(/{item})          Professional help
    GET /profiles/{id}/resources(/{item})               Guides & support
    GET /profiles/{id}/community(/{item})                Local Events, Volunteer, Support Groups

Every route takes the profile's key context, so region and language come from him — never
from the caller — and every route answers only what a pharmacist has approved
(`app.delivery.content.service`). `GET /community` narrows to one of its three kinds with
`kind=local_event|volunteer|support_group`; left out, it is all three together, the way the
design's single Community row holds three tiles.
"""

from __future__ import annotations

import uuid
from enum import StrEnum

from fastapi import APIRouter, Query

from app.channels.api.content_schemas import ContentItemOut, ContentListOut
from app.channels.api.deps import Context, Db
from app.delivery.content.models import COMMUNITY_TYPES
from app.delivery.content.service import NoSuchContentItem, list_content, read_content
from app.delivery.feed.models import CardType

router = APIRouter(prefix="/profiles", tags=["content"])


class CommunityKind(StrEnum):
    LOCAL_EVENT = "local_event"
    VOLUNTEER = "volunteer"
    SUPPORT_GROUP = "support_group"


_COMMUNITY_TYPE_OF: dict[CommunityKind, CardType] = {
    CommunityKind.LOCAL_EVENT: CardType.LOCAL_EVENT,
    CommunityKind.VOLUNTEER: CardType.VOLUNTEER,
    CommunityKind.SUPPORT_GROUP: CardType.SUPPORT_GROUP,
}


@router.get("/{profile_id}/activities")
async def activities(
    context: Context,
    session: Db,
    language: str | None = Query(default=None, min_length=2, max_length=16),
    category: str | None = Query(default=None, max_length=60),
) -> ContentListOut:
    """Things to do, suited to him: reviewed, in his region and language."""
    items = await list_content(
        session,
        context=context,
        content_types=(CardType.ACTIVITY,),
        language=language,
        category=category,
    )
    return ContentListOut.of(items)


@router.get("/{profile_id}/activities/{item_id}")
async def activity(context: Context, session: Db, item_id: uuid.UUID) -> ContentItemOut:
    item = await read_content(
        session, context=context, item_id=item_id, content_types=(CardType.ACTIVITY,)
    )
    return ContentItemOut.of(item)


@router.get("/{profile_id}/care-services")
async def care_services(
    context: Context,
    session: Db,
    language: str | None = Query(default=None, min_length=2, max_length=16),
    category: str | None = Query(default=None, max_length=60),
) -> ContentListOut:
    """A directory of professional help: home nursing, physiotherapy, meal delivery,
    transport to appointments, day care — reviewed, in his region and language."""
    items = await list_content(
        session,
        context=context,
        content_types=(CardType.CARE_SERVICE,),
        language=language,
        category=category,
    )
    return ContentListOut.of(items)


@router.get("/{profile_id}/care-services/{item_id}")
async def care_service(context: Context, session: Db, item_id: uuid.UUID) -> ContentItemOut:
    item = await read_content(
        session, context=context, item_id=item_id, content_types=(CardType.CARE_SERVICE,)
    )
    return ContentItemOut.of(item)


@router.get("/{profile_id}/resources")
async def resources(
    context: Context,
    session: Db,
    language: str | None = Query(default=None, min_length=2, max_length=16),
    category: str | None = Query(default=None, max_length=60),
) -> ContentListOut:
    """Short plain-words guides: reviewed, in his region and language."""
    items = await list_content(
        session,
        context=context,
        content_types=(CardType.RESOURCE,),
        language=language,
        category=category,
    )
    return ContentListOut.of(items)


@router.get("/{profile_id}/resources/{item_id}")
async def resource(context: Context, session: Db, item_id: uuid.UUID) -> ContentItemOut:
    item = await read_content(
        session, context=context, item_id=item_id, content_types=(CardType.RESOURCE,)
    )
    return ContentItemOut.of(item)


@router.get("/{profile_id}/community")
async def community(
    context: Context,
    session: Db,
    kind: CommunityKind | None = None,
    language: str | None = Query(default=None, min_length=2, max_length=16),
    category: str | None = Query(default=None, max_length=60),
) -> ContentListOut:
    """Local Events, Volunteer opportunities and Support Groups: one kind with `kind=`, or
    all three, reviewed, in his region and language."""
    types = (_COMMUNITY_TYPE_OF[kind],) if kind is not None else COMMUNITY_TYPES
    items = await list_content(
        session, context=context, content_types=types, language=language, category=category
    )
    return ContentListOut.of(items)


@router.get("/{profile_id}/community/{item_id}")
async def community_item(
    context: Context, session: Db, item_id: uuid.UUID
) -> ContentItemOut:
    item = await read_content(
        session, context=context, item_id=item_id, content_types=COMMUNITY_TYPES
    )
    return ContentItemOut.of(item)


__all__ = ["NoSuchContentItem", "router"]
