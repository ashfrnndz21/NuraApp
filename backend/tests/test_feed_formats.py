"""F1: the feed's richer formats, walked over HTTP the way the app and the chief's Home use them.

    E09-06  a condition's explainer clip in his language: 20–30 s, captions, narration
    E11-09  the weekly recap clip, over a still, with captions
    E09-07  dengue, haze and heat only when a condition makes them relevant; seasons
    E11-08  engagement feedback: the phone's queue; the format adapts to what he opens
    spec §1 "Sent to Pa this week" and "Watching for Pa"; spec §0 the ask bar's filters

The clock is frozen at 2026-09-03 08:00 UTC — Thursday, 16:00 on the Singapore and Penang
wall — and stepped where a test needs another day, another week or another season.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select

from app.audit.models import Outcome
from app.audit.trail import read_audit
from app.clock import FrozenClock
from app.db import utcnow
from app.delivery.feed import clips as clip_module
from app.delivery.feed.clips import (
    ClipAsk,
    Rendered,
    caption_cues,
    captions,
    clip_video,
    may_excerpt,
)
from app.delivery.feed.compose import refresh
from app.delivery.feed.compress import FixtureCompressor, FixtureSearcher, Found
from app.delivery.feed.find import find
from app.delivery.feed.local import check_area, relevant_to
from app.delivery.feed.models import (
    PLAYS,
    CardType,
    DeliverTo,
    Engagement,
    EngagementKind,
    FeedItem,
    JobKind,
    SearchJob,
)
from app.delivery.feed.search import Engine
from app.drugs.fixture import FixtureRegistry
from app.keys.context import KeyContext, resolve_key_context
from app.memory.episodic import record_event, store_artifact
from app.memory.models import ArtifactKind, EventKind, SourceChannel
from app.memory.semantic import assert_fact
from app.regions import Region
from app.safety.plain_words import verify
from tests.api import bearer, let_in, own_profile, register_by_phone
from tests.conftest import FEED, Deployment, _serve

PA = "+6591410001"
MEI = "+6591410002"
SITI = "+6591410003"
PA_MY = "+60121410001"
MEI_MY = "+60121410002"

APP = Path(__file__).resolve().parent.parent / "app"
BOUNDARY_EN = ["Nura explains one thing in simple words.", "This is not a doctor's advice."]
EVERY_PART = [
    "medicines",
    "visits",
    "readings",
    "records",
    "notes",
    "money",
    "family",
    "emergency",
    "ask",
    "send",
]


@pytest.fixture
async def penang() -> AsyncIterator[Deployment]:
    """The Malaysian backend, served: the allowlist's Malaysian ministry is usable here."""
    async for served in _serve(Region.MY):
        yield served


# --- how a test speaks for him ----------------------------------------------------------------


async def _pa(
    deployment: Deployment, phone: str = PA, language: str = "en"
) -> tuple[dict[str, str], str]:
    pa = await register_by_phone(deployment, phone, "Pa")
    return pa, await own_profile(deployment, pa, language=language)


async def _context(deployment: Deployment, person_id: str, profile_id: str) -> KeyContext:
    async with deployment.sessions() as session:
        return await resolve_key_context(
            session,
            region=deployment.region,
            person_id=uuid.UUID(person_id),
            profile_id=uuid.UUID(profile_id),
        )


async def _told(deployment: Deployment, pa: dict[str, str], profile_id: str, *codes: str) -> None:
    """The conditions he told when his profile was set up (E01): `condition.<code>` facts."""
    async with deployment.sessions() as session:
        context = await resolve_key_context(
            session,
            region=deployment.region,
            person_id=uuid.UUID(pa["person_id"]),
            profile_id=uuid.UUID(profile_id),
        )
        moment = await record_event(
            session,
            context=context,
            kind=EventKind.ONBOARDING,
            occurred_at=utcnow(),
            label="the conditions he told",
            source_channel=SourceChannel.APP,
        )
        for code in codes:
            await assert_fact(
                session,
                context=context,
                subject="condition",
                attribute=code,
                value=True,
                confidence=1.0,
                event_id=moment.id,
            )
        await session.commit()


async def _took(deployment: Deployment, pa: dict[str, str], profile_id: str, name: str) -> None:
    """A medicine read off his label photo, the way the review card writes it."""
    async with deployment.sessions() as session:
        context = await resolve_key_context(
            session,
            region=deployment.region,
            person_id=uuid.UUID(pa["person_id"]),
            profile_id=uuid.UUID(profile_id),
        )
        photo = await store_artifact(
            session,
            context=context,
            kind=ArtifactKind.PHOTO,
            storage_key=f"{deployment.region.value.lower()}/profiles/pa/label-{uuid.uuid4()}.jpg",
            content_type="image/jpeg",
            sha256="e" * 64,
            captured_at=utcnow(),
            source_channel=SourceChannel.APP,
            region=deployment.region,
        )
        await assert_fact(
            session,
            context=context,
            subject="medicine",
            attribute="name",
            value=name,
            confidence=0.95,
            artifact_id=photo.id,
        )
        await session.commit()


async def _reading(
    deployment: Deployment, profile_id: str, token: str, top: int, bottom: int, **body: Any
) -> dict[str, Any]:
    posted = await deployment.client.post(
        f"/profiles/{profile_id}/readings",
        json={"systolic": top, "diastolic": bottom, **body},
        headers=bearer(token),
    )
    assert posted.status_code == 201, posted.text
    reading: dict[str, Any] = posted.json()
    return reading


async def _feed(deployment: Deployment, profile_id: str, token: str) -> dict[str, Any]:
    answer = await deployment.client.get(f"/profiles/{profile_id}/feed", headers=bearer(token))
    assert answer.status_code == 200, answer.text
    page: dict[str, Any] = answer.json()
    return page


async def _every_page(
    deployment: Deployment, profile_id: str, token: str, pages: int = 4
) -> list[dict[str, Any]]:
    """The first few pages, one after the other by the cursor each hands back."""
    first = await _feed(deployment, profile_id, token)
    items = list(first["items"])
    cursor = first["next_cursor"]
    for _ in range(pages - 1):
        if not cursor:
            break
        answer = await deployment.client.get(
            f"/profiles/{profile_id}/feed", params={"cursor": cursor}, headers=bearer(token)
        )
        assert answer.status_code == 200, answer.text
        items.extend(answer.json()["items"])
        cursor = answer.json()["next_cursor"]
    return items


async def _made(deployment: Deployment, profile_id: str, type: CardType) -> list[FeedItem]:
    """Every card of this type the engine wrote for him, straight from the table."""
    async with deployment.sessions() as session:
        return list(
            (
                await session.scalars(
                    select(FeedItem)
                    .where(FeedItem.profile_id == uuid.UUID(profile_id), FeedItem.type == type)
                    .order_by(FeedItem.created_at)
                )
            ).all()
        )


async def _chief(
    deployment: Deployment, pa: dict[str, str], profile_id: str, phone: str = MEI
) -> dict[str, str]:
    mei = await register_by_phone(deployment, phone, "Mei")
    await let_in(deployment, pa, profile_id, phone, EVERY_PART, "daughter")
    key = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": phone, "role": "chief"},
        headers=bearer(pa["token"]),
    )
    assert key.status_code == 201, key.text
    return mei


async def _caregiver(
    deployment: Deployment, pa: dict[str, str], profile_id: str, phone: str = SITI
) -> dict[str, str]:
    siti = await register_by_phone(deployment, phone, "Siti")
    await let_in(
        deployment, pa, profile_id, phone, ["records", "medicines"], "helper", holder_display_name="Siti"
    )
    key = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": phone, "role": "caregiver", "scopes": ["records", "medicines"]},
        headers=bearer(pa["token"]),
    )
    assert key.status_code == 201, key.text
    return siti


def _fails(lines: Sequence[str], language: str) -> list[str]:
    """The lines that break docs/plain-words.md, as the verifier reads a line he hears."""
    return [
        line
        for line in lines
        if any(found.severity == "fail" for found in verify(line, language, "line"))
    ]


def _events(*events: dict[str, Any]) -> dict[str, Any]:
    return {"events": list(events)}


def _event(item_id: str, event: str, at: datetime, **extra: Any) -> dict[str, Any]:
    return {
        "client_id": str(uuid.uuid4()),
        "item_id": item_id,
        "event": event,
        "at": at.isoformat(),
        **extra,
    }


# --- E09-06: a compressed video, as a clip the server hosts ------------------------------------


async def test_an_allowlisted_video_becomes_a_clip_with_its_still_its_captions_and_the_link(
    deployment: Deployment,
) -> None:
    pa, profile_id = await _pa(deployment)
    await _reading(deployment, profile_id, pa["token"], 138, 84)
    await _feed(deployment, profile_id, pa["token"])
    [clip] = await _made(deployment, profile_id, CardType.CLIP)
    cite = dict(clip.cite or {})
    # 20–30 seconds of the National Heart Centre's own video, on its own site.
    assert cite["media"] == "video"
    assert cite["full_url"] == "https://www.nhcs.com.sg/patient-care/videos/understanding-high-blood-pressure"
    assert cite["publisher"] == "National Heart Centre Singapore"
    assert 20 <= cite["end_sec"] - cite["start_sec"] <= 30
    # The licence names no reuse: no excerpt is kept, and the clip is the still and the
    # narration with captions (spec §7).
    assert cite["licence"] is None and cite["excerpt"] is False
    assert clip.format.value == "clip"
    # Narrated in his language, ending on the boundary line, from an allowlisted source.
    assert clip.language == "en" and clip.voice == clip.body
    assert clip.body[-3:-1] == BOUNDARY_EN
    assert not _fails(list(clip.body), "en")

    base = f"/profiles/{profile_id}/feed/{clip.id}/clip"
    poster = await deployment.client.get(f"{base}/poster", headers=bearer(pa["token"]))
    assert poster.status_code == 200 and poster.headers["content-type"] == "image/png"
    assert poster.content == (FEED / "clips" / "poster.png").read_bytes()
    assert poster.headers["cache-control"] == "private"
    vtt = await deployment.client.get(f"{base}/captions", headers=bearer(pa["token"]))
    assert vtt.status_code == 200 and vtt.headers["content-type"].startswith("text/vtt")
    text = vtt.text
    assert text.startswith("WEBVTT\nLanguage: en\n")
    for line in clip.voice:
        assert line in text
    # No excerpt: the phone shows the still with the narration.
    video = await deployment.client.get(f"{base}/video", headers=bearer(pa["token"]))
    assert video.status_code == 404 and video.json()["refusal"] == "NoExcerpt"

    # As the API answers it: never autoplay.
    page = await _every_page(deployment, profile_id, pa["token"])
    shown = [item for item in page if item["item_id"] == str(clip.id)]
    assert shown and all(item["autoplay"] is False for item in shown)
    assert {item["supply"] for item in shown} == {"learning"}


async def test_a_card_that_is_not_a_clip_has_no_still_and_no_captions(
    deployment: Deployment,
) -> None:
    pa, profile_id = await _pa(deployment)
    await _reading(deployment, profile_id, pa["token"], 138, 84)
    await _feed(deployment, profile_id, pa["token"])
    [reading] = await _made(deployment, profile_id, CardType.READING)
    for part in ("poster", "captions", "video"):
        answer = await deployment.client.get(
            f"/profiles/{profile_id}/feed/{reading.id}/clip/{part}", headers=bearer(pa["token"])
        )
        assert answer.status_code == 404 and answer.json()["refusal"] == "NotAClipCard", part


async def test_a_stranger_gets_nothing_of_a_clip(deployment: Deployment) -> None:
    pa, profile_id = await _pa(deployment)
    await _reading(deployment, profile_id, pa["token"], 138, 84)
    await _feed(deployment, profile_id, pa["token"])
    [clip] = await _made(deployment, profile_id, CardType.CLIP)
    stranger = await register_by_phone(deployment, "+6591410009", "Stranger")
    for part in ("poster", "captions"):
        answer = await deployment.client.get(
            f"/profiles/{profile_id}/feed/{clip.id}/clip/{part}", headers=bearer(stranger["token"])
        )
        assert answer.status_code in (403, 404), (part, answer.text)


async def test_the_captions_are_in_his_language(deployment: Deployment) -> None:
    pa, profile_id = await _pa(deployment, language="ms")
    await _reading(deployment, profile_id, pa["token"], 138, 84)
    await _feed(deployment, profile_id, pa["token"])
    [clip] = await _made(deployment, profile_id, CardType.CLIP)
    assert clip.language == "ms"
    vtt = await deployment.client.get(
        f"/profiles/{profile_id}/feed/{clip.id}/clip/captions", headers=bearer(pa["token"])
    )
    assert vtt.text.startswith("WEBVTT\nLanguage: ms\n")
    assert clip.body[0] in vtt.text


def test_the_cues_follow_one_another_and_each_line_is_the_card_s_own() -> None:
    lines = ["High blood pressure often has no signs.", "Less salt and a daily walk help."]
    cues = caption_cues(lines, "en")
    assert [text for _, _, text in cues] == lines
    assert cues[0][0] == 0.0 and cues[0][1] == cues[1][0] and cues[1][1] > cues[1][0]
    vtt = captions(lines, "en")
    assert "00:00:00.000 --> " in vtt


def test_only_a_licence_that_allows_reuse_lets_the_server_keep_an_excerpt() -> None:
    assert may_excerpt("cc-by") and may_excerpt("CC-BY-SA") and may_excerpt("permission")
    # "No derivatives" does not allow cutting 20–30 seconds and narrating over them.
    for licence in (None, "", "standard", "youtube", "all rights reserved", "cc-by-nc", "cc-by-nd"):
        assert not may_excerpt(licence), licence


class _Licensed(FixtureSearcher):
    """The fixture pages, with the heart centre's video under a licence that allows reuse."""

    def search(self, kind: str, terms: Sequence[str], domains: Sequence[str]) -> Sequence[Found]:
        found = super().search(kind, terms, domains)
        return [
            Found(**{**_as_dict(page), "licence": "cc-by"}) if page.media == "video" else page
            for page in found
        ]


def _as_dict(page: Found) -> dict[str, Any]:
    return {name: getattr(page, name) for name in page.__dataclass_fields__}


class _Cutter:
    """A renderer that cuts excerpts, as the future ffmpeg one will: it is asked for the video
    only when the licence allowed it, and only between the card's seconds."""

    name = "cutter"
    excerpts = True

    def __init__(self) -> None:
        self.asked: list[ClipAsk] = []

    async def render(self, ask: ClipAsk) -> Rendered:
        self.asked.append(ask)
        video = None if ask.excerpt_url is None else b"\x00\x00\x00\x18ftypmp42excerpt"
        return Rendered(
            poster=b"\x89PNG still", poster_type="image/png", video=video, video_type="video/mp4"
        )


async def test_where_the_licence_allows_it_the_server_keeps_and_serves_the_excerpt(
    deployment: Deployment,
) -> None:
    pa, profile_id = await _pa(deployment)
    await _reading(deployment, profile_id, pa["token"], 138, 84)
    cutter = _Cutter()
    engine = Engine(
        searcher=_Licensed(FEED),
        compressor=FixtureCompressor(FEED),
        registry=FixtureRegistry.load(),
        clips=cutter,
    )
    context = await _context(deployment, pa["person_id"], profile_id)
    async with deployment.sessions() as session:
        await refresh(session, context=context, engine=engine)
        await session.commit()
    [clip] = await _made(deployment, profile_id, CardType.CLIP)
    assert clip.cite is not None and clip.cite["excerpt"] is True
    async with deployment.sessions() as session:
        data, kind = await clip_video(
            session, context=context, item_id=clip.id, renderer=cutter, store=deployment.objects
        )
    assert kind == "video/mp4" and data.endswith(b"excerpt")
    [ask] = cutter.asked
    assert ask.excerpt_url == clip.cite["full_url"]
    assert (ask.start_sec, ask.end_sec) == (clip.cite["start_sec"], clip.cite["end_sec"])
    # Kept in the region's own store, under his profile: asked again, it is not cut again.
    async with deployment.sessions() as session:
        await clip_video(
            session, context=context, item_id=clip.id, renderer=cutter, store=deployment.objects
        )
    assert len(cutter.asked) == 1


async def test_the_fixture_renderer_never_cuts_an_excerpt_and_carries_the_mark() -> None:
    from app.fixtures import is_fixture

    renderer = clip_module.FixtureClipRenderer(FEED)
    assert is_fixture(renderer) and renderer.excerpts is False
    made = await renderer.render(
        ClipAsk(key="k", language="en", excerpt_url="https://x", start_sec=1, end_sec=25)
    )
    assert made.video is None and made.poster_type == "image/png"


# --- E11-09: his week in 30 seconds -----------------------------------------------------------


async def test_his_week_in_thirty_seconds_repeats_his_own_numbers_over_a_still_with_captions(
    deployment: Deployment, clock: FrozenClock
) -> None:
    pa, profile_id = await _pa(deployment)
    his = pa["token"]
    for days_ago, (top, bottom) in ((10, (150, 92)), (7, (146, 90)), (3, (142, 88))):
        taken = (clock.now() - timedelta(days=days_ago)).isoformat()
        await _reading(deployment, profile_id, his, top, bottom, taken_at=taken)
    await _reading(deployment, profile_id, his, 138, 84)
    await _feed(deployment, profile_id, his)
    [recap] = await _made(deployment, profile_id, CardType.RECAP)
    assert recap.headline == "Your week, in 30 seconds"
    assert recap.body[0] == "This is your week, from your blood pressure book."
    stories = await _made(deployment, profile_id, CardType.STORY)
    firsts = {story.body[0] for story in stories}
    assert recap.body[1:] and set(recap.body[1:]) <= firsts
    # It repeats the record and infers nothing: no boundary line, and it is a clip.
    assert recap.boundary is None and recap.format.value == "clip"
    assert recap.supply.value == "story"
    assert not _fails(list(recap.body), "en")
    poster = await deployment.client.get(
        f"/profiles/{profile_id}/feed/{recap.id}/clip/poster", headers=bearer(his)
    )
    assert poster.status_code == 200
    vtt = await deployment.client.get(
        f"/profiles/{profile_id}/feed/{recap.id}/clip/captions", headers=bearer(his)
    )
    assert recap.body[0] in vtt.text
    # No video behind it: no link, no excerpt.
    assert recap.cite is not None and "full_url" not in recap.cite
    # Once a week.
    await _feed(deployment, profile_id, his)
    assert len(await _made(deployment, profile_id, CardType.RECAP)) == 1


async def test_one_number_is_not_a_week(deployment: Deployment, clock: FrozenClock) -> None:
    pa, profile_id = await _pa(deployment)
    taken = (clock.now() - timedelta(days=3)).isoformat()
    await _reading(deployment, profile_id, pa["token"], 142, 88, taken_at=taken)
    await _feed(deployment, profile_id, pa["token"])
    assert await _made(deployment, profile_id, CardType.RECAP) == []


# --- E09-07: local alerts, only when his record makes them relevant -------------------------


async def test_dengue_near_his_area_reaches_him_only_once_his_area_is_set_and_a_condition_makes_it_relevant(
    penang: Deployment, clock: FrozenClock
) -> None:
    pa, profile_id = await _pa(penang, PA_MY)
    his = pa["token"]
    await _told(penang, pa, profile_id, "diabetes")
    await _feed(penang, profile_id, his)
    # No area yet: the bulletin names his district, and nobody knows he lives there.
    assert await _made(penang, profile_id, CardType.LOCAL) == []

    set_area = await penang.client.put(
        f"/profiles/{profile_id}/area", json={"area": "air itam"}, headers=bearer(his)
    )
    assert set_area.status_code == 200, set_area.text
    assert set_area.json()["area"] == "Air Itam" and set_area.json()["may_set"] is True
    clock.step(timedelta(days=1))
    page = await _feed(penang, profile_id, his)
    [local] = await _made(penang, profile_id, CardType.LOCAL)
    assert local.headline == "More dengue near you this week"
    assert local.why["plain"] == "You are seeing this because it is near your home."
    # What to do today, then the source, then the boundary line it ends on.
    assert local.body[0] == "Start today: empty the water in pots and pails at home."
    assert local.body[-3:-1] == BOUNDARY_EN and local.boundary is not None
    assert local.cite is not None and local.cite["publisher"] == "MyHEALTH Kementerian Kesihatan"
    assert local.supply.value == "today" and local.deliver_to.value == "patient"
    assert "diabetes" in json.dumps(local.why) or local.why["fact_ids"]
    # Today's: it expires at his midnight.
    assert local.expires_at.replace(tzinfo=UTC) <= clock.now() + timedelta(days=1)
    # The patient keeps his gate: at most two new cards today, then the gate.
    types = [item["type"] for item in page["items"]]
    gate = types.index("gate")
    assert len([t for t in types[:gate] if t not in ("now", "flag")]) <= 2
    assert "local" in types[:gate]

    # His area stays on this server: never in a search job, its terms, reason or results.
    async with penang.sessions() as session:
        jobs = (
            await session.scalars(
                select(SearchJob).where(SearchJob.profile_id == uuid.UUID(profile_id))
            )
        ).all()
    stored = json.dumps([[job.terms, job.reason, job.results] for job in jobs])
    assert "Air Itam" not in stored and "air itam" not in stored.lower()
    [dengue] = [job for job in jobs if job.kind is JobKind.LOCAL and job.terms == ["dengue"]]
    assert dengue.cadence == "daily"


async def test_no_relevant_condition_no_local_alert_whatever_the_bulletin_says(
    penang: Deployment, clock: FrozenClock
) -> None:
    pa, profile_id = await _pa(penang, PA_MY)
    await _told(penang, pa, profile_id, "joints")
    await penang.client.put(
        f"/profiles/{profile_id}/area", json={"area": "Air Itam"}, headers=bearer(pa["token"])
    )
    await _feed(penang, profile_id, pa["token"])
    clock.step(timedelta(days=1))
    await _feed(penang, profile_id, pa["token"])
    assert await _made(penang, profile_id, CardType.LOCAL) == []
    async with penang.sessions() as session:
        kinds = {
            job.kind
            for job in (
                await session.scalars(
                    select(SearchJob).where(SearchJob.profile_id == uuid.UUID(profile_id))
                )
            ).all()
        }
    assert JobKind.LOCAL not in kinds


async def test_a_blood_thinner_makes_dengue_relevant(
    penang: Deployment, clock: FrozenClock
) -> None:
    pa, profile_id = await _pa(penang, PA_MY)
    await _took(penang, pa, profile_id, "Warfarin")
    await penang.client.put(
        f"/profiles/{profile_id}/area", json={"area": "11"}, headers=bearer(pa["token"])
    )
    await _feed(penang, profile_id, pa["token"])
    [local] = await _made(penang, profile_id, CardType.LOCAL)
    # Made relevant by a medicine alone: the card is under the medicines' part of the record.
    assert local.scope.value == "medicines"
    assert relevant_to("dengue", (), ("warfarin",)) == ["warfarin"]


async def test_haze_for_the_heart_and_the_lungs_over_the_whole_region(
    deployment: Deployment,
) -> None:
    pa, profile_id = await _pa(deployment)
    await _told(deployment, pa, profile_id, "breathing")
    await _feed(deployment, profile_id, pa["token"])
    [haze] = await _made(deployment, profile_id, CardType.LOCAL)
    assert haze.headline == "Haze today: stay indoors more"
    # The advisory names no district: it is for the whole region, and the why says so.
    assert haze.why["plain"] == "You are seeing this because of what is on your papers."
    assert haze.body[-3:-1] == BOUNDARY_EN


async def test_an_area_is_coarse_and_his_to_set(deployment: Deployment) -> None:
    pa, profile_id = await _pa(deployment)
    mei = await _chief(deployment, pa, profile_id)
    for refused in ("12 Ang Mo Kio Avenue 3", "560123", "Blk 123", "Paris"):
        answer = await deployment.client.put(
            f"/profiles/{profile_id}/area", json={"area": refused}, headers=bearer(pa["token"])
        )
        assert answer.status_code == 400 and answer.json()["refusal"] == "NotACoarseArea", refused
    kept = await deployment.client.put(
        f"/profiles/{profile_id}/area", json={"area": "56"}, headers=bearer(pa["token"])
    )
    assert kept.status_code == 200 and kept.json()["area"] == "56"
    # His chief reads it — so she can see why a local card came — and does not set it.
    read = await deployment.client.get(f"/profiles/{profile_id}/area", headers=bearer(mei["token"]))
    assert read.status_code == 200 and read.json()["area"] == "56"
    assert read.json()["may_set"] is False and "Ang Mo Kio" in read.json()["districts"]
    hers = await deployment.client.put(
        f"/profiles/{profile_id}/area", json={"area": "Bedok"}, headers=bearer(mei["token"])
    )
    assert hers.status_code == 403 and hers.json()["refusal"] == "OnlyHeSetsHisArea"
    cleared = await deployment.client.put(
        f"/profiles/{profile_id}/area", json={"area": None}, headers=bearer(pa["token"])
    )
    assert cleared.status_code == 200 and cleared.json()["area"] is None
    assert check_area("toa  payoh", Region.SG) == "Toa Payoh"


async def test_his_trail_says_who_set_his_area_and_when_it_was_refused(
    deployment: Deployment,
) -> None:
    """Where he lives is location data about him, so the trail carries every write of it.

    Two things are asserted. A street or a whole postcode is refused *and written down* — that
    it was refused, never what was offered, so a rejected address does not land on the trail by
    the back door. And his own write is his: the owner reads and writes his own graph with no
    key, so his line carries no key and no role, which is how a reader tells his yes from the
    steward's before he claimed the graph (`app/delivery/feed/area.py`).
    """
    pa, profile_id = await _pa(deployment)
    refused = await deployment.client.put(
        f"/profiles/{profile_id}/area",
        json={"area": "12 Ang Mo Kio Avenue 3"},
        headers=bearer(pa["token"]),
    )
    assert refused.status_code == 400 and refused.json()["refusal"] == "NotACoarseArea"
    kept = await deployment.client.put(
        f"/profiles/{profile_id}/area", json={"area": "Bedok"}, headers=bearer(pa["token"])
    )
    assert kept.status_code == 200, kept.text
    async with deployment.sessions() as session:
        trail = await read_audit(
            session, context=await _context(deployment, pa["person_id"], profile_id)
        )
    area_lines = [e for e in trail if e.target == "profile.area"]
    [turned_down] = [e for e in area_lines if e.outcome is Outcome.REFUSED]
    assert turned_down.refused_because == "NotACoarseArea"
    # The street he typed is nowhere on the trail: the line says it was refused, not what for.
    assert not any("Ang Mo Kio Avenue" in (e.target or "") for e in trail)
    written = [e for e in area_lines if e.outcome is not Outcome.REFUSED]
    assert written and all(e.key_id is None and e.actor_role is None for e in written), (
        "his own write carries no key: that is how the trail says it was him, not his steward"
    )


# --- seasons -------------------------------------------------------------------------------


async def test_festive_food_before_the_mid_autumn_festival_for_his_sugar(
    deployment: Deployment, clock: FrozenClock
) -> None:
    pa, profile_id = await _pa(deployment)
    await _told(deployment, pa, profile_id, "diabetes")
    await _feed(deployment, profile_id, pa["token"])
    # Thursday 3 September is before the card may show (three weeks ahead of the 25th).
    assert await _made(deployment, profile_id, CardType.SEASONAL) == []
    clock.step(timedelta(days=7))
    await _feed(deployment, profile_id, pa["token"])
    [season] = await _made(deployment, profile_id, CardType.SEASONAL)
    assert season.headline == "Mooncakes: just a small slice"
    assert season.why["plain"] == "The Mid-Autumn Festival is on Friday 25 September."
    assert season.body[-3:-1] == BOUNDARY_EN
    assert not _fails([*season.body, season.why["plain"]], "en")


async def test_the_fasting_month_is_added_by_a_person_and_shows_only_when_it_is_near(
    deployment: Deployment, clock: FrozenClock
) -> None:
    pa, profile_id = await _pa(deployment)
    await _told(deployment, pa, profile_id, "diabetes")
    mei = await _chief(deployment, pa, profile_id)
    await _feed(deployment, profile_id, pa["token"])
    async with deployment.sessions() as session:
        planned = (
            await session.scalars(
                select(SearchJob).where(
                    SearchJob.profile_id == uuid.UUID(profile_id),
                    SearchJob.kind == JobKind.SEASONAL,
                )
            )
        ).all()
    # Nura never guesses whether he fasts: no fasting-month watch is made by itself.
    assert ["fasting month"] not in [job.terms for job in planned]
    # Whether he fasts speaks of his faith: his chief does not add it for him.
    hers = await deployment.client.post(
        f"/profiles/{profile_id}/search-jobs",
        json={"kind": "seasonal", "terms": ["fasting month"]},
        headers=bearer(mei["token"]),
    )
    assert hers.status_code == 403 and hers.json()["refusal"] == "FastingIsHisToSay"
    added = await deployment.client.post(
        f"/profiles/{profile_id}/search-jobs",
        json={"kind": "seasonal", "terms": ["fasting month"]},
        headers=bearer(pa["token"]),
    )
    assert added.status_code == 201, added.text
    assert added.json()["cadence"] == "weekly"
    assert added.json()["label"] == "Ramadan, before it comes"
    # In September the season is months away: nothing is made.
    fasting = [
        item
        for item in await _made(deployment, profile_id, CardType.SEASONAL)
        if "Ramadan" in item.headline
    ]
    assert fasting == []
    # Six weeks before it, the card: plan it with the doctor, and the food. Four months on, he
    # signs in again (a session does not last that long).
    clock.step(datetime(2027, 1, 4, 2, 0, tzinfo=UTC) - clock.now())
    pa = await register_by_phone(deployment, PA, "Pa")
    await _feed(deployment, profile_id, pa["token"])
    [card, *_] = [
        item
        for item in await _made(deployment, profile_id, CardType.SEASONAL)
        if "Ramadan" in item.headline
    ]
    assert card.headline == "Ramadan: plan it with your doctor"
    assert card.body[0] == "See your doctor 1 to 2 months before Ramadan."
    # The low-sugar warning the sources give, for a man on sugar tablets or insulin who fasts.
    assert "If you feel shaky, sweaty or confused, check your blood sugar at once." in card.body
    assert card.why["plain"] == "Ramadan begins around Monday 8 February."


async def test_a_watch_is_for_a_hazard_or_a_season_nura_knows(deployment: Deployment) -> None:
    pa, profile_id = await _pa(deployment)
    for body, refusal in (
        ({"kind": "local", "terms": ["floods"]}, "NotAHazard"),
        ({"kind": "seasonal", "terms": ["christmas"]}, "NotASeason"),
        ({"kind": "food", "terms": ["diabetes"], "cadence": "hourly"}, "NotACadence"),
    ):
        answer = await deployment.client.post(
            f"/profiles/{profile_id}/search-jobs", json=body, headers=bearer(pa["token"])
        )
        assert answer.status_code == 400 and answer.json()["refusal"] == refusal, body


# --- food and habit: weekly, by condition, one concrete choice -------------------------------


async def test_one_food_card_a_week_for_his_conditions_with_one_choice(
    deployment: Deployment, clock: FrozenClock
) -> None:
    pa, profile_id = await _pa(deployment)
    await _told(deployment, pa, profile_id, "diabetes", "cholesterol")
    await _feed(deployment, profile_id, pa["token"])
    [food] = await _made(deployment, profile_id, CardType.FOOD)
    assert food.headline.startswith("This week: ")
    choice = food.body[: food.body.index("This comes from HealthHub.")]
    assert 1 <= len(choice) <= 2, choice
    assert food.body[-3:-1] == BOUNDARY_EN
    async with deployment.sessions() as session:
        [job] = (
            await session.scalars(
                select(SearchJob).where(
                    SearchJob.profile_id == uuid.UUID(profile_id), SearchJob.kind == JobKind.FOOD
                )
            )
        ).all()
    assert job.terms == ["cholesterol", "diabetes"] and job.cadence == "weekly"
    # Again this week: nothing new. Next week: the next choice, in turn.
    await _feed(deployment, profile_id, pa["token"])
    assert len(await _made(deployment, profile_id, CardType.FOOD)) == 1
    clock.step(timedelta(days=7))
    await _feed(deployment, profile_id, pa["token"])
    both = await _made(deployment, profile_id, CardType.FOOD)
    assert len(both) == 2 and both[0].headline != both[1].headline


# --- E11-08: the phone's queue --------------------------------------------------------------


async def test_the_phone_s_queue_is_written_once_each_at_the_moment_it_happened(
    deployment: Deployment, clock: FrozenClock
) -> None:
    pa, profile_id = await _pa(deployment)
    await _reading(deployment, profile_id, pa["token"], 138, 84)
    page = await _feed(deployment, profile_id, pa["token"])
    card = next(item for item in page["items"] if item["type"] == "reading")["item_id"]
    earlier = clock.now() - timedelta(hours=2)
    opened = _event(card, "opened", earlier)
    played = _event(card, "played", earlier + timedelta(minutes=1), seconds=12.34)
    batch = _events(
        opened,
        played,
        _event(card, "replayed", earlier + timedelta(minutes=2), seconds=11),
        _event(card, "asked_more", earlier + timedelta(minutes=3)),
        _event(card, "shared", earlier + timedelta(minutes=4)),
    )
    url = f"/profiles/{profile_id}/feed/events"
    first = await deployment.client.post(url, json=batch, headers=bearer(pa["token"]))
    assert first.status_code == 200, first.text
    assert len(first.json()["written"]) == 5 and first.json()["skipped"] == []
    # The answer was lost; the phone sends the same queue again: nothing is written twice.
    again = await deployment.client.post(url, json=batch, headers=bearer(pa["token"]))
    assert again.json()["written"] == []
    assert {one["because"] for one in again.json()["skipped"]} == {"already_written"}
    async with deployment.sessions() as session:
        rows = (
            await session.scalars(
                select(Engagement).where(Engagement.item_id == uuid.UUID(card))
            )
        ).all()
    by_kind = {row.kind: row for row in rows}
    assert by_kind[EngagementKind.PLAYED].seconds == 12.3
    assert by_kind[EngagementKind.OPENED].seconds is None
    assert by_kind[EngagementKind.OPENED].at.replace(tzinfo=UTC) == earlier

    stale = _event(card, "opened", clock.now() - timedelta(days=8))
    ahead = _event(card, "opened", clock.now() + timedelta(hours=1))
    nowhere = _event(str(uuid.uuid4()), "opened", clock.now())
    odd = await deployment.client.post(
        url, json=_events(stale, ahead, nowhere), headers=bearer(pa["token"])
    )
    because = {one["client_id"]: one["because"] for one in odd.json()["skipped"]}
    assert because == {
        stale["client_id"]: "too_old",
        ahead["client_id"]: "not_yet",
        nowhere["client_id"]: "no_such_card",
    }


async def test_a_card_on_screen_says_it_was_opened_never_for_how_long(
    deployment: Deployment, clock: FrozenClock
) -> None:
    pa, profile_id = await _pa(deployment)
    await _reading(deployment, profile_id, pa["token"], 138, 84)
    page = await _feed(deployment, profile_id, pa["token"])
    card = page["items"][0]["item_id"]
    url = f"/profiles/{profile_id}/feed/events"
    for event in ("opened", "asked_more", "shared", "dismissed"):
        answer = await deployment.client.post(
            url, json=_events(_event(card, event, clock.now(), seconds=40)), headers=bearer(pa["token"])
        )
        assert answer.status_code == 422, event
    one = await deployment.client.post(
        f"/profiles/{profile_id}/feed/{card}/engagement",
        json={"event": "opened", "seconds": 40},
        headers=bearer(pa["token"]),
    )
    assert one.status_code in (201, 422)
    if one.status_code == 201:
        async with deployment.sessions() as session:
            written = await session.get(Engagement, uuid.UUID(one.json()["engagement_id"]))
        assert written is not None and written.seconds is None


# --- spec §0: never optimise for time in the feed ---------------------------------------------


def test_no_event_measures_time_in_the_feed() -> None:
    """Only a play or a replay says how long — and that is how much of a voice note or a clip
    played. There is no event for a card on screen for a while, a session, a scroll or a view
    time, and the ranking has none to read."""
    assert PLAYS == {EngagementKind.PLAYED, EngagementKind.REPLAYED}
    for kind in EngagementKind:
        assert not any(word in kind.value for word in ("dwell", "view", "session", "scroll", "time"))


def test_nothing_that_makes_or_orders_the_feed_reads_how_long_anything_played() -> None:
    """The seconds of a play are taken in (the route's schema) and written (`engagement.py`),
    and read by nothing that ranks, composes, searches or delivers: no card is chosen, moved or
    reshaped by time spent."""
    import re

    reads = re.compile(r"\.seconds\b")
    readers = sorted(
        str(path.relative_to(APP))
        for path in APP.rglob("*.py")
        if reads.search(path.read_text(encoding="utf-8"))
    )
    assert readers == ["channels/api/feed_schemas.py", "delivery/feed/engagement.py"], readers


async def test_a_long_play_and_a_short_one_leave_the_same_feed(
    deployment: Deployment, clock: FrozenClock
) -> None:
    """Two people, the same record. One plays every voice note to the end, again and again;
    the other plays a second of each. The next day their feeds are the same cards, in the same
    order, in the same format: time spent is not something the feed learns from."""
    pages: list[list[tuple[str, str, str]]] = []
    people = []
    for n, seconds in ((1, 600.0), (2, 1.0)):
        pa, profile_id = await _pa(deployment, phone=f"+659141100{n}")
        await _reading(deployment, profile_id, pa["token"], 138, 84)
        people.append((pa, profile_id, seconds))
    for pa, profile_id, seconds in people:
        page = await _feed(deployment, profile_id, pa["token"])
        events = []
        for item in page["items"]:
            events.append(_event(item["item_id"], "played", clock.now(), seconds=seconds))
            events.append(_event(item["item_id"], "replayed", clock.now(), seconds=seconds))
        answer = await deployment.client.post(
            f"/profiles/{profile_id}/feed/events", json=_events(*events), headers=bearer(pa["token"])
        )
        assert answer.status_code == 200, answer.text
    clock.step(timedelta(days=1))
    for pa, profile_id, _ in people:
        await _reading(deployment, profile_id, pa["token"], 140, 86)
        page = await _feed(deployment, profile_id, pa["token"])
        pages.append([(item["type"], item["supply"], item["format"]) for item in page["items"]])
    assert pages[0] == pages[1]


# --- E11-08: the format adapts to what he opens -------------------------------------------


async def test_two_clips_on_his_screen_and_never_played_make_his_videos_voice_notes(
    deployment: Deployment, clock: FrozenClock
) -> None:
    pa, profile_id = await _pa(deployment)
    await _told(deployment, pa, profile_id, "diabetes")
    await _reading(deployment, profile_id, pa["token"], 138, 84)
    await _feed(deployment, profile_id, pa["token"])
    clips = await _made(deployment, profile_id, CardType.CLIP)
    assert len(clips) == 2, [clip.headline for clip in clips]
    await deployment.client.post(
        f"/profiles/{profile_id}/feed/events",
        json=_events(*(_event(str(clip.id), "opened", clock.now()) for clip in clips)),
        headers=bearer(pa["token"]),
    )
    clock.step(timedelta(days=1))
    await _feed(deployment, profile_id, pa["token"])
    state = (
        await deployment.client.get(f"/profiles/{profile_id}/state", headers=bearer(pa["token"]))
    ).json()
    assert "card" in json.dumps(state["dimensions"]), "format.clips is card"


async def test_a_clip_he_played_does_not_count_as_missed(
    deployment: Deployment, clock: FrozenClock
) -> None:
    pa, profile_id = await _pa(deployment)
    await _told(deployment, pa, profile_id, "diabetes")
    await _reading(deployment, profile_id, pa["token"], 138, 84)
    await _feed(deployment, profile_id, pa["token"])
    clips = await _made(deployment, profile_id, CardType.CLIP)
    events = [_event(str(clip.id), "opened", clock.now()) for clip in clips]
    events.append(_event(str(clips[0].id), "played", clock.now(), seconds=3))
    await deployment.client.post(
        f"/profiles/{profile_id}/feed/events", json=_events(*events), headers=bearer(pa["token"])
    )
    clock.step(timedelta(days=1))
    await _feed(deployment, profile_id, pa["token"])
    state = (
        await deployment.client.get(f"/profiles/{profile_id}/state", headers=bearer(pa["token"]))
    ).json()
    assert '"clips"' not in json.dumps(state["dimensions"])


# --- spec §1: the chief's panels ------------------------------------------------------------


async def test_sent_to_pa_this_week_says_what_became_of_each_card_and_counts_nothing(
    deployment: Deployment, clock: FrozenClock
) -> None:
    pa, profile_id = await _pa(deployment)
    mei = await _chief(deployment, pa, profile_id)
    await _reading(deployment, profile_id, pa["token"], 138, 84)
    page = await _feed(deployment, profile_id, pa["token"])
    reading = next(item for item in page["items"] if item["type"] == "reading")["item_id"]
    await deployment.client.post(
        f"/profiles/{profile_id}/feed/events",
        json=_events(_event(reading, "played", clock.now(), seconds=9)),
        headers=bearer(pa["token"]),
    )
    week = await deployment.client.get(
        f"/profiles/{profile_id}/feed/week", headers=bearer(mei["token"])
    )
    assert week.status_code == 200, week.text
    rows = week.json()
    assert rows and all(set(row) == {"item"} for row in rows), "no count of anything"
    by_id = {row["item"]["item_id"]: row["item"] for row in rows}
    assert by_id[reading]["status"] == "played"
    types = {row["item"]["type"] for row in rows}
    assert not types & {"now", "gate", "duty"}
    clip = next(row["item"] for row in rows if row["item"]["type"] == "clip")
    assert clip["search_job_id"] and clip["cite"]["publisher"] == "National Heart Centre Singapore"
    assert {row["item"]["status"] for row in rows} <= {
        "sent",
        "opened",
        "played",
        "dismissed",
        "held",
        "generated",
    }
    # A caregiver who is not his chief does not read the engine's week.
    siti = await _caregiver(deployment, pa, profile_id)
    hers = await deployment.client.get(
        f"/profiles/{profile_id}/feed/week", headers=bearer(siti["token"])
    )
    assert hers.status_code == 403 and hers.json()["refusal"] == "NotTheirsToManage"


async def test_watching_for_pa_lists_each_watch_with_its_sources_and_cadence_and_she_adds_and_pauses(
    deployment: Deployment, clock: FrozenClock
) -> None:
    pa, profile_id = await _pa(deployment)
    mei = await _chief(deployment, pa, profile_id)
    await _told(deployment, pa, profile_id, "heart")
    await _reading(deployment, profile_id, pa["token"], 138, 84)
    await _feed(deployment, profile_id, pa["token"])
    listed = await deployment.client.get(
        f"/profiles/{profile_id}/search-jobs", params={"language": "en"}, headers=bearer(mei["token"])
    )
    assert listed.status_code == 200, listed.text
    watches = {(one["kind"], one["label"]): one for one in listed.json()}
    explainer = watches[("explainer", "Blood pressure, in simple words")]
    assert explainer["cadence"] == "on_change" and "HealthHub" in explainer["sources"]
    haze = watches[("local", "The haze anywhere in the country")]
    assert haze["cadence"] == "daily" and haze["enabled"] is True
    # She pauses the haze watch: it is not run again, and no new haze card comes.
    paused = await deployment.client.patch(
        f"/profiles/{profile_id}/search-jobs/{haze['job_id']}",
        json={"enabled": False},
        headers=bearer(mei["token"]),
    )
    assert paused.status_code == 200 and paused.json()["enabled"] is False
    before = len(await _made(deployment, profile_id, CardType.LOCAL))
    clock.step(timedelta(days=1))
    await _feed(deployment, profile_id, pa["token"])
    after = [
        item for item in await _made(deployment, profile_id, CardType.LOCAL) if "Haze" in item.headline
    ]
    assert len(after) <= before and all(item.created_at < utcnow() - timedelta(hours=1) for item in after)
    # And adds one: dengue, daily by its kind.
    added = await deployment.client.post(
        f"/profiles/{profile_id}/search-jobs",
        json={"kind": "local", "terms": ["dengue"]},
        headers=bearer(mei["token"]),
    )
    assert added.status_code == 201, added.text
    assert added.json()["cadence"] == "daily" and added.json()["label"] == "Dengue anywhere in the country"
    # In Malay, for a reader who reads Malay.
    malay = await deployment.client.get(
        f"/profiles/{profile_id}/search-jobs", params={"language": "ms"}, headers=bearer(mei["token"])
    )
    assert "Denggi di seluruh negara" in {one["label"] for one in malay.json()}
    # A caregiver who is not his chief neither reads nor pauses them.
    siti = await _caregiver(deployment, pa, profile_id)
    for answer in (
        await deployment.client.get(
            f"/profiles/{profile_id}/search-jobs", headers=bearer(siti["token"])
        ),
        await deployment.client.patch(
            f"/profiles/{profile_id}/search-jobs/{haze['job_id']}",
            json={"enabled": True},
            headers=bearer(siti["token"]),
        ),
    ):
        assert answer.status_code == 403 and answer.json()["refusal"] == "NotTheirsToManage"


async def test_her_list_has_no_gate_and_the_duty_card_is_one_of_her_cards(
    deployment: Deployment,
) -> None:
    pa, profile_id = await _pa(deployment)
    mei = await _chief(deployment, pa, profile_id)
    await _reading(deployment, profile_id, pa["token"], 138, 84)
    page = await _feed(deployment, profile_id, mei["token"])
    assert page["audience"] == "caregiver"
    types = [item["type"] for item in page["items"]]
    assert "gate" not in types and page["held_by_caps"] == {}
    duty = [item for item in page["items"] if item["type"] == "duty"]
    assert duty and {item["supply"] for item in duty} == {"today"}


# --- spec §0: the ask bar's filters --------------------------------------------------------


async def test_web_and_videos_search_the_allowlist_only_and_say_each_page_in_his_words(
    deployment: Deployment,
) -> None:
    pa, profile_id = await _pa(deployment)
    web = await deployment.client.post(
        f"/profiles/{profile_id}/find",
        json={"q": "blood pressure", "where": "web", "language": "en"},
        headers=bearer(pa["token"]),
    )
    assert web.status_code == 200, web.text
    results = web.json()["results"]
    assert results
    for result in results:
        assert result["url"].startswith(("https://www.healthhub.sg/", "https://www.nhcs.com.sg/"))
        assert result["boundary"] and result["lines"]
        assert not _fails(result["lines"], "en")
    videos = await deployment.client.post(
        f"/profiles/{profile_id}/find",
        json={"q": "blood pressure", "where": "videos"},
        headers=bearer(pa["token"]),
    )
    assert {result["media"] for result in videos.json()["results"]} == {"video"}
    # A page off the allowlist is never returned, however well its words match.
    thinners = await deployment.client.post(
        f"/profiles/{profile_id}/find",
        json={"q": "natural blood thinners", "where": "web"},
        headers=bearer(pa["token"]),
    )
    assert all("supplement-shop" not in (one["url"] or "") for one in thinners.json()["results"])
    bad = await deployment.client.post(
        f"/profiles/{profile_id}/find", json={"q": "x", "where": "tiktok"}, headers=bearer(pa["token"])
    )
    assert bad.status_code == 400 and bad.json()["refusal"] == "NotAFilter"


async def test_find_results_are_sampled_for_the_pharmacists_queue_too(
    deployment: Deployment,
) -> None:
    """#188: an ask-bar Web or Videos result is never a `FeedItem`, but it is still one of the
    first fifty renderings of a learning-shaped source, sampled the same way a scheduled
    search job's learning card is (`review.sample_find_result`) — a brand-new source is read
    by the pharmacist whether it was found on a schedule or on demand."""
    from app.language.models import ReviewItem, ReviewKind

    pa, profile_id = await _pa(deployment)
    context = await _context(deployment, pa["person_id"], profile_id)
    engine = Engine(
        searcher=FixtureSearcher(FEED), compressor=FixtureCompressor(FEED), registry=FixtureRegistry.load()
    )
    async with deployment.sessions() as session:
        before = (
            await session.scalars(select(ReviewItem).where(ReviewItem.card_type == "learning"))
        ).all()
        results = await find(
            session, context=context, engine=engine, words="blood pressure", where="web", language="en"
        )
        assert results
        after = (
            await session.scalars(select(ReviewItem).where(ReviewItem.card_type == "learning"))
        ).all()
    assert len(after) == len(before) + len(results)
    new = [row for row in after if row not in before]
    assert all(row.kind is ReviewKind.CARD for row in new)
    assert all(row.source_id is None for row in new), "a card's sample, not a source proposal"
    sampled_headlines = {row.lines["headline"] for row in new}
    assert sampled_headlines == {result.title for result in results}
    # No name of his, no query he typed, reaches the de-identified sample.
    assert "Pa" not in json.dumps([row.lines for row in new])


class _Spy(FixtureSearcher):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.sent: list[tuple[list[str], list[str]]] = []

    def find(
        self, words: Sequence[str], domains: Sequence[str], *, media: str | None = None
    ) -> Sequence[Found]:
        self.sent.append((list(words), list(domains)))
        return super().find(words, domains, media=media)


async def test_what_a_search_sends_is_the_words_typed_and_the_allowlist_nothing_of_his(
    deployment: Deployment,
) -> None:
    pa, profile_id = await _pa(deployment)
    await deployment.client.put(
        f"/profiles/{profile_id}/area", json={"area": "Bedok"}, headers=bearer(pa["token"])
    )
    spy = _Spy(FEED)
    engine = Engine(searcher=spy, compressor=FixtureCompressor(FEED), registry=FixtureRegistry.load())
    context = await _context(deployment, pa["person_id"], profile_id)
    async with deployment.sessions() as session:
        await find(
            session, context=context, engine=engine, words="Diabetes", where="web", language="en"
        )
    [(words, domains)] = spy.sent
    assert words == ["diabetes"]
    assert "Bedok" not in json.dumps(spy.sent) and "Pa" not in words
    assert all("." in domain for domain in domains)


async def test_providers_finds_his_own_directory_by_name(deployment: Deployment) -> None:
    pa, profile_id = await _pa(deployment)
    made = await deployment.client.post(
        f"/profiles/{profile_id}/providers",
        json={"name": "Dr Tan", "kind": "doctor"},
        headers=bearer(pa["token"]),
    )
    assert made.status_code == 201, made.text
    found = await deployment.client.post(
        f"/profiles/{profile_id}/find", json={"q": "tan", "where": "providers"}, headers=bearer(pa["token"])
    )
    assert [one["title"] for one in found.json()["results"]] == ["Dr Tan"]


# --- the self-review's findings, held (privacy and clinical safety) --------------------------


def test_the_treatment_check_reads_malay_and_chinese_as_well_as_english() -> None:
    from app.delivery.feed.compress import changes_treatment

    for line in (
        "Skip a dose of warfarin if your number is too high.",
        "Berhenti ambil ubat warfarin anda.",
        "Jangan makan ubat ini esok.",
        "Jangan guna ubat ini lagi.",
        "Do not take your water pill tomorrow.",
        "不要吃华法林。",
        "停药两天。",
        "别吃这个药了。",
        "降压药减量一半。",
    ):
        assert changes_treatment([line]), line
    for line in (
        "Tanya cara merancang makanan dan ubat anda.",
        "Simpan ubat anda dekat dengan anda.",
        "问问怎样安排饮食和吃药。",
        "把药放在身边。",
    ):
        assert not changes_treatment([line]), line


async def test_his_chief_s_taps_on_her_list_are_not_his(
    deployment: Deployment, clock: FrozenClock
) -> None:
    pa, profile_id = await _pa(deployment)
    mei = await _chief(deployment, pa, profile_id)
    await _reading(deployment, profile_id, pa["token"], 138, 84)
    page = await _feed(deployment, profile_id, pa["token"])
    reading = next(item for item in page["items"] if item["type"] == "reading")["item_id"]
    hers = await deployment.client.post(
        f"/profiles/{profile_id}/feed/events",
        json=_events(
            _event(reading, "opened", clock.now()),
            _event(reading, "played", clock.now(), seconds=20),
        ),
        headers=bearer(mei["token"]),
    )
    assert hers.status_code == 200 and len(hers.json()["written"]) == 2
    week = await deployment.client.get(
        f"/profiles/{profile_id}/feed/week", headers=bearer(mei["token"])
    )
    status = {row["item"]["item_id"]: row["item"]["status"] for row in week.json()}
    # "Pa opened this card" is said only when he did.
    assert status[reading] == "sent"


async def test_no_food_card_when_his_kidneys_are_on_his_record(deployment: Deployment) -> None:
    pa, profile_id = await _pa(deployment)
    await _told(deployment, pa, profile_id, "diabetes", "kidneys")
    await _feed(deployment, profile_id, pa["token"])
    assert await _made(deployment, profile_id, CardType.FOOD) == []
    async with deployment.sessions() as session:
        [job] = (
            await session.scalars(
                select(SearchJob).where(
                    SearchJob.profile_id == uuid.UUID(profile_id), SearchJob.kind == JobKind.FOOD
                )
            )
        ).all()
    assert {r["because"] for r in job.results["rejected"]} == {"held_for_his_dietitian"}


async def test_a_bulletin_is_one_card_not_one_every_day(
    penang: Deployment, clock: FrozenClock
) -> None:
    pa, profile_id = await _pa(penang, PA_MY)
    await _told(penang, pa, profile_id, "diabetes")
    await penang.client.put(
        f"/profiles/{profile_id}/area", json={"area": "Air Itam"}, headers=bearer(pa["token"])
    )
    await _feed(penang, profile_id, pa["token"])
    assert len(await _made(penang, profile_id, CardType.LOCAL)) == 1
    # The same bulletin tomorrow: it does not take one of his two new cards again.
    clock.step(timedelta(days=1))
    await _feed(penang, profile_id, pa["token"])
    assert len(await _made(penang, profile_id, CardType.LOCAL)) == 1


async def test_a_season_page_for_a_condition_he_has_not_told_is_not_for_him(
    deployment: Deployment, clock: FrozenClock
) -> None:
    pa, profile_id = await _pa(deployment)
    await _told(deployment, pa, profile_id, "joints")
    added = await deployment.client.post(
        f"/profiles/{profile_id}/search-jobs",
        json={"kind": "seasonal", "terms": ["fasting month"]},
        headers=bearer(pa["token"]),
    )
    assert added.status_code == 201, added.text
    clock.step(datetime(2027, 1, 4, 2, 0, tzinfo=UTC) - clock.now())
    pa = await register_by_phone(deployment, PA, "Pa")
    await _feed(deployment, profile_id, pa["token"])
    # "Fasting safely with diabetes" is written for diabetes, which he has not told.
    assert await _made(deployment, profile_id, CardType.SEASONAL) == []


async def test_his_chief_neither_resumes_nor_stops_his_ramadan_watch(deployment: Deployment) -> None:
    pa, profile_id = await _pa(deployment)
    mei = await _chief(deployment, pa, profile_id)
    added = await deployment.client.post(
        f"/profiles/{profile_id}/search-jobs",
        json={"kind": "seasonal", "terms": ["fasting month"]},
        headers=bearer(pa["token"]),
    )
    job = added.json()["job_id"]
    stopped = await deployment.client.patch(
        f"/profiles/{profile_id}/search-jobs/{job}", json={"enabled": False}, headers=bearer(pa["token"])
    )
    assert stopped.status_code == 200 and stopped.json()["enabled"] is False
    for enabled in (True, False):
        hers = await deployment.client.patch(
            f"/profiles/{profile_id}/search-jobs/{job}",
            json={"enabled": enabled},
            headers=bearer(mei["token"]),
        )
        assert hers.status_code == 403 and hers.json()["refusal"] == "FastingIsHisToSay"
    still = await deployment.client.get(
        f"/profiles/{profile_id}/search-jobs/{job}", headers=bearer(pa["token"])
    )
    assert still.json()["enabled"] is False


async def test_his_own_week_shows_only_what_reached_him(deployment: Deployment) -> None:
    pa, profile_id = await _pa(deployment)
    mei = await _chief(deployment, pa, profile_id)
    await _took(deployment, pa, profile_id, "warfarin")
    await _reading(deployment, profile_id, pa["token"], 138, 84)
    await _feed(deployment, profile_id, pa["token"])
    async with deployment.sessions() as session:
        rows = (
            await session.scalars(select(FeedItem).where(FeedItem.profile_id == uuid.UUID(profile_id)))
        ).all()
    not_his = {str(row.id) for row in rows if row.deliver_to is not DeliverTo.PATIENT}
    assert not_his, "the warfarin pages make a card for the memo or for his chief"
    his = await deployment.client.get(f"/profiles/{profile_id}/feed/week", headers=bearer(pa["token"]))
    assert his.status_code == 200, his.text
    assert not {row["item"]["item_id"] for row in his.json()} & not_his
    hers = await deployment.client.get(f"/profiles/{profile_id}/feed/week", headers=bearer(mei["token"]))
    assert {row["item"]["item_id"] for row in hers.json()} & not_his, "his chief still reads them"


async def test_no_season_card_when_his_kidneys_are_on_his_record(
    deployment: Deployment, clock: FrozenClock
) -> None:
    pa, profile_id = await _pa(deployment)
    await _told(deployment, pa, profile_id, "diabetes", "kidneys")
    await _feed(deployment, profile_id, pa["token"])
    clock.step(timedelta(days=7))
    await _feed(deployment, profile_id, pa["token"])
    assert await _made(deployment, profile_id, CardType.SEASONAL) == []
    async with deployment.sessions() as session:
        jobs = (
            await session.scalars(
                select(SearchJob).where(
                    SearchJob.profile_id == uuid.UUID(profile_id), SearchJob.kind == JobKind.SEASONAL
                )
            )
        ).all()
    assert jobs and all(
        "held_for_his_dietitian" in {r["because"] for r in job.results["rejected"]} for job in jobs
    )


async def test_his_chief_cannot_ask_about_his_faith_under_another_kind_of_watch(
    deployment: Deployment,
) -> None:
    pa, profile_id = await _pa(deployment)
    mei = await _chief(deployment, pa, profile_id)
    for kind, term in (("explainer", "ramadan"), ("worth_knowing", "puasa"), ("explainer", "Fasting month")):
        hers = await deployment.client.post(
            f"/profiles/{profile_id}/search-jobs",
            json={"kind": kind, "terms": [term]},
            headers=bearer(mei["token"]),
        )
        assert hers.status_code == 403 and hers.json()["refusal"] == "FastingIsHisToSay", hers.text
    # "Fasting" alone is his word for no food before a blood test, not his faith.
    fine = await deployment.client.post(
        f"/profiles/{profile_id}/search-jobs",
        json={"kind": "explainer", "terms": ["fasting blood sugar"]},
        headers=bearer(mei["token"]),
    )
    assert fine.status_code == 201, fine.text
    his = await deployment.client.post(
        f"/profiles/{profile_id}/search-jobs",
        json={"kind": "explainer", "terms": ["ramadan"]},
        headers=bearer(pa["token"]),
    )
    assert his.status_code == 201, his.text
    async with deployment.sessions() as session:
        trail = await read_audit(session, context=await _context(deployment, pa["person_id"], profile_id))
    assert sum(e.refused_because == "FastingIsHisToSay" for e in trail) == 3


async def test_a_key_without_the_record_is_refused_on_the_queue_and_it_is_on_his_trail(
    deployment: Deployment, clock: FrozenClock
) -> None:
    pa, profile_id = await _pa(deployment)
    await _reading(deployment, profile_id, pa["token"], 138, 84)
    page = await _feed(deployment, profile_id, pa["token"])
    item = page["items"][0]["item_id"]
    kit = await register_by_phone(deployment, SITI, "Kit")
    await let_in(deployment, pa, profile_id, SITI, ["medicines"], "helper", holder_display_name="Kit")
    key = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": SITI, "role": "caregiver", "scopes": ["medicines"]},
        headers=bearer(pa["token"]),
    )
    assert key.status_code == 201, key.text
    sent = await deployment.client.post(
        f"/profiles/{profile_id}/feed/events",
        json=_events(_event(item, "opened", clock.now())),
        headers=bearer(kit["token"]),
    )
    assert sent.status_code == 403, sent.text
    async with deployment.sessions() as session:
        trail = await read_audit(session, context=await _context(deployment, pa["person_id"], profile_id))
    refused = [e for e in trail if e.outcome is Outcome.REFUSED and e.target == "feed_engagement"]
    assert len(refused) == 1


async def test_a_card_about_his_medicine_says_not_to_stop_it(deployment: Deployment) -> None:
    pa, profile_id = await _pa(deployment)
    await _took(deployment, pa, profile_id, "amlodipine")
    await _feed(deployment, profile_id, pa["token"])
    made = await _made(deployment, profile_id, CardType.LEARNING)
    [tablet] = [card for card in made if card.headline == "Your blood pressure tablet"]
    keep = "Ask your doctor before you stop this medicine."
    assert keep in tablet.body
    assert tablet.body.index(keep) < tablet.body.index("This comes from HealthHub.")
    assert not _fails([keep], "en")
    # A card about a condition, not a medicine, has no such line.
    assert all(keep not in card.body for card in made if card is not tablet)
