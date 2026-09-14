"""E11-03: card grammar — one number, one direction, one colour, one action.

`grammar.check` is the rule and `items.create_item` enforces it: a card that shows a number
it does not say, a direction with no number, a colour that is not the State wash, or a
headline with two numbers is refused and not written. Every card the feed composes carries
its colour and its one action; his reading shows one number and which way it went.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import FrozenClock
from app.delivery.feed.compose import refresh, today_for
from app.delivery.feed.grammar import (
    Action,
    Colour,
    Direction,
    Grammar,
    NotCardGrammar,
    action_for,
    check,
    numbers_in,
)
from app.delivery.feed.items import Why, create_item
from app.delivery.feed.models import CardType, DeliverTo, FeedItem
from app.delivery.strings import render
from app.keys.scopes import Scope
from app.memory.episodic import record_event
from app.memory.models import EventKind, SourceChannel
from app.memory.semantic import assert_fact
from app.state.service import current_state
from tests.test_feed import ENGINE, _pa

MONDAY = datetime(2026, 9, 14, 2, 0, tzinfo=UTC)


def test_a_card_shows_one_number_and_says_it() -> None:
    check(
        Grammar(colour=Colour.STABLE, action=Action.HEAR, number="138/84", direction=Direction.UP),
        headline="Your blood pressure today",
        body=("Your blood pressure today was 138 over 84.",),
    )
    with pytest.raises(NotCardGrammar, match="says the number"):
        check(
            Grammar(colour=Colour.STABLE, action=Action.HEAR, number="150/90"),
            headline="Your blood pressure today",
            body=("Your blood pressure today was 138 over 84.",),
        )
    with pytest.raises(NotCardGrammar, match="one value or one reading"):
        check(
            Grammar(colour=Colour.STABLE, action=Action.HEAR, number="138, 140"),
            headline="Your blood pressure",
            body=("138 and 140.",),
        )


def test_a_direction_sits_beside_a_number() -> None:
    with pytest.raises(NotCardGrammar, match="direction"):
        check(
            Grammar(colour=Colour.WATCH, action=Action.HEAR, direction=Direction.DOWN),
            headline="Your blood pressure",
            body=("It is in your blood pressure book.",),
        )


def test_the_colour_is_the_state_wash_never_red() -> None:
    with pytest.raises(ValueError):
        Colour("red")
    with pytest.raises(NotCardGrammar, match="State wash"):
        check(
            Grammar(colour="red", action=Action.HEAR),  # type: ignore[arg-type]
            headline="Your tablets today",
            body=("Your tablets for today are on your list.",),
        )
    assert {colour.value for colour in Colour} == {"stable", "watch", "act"}


def test_one_number_in_a_headline_and_the_day_is_not_a_number() -> None:
    assert numbers_in("Dr Tan on Monday 14 September") == []
    assert numbers_in("9月14日星期一见Dr Tan") == []
    assert numbers_in("Your blood pressure was 138 over 84") == ["138", "84"]
    with pytest.raises(NotCardGrammar, match="headline"):
        check(
            Grammar(colour=Colour.STABLE, action=Action.HEAR),
            headline="138 over 84 and 140 over 86",
            body=("Two numbers.",),
        )


def test_each_kind_of_card_has_exactly_one_action() -> None:
    assert action_for(CardType.NOW, Scope.MEDICINES, DeliverTo.PATIENT) is Action.TAKEN
    assert action_for(CardType.NOW, Scope.PROFILE, DeliverTo.PATIENT) is Action.KEEP_GOING
    assert action_for(CardType.FLAG, Scope.EMERGENCY, DeliverTo.PATIENT) is Action.CALL
    assert action_for(CardType.FLAG, Scope.EMERGENCY, DeliverTo.CAREGIVER) is Action.OPEN
    assert action_for(CardType.REORDER, Scope.MEDICINES, DeliverTo.PATIENT) is Action.ASK_TO_ORDER
    assert action_for(CardType.GATE, Scope.PROFILE, DeliverTo.PATIENT) is Action.KEEP_GOING
    assert action_for(CardType.READING, Scope.READINGS, DeliverTo.PATIENT) is Action.HEAR


async def _reading(session: AsyncSession, context: object, top: int, bottom: int) -> None:
    moment = await record_event(
        session,
        context=context,  # type: ignore[arg-type]
        kind=EventKind.READING,
        occurred_at=datetime.now(UTC),
        source_channel=SourceChannel.APP,
        label="blood pressure",
    )
    await assert_fact(
        session,
        context=context,  # type: ignore[arg-type]
        subject="blood_pressure",
        attribute="reading",
        value={"systolic": top, "diastolic": bottom},
        confidence=1.0,
        event_id=moment.id,
    )


async def test_a_card_that_breaks_the_grammar_is_not_written(sg: AsyncSession) -> None:
    owner = await _pa(sg)
    state = await current_state(sg, context=owner)
    day = today_for(owner)
    lines = render(
        "reading", "en", body=("reading", "reading_alone"), top_number=138, bottom_number=84
    )
    with pytest.raises(NotCardGrammar):
        await create_item(
            sg,
            context=owner,
            state=state,
            type=CardType.READING,
            lines=lines,
            why=Why(kind="reading", plain=lines.why),
            scope=Scope.READINGS,
            deliver_to=DeliverTo.PATIENT,
            day=day.key,
            dedupe_key="reading:broken",
            expires_at=day.ends_at,
            number="150/90",
        )
    assert (await sg.scalars(select(FeedItem))).all() == []


async def test_every_card_the_feed_makes_carries_its_colour_and_one_action(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(MONDAY - timedelta(days=1))
    owner = await _pa(sg)
    await _reading(sg, owner, 130, 80)
    clock.set(MONDAY)
    await _reading(sg, owner, 138, 84)
    await refresh(sg, context=owner, engine=ENGINE)
    items = (await sg.scalars(select(FeedItem))).all()
    assert items
    for item in items:
        assert item.colour in {colour.value for colour in Colour}, item.type
        assert item.action in {action.value for action in Action}, item.type
    today = next(item for item in items if item.type is CardType.READING)
    assert today.number == "138/84" and today.direction == "up"
    count = next(item for item in items if item.dedupe_key.startswith("story:count"))
    assert count.number == "2" and count.direction == "up"
