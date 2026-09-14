"""What he did with a card, written back.

Every engagement — seen, heard, tapped, not for me, shared — is posted by the client and
written twice: as a memory Event of kind `ENGAGEMENT` (the moment it happened, on which
channel), and as an `Engagement` row beside the item, so the caregiver's list can say
opened or dismissed and the format switch can count what went unopened.

"Not for me" goes one step further. It is his word about his own feed, so it becomes a
Fact — subject `declined`, attribute the card type, holding until midnight on his wall
clock — resting on the engagement event and confirmed by him. State folds it into the
preference dimension (`app.state.dimensions.SUBJECT_DIMENSION`), and ranking reads it back
from there (`rank.DECLINED`). That is the engagement input to State: not a new dimension,
a fact with provenance and a window, the way everything else State holds got there.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_read, audited_write
from app.audit.models import Action
from app.db import utcnow
from app.delivery.feed.compose import today_for
from app.delivery.feed.models import (
    Engagement,
    EngagementChannel,
    EngagementKind,
    FeedItem,
)
from app.delivery.feed.rank import DECLINED
from app.drafts import FactDraft
from app.errors import Refusal
from app.keys.confirm import confirm
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.memory.episodic import record_event
from app.memory.models import ConfidenceState, EventKind, SourceChannel
from app.memory.semantic import assert_fact, current_facts

ENGAGEMENT_TARGET = Engagement.__tablename__


class NoSuchItem(Refusal):
    """No feed item by that id on this profile that this key can see."""


SOURCE_OF: dict[EngagementChannel, SourceChannel] = {
    EngagementChannel.APP: SourceChannel.APP,
    EngagementChannel.WHATSAPP: SourceChannel.WHATSAPP,
    EngagementChannel.WIDGET: SourceChannel.APP,
}


@audited(Action.WRITE, Scope.PROFILE, ENGAGEMENT_TARGET)
async def record_engagement(
    session: AsyncSession,
    *,
    context: KeyContext,
    item_id: uuid.UUID,
    kind: EngagementKind,
    channel: EngagementChannel = EngagementChannel.APP,
) -> Engagement:
    """Write down what this person did with this card.

    The item is read under the profile scope and then required under its own, so a key that
    does not cover the part of the record the card came from cannot engage with it. The
    event needs the record scope, as every event does. For the owner, "not for me" also
    writes the `declined` fact that holds the card's kind back for the rest of his day.
    """
    found = await audited_read(
        session, FeedItem, context, Scope.PROFILE, where=(FeedItem.id == item_id,)
    )
    if not found:
        raise NoSuchItem(f"no feed item {item_id} on profile {context.profile_id}")
    item = found[0]
    context.require(item.scope)
    moment = utcnow()
    event = await record_event(
        session,
        context=context,
        kind=EventKind.ENGAGEMENT,
        occurred_at=moment,
        label=f"{kind.value}: {item.type.value} card",
        source_channel=SOURCE_OF[channel],
    )
    engagement = await audited_write(
        session,
        Engagement,
        context,
        item.scope,
        item_id=item.id,
        person_id=context.person_id,
        kind=kind,
        via=channel,
        event_id=event.id,
        at=moment,
    )
    if kind is EngagementKind.DISMISSED and context.is_owner:
        await _decline_for_the_day(session, context=context, item=item, event_id=event.id)
    return engagement


async def _decline_for_the_day(
    session: AsyncSession, *, context: KeyContext, item: FeedItem, event_id: uuid.UUID
) -> None:
    day = today_for(context)
    already = await current_facts(
        session, context=context, subject=DECLINED, attribute=item.type.value
    )
    if any(isinstance(fact.value, dict) and fact.value.get("day") == day.key for fact in already):
        return
    draft = FactDraft(
        subject=DECLINED,
        attribute=item.type.value,
        value={"day": day.key, "item_id": str(item.id)},
        unit=None,
        confidence=1.0,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
        artifact_id=None,
        event_id=event_id,
        episode_id=None,
        supersedes_id=None,
    )
    yes = await confirm(session, context, draft)
    await assert_fact(
        session,
        context=context,
        subject=draft.subject,
        attribute=draft.attribute,
        value=draft.value,
        confidence=draft.confidence,
        confidence_state=draft.confidence_state,
        confirmation_id=yes.id,
        event_id=event_id,
        valid_from=day.now,
        valid_to=day.ends_at,
    )
