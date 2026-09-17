"""The content library: Activities, Care Services, Resources and Community.

Four features, one rule that binds all of them: an unreviewed item is never shown as if it
were checked (docs/design-direction.md). `fixtures.seed` writes the curated set and queues
every item under the very same pharmacist review queue a card's first fifty go through
(ADR 0007); nothing is visible until a pharmacist decides it, region and language never
cross, and a missing, still-pending or another region's item all refuse the same way.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.delivery.content import fixtures
from app.delivery.content.catalogue import ITEMS
from app.delivery.content.models import COMMUNITY_TYPES, ContentItem
from app.delivery.content.service import (
    NoSuchContentItem,
    list_content,
    read_content,
)
from app.delivery.feed.models import CardType, ReviewStatus
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.language import review
from app.language.models import ReviewItem, Verdict
from app.language.review import KEPT_AS_WRITTEN, REVIEWED_TYPES, Staff
from app.regions import Region
from tests.api import bearer, own_profile, register_by_phone
from tests.conftest import STAFF_TOKEN, Deployment

PHARMACIST = Staff("pharmacist")
PA = "+6591230001"


def context_for(region: Region, scopes: frozenset[Scope] | None = None) -> KeyContext:
    return KeyContext(
        profile_id=uuid.uuid4(),
        region=region,
        person_id=uuid.uuid4(),
        scopes=scopes if scopes is not None else frozenset({Scope.PROFILE}),
    )


async def _approve_all(session: AsyncSession) -> None:
    for item in (await session.scalars(select(ReviewItem))).all():
        if item.verdict is Verdict.PENDING:
            await review.decide(
                session, staff=PHARMACIST, item_id=item.id, verdict=Verdict.APPROVED
            )


# --- the catalogue itself -------------------------------------------------------------------


def test_every_content_type_is_in_the_catalogue() -> None:
    """A type the review guard expects (`test_review_queue.py`) is not fixture content the
    catalogue forgot, and the other way round."""
    content_types = {
        CardType.ACTIVITY,
        CardType.CARE_SERVICE,
        CardType.RESOURCE,
        CardType.LOCAL_EVENT,
        CardType.VOLUNTEER,
        CardType.SUPPORT_GROUP,
    }
    assert content_types <= set(REVIEWED_TYPES)
    assert content_types <= KEPT_AS_WRITTEN
    assert {spec.content_type for spec in ITEMS} == content_types
    assert {spec.region for spec in ITEMS} == {Region.SG, Region.MY}


def test_the_fixture_set_is_small_and_has_every_language() -> None:
    items = fixtures.fixture_items()
    assert len(items) == len(ITEMS) * 3
    for item in items:
        assert item.language in ("en", "ms", "zh")
        assert item.title.strip()
        assert item.summary.strip()
        assert item.body


# --- seeding and review gate together ---------------------------------------------------------


async def test_seeding_queues_every_item_and_nothing_shows_before_review(sg: AsyncSession) -> None:
    written = await fixtures.seed(sg)
    assert len(written) == len(ITEMS) * 3
    assert all(row.review_status is ReviewStatus.PENDING for row in written)
    assert all(row.review_item_id is not None for row in written)

    context = context_for(Region.SG)
    found = await list_content(sg, context=context, content_types=(CardType.ACTIVITY,))
    assert found == []


async def test_seeding_is_idempotent(sg: AsyncSession) -> None:
    first = await fixtures.seed(sg)
    second = await fixtures.seed(sg)
    assert {row.id for row in first} == {row.id for row in second}
    rows = (await sg.scalars(select(ContentItem))).all()
    assert len(rows) == len(first)


async def test_an_approved_item_shows_and_a_rejected_one_never_does(sg: AsyncSession) -> None:
    await fixtures.seed(sg)
    activity = (
        await sg.scalar(
            select(ContentItem).where(
                ContentItem.content_type == CardType.ACTIVITY,
                ContentItem.region == Region.SG,
                ContentItem.language == "en",
            )
        )
    )
    assert activity is not None
    other = (
        await sg.scalars(
            select(ContentItem).where(
                ContentItem.content_type == CardType.ACTIVITY,
                ContentItem.region == Region.SG,
                ContentItem.language == "en",
                ContentItem.id != activity.id,
            )
        )
    ).first()
    assert other is not None

    approved_item = await sg.get(ReviewItem, activity.review_item_id)
    assert approved_item is not None
    await review.decide(sg, staff=PHARMACIST, item_id=approved_item.id, verdict=Verdict.APPROVED)
    rejected_item = await sg.get(ReviewItem, other.review_item_id)
    assert rejected_item is not None
    await review.decide(
        sg, staff=PHARMACIST, item_id=rejected_item.id, verdict=Verdict.REJECTED, reason="stale"
    )

    context = context_for(Region.SG)
    found = await list_content(sg, context=context, content_types=(CardType.ACTIVITY,))
    ids = {item.id for item in found}
    assert activity.id in ids
    assert other.id not in ids

    read = await read_content(
        sg, context=context, item_id=activity.id, content_types=(CardType.ACTIVITY,)
    )
    assert read.id == activity.id

    try:
        await read_content(
            sg, context=context, item_id=other.id, content_types=(CardType.ACTIVITY,)
        )
    except NoSuchContentItem:
        pass
    else:
        raise AssertionError("a rejected item must never be read back")


async def test_a_missing_item_and_a_pending_one_refuse_the_same_way(sg: AsyncSession) -> None:
    await fixtures.seed(sg)
    context = context_for(Region.SG)
    pending = await sg.scalar(
        select(ContentItem).where(
            ContentItem.content_type == CardType.ACTIVITY, ContentItem.language == "en"
        )
    )
    assert pending is not None
    for item_id in (pending.id, uuid.uuid4()):
        try:
            await read_content(
                sg, context=context, item_id=item_id, content_types=(CardType.ACTIVITY,)
            )
        except NoSuchContentItem:
            continue
        raise AssertionError("a pending item and a missing one both refuse")


# --- region and language ----------------------------------------------------------------------


async def test_region_never_crosses(sg: AsyncSession) -> None:
    """Two regions' rows can sit in the same database (as they never would in a real
    deployment, one per country); the service is what must never let them cross."""
    await fixtures.seed(sg)
    await _approve_all(sg)

    sg_found = await list_content(
        sg, context=context_for(Region.SG), content_types=(CardType.ACTIVITY,)
    )
    my_found = await list_content(
        sg, context=context_for(Region.MY), content_types=(CardType.ACTIVITY,)
    )
    assert sg_found and my_found
    assert {item.region for item in sg_found} == {Region.SG}
    assert {item.region for item in my_found} == {Region.MY}
    assert {item.id for item in sg_found}.isdisjoint({item.id for item in my_found})

    # An SG item read from a MY context is the same refusal as one that does not exist.
    an_sg_item = sg_found[0]
    try:
        await read_content(
            sg,
            context=context_for(Region.MY),
            item_id=an_sg_item.id,
            content_types=(CardType.ACTIVITY,),
        )
    except NoSuchContentItem:
        pass
    else:
        raise AssertionError("another region's item must not be read")


async def test_his_own_language_and_english_when_his_has_none_approved_yet(
    sg: AsyncSession,
) -> None:
    await fixtures.seed(sg)
    rows = (
        await sg.scalars(
            select(ContentItem).where(
                ContentItem.content_type == CardType.ACTIVITY,
                ContentItem.region == Region.SG,
                ContentItem.slug == "activity-chair-exercise",
            )
        )
    ).all()
    by_language = {row.language: row for row in rows}
    assert set(by_language) == {"en", "ms", "zh"}
    # Only the English row of this item is approved; Malay and Chinese still wait.
    review_item = await sg.get(ReviewItem, by_language["en"].review_item_id)
    assert review_item is not None
    await review.decide(sg, staff=PHARMACIST, item_id=review_item.id, verdict=Verdict.APPROVED)

    context = context_for(Region.SG)
    in_malay = await list_content(
        sg, context=context, content_types=(CardType.ACTIVITY,), language="ms"
    )
    assert any(item.id == by_language["en"].id for item in in_malay), (
        "no Malay row is approved yet, so English stands in rather than showing nothing"
    )

    in_english = await list_content(
        sg, context=context, content_types=(CardType.ACTIVITY,), language="en"
    )
    assert any(item.id == by_language["en"].id for item in in_english)


async def test_category_narrows_the_list(sg: AsyncSession) -> None:
    await fixtures.seed(sg)
    await _approve_all(sg)
    context = context_for(Region.SG)
    physio = await list_content(
        sg, context=context, content_types=(CardType.CARE_SERVICE,), category="physiotherapy"
    )
    assert physio and all(item.category == "physiotherapy" for item in physio)


async def test_community_is_its_three_kinds(sg: AsyncSession) -> None:
    await fixtures.seed(sg)
    await _approve_all(sg)
    context = context_for(Region.SG)
    every_kind = await list_content(sg, context=context, content_types=COMMUNITY_TYPES)
    assert {item.content_type for item in every_kind} == set(COMMUNITY_TYPES)

    just_groups = await list_content(
        sg, context=context, content_types=(CardType.SUPPORT_GROUP,)
    )
    assert just_groups and all(
        item.content_type is CardType.SUPPORT_GROUP for item in just_groups
    )


async def test_a_key_that_does_not_hold_scope_profile_is_refused(sg: AsyncSession) -> None:
    await fixtures.seed(sg)
    await _approve_all(sg)
    from app.keys.context import OutOfScope

    context = context_for(Region.SG, scopes=frozenset())
    try:
        await list_content(sg, context=context, content_types=(CardType.ACTIVITY,))
    except OutOfScope:
        pass
    else:
        raise AssertionError("no key holds nothing, not even Scope.PROFILE, here")


# --- over HTTP: the same gate, reached the way a person reaches it -----------------------------


async def test_activities_over_http_are_reviewed_before_a_key_holder_sees_them(
    deployment: Deployment,
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")

    before = await deployment.client.get(
        f"/profiles/{profile_id}/activities", headers=bearer(pa["token"])
    )
    assert before.status_code == 200, before.text
    assert before.json()["items"] == []

    async with deployment.sessions() as session:
        await fixtures.seed(session)
        await session.commit()

    queued = await deployment.client.get(
        "/review/queue",
        params={"card_type": "activity", "verdict": "pending"},
        headers=bearer(STAFF_TOKEN),
    )
    assert queued.status_code == 200, queued.text
    items = queued.json()
    assert items, "the fixture activities are queued for a pharmacist"
    for item in items:
        approved = await deployment.client.post(
            f"/review/items/{item['item_id']}/approve",
            json={},
            headers=bearer(STAFF_TOKEN),
        )
        assert approved.status_code == 200, approved.text

    after = await deployment.client.get(
        f"/profiles/{profile_id}/activities", headers=bearer(pa["token"])
    )
    assert after.status_code == 200, after.text
    listed = after.json()["items"]
    assert listed, "an approved activity now shows"
    first_id = listed[0]["id"]

    detail = await deployment.client.get(
        f"/profiles/{profile_id}/activities/{first_id}", headers=bearer(pa["token"])
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["title"] == listed[0]["title"]

    missing = await deployment.client.get(
        f"/profiles/{profile_id}/activities/{uuid.uuid4()}", headers=bearer(pa["token"])
    )
    assert missing.status_code == 404
    assert missing.json() == {"refusal": "NoSuchContentItem"}


async def test_care_services_and_resources_and_community_are_also_wired_over_http(
    deployment: Deployment,
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    async with deployment.sessions() as session:
        await fixtures.seed(session)
        await _approve_all(session)
        await session.commit()

    for path in ("care-services", "resources", "community"):
        answer = await deployment.client.get(
            f"/profiles/{profile_id}/{path}", headers=bearer(pa["token"])
        )
        assert answer.status_code == 200, (path, answer.text)
        assert answer.json()["items"], path

    events_only = await deployment.client.get(
        f"/profiles/{profile_id}/community",
        params={"kind": "support_group"},
        headers=bearer(pa["token"]),
    )
    assert events_only.status_code == 200, events_only.text
    assert all(item["content_type"] == "support_group" for item in events_only.json()["items"])
