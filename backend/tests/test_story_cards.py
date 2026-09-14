"""E21-05 acceptance: story cards from the record.

    Story cards from the record: what the doctor said, number changes, family photos, the
    proud number. Acceptance: story supply regenerates weekly from memory.

Every story card says what memory already holds, a week at a time: the number that only goes
up is his tablet days — the Me page's number, not a count of blood pressures; a blood pressure
that moved is told by its two numbers and which way it went, a lab result by the trend's own
lines against its range, ending on the trend's boundary; what the doctor said is the memos of
a visit whose card he confirmed, once the memo card has moved on; a family photo is on his
story only with the sharer's yes, only for keys that read the family, and not after it is
taken back. On the frozen clock, a week later the supply is made again from what memory holds
then.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import FrozenClock
from app.db import utcnow
from app.delivery.feed.compose import refresh
from app.delivery.feed.compress import FixtureCompressor, FixtureSearcher
from app.delivery.feed.models import CardType, FeedItem
from app.delivery.feed.search import Engine
from app.ingestion.objects import LocalObjectStore
from app.keys.confirm import confirm
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.medicines.service import proud_days, record_dose_taken
from app.reasoning.ranges import FixtureRanges
from app.reasoning.visits.models import ItemState
from app.reasoning.visits.summary import (
    Decision,
    FixtureSummariser,
    confirm_summary,
    post_visit_summary,
    store_transcript,
    summary_draft_for,
    summary_items,
)
from app.regions import Region
from app.safety.boundary import Surface, boundary_line, is_boundary_line
from tests.api import bearer, let_in, own_profile, register_by_phone
from tests.capture_support import b64
from tests.conftest import FEED, Deployment
from tests.medicines_support import REGISTRY, add, label
from tests.paper import LIPID_PANEL, LIPID_PANEL_2025, PNG_SIGNATURE
from tests.trio_api_support import confirm_paper
from tests.visits import ROUTINE, VISIT_AT, VISITS, medicine, pa, reading, transcript, visit

ENGINE = Engine(
    searcher=FixtureSearcher(FEED),
    compressor=FixtureCompressor(FEED),
    registry=REGISTRY,
    ranges=FixtureRanges.load(),
)
PA = "+6591410001"
MEI = "+6591410002"
KIT = "+6591410003"
EVERY_PART = sorted(scope.value for scope in Scope if scope is not Scope.PROFILE)


async def _live(session: AsyncSession, context: KeyContext) -> list[FeedItem]:
    return list(
        await session.scalars(
            select(FeedItem).where(
                FeedItem.profile_id == context.profile_id, FeedItem.expires_at > utcnow()
            )
        )
    )


def _story(cards: list[FeedItem], prefix: str) -> list[FeedItem]:
    return [c for c in cards if c.type is CardType.STORY and c.dedupe_key.startswith(prefix)]


async def test_the_proud_number_is_his_tablet_days_the_number_the_me_page_shows(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    context = await pa(sg, language="en")
    line = (await add(sg, context, label("amlodipine", "5 mg"))).line
    await reading(sg, context, when=clock.now() - timedelta(days=1))
    await record_dose_taken(sg, context=context, line_id=line.id)
    clock.step(timedelta(days=1))
    await record_dose_taken(sg, context=context, line_id=line.id)
    await refresh(sg, context=context, engine=ENGINE)

    [card] = _story(await _live(sg, context), "story:proud:")
    days = (await proud_days(sg, context=context)).days
    assert days == 2 and card.number == "2" and card.direction == "up"
    assert card.headline == "The number that only goes up"
    assert list(card.body) == ["You have taken your tablets on 2 days.", "This number only goes up."]
    assert card.why["plain"] == "Nura counted the days you took your tablets."
    assert card.scope is Scope.MEDICINES
    # A blood pressure written down is not a tablet day, and no card counts one.
    assert not any("written your blood pressure" in line for c in await _live(sg, context) for line in c.body)


async def test_a_blood_pressure_that_moved_is_told_by_its_two_numbers_and_its_direction(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    context = await pa(sg, language="en")
    first = await reading(sg, context, systolic=138, diastolic=84, when=clock.now() - timedelta(days=2))
    latest = await reading(sg, context, systolic=146, diastolic=90, when=clock.now() - timedelta(days=1))
    await refresh(sg, context=context, engine=ENGINE)

    [card] = _story(await _live(sg, context), "story:change:")
    assert card.headline == "How your blood pressure moved"
    assert list(card.body) == [
        "On Wednesday 2 September your blood pressure was 146 over 90.",
        "On Tuesday 1 September it was 138 over 84.",
        "The top number went up.",
    ]
    assert (card.number, card.direction, card.boundary) == ("146/90", "up", None)
    assert card.why["fact_ids"] == [str(latest.id), str(first.id)]
    assert card.scope is Scope.READINGS


async def test_a_lab_result_that_moved_is_told_against_its_range_ending_on_the_trend_boundary(
    deployment: Deployment,
) -> None:
    pa_ = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa_, display_name="Pa", language="en")
    for paper in (LIPID_PANEL, LIPID_PANEL_2025):
        await confirm_paper(deployment, pa_["token"], profile_id, paper)
    got = await deployment.client.get(f"/profiles/{profile_id}/feed", headers=bearer(pa_["token"]))
    assert got.status_code == 200, got.text

    async with deployment.sessions() as session:
        rows = list(await session.scalars(select(FeedItem).where(FeedItem.dedupe_key.like("story:trend:%"))))
    cholesterol = [r for r in rows if r.dedupe_key.startswith("story:trend:total_cholesterol:")]
    assert len(cholesterol) == 1, [r.dedupe_key for r in rows]
    card = cholesterol[0]
    line = boundary_line(Surface.TREND, "en")
    assert card.headline == "Your blood test over time"
    assert card.body[0] == "Your cholesterol was 212 on Friday 29 August 2025."
    assert "The range on your blood test is under 200." in card.body
    assert "It is above the range on your blood test." in card.body
    assert "It has gone down since Thursday 7 September 2023." in card.body
    assert list(card.body[-len(line.splitlines()) :]) == line.splitlines()
    assert card.boundary == line and is_boundary_line(Surface.TREND, card.boundary)
    assert card.supply.value == "story" and card.scope is Scope.RECORDS


async def test_what_the_doctor_said_is_told_again_once_the_memo_card_has_moved_on(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    context = await pa(sg, language="en")
    await reading(sg, context)
    await medicine(sg, context, generic="frusemide", strength="40 mg")
    _provider, appointment = await visit(sg, context)
    store = LocalObjectStore(tmp_path, Region.SG)
    clock.set(VISIT_AT + timedelta(hours=1))
    kept = await store_transcript(
        sg, context=context, store=store, text=transcript(ROUTINE), captured_at=VISIT_AT
    )
    summary = await post_visit_summary(
        sg,
        context=context,
        appointment_id=appointment.id,
        artifact_id=kept.id,
        store=store,
        summariser=FixtureSummariser(VISITS),
        registry=REGISTRY,
    )
    items = await summary_items(sg, context=context, summary_id=summary.id)
    decisions = [Decision(item.id, ItemState.CONFIRMED) for item in items]
    draft = await summary_draft_for(sg, context=context, summary_id=summary.id, decisions=decisions)
    yes = await confirm(sg, context, draft)
    await confirm_summary(
        sg,
        context=context,
        summary_id=summary.id,
        decisions=decisions,
        confirmation_id=yes.id,
        registry=REGISTRY,
    )

    # While the memo card carries this visit, the story does not tell it a second time.
    await refresh(sg, context=context, engine=ENGINE)
    cards = await _live(sg, context)
    assert [c for c in cards if c.type is CardType.MEMO]
    assert _story(cards, "story:doctor:") == []

    # The memos were filed against the visit on Thursday 15 October; after it, the memo card
    # is done, and the story tells what Dr Tan said.
    clock.set(datetime(2026, 10, 16, 2, 0, tzinfo=UTC))
    await refresh(sg, context=context, engine=ENGINE)
    [told] = _story(await _live(sg, context), "story:doctor:")
    line = boundary_line(Surface.SUMMARY, "en", doctor="Dr Tan")
    assert told.headline == "What Dr Tan said"
    assert told.body[0] == "At your visit on Thursday 10 September, Dr Tan said this:"
    assert "Every morning, stand on the scale before breakfast." in told.body
    # A memo about a medicine is left to the memo card: a later visit may have changed it.
    assert not any("water pill" in line for line in told.body)
    assert told.boundary == line and list(told.body[-len(line.splitlines()) :]) == line.splitlines()
    assert is_boundary_line(Surface.SUMMARY, told.boundary) and told.scope is Scope.VISITS
    assert told.why["visit_id"] == str(appointment.id) and told.why["memo_ids"]


async def _pages(deployment: Deployment, profile_id: str, token: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    cursor: str | None = None
    for _ in range(8):
        params = {"cursor": cursor} if cursor else {}
        page = await deployment.client.get(
            f"/profiles/{profile_id}/feed", params=params, headers=bearer(token)
        )
        assert page.status_code == 200, page.text
        items.extend(page.json()["items"])
        cursor = page.json()["next_cursor"]
        if cursor is None:
            break
    return items


async def test_a_family_photo_is_on_his_story_with_the_sharers_yes_for_the_family_until_taken_back(
    deployment: Deployment,
) -> None:
    client = deployment.client
    pa_ = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa_, display_name="Pa", language="en")
    his = bearer(pa_["token"])
    mei = await register_by_phone(deployment, MEI, "Mei")
    hers = bearer(mei["token"])
    await let_in(deployment, pa_, profile_id, MEI, EVERY_PART, relationship="daughter")
    cut = await client.post(
        f"/profiles/{profile_id}/keys", json={"holder_phone_e164": MEI, "role": "chief"}, headers=his
    )
    assert cut.status_code == 201, cut.text
    kit = await register_by_phone(deployment, KIT, "Kit")
    await let_in(
        deployment, pa_, profile_id, KIT, ["records", "readings"], relationship="son",
        holder_display_name="Kit",
    )
    cut = await client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": KIT, "role": "caregiver", "scopes": ["records", "readings"]},
        headers=his,
    )
    assert cut.status_code == 201, cut.text

    lunch = PNG_SIGNATURE + b"nura-family-photo:lunch"
    photos = f"/profiles/{profile_id}/thread/photos"
    shared = await client.post(
        photos,
        json={"data": b64(lunch), "content_type": "image/png", "caption": "Lunch on Sunday.", "on_his_feed": True},
        headers=hers,
    )
    assert shared.status_code == 201, shared.text
    kept = await client.post(
        photos,
        json={"data": b64(PNG_SIGNATURE + b"just-us"), "content_type": "image/png", "caption": "Just for us.", "on_his_feed": False},
        headers=hers,
    )
    assert kept.status_code == 201, kept.text
    photo_id = shared.json()["photo"]["photo_id"]
    missing = await client.post(
        photos, json={"data": b64(lunch), "content_type": "image/png", "caption": "No yes."}, headers=hers
    )
    assert missing.status_code == 422  # the sharer's yes is asked every time; no default

    cards = [c for c in await _pages(deployment, profile_id, pa_["token"]) if c["why"].get("photo_id")]
    assert {c["why"]["photo_id"] for c in cards} == {photo_id}
    card = cards[0]
    assert card["headline"] == "A photo from Mei" and card["scope"] == "family"
    assert card["body"] == ["Mei shared this photo on Thursday 3 September."]
    assert card["why"]["plain"] == "Mei chose to share this photo with you."

    content = f"{photos}/{photo_id}/content"
    seen = await client.get(content, headers=his)
    assert seen.status_code == 200 and seen.content == lunch
    not_family = await client.get(content, headers=bearer(kit["token"]))
    assert not_family.status_code == 403 and not_family.json() == {"refusal": "OutOfScope", "scope": "family"}
    thread = await client.get(f"/profiles/{profile_id}/thread", headers=his)
    on_it = [e for e in thread.json()["entries"] if e["photo"]]
    assert {e["photo"]["photo_id"] for e in on_it} == {photo_id, kept.json()["photo"]["photo_id"]}

    # Only the sharer takes it back; then nobody sees it, on his story or by its bytes.
    his_try = await client.post(f"{photos}/{photo_id}/take-back", headers=his)
    assert his_try.status_code == 403 and his_try.json() == {"refusal": "NotTheirsToTakeBack"}
    back = await client.post(f"{photos}/{photo_id}/take-back", headers=hers)
    assert back.status_code == 200 and back.json()["taken_back"] is True
    gone = await client.get(content, headers=his)
    assert gone.status_code == 404 and gone.json() == {"refusal": "NoSuchPhoto"}
    after = await _pages(deployment, profile_id, pa_["token"])
    assert not [c for c in after if c["why"].get("photo_id") == photo_id]
    thread = await client.get(f"/profiles/{profile_id}/thread", headers=his)
    assert photo_id not in {e["photo"]["photo_id"] for e in thread.json()["entries"] if e["photo"]}


async def test_the_story_supply_regenerates_weekly_from_memory_on_the_frozen_clock(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(datetime(2026, 9, 14, 2, 0, tzinfo=UTC))  # Monday 14 September, 10 in the morning
    context = await pa(sg, language="en")
    await reading(sg, context, systolic=138, diastolic=84, when=clock.now() - timedelta(days=3))
    await reading(sg, context, systolic=142, diastolic=88, when=clock.now() - timedelta(days=2))
    await refresh(sg, context=context, engine=ENGINE)
    first = {c.dedupe_key: c for c in await _live(sg, context) if c.type is CardType.STORY}
    assert first and all(key.endswith(":2026-W38") for key in first)
    assert any(key.startswith("story:change:") for key in first)

    # A week on, with a new number written down: the week's cards have lapsed, and the story
    # is made again from what memory holds now.
    clock.step(timedelta(days=7))
    newest = await reading(sg, context, systolic=150, diastolic=92, when=clock.now() - timedelta(days=1))
    await refresh(sg, context=context, engine=ENGINE)
    second = {c.dedupe_key: c for c in await _live(sg, context) if c.type is CardType.STORY}
    assert second and all(key.endswith(":2026-W39") for key in second)
    assert not set(first) & set(second)
    [moved] = [c for key, c in second.items() if key.startswith("story:change:")]
    assert moved.dedupe_key == f"story:change:{newest.id}:2026-W39"
    assert moved.body[0] == "On Sunday 20 September your blood pressure was 150 over 92."
    # Refreshing again inside the week makes nothing new.
    _, again = await refresh(sg, context=context, engine=ENGINE)
    assert [c for c in again if c.type is CardType.STORY] == []
