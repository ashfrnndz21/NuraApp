"""RE-01 follow-up: every by-id read of a `FeedItem` goes through one door.

Independent review of #233 found that `rank._visible_to` guarded the listing routes (the
feed, today's three, "Sent to Pa this week", the offline cache) but five other functions read
a `FeedItem` **by id** — `twin.spoken_twin`, `twin.one_card`, `clips._clip_item`,
`engagement.record_events` and `engagement.record_engagement` — each with its own copy of
`FeedItem.id == item_id`, and none of them checked `private_to`. A caregiver holding the id of
a card resting on his search history could play its audio, get its clip and captions, or
write engagement on it, none of which the listing routes' guard ever saw.

The fix is one accessor, `rank.require_item`, that every one of those five now calls
(`app/delivery/feed/twin.py`, `clips.py`, `engagement.py`). This is the test that keeps it
that way: a hand-picked list of routes is exactly what let the leak through the first time, so
this scans every module under `app/` for the pattern that bypasses it, rather than naming the
five functions again.
"""

from __future__ import annotations

import ast
import inspect
import uuid
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import now
from app.delivery.feed.days import today_for
from app.delivery.feed.engagement import Queued, record_engagement, record_events
from app.delivery.feed.items import Lines, Why, create_item
from app.delivery.feed.models import CardType, DeliverTo, Engagement, EngagementKind, FeedItem
from app.delivery.feed.rank import NoSuchItem
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.state.service import current_state
from tests.family_support import household
from tests.support import refused_unit

APP = Path(__file__).resolve().parents[1] / "app"

# Reading a `FeedItem` by id is legitimate only inside these functions: `rank.require_item`
# (the one door), and the two bulk fetches that apply the same rule item by item afterwards
# (`rank.cached_page` via `_visible_to`, `engagement.record_events` via `_visible`) —
# `tests/test_row_scope.py::test_a_private_card_is_on_no_other_persons_route` and this file's
# own tests below hold each of those three to actually doing that.
ALLOWED: dict[str, frozenset[str]] = {
    "app/delivery/feed/rank.py": frozenset({"require_item", "cached_page"}),
    "app/delivery/feed/engagement.py": frozenset({"record_events"}),
}


def _feed_item_id_reads(path: Path) -> list[tuple[str, int]]:
    """Every function in this file whose body compares or filters on `FeedItem.id`, by name
    and line — a module-level use (none expected) is reported as `("<module>", 0)`."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[str, int]] = []

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[str] = []

        def _enter(self, node: ast.AST, name: str) -> None:
            self.stack.append(name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._enter(node, node.name)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._enter(node, node.name)

        def visit_Attribute(self, node: ast.Attribute) -> None:
            if (
                node.attr == "id"
                and isinstance(node.value, ast.Name)
                and node.value.id == "FeedItem"
            ):
                found.append((self.stack[-1] if self.stack else "<module>", node.lineno))
            self.generic_visit(node)

    Visitor().visit(tree)
    return found


def test_every_by_id_feed_item_read_goes_through_the_one_door() -> None:
    offenders: list[str] = []
    for path in sorted(APP.rglob("*.py")):
        rel = str(path.relative_to(APP.parents[0]))
        reads = _feed_item_id_reads(path)
        if not reads:
            continue
        allowed_here = ALLOWED.get(rel, frozenset())
        for func, line in reads:
            if func not in allowed_here:
                offenders.append(f"{rel}:{line} in {func}() reads FeedItem.id directly")
    assert offenders == [], (
        "a by-id FeedItem read outside rank.require_item (or the two bulk fetches that apply "
        "the same private_to rule item by item) can skip the private_to check:\n"
        + "\n".join(offenders)
    )


def test_twin_and_clips_have_no_feed_item_id_read_of_their_own() -> None:
    """The two routes the leak was found in by name: neither reads `FeedItem` by id any more,
    they only call `rank.require_item`."""
    from app.delivery.feed import clips, twin

    assert "FeedItem.id" not in inspect.getsource(twin)
    assert "FeedItem.id" not in inspect.getsource(clips)


def test_record_engagement_with_a_passed_item_still_checks_private_to() -> None:
    """`record_engagement` takes an already-fetched `item` too (`record_events`' own path):
    the source names the check explicitly, so the fast path cannot silently trust a caller's
    item without it."""
    from app.delivery.feed import engagement

    source = inspect.getsource(engagement.record_engagement)
    assert "item.private_to" in source


async def _private_card(sg: AsyncSession, *, owner: KeyContext) -> FeedItem:
    state = await current_state(sg, context=owner)
    lines = Lines(
        language="en",
        headline="What you asked about",
        body=["This explains your kidney number in simple words."],
        voice=["This explains your kidney number in simple words."],
        why="You asked about this twice.",
    )
    return await create_item(
        sg,
        context=owner,
        state=state,
        type=CardType.STORY,
        lines=lines,
        why=Why(kind="asked_topic", plain="You asked about this twice."),
        scope=Scope.ASK,
        deliver_to=DeliverTo.PATIENT,
        day=today_for(owner).key,
        dedupe_key="asked:kidney:engagement",
        expires_at=now() + timedelta(days=7),
        private_to=owner.person_id,
    )


async def test_record_engagement_refuses_a_private_card_to_another_person(
    sg: AsyncSession,
) -> None:
    """The single-item route (`record_engagement`, `POST /feed/{item}/engagement`): a chief
    holding every scope the card rests on still may not engage with a card private to him."""
    home = await household(sg)
    owner = await home.ctx(sg, home.pa)
    chief = await home.ctx(sg, home.mei)  # ALL_SCOPES, ASK included
    card = await _private_card(sg, owner=owner)

    async with refused_unit(sg, NoSuchItem):
        await record_engagement(sg, context=chief, item_id=card.id, kind=EngagementKind.SEEN)
    # He may, of course.
    his = await record_engagement(sg, context=owner, item_id=card.id, kind=EngagementKind.SEEN)
    assert his.item_id == card.id


async def test_record_events_skips_a_private_card_for_another_person(sg: AsyncSession) -> None:
    """The bulk offline-queue path (`record_events`, what a phone flushes after being
    offline): the fifth site the leak was found in. It never raises per event — a bad event
    is skipped and the rest of the queue still writes — so it cannot call `require_item`
    directly; it applies the same rule, `rank._visible`, item by item instead."""
    home = await household(sg)
    owner = await home.ctx(sg, home.pa)
    chief = await home.ctx(sg, home.mei)
    card = await _private_card(sg, owner=owner)

    queued = Queued(client_id=uuid.uuid4(), item_id=card.id, kind=EngagementKind.SEEN, at=now())
    flushed = await record_events(sg, context=chief, events=[queued])
    assert flushed.written == []
    assert flushed.skipped == [(queued.client_id, "out_of_scope")]
    assert (
        await sg.scalars(select(Engagement).where(Engagement.item_id == card.id))
    ).all() == []

    # The owner's own queue, naming the same card, writes.
    his_queued = Queued(client_id=uuid.uuid4(), item_id=card.id, kind=EngagementKind.SEEN, at=now())
    his_flushed = await record_events(sg, context=owner, events=[his_queued])
    assert [e.item_id for e in his_flushed.written] == [card.id]
