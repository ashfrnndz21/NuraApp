"""Every card's spoken twin, rendered to audio on request (E11-04).

The twin is the card's voice script (`app.language.voice_script.script_for` over
`FeedItem.voice`, the body when a card has none, with its boundary line): the same words the
card says, which passed plain words when the card was made, and the same digest the feed
serves as the card's `voice_script`. It is said by the
one `Voice` port and kept in the region's object store by digest (`app.delivery.voice`), so
the second play of the same card is a read. A key sees the twin of a card it may see, and
nothing else: the card's own scope is checked, and a refusal is on the trail.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_guard, audited_read
from app.audit.models import Action
from app.db import utcnow
from app.delivery.feed.engagement import NoSuchItem
from app.delivery.feed.models import FeedItem
from app.delivery.feed.rank import _visible_to, _without_photos_taken_back
from app.delivery.voice import Voice, Voiced, voice_language, voiced
from app.errors import Refusal
from app.ingestion.objects import ObjectStore
from app.keys.context import KeyContext
from app.keys.scopes import Scope

FEED_TARGET = FeedItem.__tablename__


class NotInThatLanguage(Refusal):
    """A card is written in the profile's language, and its twin is said in the same one."""


async def spoken_twin(
    session: AsyncSession,
    *,
    context: KeyContext,
    item_id: uuid.UUID,
    voice: Voice,
    store: ObjectStore,
    language: str | None = None,
) -> Voiced:
    """The twin of one card, said in its language: under thirty seconds, from the cache when
    it has been said before."""
    found = await audited_read(
        session, FeedItem, context, Scope.PROFILE, where=(FeedItem.id == item_id,)
    )
    if not found:
        raise NoSuchItem(f"no card {item_id} on this profile")
    item = found[0]
    async with audited_guard(session, context, Action.READ, item.scope, FEED_TARGET):
        context.require(item.scope)
        if language is not None and voice_language(language) != voice_language(item.language):
            raise NotInThatLanguage(f"this card is in {item.language}; its twin is too")
    return await voiced(
        store,
        voice,
        profile_id=context.profile_id,
        region=context.region,
        lines=list(item.voice or item.body),
        language=item.language,
        boundary=item.boundary,
    )


async def one_card(session: AsyncSession, *, context: KeyContext, item_id: uuid.UUID) -> FeedItem:
    """One card by its id, under its own scope: what a push opens (#143). A card that is not
    on this profile, has expired, or is not one this key's feed shows (its audience, a photo
    taken back) is `NoSuchItem`; one outside this key's scope is refused, on the trail."""
    found = await audited_read(
        session,
        FeedItem,
        context,
        Scope.PROFILE,
        where=(FeedItem.id == item_id, FeedItem.expires_at > utcnow()),
    )
    visible = await _without_photos_taken_back(session, context, _visible_to(found, context))
    if not visible:
        raise NoSuchItem(f"no card {item_id} on this profile")
    item = visible[0]
    async with audited_guard(session, context, Action.READ, item.scope, FEED_TARGET):
        context.require(item.scope)
    return item
