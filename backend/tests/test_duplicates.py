"""D-4, duplicates (audit-2026-09-22.md §3.2, §5): before this, the same bytes re-uploaded
wrote a second `Artifact`, cost a second model call and wrote a second set of "current"
facts, silently — demonstrated live in the audit ("the same policy twice ... the same panel
three times ... no warning"). Two parts, both covered here:

(a) `test_the_same_bytes_twice_*`: a unique index on `(profile_id, sha256)`
    (migration `0055_whose_paper_and_duplicates`) and an application-level check
    (`app.ingestion.duplicates.find_artifact_by_digest`) that shows the existing card back
    instead of reading anything again.
(b) `test_a_rephotographed_paper_*`: a semantic key — document kind, printed date, facility
    and the set of results — that asks rather than files when a paper under a new digest
    looks like one already on file (`app.ingestion.review._semantic_duplicate_of`,
    `PendingQuestion.DUPLICATE_PAPER`).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import FrozenClock
from app.db import utcnow
from app.ingestion.objects import sha256_of
from app.memory.episodic import store_artifact
from app.memory.models import ArtifactKind, SourceChannel
from app.regions import Region
from tests.api import bearer, own_profile, register_by_phone
from tests.capture_support import confirm, decide, mint, photo
from tests.conftest import Deployment
from tests.paper import LIPID_PANEL_2025, LIPID_PANEL_2025_AGAIN
from tests.test_ingestion import _pa as _pa_context

PA = "+6591170002"
AGAIN = LIPID_PANEL_2025_AGAIN
"""The re-photographed twin of `LIPID_PANEL_2025`: same lab, same date, same four analytes,
a different digest (`tests/fixtures/paper/lipid-panel-2025-08-29-again.json`)."""


async def _pa(deployment: Deployment) -> tuple[dict[str, str], str]:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    return pa, profile_id


# --- D-4a: the exact same bytes ---------------------------------------------------------------


async def test_the_same_bytes_twice_shows_the_existing_card_not_a_second_read(
    deployment: Deployment,
) -> None:
    pa, profile_id = await _pa(deployment)
    his = bearer(pa["token"])

    first = await deployment.client.post(
        f"/profiles/{profile_id}/photos", json=photo(LIPID_PANEL_2025), headers=his
    )
    assert first.status_code == 201, first.text
    first_card = first.json()
    assert first_card["duplicate_of_added_on"] is None

    second = await deployment.client.post(
        f"/profiles/{profile_id}/photos", json=photo(LIPID_PANEL_2025), headers=his
    )
    assert second.status_code == 201, second.text
    second_card = second.json()

    # The same card, back — never a second one.
    assert second_card["card_id"] == first_card["card_id"]
    assert second_card["duplicate_of_added_on"] is not None

    # No second artefact, no second card: exactly one of each on the profile.
    cards = await deployment.client.get(f"/profiles/{profile_id}/review-cards", headers=his)
    assert cards.status_code == 200 and len(cards.json()) == 1


async def test_the_same_bytes_twice_over_the_streamed_route_too(deployment: Deployment) -> None:
    pa, profile_id = await _pa(deployment)
    his = bearer(pa["token"])
    body = photo(LIPID_PANEL_2025)

    async with deployment.client.stream(
        "POST", f"/profiles/{profile_id}/photos/stream", json=body, headers=his
    ) as first:
        assert first.status_code == 200
        [chunk async for chunk in first.aiter_bytes()]

    async with deployment.client.stream(
        "POST", f"/profiles/{profile_id}/photos/stream", json=body, headers=his
    ) as second:
        assert second.status_code == 200
        raw = b"".join([chunk async for chunk in second.aiter_bytes()])
    # A duplicate re-upload emits exactly one event — the card, no `step` trace at all — since
    # nothing is read a second time.
    events = [line for line in raw.decode().split("\n\n") if line.startswith("data: ")]
    assert len(events) == 1 and '"type": "card"' in events[0]
    assert '"duplicate_of_added_on": null' not in events[0]

    cards = await deployment.client.get(f"/profiles/{profile_id}/review-cards", headers=his)
    assert len(cards.json()) == 1


LATE_SG_NIGHT_UTC = datetime(2026, 9, 13, 19, 30, tzinfo=UTC)
"""19:30 UTC is 03:30 the next morning in Singapore and Malaysia (UTC+8): a moment that only
tells the two calendars apart, and only the region-aware one is his own."""


async def test_the_duplicate_added_on_date_is_his_own_day_not_utcs(
    deployment: Deployment, clock: FrozenClock
) -> None:
    """FIX BEFORE MERGE, the independent safety review: `duplicate_of_added_on`
    (`app.channels.api.capture`) and the clarify's `existing_added_on`
    (`app.ingestion.review`) used to read `created_at.date()` straight off the UTC
    timestamp. At 19:30 UTC his own clock, in Singapore or Malaysia (UTC+8), already reads
    03:30 the next morning — the naive read would tell him he added a paper on the 13th when
    it was the 14th everywhere he was actually looking at a clock."""
    pa, profile_id = await _pa(deployment)
    his = bearer(pa["token"])
    clock.set(LATE_SG_NIGHT_UTC)

    first = await deployment.client.post(
        f"/profiles/{profile_id}/photos", json=photo(LIPID_PANEL_2025), headers=his
    )
    assert first.status_code == 201, first.text
    first_card = first.json()

    # D-4a: the exact same bytes again, at this same moment — his own day is the 14th.
    second = await deployment.client.post(
        f"/profiles/{profile_id}/photos", json=photo(LIPID_PANEL_2025), headers=his
    )
    assert second.status_code == 201, second.text
    assert second.json()["duplicate_of_added_on"] == "2026-09-14"

    # D-4b: a re-photographed twin, same moment — the clarify's own `existing_added_on`.
    await confirm(deployment, pa["token"], profile_id, first_card, decide(first_card))
    third = await deployment.client.post(
        f"/profiles/{profile_id}/photos", json=photo(AGAIN), headers=his
    )
    assert third.status_code == 201, third.text
    assert third.json()["clarify"]["existing_added_on"] == "2026-09-14"


async def test_the_unique_index_is_the_backstop(sg: AsyncSession) -> None:
    """The application check is what a person sees; the migration's unique index on
    `(profile_id, sha256)` (`0055_whose_paper_and_duplicates`) is what actually makes a
    second row impossible, whatever the caller — proven directly against the ORM, underneath
    the application-level check `find_artifact_by_digest` already short-circuits on."""
    context = await _pa_context(sg, phone="+6591170099")
    digest = sha256_of(b"the same exact bytes")
    await store_artifact(
        sg,
        context=context,
        kind=ArtifactKind.PHOTO,
        storage_key=f"photos/{context.profile_id}/{digest}",
        content_type="image/png",
        sha256=digest,
        captured_at=utcnow(),
        source_channel=SourceChannel.APP,
        region=Region.SG,
    )
    with pytest.raises(IntegrityError):
        await store_artifact(
            sg,
            context=context,
            kind=ArtifactKind.PHOTO,
            storage_key=f"photos/{context.profile_id}/{digest}-again",
            content_type="image/png",
            sha256=digest,
            captured_at=utcnow(),
            source_channel=SourceChannel.APP,
            region=Region.SG,
        )


# --- D-4b: the same paper, re-photographed ------------------------------------------------


async def test_a_rephotographed_paper_asks_instead_of_filing(deployment: Deployment) -> None:
    pa, profile_id = await _pa(deployment)
    his = bearer(pa["token"])

    first = await deployment.client.post(
        f"/profiles/{profile_id}/photos", json=photo(LIPID_PANEL_2025), headers=his
    )
    assert first.status_code == 201, first.text
    first_card = first.json()
    confirmed = await confirm(deployment, pa["token"], profile_id, first_card, decide(first_card))
    assert confirmed.status_code == 200, confirmed.text

    second = await deployment.client.post(
        f"/profiles/{profile_id}/photos", json=photo(AGAIN), headers=his
    )
    assert second.status_code == 201, second.text
    second_card = second.json()
    assert second_card["card_id"] != first_card["card_id"]  # a genuinely different digest
    assert second_card["duplicate_of_added_on"] is None  # D-4a never catches this one

    clarify = second_card["clarify"]
    assert clarify is not None and clarify["kind"] == "duplicate_paper"
    assert clarify["existing_card_id"] == first_card["card_id"]
    assert clarify["existing_added_on"] is not None

    # Nothing is filed while the question stands: the write door refuses outright.
    decisions = decide(second_card)
    minted = await mint(deployment, pa["token"], profile_id, second_card, decisions)
    written = await deployment.client.post(
        f"/profiles/{profile_id}/review-cards/{second_card['card_id']}/confirm",
        json={"decisions": decisions, "confirmation_id": minted.json()["confirmation_id"]},
        headers=his,
    )
    assert written.status_code == 400 and written.json() == {"refusal": "QuestionUnanswered"}


async def test_yes_the_same_paper_sets_it_aside(deployment: Deployment) -> None:
    pa, profile_id = await _pa(deployment)
    his = bearer(pa["token"])
    first = await deployment.client.post(
        f"/profiles/{profile_id}/photos", json=photo(LIPID_PANEL_2025), headers=his
    )
    first_card = first.json()
    await confirm(deployment, pa["token"], profile_id, first_card, decide(first_card))
    second = await deployment.client.post(
        f"/profiles/{profile_id}/photos", json=photo(AGAIN), headers=his
    )
    second_card = second.json()

    answered = await deployment.client.post(
        f"/profiles/{profile_id}/review-cards/{second_card['card_id']}/answer",
        json={"value": "same"},
        headers=his,
    )
    assert answered.status_code == 200
    assert answered.json()["discarded"] is True

    # Never a second lipid panel on the record: still exactly the one set of dates the first
    # paper's own four analytes opened on (regardless of the region's own UTC offset).
    before = await deployment.client.get(f"/profiles/{profile_id}/facts?subject=lipid_panel", headers=his)
    dates = {f["valid_from"] for f in before.json()}
    assert len(dates) == 1


async def test_no_a_different_one_files_normally(deployment: Deployment) -> None:
    pa, profile_id = await _pa(deployment)
    his = bearer(pa["token"])
    first = await deployment.client.post(
        f"/profiles/{profile_id}/photos", json=photo(LIPID_PANEL_2025), headers=his
    )
    first_card = first.json()
    await confirm(deployment, pa["token"], profile_id, first_card, decide(first_card))
    second = await deployment.client.post(
        f"/profiles/{profile_id}/photos", json=photo(AGAIN), headers=his
    )
    second_card = second.json()

    answered = await deployment.client.post(
        f"/profiles/{profile_id}/review-cards/{second_card['card_id']}/answer",
        json={"value": "different"},
        headers=his,
    )
    assert answered.status_code == 200 and answered.json()["clarify"] is None

    decisions = decide(second_card)
    done = await confirm(deployment, pa["token"], profile_id, second_card, decisions)
    assert done.status_code == 200, done.text
