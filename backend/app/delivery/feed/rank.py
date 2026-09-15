"""Ranking: the order he sees, the caps, the quiet hours, and the cursor.

The supply is walked in one order — a flag, then now, then today's cards, then the gate,
then his story, then learning — and inside each section by priority, then by age. Two rules
sit on top of the order for the patient. The caps: one card of each kind a day, two new cards
a day in all; what the caps hold back is counted and shown to the caregiver as held, never
dropped in silence. The quiet hours: nothing between 21:00 and 07:00 on his wall clock,
except a red flag, which is never capped and never quiet.

Past the gate the list is endless: the story and learning cards are repeated in order, so
the pager never runs out and everything in it is still about him. A cursor is opaque and
pins the moment the page was built, so two requests with the same cursor answer the same
page whatever landed in between; a request with no cursor makes today's cards first.

"Not for me" is a Fact (`engagement.py`), and State folds it into the preference dimension;
ranking reads it back and holds that kind of card for the rest of the day.
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_profile_read, audited_read, audited_write
from app.db import as_utc, utcnow
from app.delivery.feed.compose import Day, can_compose, refresh, today_for
from app.delivery.feed.models import (
    PLAYS,
    SUPPLY_ORDER,
    CapsClass,
    CardType,
    DeliverTo,
    Engagement,
    EngagementKind,
    FeedItem,
    FeedPage,
    Supply,
)
from app.delivery.feed.search import Engine
from app.delivery.feed.sources import require_manager
from app.errors import Refusal
from app.family.photos import taken_back
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.language.voice_script import script_for
from app.memory.semantic import current_facts
from app.state.service import StateView, current_state

PAGE_SIZE = 5
DAILY_CAP = 2
"""New cards a day for the patient in the app: today's section (spec §1)."""
QUIET_FROM = time(21, 0)
QUIET_UNTIL = time(7, 0)
"""Nothing is delivered between these, on the patient's wall clock, except a flag."""
DECLINED = "declined"
"""The subject of the "not for me" fact; the attribute is the card type."""
OPENED: frozenset[EngagementKind] = frozenset(
    {
        EngagementKind.SEEN,
        EngagementKind.OPENED,
        EngagementKind.HEARD,
        EngagementKind.TAPPED,
        EngagementKind.ASKED_MORE,
    }
)
"""What says a card was opened: on his screen, heard, tapped or asked about."""
WEEK_TARGET = "feed_item.week"
"""What the trail names when "Sent to Pa this week" is read, or refused."""
NOT_IN_THE_WEEK: frozenset[CardType] = frozenset({CardType.NOW, CardType.GATE, CardType.DUTY})
"""The cards that are not something sent: the now card is Today's, the gate is a turn of the
page, the duty card is hers."""


class NotACursor(Refusal):
    """The cursor is Nura's own, handed back as it was given. This was not one."""


class NotOnADevRun(Refusal):
    """`?at=` pretends it is another hour, for checkpoints; only a declared dev run has it."""


def in_quiet_hours(local: datetime) -> bool:
    at = local.time()
    return at >= QUIET_FROM or at < QUIET_UNTIL


def encode_cursor(offset: int, as_of: datetime) -> str:
    raw = json.dumps({"o": offset, "t": as_utc(as_of).isoformat()}, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[int, datetime]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        loaded = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
        offset, as_of = int(loaded["o"]), datetime.fromisoformat(loaded["t"])
    except (binascii.Error, ValueError, KeyError, TypeError, json.JSONDecodeError) as bad:
        raise NotACursor("not a cursor this feed handed out") from bad
    if offset < 0 or as_of.tzinfo is None:
        raise NotACursor("not a cursor this feed handed out")
    return offset, as_of


@dataclass(frozen=True, slots=True)
class Page:
    """One page of the feed as it was answered."""

    audience: DeliverTo
    items: tuple[FeedItem, ...]
    cursor: str | None
    next_cursor: str | None
    quiet: bool
    held_by_caps: dict[str, int]
    status: dict[uuid.UUID, str] = field(default_factory=dict)
    """Per item: generated, held, sent, opened, dismissed — from the engagement rows and the
    pages rendered, never from a column on the item."""


def audience_of(context: KeyContext) -> DeliverTo:
    """Whose supply this key gets: the owner reads as the patient; everyone else — chief,
    caregiver, steward, viewer — reads the caregiver's list."""
    return DeliverTo.PATIENT if context.is_owner else DeliverTo.CAREGIVER


_SECTION: dict[Supply, int] = {supply: index for index, supply in enumerate(SUPPLY_ORDER)}
_SECTION[Supply.HELD] = len(SUPPLY_ORDER)


def _order_key(item: FeedItem) -> tuple[int, int, datetime]:
    return (_SECTION[item.supply], -item.priority, as_utc(item.created_at))


def _visible_to(items: Sequence[FeedItem], context: KeyContext) -> list[FeedItem]:
    """Only the cards built from parts of the record the key covers."""
    return [item for item in items if context.allows(item.scope)]


async def _without_photos_taken_back(
    session: AsyncSession, context: KeyContext, items: Sequence[FeedItem]
) -> list[FeedItem]:
    """A story card of a family photo whose sharer has since taken it back is not shown
    (E21-05): the photo was theirs to share and is theirs to take back, and a card made before
    is not shown after. A card is never edited, so it is left out here, on every page."""
    named = {str(item.why.get("photo_id")) for item in items if item.why.get("photo_id")}
    if not named or not context.allows(Scope.FAMILY):
        return list(items)
    gone = {
        str(ident)
        for ident in await taken_back(
            session, context=context, photo_ids=[uuid.UUID(one) for one in sorted(named)]
        )
    }
    return [item for item in items if str(item.why.get("photo_id") or "") not in gone]


def _patient_supply(
    items: Sequence[FeedItem], *, day: Day, declined: set[str], quiet: bool
) -> tuple[list[FeedItem], Counter[str]]:
    """The patient's order with the caps and the quiet hours applied."""
    held: Counter[str] = Counter()
    chosen: list[FeedItem] = []
    per_type: Counter[str] = Counter()
    new_today = 0
    for item in sorted(items, key=_order_key):
        if item.deliver_to is not DeliverTo.PATIENT or item.supply is Supply.HELD:
            continue
        if item.caps_class is CapsClass.FLAG:
            chosen.append(item)
            continue
        if quiet:
            held[item.type.value] += 1
            continue
        if item.type.value in declined:
            held[item.type.value] += 1
            continue
        if item.caps_class is CapsClass.ONE:
            if per_type[item.type.value] >= 1 or new_today >= DAILY_CAP:
                held[item.type.value] += 1
                continue
            per_type[item.type.value] += 1
            new_today += 1
        chosen.append(item)
    return chosen, held


def _caregiver_supply(items: Sequence[FeedItem]) -> list[FeedItem]:
    """Everything generated for him or held for her, in the same order, no gate before the
    story, no caps: her list is what needs a person today and what was made this week."""
    return [
        item
        for item in sorted(items, key=_order_key)
        if item.deliver_to in (DeliverTo.PATIENT, DeliverTo.CAREGIVER)
        and item.type is not CardType.GATE
    ]


def _endless(ordered: Sequence[FeedItem], offset: int) -> tuple[list[FeedItem], int | None]:
    """The page at `offset`, cycling the story and learning cards past the end of the list."""
    tail = [item for item in ordered if item.supply in (Supply.STORY, Supply.LEARNING)]
    page: list[FeedItem] = []
    position = offset
    while len(page) < PAGE_SIZE:
        if position < len(ordered):
            page.append(ordered[position])
        elif tail:
            page.append(tail[(position - len(ordered)) % len(tail)])
        else:
            break
        position += 1
    more = position < len(ordered) or bool(tail)
    return page, (position if more and page else None)


async def _declined_today(session: AsyncSession, *, context: KeyContext, day: Day) -> set[str]:
    """The card types he said "not for me" to today: the facts State folded in."""
    if not context.allows(Scope.RECORDS):
        return set()
    facts = await current_facts(session, context=context, subject=DECLINED)
    return {
        fact.attribute
        for fact in facts
        if isinstance(fact.value, dict) and fact.value.get("day") == day.key
    }


async def _statuses(
    session: AsyncSession, *, context: KeyContext, items: Sequence[FeedItem], held: Counter[str]
) -> dict[uuid.UUID, str]:
    ids = [item.id for item in items]
    if not ids:
        return {}
    # What became of a card is what *he* did with it: his chief's own taps on her list are
    # not his opening it ("Pa opened this card" is said only when he did).
    owner = (await audited_profile_read(session, context)).owner_person_id
    engaged = [
        one
        for one in await audited_read(
            session, Engagement, context, Scope.PROFILE, where=(Engagement.item_id.in_(ids),)
        )
        if one.person_id == owner
    ]
    pages = await audited_read(
        session, FeedPage, context, Scope.PROFILE, where=(FeedPage.audience == DeliverTo.PATIENT,)
    )
    sent = {uuid.UUID(one) for page in pages for one in page.item_ids}
    by_item: dict[uuid.UUID, set[EngagementKind]] = {}
    for one in engaged:
        by_item.setdefault(one.item_id, set()).add(one.kind)
    status: dict[uuid.UUID, str] = {}
    for item in items:
        kinds = by_item.get(item.id, set())
        if EngagementKind.DISMISSED in kinds:
            status[item.id] = "dismissed"
        elif kinds & PLAYS:
            status[item.id] = "played"
        elif kinds & OPENED:
            status[item.id] = "opened"
        elif item.id in sent:
            status[item.id] = "sent"
        elif item.deliver_to is not DeliverTo.PATIENT or held.get(item.type.value):
            status[item.id] = "held"
        else:
            status[item.id] = "generated"
    return status


async def feed_page(
    session: AsyncSession,
    *,
    context: KeyContext,
    engine: Engine,
    cursor: str | None = None,
    pretend_local: datetime | None = None,
) -> Page:
    """One page of the feed for this key.

    No cursor: today's cards are made first (when the key can render — the owner's, or a
    chief's), the page is built as of now, and it is kept as the offline page for this
    person. A cursor: the page it names, as of the moment the cursor was minted.
    `pretend_local` is the dev-only "what if it were this hour" for the quiet-hours check —
    the route allows it on a declared dev run only; nothing written uses it.
    """
    audience = audience_of(context)
    day = today_for(context)
    if cursor is None:
        if await can_compose(context):
            await refresh(session, context=context, engine=engine)
        # After the refresh, on the live clock: the cards just made are part of this page.
        offset, as_of = 0, utcnow()
    else:
        offset, as_of = decode_cursor(cursor)
    found = await audited_read(
        session,
        FeedItem,
        context,
        Scope.PROFILE,
        where=(FeedItem.created_at <= as_of, FeedItem.expires_at > day.now),
    )
    visible = await _without_photos_taken_back(session, context, _visible_to(found, context))
    held: Counter[str] = Counter()
    quiet = False
    if audience is DeliverTo.PATIENT:
        local = pretend_local if pretend_local is not None else day.local
        quiet = in_quiet_hours(local)
        declined = await _declined_today(session, context=context, day=day)
        ordered, held = _patient_supply(visible, day=day, declined=declined, quiet=quiet)
    else:
        ordered = _caregiver_supply(visible)
    page, next_offset = _endless(ordered, offset)
    next_cursor = None if next_offset is None else encode_cursor(next_offset, as_of)
    status = await _statuses(session, context=context, items=page, held=held)
    if cursor is None:
        await audited_write(
            session,
            FeedPage,
            context,
            Scope.PROFILE,
            person_id=context.person_id,
            audience=audience,
            item_ids=[str(item.id) for item in page],
            cursor=None,
            next_cursor=next_cursor,
            quiet=quiet,
            held_by_caps=dict(held),
            rendered_at=day.now,
        )
    return Page(
        audience=audience,
        items=tuple(page),
        cursor=cursor,
        next_cursor=next_cursor,
        quiet=quiet,
        held_by_caps=dict(held),
        status=status,
    )


async def morning_supply(
    session: AsyncSession, *, context: KeyContext, engine: Engine
) -> tuple[StateView, list[FeedItem]]:
    """The now and today cards the patient's feed leads with, and the State they came from.

    What the morning card on WhatsApp says (E19-03), so the thread and the app lead his day
    with the same things: today's cards are made first, as a first page makes them, then
    walked in the patient's order with the caps and his "not for me" applied. The flag, the
    gate and everything past it are left out — a flag is its own message, never a line in a
    routine card — and so are the quiet hours, which are the sender's clock to keep. Nothing
    is written as a page: this is not the app's page, and nothing on it is marked sent.
    """
    if await can_compose(context):
        state, _ = await refresh(session, context=context, engine=engine)
    else:
        state = await current_state(session, context=context)
    day = today_for(context)
    found = await audited_read(
        session, FeedItem, context, Scope.PROFILE, where=(FeedItem.expires_at > day.now,)
    )
    declined = await _declined_today(session, context=context, day=day)
    ordered, _ = _patient_supply(
        await _without_photos_taken_back(session, context, _visible_to(found, context)),
        day=day,
        declined=declined,
        quiet=False,
    )
    return state, [item for item in ordered if item.supply in (Supply.NOW, Supply.TODAY)]


CATEGORY_OF: dict[CardType, str] = {
    CardType.FLAG: "alert",
    CardType.NOW: "reminder",
    CardType.VISIT: "reminder",
    CardType.REORDER: "reminder",
    CardType.MEMO: "reminder",
    CardType.READING: "insight",
    CardType.NOTICE: "insight",
    CardType.STORY: "insight",
    CardType.LEARNING: "insight",
    # A local alert says what to do today; the rest are something to know.
    CardType.LOCAL: "reminder",
    CardType.CLIP: "insight",
    CardType.RECAP: "insight",
    CardType.SEASONAL: "insight",
    CardType.FOOD: "insight",
}
"""What each card is to "today's top three" (E11-02): an alert, a reminder, or an insight.
The gate, the duty card and a doctor's question are none of the three."""
CATEGORY_ORDER: tuple[str, ...] = ("alert", "reminder", "insight")
TOP = 3


def _by_category(item: FeedItem) -> tuple[int, tuple[int, int, datetime]]:
    return (CATEGORY_ORDER.index(CATEGORY_OF[item.type]), _order_key(item))


async def top_three(session: AsyncSession, *, context: KeyContext, engine: Engine) -> Page:
    """Today's top three for this key (E11-02): alerts first, then reminders, then insights,
    and inside each the feed's own order — from the supply this key gets, with the caps, the
    quiet hours and his "not for me" applied exactly as the feed applies them. Every card
    carries its why. Nothing is written as a page: the first page of the feed is the page."""
    audience = audience_of(context)
    day = today_for(context)
    if await can_compose(context):
        await refresh(session, context=context, engine=engine)
    found = await audited_read(
        session, FeedItem, context, Scope.PROFILE, where=(FeedItem.expires_at > day.now,)
    )
    visible = await _without_photos_taken_back(session, context, _visible_to(found, context))
    held: Counter[str] = Counter()
    quiet = False
    if audience is DeliverTo.PATIENT:
        quiet = in_quiet_hours(day.local)
        declined = await _declined_today(session, context=context, day=day)
        ordered, held = _patient_supply(visible, day=day, declined=declined, quiet=quiet)
    else:
        ordered = _caregiver_supply(visible)
    chosen = sorted((item for item in ordered if item.type in CATEGORY_OF), key=_by_category)[:TOP]
    return Page(
        audience=audience,
        items=tuple(chosen),
        cursor=None,
        next_cursor=None,
        quiet=quiet,
        held_by_caps=dict(held),
        status=await _statuses(session, context=context, items=chosen, held=held),
    )


@dataclass(frozen=True, slots=True)
class Sent:
    """One card made for him this week, as his chief's list shows it (spec §1): the card and
    what became of it. Never how many times, and never for how long: the list says whether a
    card was opened or played, and no count of anything (spec §0, "no counts")."""

    item: FeedItem
    status: str


async def sent_this_week(session: AsyncSession, *, context: KeyContext) -> list[Sent]:
    """Every card made for him since Monday on his wall clock — delivered, held for her, or
    kept for the doctor's memo — newest first, each with its status (sent, opened, played,
    dismissed, held): "Sent to Pa this week". The now card, the gate and her own duty card are
    not sent things and are left out. Narrowed to the parts the key covers, like every read
    of the feed; the owner's and his chief's to read (`NotTheirsToManage`). Nothing is made
    here."""
    await require_manager(session, context=context, target=WEEK_TARGET)
    day = today_for(context)
    found = await audited_read(
        session,
        FeedItem,
        context,
        Scope.PROFILE,
        where=(FeedItem.created_at >= day.week_starts_at, FeedItem.created_at <= day.now),
    )
    visible = await _without_photos_taken_back(session, context, _visible_to(found, context))
    if context.is_owner:
        # His own read of the week is of what reached him: a card held for his chief or kept
        # for the doctor's memo is not on his feed, so it is not on his week either.
        visible = [item for item in visible if item.deliver_to is DeliverTo.PATIENT]
    shown = sorted(
        (item for item in visible if item.type not in NOT_IN_THE_WEEK),
        key=lambda item: (as_utc(item.created_at), item.priority),
        reverse=True,
    )
    if not shown:
        return []
    status = await _statuses(session, context=context, items=shown, held=Counter())
    return [Sent(item, status.get(item.id, "generated")) for item in shown]


class NoCachedPage(Refusal):
    """No page has been rendered for this person yet: nothing to open offline."""


async def cached_page(session: AsyncSession, *, context: KeyContext) -> Page:
    """The last first page rendered for this person, as it was: what the app stores for an
    offline launch. Items that have since expired are still returned; it is a cache."""
    pages = await audited_read(
        session,
        FeedPage,
        context,
        Scope.PROFILE,
        where=(FeedPage.person_id == context.person_id,),
        order_by=(FeedPage.rendered_at.desc(),),
        limit=1,
    )
    if not pages:
        raise NoCachedPage("no page has been rendered for this person")
    kept = pages[0]
    ids = [uuid.UUID(one) for one in kept.item_ids]
    items = (
        await audited_read(session, FeedItem, context, Scope.PROFILE, where=(FeedItem.id.in_(ids),))
        if ids
        else []
    )
    by_id = {
        item.id: item
        for item in await _without_photos_taken_back(session, context, _visible_to(items, context))
    }
    ordered = tuple(by_id[one] for one in ids if one in by_id)
    return Page(
        audience=kept.audience,
        items=ordered,
        cursor=kept.cursor,
        next_cursor=kept.next_cursor,
        quiet=kept.quiet,
        held_by_caps=dict(kept.held_by_caps),
        status=await _statuses(
            session, context=context, items=ordered, held=Counter(kept.held_by_caps)
        ),
    )


def item_json(item: FeedItem, status: str) -> dict[str, Any]:
    """The item as the API answers it. `autoplay` is false; it is a column, and it is here so
    the client can see the promise, not decide it."""
    return {
        "item_id": str(item.id),
        "type": item.type.value,
        "supply": item.supply.value,
        "status": status,
        "rendered_from_state": str(item.state_id),
        "language": item.language,
        "format": item.format.value,
        "headline": item.headline,
        "body": list(item.body),
        "voice": list(item.voice),
        "why": dict(item.why),
        "priority": item.priority,
        "caps_class": item.caps_class.value,
        "scope": item.scope.value,
        "deliver_to": item.deliver_to.value,
        "autoplay": False,
        "source_id": None if item.source_id is None else str(item.source_id),
        "cite": None if item.cite is None else dict(item.cite),
        "boundary": item.boundary,
        # The card as it is said (E22-03): its voice lines, a pause after each and a longer
        # one before the boundary — the same verified words, never others.
        "voice_script": script_for(item.voice, item.language, boundary=item.boundary).as_json(),
        "day": item.day,
        "created_at": as_utc(item.created_at).isoformat(),
        "expires_at": as_utc(item.expires_at).isoformat(),
        "number": item.number,
        "direction": item.direction,
        "colour": item.colour,
        "action": item.action,
        "category": CATEGORY_OF.get(item.type),
        # The watch that found it, for a card a search made: what her "Pause this watch" on
        # "Sent to Pa this week" pauses. None for every card made from his own record.
        "search_job_id": None if item.search_job_id is None else str(item.search_job_id),
    }
