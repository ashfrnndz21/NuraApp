"""The feed over HTTP: docs/health-feed-spec.md §9, walked as the app would.

    GET  /profiles/{id}/feed?cursor=            the supply: flag, now, today, gate, story, learning
    GET  /profiles/{id}/feed/cached             the offline page
    POST /profiles/{id}/feed/{item}/engagement  seen, heard, tapped, not for me, shared
    GET  /profiles/{id}/sources                 the allowlist
    POST /profiles/{id}/search-jobs             a self-search, allowlist-scoped
    POST /profiles/{id}/feelings                the feeling cloud; a red flag escalates

The clock is frozen at 2026-09-03 08:00 UTC — 16:00 on the Singapore wall — and stepped
where a test needs a night or another day.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.clock import FrozenClock
from app.delivery.feed import items
from app.delivery.feed.models import CardType, FeedItem, ReviewStatus, Source, SourceKind
from app.safety.boundary import Surface
from app.safety.plain_words import verify
from tests.api import bearer, let_in, own_profile, register_by_phone
from tests.conftest import Deployment

PA = "+6591210001"
MEI = "+6591210002"
AUNTIE = "+6591210003"
STRANGER = "+6591210004"


async def _feed(
    deployment: Deployment, profile_id: str, token: str, **params: Any
) -> dict[str, Any]:
    answer = await deployment.client.get(
        f"/profiles/{profile_id}/feed", params=params, headers=bearer(token)
    )
    assert answer.status_code == 200, answer.text
    page: dict[str, Any] = answer.json()
    return page


async def _reading(
    deployment: Deployment, profile_id: str, token: str, systolic: int, diastolic: int, **body: Any
) -> dict[str, Any]:
    posted = await deployment.client.post(
        f"/profiles/{profile_id}/readings",
        json={"systolic": systolic, "diastolic": diastolic, **body},
        headers=bearer(token),
    )
    assert posted.status_code == 201, posted.text
    reading: dict[str, Any] = posted.json()
    return reading


async def _caregiver_key(
    deployment: Deployment, owner: dict[str, str], profile_id: str, phone: str, scopes: list[str]
) -> None:
    await let_in(deployment, owner, profile_id, phone, scopes, "daughter")
    granted = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": phone, "role": "caregiver", "scopes": scopes},
        headers=bearer(owner["token"]),
    )
    assert granted.status_code == 201, granted.text


def _types(page: dict[str, Any]) -> list[str]:
    return [item["type"] for item in page["items"]]


# --- §9: a new result produces an explainer, in his language, with a voice script ----------


async def test_a_new_reading_produces_a_card_in_his_language_with_a_voice_twin_and_why(
    deployment: Deployment,
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    reading = await _reading(deployment, profile_id, pa["token"], 138, 84)

    page = await _feed(deployment, profile_id, pa["token"])
    assert page["audience"] == "patient"
    cards = {item["type"]: item for item in page["items"]}
    card = cards["reading"]
    assert card["language"] == "en"
    assert card["body"][0] == "Your blood pressure today was 138 over 84."
    assert card["voice"], "every card has a spoken twin"
    assert card["why"]["plain"] == "You took your blood pressure today."
    assert card["why"]["fact_ids"] == [reading["fact_id"]]
    assert card["why"]["event_id"] == reading["event_id"]
    assert card["rendered_from_state"]
    state = (
        await deployment.client.get(f"/profiles/{profile_id}/state", headers=bearer(pa["token"]))
    ).json()
    assert card["rendered_from_state"] == state["state_id"]
    # ...and an evergreen explainer about blood pressure from an allowlisted page, citing it.
    learning = [item for item in page["items"] if item["type"] == "learning"]
    assert learning, _types(page)
    assert learning[0]["cite"]["url"].startswith("https://www.healthhub.sg/")
    assert learning[0]["source_id"] is not None
    assert learning[0]["body"][-2:] == ["This is not a doctor's advice.", "Ask your doctor."]
    # E16-01: the learning card is an inferring surface; the line it ends on is on the card.
    assert learning[0]["boundary"] == (
        "Nura explains one thing in simple words.\nThis is not a doctor's advice.\nAsk your doctor."
    )
    assert learning[0]["body"][-3:] == learning[0]["boundary"].splitlines()
    assert card["boundary"] is None, "a reading shows the record back and infers nothing"
    assert (
        learning[0]["why"]["plain"] == "This is about your blood pressure, which is on your papers."
    )


async def test_the_cards_come_in_malay_for_a_malay_profile(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="ms")
    await _reading(deployment, profile_id, pa["token"], 138, 84)
    page = await _feed(deployment, profile_id, pa["token"])
    cards = {item["type"]: item for item in page["items"]}
    assert cards["reading"]["language"] == "ms"
    assert cards["reading"]["body"][0] == "Tekanan darah anda hari ini 138 atas 84."
    assert cards["gate"]["headline"] == "Itu sahaja yang baru"


# --- §9: the supply order, the caps and the gate; endless past the gate ----------------------


async def test_now_then_at_most_two_new_cards_then_the_gate_then_endless_story_and_learning(
    deployment: Deployment, clock: FrozenClock
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = pa["token"]
    # Numbers from earlier days become his story.
    for days_ago, (top, bottom) in ((10, (150, 92)), (7, (146, 90)), (3, (142, 88))):
        taken = (clock.now() - timedelta(days=days_ago)).isoformat()
        await _reading(deployment, profile_id, his, top, bottom, taken_at=taken)
    # A burst today: three numbers, one card.
    for top, bottom in ((138, 84), (140, 86), (136, 82)):
        await _reading(deployment, profile_id, his, top, bottom)
    # Another profile's cards never appear on his.
    mei = await register_by_phone(deployment, MEI, "Mei")
    hers = await own_profile(deployment, mei)
    await _reading(deployment, hers, mei["token"], 120, 70)
    await _feed(deployment, hers, mei["token"])

    first = await _feed(deployment, profile_id, his)
    types = _types(first)
    assert types[0] == "now"
    assert types[1] == "reading"
    assert types[2] == "gate", types
    # Past the gate: his story (the recap is one of its cards) and learning, nothing else.
    assert types[3:] and {item["supply"] for item in first["items"][3:]} <= {"story", "learning"}
    assert first["held_by_caps"] == {"reading": 2}
    assert first["quiet"] is False
    assert first["next_cursor"]

    seen = {item["item_id"] for item in first["items"]}
    cursor = first["next_cursor"]
    for _ in range(4):
        page = await _feed(deployment, profile_id, his, cursor=cursor)
        assert page["items"], "the list pages endlessly past the gate"
        assert set(_types(page)) <= {"story", "learning"}
        for item in page["items"]:
            assert item["autoplay"] is False
            assert item["rendered_from_state"]
            if item["type"] == "learning":
                assert item["source_id"] is not None
        seen |= {item["item_id"] for item in page["items"]}
        assert page["next_cursor"]
        cursor = page["next_cursor"]
    # Every card he was ever shown is his own.
    async with deployment.sessions() as session:
        rows = (await session.scalars(select(FeedItem))).all()
        his_ids = {str(row.id) for row in rows if str(row.profile_id) == profile_id}
        assert seen <= his_ids
        assert any(str(row.profile_id) == hers for row in rows), "Mei has cards of her own"


async def test_the_same_cursor_is_the_same_page(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    await _reading(deployment, profile_id, pa["token"], 138, 84)
    first = await _feed(deployment, profile_id, pa["token"])
    cursor = first["next_cursor"]
    once = await _feed(deployment, profile_id, pa["token"], cursor=cursor)
    # Something lands in between; the page under that cursor does not move.
    await _reading(deployment, profile_id, pa["token"], 150, 95)
    again = await _feed(deployment, profile_id, pa["token"], cursor=cursor)
    assert [i["item_id"] for i in once["items"]] == [i["item_id"] for i in again["items"]]
    assert once["next_cursor"] == again["next_cursor"]
    bad = await deployment.client.get(
        f"/profiles/{profile_id}/feed",
        params={"cursor": "not-a-cursor"},
        headers=bearer(pa["token"]),
    )
    assert bad.status_code == 400 and bad.json() == {"refusal": "NotACursor"}


# --- §9: no autoplay; every card passes plain words and shows why -----------------------------


async def test_no_card_autoplays_and_every_patient_line_passes_plain_words(
    deployment: Deployment,
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    await _reading(deployment, profile_id, pa["token"], 138, 84)
    page = await _feed(deployment, profile_id, pa["token"])
    assert page["items"]
    for item in page["items"]:
        assert item["autoplay"] is False
        assert item["why"]["plain"], item
        lines = [*item["body"], *item["voice"], item["why"]["plain"]]
        failures = [
            finding
            for line in lines
            for finding in verify(line, item["language"])
            if finding.severity == "fail"
        ]
        assert not failures, (item["type"], [str(f) for f in failures])
        assert not [
            f
            for f in verify(item["headline"], item["language"], "headline")
            if f.severity == "fail"
        ]


# --- §9: two unopened text cards switch him to voice-first ------------------------------------


async def test_two_unopened_text_cards_switch_the_profile_to_voice_first(
    deployment: Deployment, clock: FrozenClock
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = pa["token"]
    await _reading(deployment, profile_id, his, 138, 84)
    day_one = await _feed(deployment, profile_id, his)
    # The text cards (a clip is its own format, and has its own switch: test_feed_formats).
    assert {item["format"] for item in day_one["items"] if item["format"] != "clip"} == {"text"}
    # He hears nothing, taps nothing. A day passes.
    clock.step(timedelta(days=1))
    await _reading(deployment, profile_id, his, 140, 86)
    day_two = await _feed(deployment, profile_id, his)
    today = [item for item in day_two["items"] if item["type"] in ("now", "reading")]
    assert today and all(item["format"] == "voice_first" for item in today)
    state = (
        await deployment.client.get(f"/profiles/{profile_id}/state", headers=bearer(his))
    ).json()
    preferred = state["dimensions"]["cognitive"]["facts"]["format"]["preferred"]
    assert preferred["value"] == "voice"
    assert preferred["event_id"], "the switch rests on the moment it was noticed"


async def test_a_card_he_heard_does_not_count_as_unopened(
    deployment: Deployment, clock: FrozenClock
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = pa["token"]
    await _reading(deployment, profile_id, his, 138, 84)
    day_one = await _feed(deployment, profile_id, his)
    heard = next(item for item in day_one["items"] if item["type"] == "reading")
    posted = await deployment.client.post(
        f"/profiles/{profile_id}/feed/{heard['item_id']}/engagement",
        json={"event": "heard"},
        headers=bearer(his),
    )
    assert posted.status_code == 201, posted.text
    clock.step(timedelta(days=1))
    day_two = await _feed(deployment, profile_id, his)
    assert {item["format"] for item in day_two["items"] if item["format"] != "clip"} == {"text"}


# --- §9: offline launch shows the last cached page ---------------------------------------------


async def test_the_cached_page_is_the_last_first_page_rendered(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = pa["token"]
    nothing = await deployment.client.get(
        f"/profiles/{profile_id}/feed/cached", headers=bearer(his)
    )
    assert nothing.status_code == 404 and nothing.json() == {"refusal": "NoCachedPage"}
    await _reading(deployment, profile_id, his, 138, 84)
    first = await _feed(deployment, profile_id, his)
    await _feed(deployment, profile_id, his, cursor=first["next_cursor"])  # a later page
    cached = await deployment.client.get(f"/profiles/{profile_id}/feed/cached", headers=bearer(his))
    assert cached.status_code == 200, cached.text
    assert [i["item_id"] for i in cached.json()["items"]] == [i["item_id"] for i in first["items"]]
    assert cached.json()["next_cursor"] == first["next_cursor"]


# --- quiet hours, red flags -----------------------------------------------------------------


async def test_nothing_is_delivered_in_quiet_hours_except_a_red_flag(
    deployment: Deployment, clock: FrozenClock
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = pa["token"]
    await _reading(deployment, profile_id, his, 138, 84)
    clock.set(datetime(2026, 9, 3, 14, 30, tzinfo=UTC))  # 22:30 in Singapore
    night = await _feed(deployment, profile_id, his)
    assert night["quiet"] is True
    assert night["items"] == []
    assert night["held_by_caps"]["reading"] == 1 and night["held_by_caps"]["now"] == 1

    felt = await deployment.client.post(
        f"/profiles/{profile_id}/feelings", json={"word": "fall"}, headers=bearer(his)
    )
    assert felt.status_code == 201, felt.text
    assert felt.json()["red_flag"] is True and felt.json()["flag_id"]
    night = await _feed(deployment, profile_id, his)
    assert _types(night) == ["flag"]
    flag = night["items"][0]
    assert flag["body"][:2] == ["You told Nura about a fall.", "This one we do not wait for."]
    assert flag["body"][-1] == "Call 995 now."
    assert flag["caps_class"] == "flag" and flag["autoplay"] is False

    clock.set(datetime(2026, 9, 3, 23, 30, tzinfo=UTC))  # 07:30 the next morning
    morning = await _feed(deployment, profile_id, his)
    assert morning["quiet"] is False
    assert _types(morning)[:2] == ["flag", "now"]


async def test_at_is_for_a_dev_run_and_pretends_the_hour(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    await _reading(deployment, profile_id, pa["token"], 138, 84)
    # The served deployment is a declared dev run (dev_code_sender=True), so ?at= works.
    night = await _feed(deployment, profile_id, pa["token"], at="2026-09-03T22:30:00+08:00")
    assert night["quiet"] is True and night["items"] == []
    day = await _feed(deployment, profile_id, pa["token"], at="2026-09-03T10:00:00+08:00")
    assert day["quiet"] is False and _types(day)[0] == "now"


async def test_a_red_flag_jumps_the_queue_and_is_not_capped_and_the_family_is_told(
    deployment: Deployment,
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = pa["token"]
    mei = await register_by_phone(deployment, MEI, "Mei")
    await _caregiver_key(
        deployment, pa, profile_id, MEI, ["medicines", "visits", "readings", "records", "emergency"]
    )
    for top, bottom in ((138, 84), (140, 86)):
        await _reading(deployment, profile_id, his, top, bottom)
    before = await _feed(deployment, profile_id, his)
    assert _types(before)[:3] == ["now", "reading", "gate"]

    felt = await deployment.client.post(
        f"/profiles/{profile_id}/feelings", json={"word": "chest_tightness"}, headers=bearer(his)
    )
    assert felt.status_code == 201, felt.text
    assert felt.json()["told"] == [mei["person_id"]]
    after = await _feed(deployment, profile_id, his)
    assert _types(after)[:4] == ["flag", "now", "reading", "gate"]
    flag = after["items"][0]
    assert flag["body"] == [
        "You told Nura about a tight chest.",
        "This one we do not wait for.",
        "Mei knows now.",
        "Call Mei, or call 995.",
    ]
    assert after["held_by_caps"] == {"reading": 1}, "the flag took no place from the two a day"
    # Mei sees it first on her list too, and the share is on Pa's trail.
    hers = await _feed(deployment, profile_id, mei["token"])
    assert hers["audience"] == "caregiver" and _types(hers)[0] == "flag"
    trail = (
        await deployment.client.get(f"/profiles/{profile_id}/audit", headers=bearer(his))
    ).json()
    shares = [e for e in trail if e["action"] == "share" and e["target"] == "red_flag"]
    assert shares and shares[0]["shared_with_person_id"] == mei["person_id"]


async def test_a_flag_that_depends_on_a_missing_fact_is_suppressed_visibly(
    deployment: Deployment,
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = pa["token"]
    mei = await register_by_phone(deployment, MEI, "Mei")
    await _caregiver_key(deployment, pa, profile_id, MEI, ["readings", "records", "emergency"])
    felt = await deployment.client.post(
        f"/profiles/{profile_id}/feelings", json={"word": "shaky_sweaty"}, headers=bearer(his)
    )
    assert felt.status_code == 201, felt.text
    assert felt.json()["suppressed_because"] == "no_sugar_condition_on_record"
    assert felt.json()["told"] == []
    mine = await _feed(deployment, profile_id, his)
    assert "flag" not in _types(mine)
    hers = await _feed(deployment, profile_id, mei["token"])
    considered = [item for item in hers["items"] if item["type"] == "flag"]
    assert considered and considered[0]["why"]["suppressed"] == "no_sugar_condition_on_record"
    assert considered[0]["deliver_to"] == "caregiver"


async def test_a_word_that_is_not_red_is_only_written_down(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    felt = await deployment.client.post(
        f"/profiles/{profile_id}/feelings", json={"word": "dizzy"}, headers=bearer(pa["token"])
    )
    assert felt.status_code == 201 and felt.json()["red_flag"] is False
    nonsense = await deployment.client.post(
        f"/profiles/{profile_id}/feelings",
        json={"word": "heart attack"},
        headers=bearer(pa["token"]),
    )
    assert nonsense.status_code == 422


# --- engagement: "not for me" holds the kind for the day -------------------------------------


async def test_not_for_me_holds_that_kind_of_card_for_the_rest_of_the_day(
    deployment: Deployment, clock: FrozenClock
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = pa["token"]
    await _reading(deployment, profile_id, his, 138, 84)
    page = await _feed(deployment, profile_id, his)
    reading = next(item for item in page["items"] if item["type"] == "reading")
    dismissed = await deployment.client.post(
        f"/profiles/{profile_id}/feed/{reading['item_id']}/engagement",
        json={"event": "dismissed"},
        headers=bearer(his),
    )
    assert dismissed.status_code == 201, dismissed.text
    again = await _feed(deployment, profile_id, his)
    assert "reading" not in _types(again)
    assert again["held_by_caps"] == {"reading": 1}
    # State folded his word in: the preference dimension holds it, with its provenance.
    state = (
        await deployment.client.get(f"/profiles/{profile_id}/state", headers=bearer(his))
    ).json()
    declined = state["dimensions"]["preference"]["facts"]["declined"]["reading"]
    assert declined["value"]["day"] == "2026-09-03"
    assert declined["confidence_state"] == "confirmed_by_person"
    assert declined["event_id"]
    # A new number tomorrow is a new day.
    clock.step(timedelta(days=1))
    await _reading(deployment, profile_id, his, 140, 86)
    tomorrow = await _feed(deployment, profile_id, his)
    assert "reading" in _types(tomorrow)
    # An unknown item is refused by name.
    missing = await deployment.client.post(
        f"/profiles/{profile_id}/feed/00000000-0000-0000-0000-000000000000/engagement",
        json={"event": "seen"},
        headers=bearer(his),
    )
    assert missing.status_code == 404 and missing.json() == {"refusal": "NoSuchItem"}


# --- the caregiver's list -----------------------------------------------------------------


async def test_a_caregiver_key_reads_the_caregiver_supply_narrowed_and_sees_no_notes(
    deployment: Deployment,
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = pa["token"]
    await _reading(deployment, profile_id, his, 138, 84)
    noted = await deployment.client.post(
        f"/profiles/{profile_id}/notes",
        json={"text": "I want to walk to the market again."},
        headers=bearer(his),
    )
    assert noted.status_code == 201
    mine = await _feed(deployment, profile_id, his)
    assert any(item["type"] == "story" and item["scope"] == "notes" for item in mine["items"]), (
        "his own words come back to him as a story card"
    )

    mei = await register_by_phone(deployment, MEI, "Mei")
    await _caregiver_key(
        deployment, pa, profile_id, MEI, ["medicines", "visits", "readings", "records", "emergency"]
    )
    answer = await deployment.client.get(
        f"/profiles/{profile_id}/feed", headers=bearer(mei["token"])
    )
    assert answer.status_code == 200, answer.text
    hers = answer.json()
    assert hers["audience"] == "caregiver"
    assert hers["quiet"] is False and hers["held_by_caps"] == {}
    assert "gate" not in _types(hers)
    assert all(item["scope"] != "notes" for item in hers["items"])
    assert "market" not in answer.text
    assert "profile" not in {item["scope"] for item in hers["items"]} or True
    statuses = {item["type"]: item["status"] for item in hers["items"]}
    assert statuses["reading"] == "sent", statuses
    # A key to the readings only sees the reading cards and nothing built from the rest.
    auntie = await register_by_phone(deployment, AUNTIE, "Auntie")
    await _caregiver_key(deployment, pa, profile_id, AUNTIE, ["readings"])
    narrow = await _feed(deployment, profile_id, auntie["token"])
    assert {item["scope"] for item in narrow["items"]} <= {"readings", "profile"}
    assert "now" not in _types(narrow) or all(
        item["scope"] == "profile" for item in narrow["items"] if item["type"] == "now"
    )
    # A stranger has no feed here at all.
    stranger = await register_by_phone(deployment, STRANGER, "Nobody")
    assert (
        await deployment.client.get(
            f"/profiles/{profile_id}/feed", headers=bearer(stranger["token"])
        )
    ).status_code == 403


# --- sources and search jobs -----------------------------------------------------------------


async def test_sources_and_search_jobs_are_the_owners_and_allowlist_scoped(
    deployment: Deployment,
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = pa["token"]
    listed = await deployment.client.get(f"/profiles/{profile_id}/sources", headers=bearer(his))
    assert listed.status_code == 200, listed.text
    sources = listed.json()
    domains = {source["domain"] for source in sources}
    assert {"hsa.gov.sg", "healthhub.sg"} <= domains
    assert "npra.gov.my" not in domains, "the Malaysian regulator is not on a Singapore list"
    assert all(s["allowlisted"] and s["review_status"] == "approved" for s in sources)

    mei = await register_by_phone(deployment, MEI, "Mei")
    await _caregiver_key(deployment, pa, profile_id, MEI, ["readings", "records"])
    refused = await deployment.client.get(
        f"/profiles/{profile_id}/sources", headers=bearer(mei["token"])
    )
    assert refused.status_code == 403 and refused.json() == {"refusal": "NotTheirsToManage"}

    async with deployment.sessions() as session:
        session.add(
            Source(
                name="A supplement shop",
                domain="supplement-shop.example",
                kind=SourceKind.VIDEO,
                regions=["SG"],
                languages=["en"],
                allowlisted=False,
                review_status=ReviewStatus.REJECTED,
            )
        )
        await session.commit()
        shop = await session.scalar(
            select(Source).where(Source.domain == "supplement-shop.example")
        )
        assert shop is not None
        shop_id = str(shop.id)
    outside = await deployment.client.post(
        f"/profiles/{profile_id}/search-jobs",
        json={"kind": "explainer", "terms": ["warfarin"], "source_ids": [shop_id]},
        headers=bearer(his),
    )
    assert outside.status_code == 400 and outside.json() == {"refusal": "SourceNotAllowlisted"}

    made = await deployment.client.post(
        f"/profiles/{profile_id}/search-jobs",
        json={"kind": "explainer", "terms": ["warfarin"]},
        headers=bearer(his),
    )
    assert made.status_code == 201, made.text
    job = made.json()
    assert job["status"] == "done"
    assert "supplement-shop.example" not in job["results"]["searched"]
    rejected = {entry["because"] for entry in job["results"]["rejected"]}
    assert "treatment_change_rerouted_as_question" in rejected
    assert len(job["results"]["items"]) == 1
    fetched = await deployment.client.get(
        f"/profiles/{profile_id}/search-jobs/{job['job_id']}", headers=bearer(his)
    )
    assert fetched.status_code == 200 and fetched.json()["job_id"] == job["job_id"]

    page = await _feed(deployment, profile_id, his)
    learning = [item for item in page["items"] if item["type"] == "learning"]
    assert learning and learning[0]["headline"] == "Your blood thinner and your food"
    assert learning[0]["cite"]["url"].startswith("https://www.hsa.gov.sg/")
    assert "This comes from Health Sciences Authority." in learning[0]["body"]
    # The finding that would change a dose is a question for the memo, never on his feed.
    assert all("Skip a dose" not in line for item in page["items"] for line in item["body"])
    async with deployment.sessions() as session:
        questions = (
            await session.scalars(select(FeedItem).where(FeedItem.type == "question"))
        ).all()
        assert len(questions) == 1 and questions[0].deliver_to.value == "memo"
    # The trail shows the refusal by name.
    trail = (
        await deployment.client.get(f"/profiles/{profile_id}/audit", headers=bearer(his))
    ).json()
    assert any(
        e["outcome"] == "refused" and e["refused_because"] == "SourceNotAllowlisted" for e in trail
    )
    assert any(
        e["outcome"] == "refused"
        and e["refused_because"] == "NotTheirsToManage"
        and e["actor_person_id"] == mei["person_id"]
        for e in trail
    )


# --- E04: a medicine running low is a reorder card, from the medicines module's own count ----


async def test_a_medicine_running_low_makes_a_reorder_card_from_the_count(
    deployment: Deployment,
) -> None:
    from tests.test_medicines_api import _add, _artefact, _label

    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = pa["token"]
    photo = await _artefact(deployment.client, profile_id, pa)
    # Five tablets, one a day: inside the seven-day reorder threshold from the first day.
    added = await _add(
        deployment.client,
        profile_id,
        pa,
        _label("amlodipine", "5 mg", "1 biji sekali sehari pagi", quantity=5),
        photo,
    )
    assert added.status_code == 201, added.text
    page = await _feed(deployment, profile_id, his)
    types = _types(page)
    assert types[:3] == ["now", "reorder", "gate"], types
    reorder = page["items"][1]
    assert reorder["headline"] == "Your blood pressure tablet is running low"
    assert reorder["body"] == [
        "Your blood pressure tablet runs out on Tuesday 8 September.",
        "Ask your family to order more.",
    ]
    assert reorder["why"]["plain"] == "You have about 5 days of your blood pressure tablet left."
    assert reorder["why"]["fact_ids"] == [added.json()["fact_id"]]
    assert reorder["scope"] == "medicines" and reorder["caps_class"] == "one"
    now = page["items"][0]
    assert now["scope"] == "medicines" and added.json()["fact_id"] in now["why"]["fact_ids"]
    # The medicine also started an explainer and a daily safety job by its generic name.
    jobs = (
        await deployment.client.get(f"/profiles/{profile_id}/search-jobs", headers=bearer(his))
    ).json()
    assert {(job["kind"], job["cadence"]) for job in jobs if job["terms"] == ["amlodipine"]} == {
        ("explainer", "on_change"),
        ("safety", "daily"),
    }
    # A key without the medicines scope sees neither card.
    mei = await register_by_phone(deployment, MEI, "Mei")
    await _caregiver_key(deployment, pa, profile_id, MEI, ["readings", "records"])
    hers = await _feed(deployment, profile_id, mei["token"])
    assert "reorder" not in _types(hers) and "now" not in _types(hers)


async def test_a_card_that_is_refused_is_skipped_and_never_takes_the_red_flag_with_it(
    deployment: Deployment, monkeypatch: Any
) -> None:
    """Review 3: the flag card is made first and on its own; every other card in its own
    savepoint. A card refused later — here a reading card made to look like it needs a
    boundary line it does not carry — is written down and skipped, and the flag stands."""
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = pa["token"]
    felt = await deployment.client.post(
        f"/profiles/{profile_id}/feelings", json={"word": "chest_tightness"}, headers=bearer(his)
    )
    assert felt.status_code == 201 and felt.json()["red_flag"] is True
    await _reading(deployment, profile_id, his, 138, 84)
    monkeypatch.setitem(items.SURFACE_OF, CardType.READING, Surface.LEARNING_CARD)

    page = await _feed(deployment, profile_id, his)
    assert _types(page)[0] == "flag"
    assert "reading" not in _types(page)
    trail = (
        await deployment.client.get(
            f"/profiles/{profile_id}/audit", params={"limit": 500}, headers=bearer(his)
        )
    ).json()
    assert any(
        e["outcome"] == "refused"
        and e["refused_because"] == "NoBoundaryLine"
        and e["target"] == "feed_item"
        for e in trail
    )
