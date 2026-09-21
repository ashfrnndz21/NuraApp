"""Past the gate, his story and what Nura found for him take turns (`rank._mixed`), and a
story made again this week is told once (`rank._told_once`).

Measured on the owner's test copy on 22 Sep 2026: 26 story cards — every one of last week's
still alive beside this week's — stood in front of the first of 8 learning cards, six "From
your blood pressure book" in a row. Pure functions over unsaved rows: no database, no clock."""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.delivery.feed import rank
from app.delivery.feed.days import Day
from app.delivery.feed.models import CapsClass, CardType, DeliverTo, FeedItem, Supply
from app.delivery.feed.rank import _patient_supply
from app.delivery.recommend import rules

_START = datetime(2026, 9, 18, 1, 0, tzinfo=UTC)


def _card(
    type_: CardType,
    supply: Supply,
    headline: str,
    key: str,
    *,
    priority: int,
    minutes: int = 0,
) -> FeedItem:
    return FeedItem(
        id=uuid.uuid4(),
        type=type_,
        supply=supply,
        caps_class=CapsClass.SUPPLY,
        deliver_to=DeliverTo.PATIENT,
        headline=headline,
        dedupe_key=key,
        priority=priority,
        why={},
        day="2026-09-22",
        created_at=_START + timedelta(minutes=minutes),
    )


def _order(items: list[FeedItem]) -> list[FeedItem]:
    tz = ZoneInfo("Asia/Singapore")
    now = datetime(2026, 9, 22, 1, 0, tzinfo=UTC)
    day = Day(tz=tz, now=now, local=now.astimezone(tz))
    ordered, held = _patient_supply(items, day=day, declined=set(), quiet=False)
    assert held == Counter()
    return ordered


def _a_week_twice() -> list[FeedItem]:
    cards = [
        _card(CardType.NOW, Supply.NOW, "Your tablets today", "now:2026-09-22", priority=90),
        _card(CardType.GATE, Supply.GATE, "That is all that is new", "gate:2026-09-22", priority=0),
    ]
    for week, minutes in (("2026-W38", 0), ("2026-W39", 60 * 72)):
        for reading in range(6):
            cards.append(
                _card(
                    CardType.STORY,
                    Supply.STORY,
                    "From your blood pressure book",
                    f"story:reading:r{reading}:{week}",
                    priority=30,
                    minutes=minutes + reading,
                )
            )
        cards.append(
            _card(
                CardType.STORY,
                Supply.STORY,
                "From your papers",
                f"story:paper:p1:{week}",
                priority=30,
                minutes=minutes + 10,
            )
        )
    cards.append(
        _card(
            CardType.CLIP,
            Supply.LEARNING,
            "Your blood pressure, in 30 seconds",
            "clip:a",
            priority=25,
        )
    )
    cards.append(
        _card(
            CardType.LEARNING,
            Supply.LEARNING,
            "Taking your blood pressure at home",
            "learning:a",
            priority=20,
        )
    )
    cards.append(
        _card(
            CardType.LEARNING,
            Supply.LEARNING,
            "About your cholesterol",
            "learning:b",
            priority=20,
            minutes=1,
        )
    )
    return cards


def test_a_story_made_again_this_week_is_told_once_and_it_is_the_newer_card() -> None:
    ordered = _order(_a_week_twice())
    story = [item for item in ordered if item.supply is Supply.STORY]
    assert len(story) == 7
    assert all(item.dedupe_key.endswith("2026-W39") for item in story)


def test_the_first_card_past_the_gate_is_one_nura_found_for_him_and_the_clip_leads() -> None:
    ordered = _order(_a_week_twice())
    gate = next(index for index, item in enumerate(ordered) if item.type is CardType.GATE)
    assert [item.type for item in ordered[: gate + 1]] == [CardType.NOW, CardType.GATE]
    assert ordered[gate + 1].type is CardType.CLIP
    assert ordered[gate + 2].supply is Supply.STORY
    assert ordered[gate + 3].supply is Supply.LEARNING


def test_every_learning_card_is_reached_before_the_story_runs_out() -> None:
    ordered = _order(_a_week_twice())
    gate = next(index for index, item in enumerate(ordered) if item.type is CardType.GATE)
    last_learning = max(
        index for index, item in enumerate(ordered) if item.supply is Supply.LEARNING
    )
    assert last_learning - gate <= 5  # three learning cards, a story card between each


def test_no_two_cards_with_one_headline_sit_together_while_another_kind_waits() -> None:
    ordered = _order(_a_week_twice())
    story = [item.headline for item in ordered if item.supply is Supply.STORY]
    assert story[:3] == [
        "From your blood pressure book",
        "From your papers",
        "From your blood pressure book",
    ]


def test_nothing_is_lost_or_said_twice_and_the_order_is_the_same_every_time() -> None:
    cards = _a_week_twice()
    first, second = _order(cards), _order(list(reversed(cards)))
    assert [item.id for item in first] == [item.id for item in second]
    assert len({item.id for item in first}) == len(first) == 2 + 7 + 3


def test_a_feed_with_no_learning_card_keeps_his_story_and_one_with_no_story_keeps_learning() -> (
    None
):
    cards = _a_week_twice()
    only_story = _order([item for item in cards if item.supply is not Supply.LEARNING])
    assert [item.supply for item in only_story[2:]] == [Supply.STORY] * 7
    only_learning = _order([item for item in cards if item.supply is not Supply.STORY])
    assert [item.type for item in only_learning[2:]] == [
        CardType.CLIP,
        CardType.LEARNING,
        CardType.LEARNING,
    ]


def test_one_did_you_know_fact_a_day_the_clip_is_shown_and_its_article_is_held() -> None:
    assert rank.RULE_DID_YOU_KNOW == rules.RULE_DID_YOU_KNOW
    cards = _a_week_twice()
    pick = [
        _card(
            CardType.CLIP, Supply.LEARNING, "Your tablet, in 30 seconds", "clip:dyk", priority=25
        ),
        _card(CardType.LEARNING, Supply.LEARNING, "Your tablet", "learning:dyk", priority=20),
    ]
    yesterday = _card(
        CardType.LEARNING, Supply.LEARNING, "Your sugar tablet", "learning:dyk:old", priority=20
    )
    yesterday.day = "2026-09-21"
    for card in (*pick, yesterday):
        card.why = {"rule": rules.RULE_DID_YOU_KNOW}
    tz = ZoneInfo("Asia/Singapore")
    now = datetime(2026, 9, 22, 1, 0, tzinfo=UTC)
    day = Day(tz=tz, now=now, local=now.astimezone(tz))
    ordered, held = _patient_supply(
        [*cards, *pick, yesterday], day=day, declined=set(), quiet=False
    )
    shown = [item for item in ordered if item.why.get("rule") == rules.RULE_DID_YOU_KNOW]
    assert [item.dedupe_key for item in shown] == ["clip:dyk", "learning:dyk:old"]
    assert held == Counter({"learning": 1})
