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
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_guard, audited_read, audited_write
from app.audit.models import Action, Outcome
from app.audit.trail import record
from app.db import as_utc, utcnow
from app.delivery.feed.compose import today_for
from app.delivery.feed.models import (
    PLAYS,
    Engagement,
    EngagementChannel,
    EngagementKind,
    FeedItem,
)
from app.delivery.feed.rank import DECLINED, FEED_TARGET, NoSuchItem, _visible, require_item
from app.drafts import FactDraft
from app.errors import Refusal
from app.keys.confirm import confirm
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.memory.episodic import record_event
from app.memory.models import ConfidenceState, EventKind, SourceChannel
from app.memory.semantic import assert_fact, current_facts

ENGAGEMENT_TARGET = Engagement.__tablename__

__all__ = [
    "ENGAGEMENT_TARGET",
    "Flushed",
    "NoSuchItem",
    "Queued",
    "SecondsOnlyOnAPlay",
    "record_engagement",
    "record_events",
]


class SecondsOnlyOnAPlay(Refusal):
    """Seconds say how much of a clip or a voice note played. No other event carries time:
    the feed is never measured by how long anyone spent in it."""


QUEUE_LIMIT = 200
"""The most events one flush carries."""
QUEUE_WINDOW = timedelta(days=7)
"""How old an event the phone kept offline may be and still be written."""
CLOCK_SLACK = timedelta(minutes=5)
"""A phone's clock a little ahead of ours is the phone's clock, not the future."""


@dataclass(frozen=True, slots=True)
class Queued:
    """One event from the phone's queue: its own id, the card, what, when, where, and — for a
    play only — how many seconds played."""

    client_id: uuid.UUID
    item_id: uuid.UUID
    kind: EngagementKind
    at: datetime
    channel: EngagementChannel = EngagementChannel.APP
    seconds: float | None = None


@dataclass(frozen=True, slots=True)
class Flushed:
    written: list[Engagement] = field(default_factory=list)
    skipped: list[tuple[uuid.UUID, str]] = field(default_factory=list)
    """Each event not written, by its id, and why: already written, no such card, a card this
    key does not cover, too old, or not yet."""


@audited(Action.WRITE, Scope.RECORDS, ENGAGEMENT_TARGET)
async def record_events(
    session: AsyncSession, *, context: KeyContext, events: Sequence[Queued]
) -> Flushed:
    """Write the phone's queue (E11-08): opened, played (with seconds), replayed, dismissed,
    asked more, shared — each once, by the id the phone gave it, at the moment it happened.

    An event already written (the answer to an earlier flush was lost) is skipped; so is one
    about a card that is not on this profile, one about a card this key does not cover (the
    refusal on the trail), and one older than a week or from the future. The rest are written
    as `record_engagement` writes one. Every event needs the record scope, as every event does.
    """
    context.require(Scope.RECORDS)
    flushed = Flushed()
    if not events:
        return flushed
    ids = sorted({event.client_id for event in events}, key=str)
    done = {
        one.client_id
        for one in await audited_read(
            session, Engagement, context, Scope.PROFILE, where=(Engagement.client_id.in_(ids),)
        )
    }
    cards = {
        item.id: item
        for item in await audited_read(
            session,
            FeedItem,
            context,
            Scope.PROFILE,
            where=(FeedItem.id.in_(sorted({event.item_id for event in events}, key=str)),),
        )
    }
    now = utcnow()
    for event in sorted(events, key=lambda one: as_utc(one.at)):
        at = as_utc(event.at)
        item = cards.get(event.item_id)
        if event.client_id in done:
            flushed.skipped.append((event.client_id, "already_written"))
        elif item is None:
            flushed.skipped.append((event.client_id, "no_such_card"))
        elif not _visible(item, context):
            # Out of scope and `private_to` someone else (RE-01, §3.5) are refused the same
            # skip reason to the caller — a caregiver's flush of a queue that names a private
            # card learns nothing about why it did not write — but the trail he owns still
            # names which one it was.
            private = item.private_to is not None and item.private_to != context.person_id
            await record(
                session,
                context=context,
                action=Action.WRITE,
                scope=item.scope,
                target=ENGAGEMENT_TARGET,
                outcome=Outcome.REFUSED,
                refused_because="NoSuchItem" if private else "OutOfScope",
            )
            flushed.skipped.append((event.client_id, "out_of_scope"))
        elif at < now - QUEUE_WINDOW:
            flushed.skipped.append((event.client_id, "too_old"))
        elif at > now + CLOCK_SLACK:
            flushed.skipped.append((event.client_id, "not_yet"))
        else:
            written = await record_engagement(
                session,
                context=context,
                item_id=item.id,
                kind=event.kind,
                channel=event.channel,
                at=min(at, now),
                seconds=event.seconds,
                client_id=event.client_id,
                item=item,
            )
            done.add(event.client_id)
            flushed.written.append(written)
    return flushed


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
    at: datetime | None = None,
    seconds: float | None = None,
    client_id: uuid.UUID | None = None,
    item: FeedItem | None = None,
) -> Engagement:
    """Write down what this person did with this card.

    The item is read under the profile scope and then required under its own, so a key that
    does not cover the part of the record the card came from cannot engage with it; a card
    `private_to` someone else is the same refusal as one that does not exist (RE-01, §3.5).
    The event needs the record scope, as every event does. For the owner, "not for me" also
    writes the `declined` fact that holds the card's kind back for the rest of his day.
    """
    if seconds is not None and kind not in PLAYS:
        raise SecondsOnlyOnAPlay(f"a {kind.value} event carries no seconds")
    if item is None:
        item = await require_item(session, context=context, item_id=item_id)
    else:
        # The same door `require_item` opens for the item's own scope (PR #233 review, 8):
        # a card `private_to` someone else raised here, without it, was caught only by this
        # function's own `@audited(Scope.PROFILE, ...)` door — a different scope and a
        # different target than `require_item`'s write, so the trail told the two refusals
        # apart though the promise at `rank.require_item` says they should not be told apart.
        async with audited_guard(session, context, Action.READ, item.scope, FEED_TARGET):
            context.require(item.scope)
            if item.private_to is not None and item.private_to != context.person_id:
                raise NoSuchItem(f"no feed item {item_id} on profile {context.profile_id}")
    moment = utcnow() if at is None else at
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
        seconds=None if seconds is None else round(seconds, 1),
        client_id=client_id,
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
