"""The pharmacist's review queue (E22-04): nothing from a new source reaches a patient first.

The acceptance line is "nothing from a new source reaches a patient before review". A source
proposed to the queue is pending and not allowlisted, so no job searches it and no card cites
it until staff approve it. The first fifty renderings of each card type are queued too,
de-identified — lines only, no profile id, no names — and a type whose first fifty are not
all decided shows a flag. The queue is staff's: a patient's key is refused.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.delivery.feed.models import (
    SUPPLY_OF,
    CardType,
    DeliverTo,
    FeedItem,
    ReviewStatus,
    Source,
    SourceKind,
    Supply,
)
from app.delivery.feed.sources import usable
from app.delivery.strings import LINES
from app.language import review
from app.language.models import ReviewItem, ReviewKind, Verdict
from app.language.review import (
    FIRST,
    KEPT_AS_WRITTEN,
    NOT_THE_CATALOGUES,
    REVIEWED_TYPES,
    AlreadyReviewed,
    NotStaff,
    ReasonRequired,
    Staff,
    deidentify,
    sample_card,
    staff_for,
)
from app.language.voice_script import BOUNDARY_PAUSE_MS, script_for
from app.regions import Region
from app.settings import BadStaffTokens, load_settings
from tests.api import bearer, let_in, own_profile, register_by_phone
from tests.conftest import STAFF_TOKEN, Deployment

PA = "+6591230001"
MEI = "+6591230002"
PHARMACIST = Staff("pharmacist")


def staff() -> dict[str, str]:
    return bearer(STAFF_TOKEN)


async def _pa_and_mei(deployment: Deployment) -> tuple[dict[str, str], str]:
    """Pa with a reading and Mei holding a caregiver key: his reading card says her name."""
    pa = await register_by_phone(deployment, PA, "Pa")
    await register_by_phone(deployment, MEI, "Mei")
    profile_id = await own_profile(deployment, pa, language="en")
    scopes = ["medicines", "readings", "family"]
    await let_in(deployment, pa, profile_id, MEI, scopes, "daughter", role="caregiver")
    granted = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": MEI, "role": "caregiver", "scopes": scopes},
        headers=bearer(pa["token"]),
    )
    assert granted.status_code == 201, granted.text
    posted = await deployment.client.post(
        f"/profiles/{profile_id}/readings",
        json={"systolic": 138, "diastolic": 84},
        headers=bearer(pa["token"]),
    )
    assert posted.status_code == 201, posted.text
    return pa, profile_id


async def _feed(deployment: Deployment, profile_id: str, token: str) -> dict[str, Any]:
    answer = await deployment.client.get(f"/profiles/{profile_id}/feed", headers=bearer(token))
    assert answer.status_code == 200, answer.text
    page: dict[str, Any] = answer.json()
    return page


# --- who may ------------------------------------------------------------------------------------


async def test_a_patient_key_is_refused_and_so_is_no_key(deployment: Deployment) -> None:
    pa, _ = await _pa_and_mei(deployment)
    for method, path, body in (
        ("GET", "/review/status", None),
        ("GET", "/review/queue", None),
        ("GET", "/review/proposals", None),
        ("POST", f"/review/items/{uuid.uuid4()}/approve", {}),
        (
            "POST",
            "/review/sources",
            {
                "name": "A heart page",
                "domain": "heart.example.sg",
                "kind": "hospital",
                "regions": ["SG"],
                "languages": ["en"],
            },
        ),
    ):
        for headers in (bearer(pa["token"]), {}, bearer("not-a-staff-token-at-all-000")):
            answer = await deployment.client.request(method, path, json=body, headers=headers)
            assert answer.status_code == 403, (method, path, answer.text)
            assert answer.json() == {"refusal": "NotStaff"}
    # The same routes answer under /api for the web client, and refuse him there too.
    answer = await deployment.client.get("/api/review/queue", headers=bearer(pa["token"]))
    assert answer.status_code == 403


def test_the_staff_check_compares_every_token() -> None:
    listed = (("pharmacist", "a" * 30), ("reviewer", "b" * 30))
    assert staff_for("b" * 30, listed) == Staff("reviewer")
    for wrong in (None, "", "a" * 29, "c" * 30):
        with pytest.raises(NotStaff):
            staff_for(wrong, listed)
    with pytest.raises(NotStaff):
        staff_for("a" * 30, ())


def test_the_staff_list_is_read_strictly() -> None:
    base = {"NURA_REGION": "SG", "NURA_DATABASE_URL": "sqlite+aiosqlite://"}
    read = load_settings({**base, "NURA_REVIEW_STAFF_TOKENS": "pharmacist:" + "t" * 24})
    assert read.review_staff == (("pharmacist", "t" * 24),)
    assert load_settings(base).review_staff == ()
    for bad in (
        "pharmacist",
        "Pharmacist:" + "t" * 24,
        "pharmacist:short",
        "a:" + "t" * 24 + ",a:" + "u" * 24,
    ):
        with pytest.raises(BadStaffTokens):
            load_settings({**base, "NURA_REVIEW_STAFF_TOKENS": bad})
    laptop = "pharmacist:nura-dev-pharmacist-token-0001"
    with pytest.raises(BadStaffTokens):
        load_settings({**base, "NURA_REVIEW_STAFF_TOKENS": laptop})
    dev = load_settings({**base, "NURA_DEV_CODE_SENDER": "1", "NURA_REVIEW_STAFF_TOKENS": laptop})
    assert dev.review_staff == (("pharmacist", "nura-dev-pharmacist-token-0001"),)


# --- the samples carry no profile and no name ---------------------------------------------------


def test_the_queue_table_names_no_profile_and_no_person() -> None:
    columns = {column.name for column in ReviewItem.__table__.columns}
    assert not {c for c in columns if "profile" in c or "person" in c}


async def test_staff_read_the_first_cards_with_nobody_in_them(deployment: Deployment) -> None:
    pa, profile_id = await _pa_and_mei(deployment)
    page = await _feed(deployment, profile_id, pa["token"])
    reading = next(item for item in page["items"] if item["type"] == "reading")
    assert "Mei can see it too." in reading["body"], reading["body"]

    answer = await deployment.client.get("/review/queue", params={"kind": "card"}, headers=staff())
    assert answer.status_code == 200, answer.text
    queued = answer.json()
    assert queued, "the first cards of each type are queued"
    sample = next(item for item in queued if item["card_type"] == "reading")
    assert sample["lines"]["body"][:3] == [
        "Your blood pressure today was 138 over 84.",
        "It is in your blood pressure book.",
        "{name} can see it too.",
    ]
    assert "backend/app/delivery/strings:LINES.reading_family.0:en" in sample["catalogue_ids"]
    assert sample["sample_number"] == 1 and sample["verdict"] == "pending"

    # Nothing in any stored item names him, her, or the profile — on the wire or in the row.
    async with deployment.sessions() as session:
        rows = (await session.scalars(select(ReviewItem))).all()
    stored = json.dumps([row.lines for row in rows] + queued, ensure_ascii=False)
    assert profile_id not in stored
    assert pa["person_id"] not in stored if "person_id" in pa else True
    for name in ("Pa", "Mei", PA, MEI):
        assert not re.search(rf"(?<![\w]){re.escape(name)}(?![\w])", stored), name


def test_a_doctor_and_a_family_member_become_slots_and_his_own_words_are_left_out() -> None:
    visit = deidentify(
        CardType.VISIT,
        "en",
        headline="Dr Tan on Monday 21 September",
        body=(
            "You see Dr Tan on Monday 21 September.",
            "Bring your blood pressure book and your tablets.",
        ),
        voice=("You see Dr Tan on Monday 21 September.",),
        why="Your visit to Dr Tan is on Monday 21 September.",
    )
    assert visit.lines["headline"] == "{doctor} on Monday 21 September"
    assert visit.lines["body"][0] == "You see {doctor} on Monday 21 September."
    assert visit.lines["why"] == "Your visit to {doctor} is on Monday 21 September."

    note = deidentify(
        CardType.STORY,
        "en",
        headline="Your own words",
        body=("On Monday 14 September you wrote this down:", "Mei and I walked to the market."),
        voice=("On Monday 14 September you wrote this down:", "Mei and I walked to the market."),
        why="These are your own words, from your private notes.",
    )
    assert note.lines["body"] == ["On Monday 14 September you wrote this down:", NOT_THE_CATALOGUES]
    assert "Mei" not in json.dumps(note.lines)

    flag = deidentify(
        CardType.FLAG,
        "zh",
        headline="这个我们不等",
        body=(
            "您告诉Nura您跌倒了。",
            "这个我们不等。",
            "美和凯已经知道了。",
            "请打给美，或者打995。",
        ),
        voice=("您告诉Nura您跌倒了。",),
        why="这是我们从不等的事情之一。",
    )
    said = json.dumps(flag.lines, ensure_ascii=False)
    assert "美" not in said and "凯" not in said
    assert "{name}已经知道了。" in flag.lines["body"]


def test_a_learning_card_keeps_its_compressed_lines_but_never_a_name() -> None:
    learning = deidentify(
        CardType.LEARNING,
        "en",
        headline="Your blood pressure in simple words",
        body=(
            "Blood pressure is how hard your blood pushes.",
            "Ask Dr Tan what your number should be.",
            "This comes from HealthHub.",
        ),
        voice=("Blood pressure is how hard your blood pushes.",),
        why="This is about your blood pressure, which is on your papers.",
    )
    assert learning.lines["body"][0] == "Blood pressure is how hard your blood pushes."
    assert learning.lines["body"][1] == "Ask {doctor} what your number should be."


# --- the first fifty of each type ------------------------------------------------------------------


def _reading_card(n: int, deliver_to: DeliverTo = DeliverTo.PATIENT) -> FeedItem:
    lines = [
        f"Your blood pressure today was {100 + n} over 80.",
        "It is in your blood pressure book.",
    ]
    return FeedItem(
        type=CardType.READING,
        deliver_to=deliver_to,
        language="en",
        headline="Your blood pressure today",
        body=lines,
        voice=lines,
        why={"plain": "You took your blood pressure today."},
    )


async def test_fifty_of_a_type_are_queued_and_then_no_more(sg: AsyncSession) -> None:
    for n in range(FIRST + 5):
        await sample_card(sg, _reading_card(n))
    rows = (await sg.scalars(select(ReviewItem).where(ReviewItem.card_type == "reading"))).all()
    assert len(rows) == FIRST
    assert sorted(row.sample_number or 0 for row in rows) == list(range(1, FIRST + 1))


async def test_the_same_rendering_is_queued_once_and_a_caregivers_card_not_at_all(
    sg: AsyncSession,
) -> None:
    assert await sample_card(sg, _reading_card(1)) is not None
    assert await sample_card(sg, _reading_card(1)) is None
    assert await sample_card(sg, _reading_card(2, DeliverTo.CAREGIVER)) is None


def test_every_card_type_he_is_shown_is_reviewed() -> None:
    """The queue's list is not self-certifying: it is checked against the supply itself.

    A card type the patient reads goes in front of the pharmacist's first fifty. Two types do
    not: the doctor questions held for the memo (`Supply.HELD`), which never reach him, and
    the caregiver's duty card, which is hers. Every other type in `SUPPLY_OF` is his, so a
    type added later without a line in `REVIEWED_TYPES` fails here rather than quietly
    skipping the only human read of its words (F1: clip, recap, local, seasonal, food).
    """
    his = {
        card_type
        for card_type, supply in SUPPLY_OF.items()
        if supply is not Supply.HELD and card_type is not CardType.DUTY
    }
    assert his - set(REVIEWED_TYPES) == set(), "a card type he is shown that no pharmacist reads"
    assert set(REVIEWED_TYPES) - his == set(), "a reviewed type the patient is never shown"


def test_the_pages_he_is_shown_keep_their_compressed_words() -> None:
    """A card whose lines come from an outside page is kept as written, so the pharmacist
    reads the words themselves; a card made of his own record is not kept at all."""
    assert KEPT_AS_WRITTEN <= set(REVIEWED_TYPES)
    for card_type in (CardType.CLIP, CardType.LOCAL, CardType.SEASONAL, CardType.FOOD):
        assert card_type in KEPT_AS_WRITTEN, f"{card_type} is compressed from a page"
    for card_type in (CardType.MEMO, CardType.READING, CardType.RECAP):
        assert card_type not in KEPT_AS_WRITTEN, f"{card_type} is his record's own words"


async def test_a_type_shows_a_flag_until_its_first_fifty_are_decided(sg: AsyncSession) -> None:
    status = {t.card_type: t for t in (await review.status(sg)).card_types}
    assert set(status) == {t.value for t in REVIEWED_TYPES}
    assert all(t.flag for t in status.values()), "nothing reviewed yet: every type is flagged"

    for n in range(FIRST):
        await sample_card(sg, _reading_card(n))
    reading = {t.card_type: t for t in (await review.status(sg)).card_types}["reading"]
    assert (reading.sampled, reading.pending, reading.flag) == (FIRST, FIRST, True)

    for item in await review.queue(sg, card_type=CardType.READING):
        await review.decide(sg, staff=PHARMACIST, item_id=item.id, verdict=Verdict.APPROVED)
    reading = {t.card_type: t for t in (await review.status(sg)).card_types}["reading"]
    assert (reading.reviewed, reading.first_fifty_reviewed, reading.flag) == (FIRST, True, False)
    others = {t.card_type: t for t in (await review.status(sg)).card_types}
    assert others["visit"].flag, "a type with none reviewed is still flagged"


async def test_status_over_http(deployment: Deployment) -> None:
    answer = await deployment.client.get("/review/status", headers=staff())
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["first"] == FIRST
    assert {t["card_type"] for t in body["card_types"]} == {t.value for t in REVIEWED_TYPES}
    assert all(t["flag"] for t in body["card_types"])


# --- a new source is unused until it is approved -------------------------------------------------


async def test_nothing_from_a_new_source_reaches_him_before_review(deployment: Deployment) -> None:
    pa, profile_id = await _pa_and_mei(deployment)
    proposed = await deployment.client.post(
        "/review/sources",
        json={
            "name": "A heart hospital",
            "domain": "heart.example.sg",
            "kind": "hospital",
            "regions": ["SG"],
            "languages": ["en"],
        },
        headers=staff(),
    )
    assert proposed.status_code == 201, proposed.text
    item = proposed.json()
    assert (item["kind"], item["verdict"]) == ("source", "pending")
    source_id = item["source_id"]

    # Pending: no job may search it, so no card can come from it.
    job = {
        "kind": "explainer",
        "terms": ["blood pressure"],
        "source_ids": [source_id],
        "cadence": "once",
        "reason": "a new page about his heart",
    }
    refused = await deployment.client.post(
        f"/profiles/{profile_id}/search-jobs", json=job, headers=bearer(pa["token"])
    )
    assert refused.status_code == 400, refused.text
    assert refused.json()["refusal"] == "SourceNotAllowlisted"
    page = await _feed(deployment, profile_id, pa["token"])
    assert source_id not in {i["source_id"] for i in page["items"]}

    approved = await deployment.client.post(
        f"/review/items/{item['item_id']}/approve", json={}, headers=staff()
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["decided_by"] == "pharmacist"
    accepted = await deployment.client.post(
        f"/profiles/{profile_id}/search-jobs", json=job, headers=bearer(pa["token"])
    )
    assert accepted.status_code == 201, accepted.text

    again = await deployment.client.post(
        f"/review/items/{item['item_id']}/reject",
        json={"reason": "second thoughts"},
        headers=staff(),
    )
    assert again.status_code == 409 and again.json() == {"refusal": "AlreadyReviewed"}


async def test_a_rejected_source_stays_off_and_a_rejection_says_why(sg: AsyncSession) -> None:
    item = await review.propose_source(
        sg,
        staff=PHARMACIST,
        name="A shop that sells pills",
        domain="pills.example.my",
        kind=SourceKind.HOSPITAL,
        regions=["MY"],
        languages=["ms"],
    )
    source = await sg.get(Source, item.source_id)
    assert source is not None and not usable(source, Region.MY)
    with pytest.raises(ReasonRequired):
        await review.decide(sg, staff=PHARMACIST, item_id=item.id, verdict=Verdict.REJECTED)
    await review.decide(
        sg, staff=PHARMACIST, item_id=item.id, verdict=Verdict.REJECTED, reason="It sells pills."
    )
    assert source.review_status is ReviewStatus.REJECTED and not source.allowlisted
    assert not usable(source, Region.MY)
    with pytest.raises(AlreadyReviewed):
        await review.decide(sg, staff=PHARMACIST, item_id=item.id, verdict=Verdict.APPROVED)


async def test_a_pending_source_put_in_the_table_another_way_is_queued(sg: AsyncSession) -> None:
    sg.add(
        Source(
            name="A society",
            domain="society.example.sg",
            kind=SourceKind.SOCIETY,
            regions=["SG"],
            languages=["en"],
            allowlisted=False,
            review_status=ReviewStatus.PENDING,
        )
    )
    await sg.flush()
    queued = await review.queue(sg, kind=ReviewKind.SOURCE)
    assert [item.lines["domain"] for item in queued] == ["society.example.sg"]


# --- a rewrite is a proposal, never production text ---------------------------------------------


async def test_a_rewrite_proposes_a_catalogue_change_and_changes_nothing_he_sees(
    deployment: Deployment,
) -> None:
    pa, profile_id = await _pa_and_mei(deployment)
    await _feed(deployment, profile_id, pa["token"])
    queued = (
        await deployment.client.get(
            "/review/queue", params={"card_type": "reading"}, headers=staff()
        )
    ).json()
    sample = queued[0]
    body = list(sample["lines"]["body"])
    body[1] = "Nura keeps it in your blood pressure book."

    bad = await deployment.client.post(
        f"/review/items/{sample['item_id']}/rewrite",
        json={"lines": {"body": [body[0], "One reading was missed.", *body[2:]]}},
        headers=staff(),
    )
    assert bad.status_code == 400, bad.text
    assert bad.json()["refusal"] == "RewriteNotPlainWords" and bad.json()["findings"]

    rewritten = await deployment.client.post(
        f"/review/items/{sample['item_id']}/rewrite",
        json={"lines": {"body": body}, "reason": "Say who keeps it."},
        headers=staff(),
    )
    assert rewritten.status_code == 200, rewritten.text
    assert rewritten.json()["verdict"] == "rewritten"
    proposals = (await deployment.client.get("/review/proposals", headers=staff())).json()
    assert proposals == [
        {
            "item_id": sample["item_id"],
            "card_type": "reading",
            "language": "en",
            "changes": [
                {
                    "field": "body",
                    "index": 1,
                    "from": "It is in your blood pressure book.",
                    "to": "Nura keeps it in your blood pressure book.",
                    "catalogue_id": "backend/app/delivery/strings:LINES.reading.1:en",
                }
            ],
            "reason": "Say who keeps it.",
            "decided_by": "pharmacist",
            "decided_at": proposals[0]["decided_at"],
        }
    ]
    # Production text is untouched: the catalogue, and the card he is shown.
    assert LINES["en"]["reading"][1] == "It is in your blood pressure book."
    page = await _feed(deployment, profile_id, pa["token"])
    reading = next(item for item in page["items"] if item["type"] == "reading")
    assert "It is in your blood pressure book." in reading["body"]


# --- every card carries its voice script ---------------------------------------------------------


async def test_every_card_on_the_feed_carries_its_voice_script(deployment: Deployment) -> None:
    pa, profile_id = await _pa_and_mei(deployment)
    page = await _feed(deployment, profile_id, pa["token"])
    assert page["items"]
    for item in page["items"]:
        expected = script_for(item["voice"], item["language"], boundary=item["boundary"]).as_json()
        assert item["voice_script"] == expected, item["type"]
    reading = next(item for item in page["items"] if item["type"] == "reading")
    assert reading["voice_script"]["segments"][0]["text"] == (
        "Your blood pressure today was one hundred and thirty-eight over eighty-four."
    )
    learning = [item for item in page["items"] if item["type"] == "learning"]
    assert learning
    pauses = [s["pause_ms"] for s in learning[0]["voice_script"]["segments"]]
    closing = len(learning[0]["boundary"].splitlines())
    assert pauses[-closing - 1] == BOUNDARY_PAUSE_MS


# --- the clinical-safety review's cases -----------------------------------------------------------


def test_a_name_with_a_particle_is_still_a_name() -> None:
    for name in ("Ahmad bin Ali", "Siti binti Hassan", "Siva a/l Kumar"):
        sample = deidentify(
            CardType.READING,
            "en",
            headline="Your blood pressure today",
            body=("Your blood pressure today was 138 over 84.", f"{name} can see it too."),
            voice=(),
            why="You took your blood pressure today.",
        )
        assert sample.lines["body"][1] == "{name} can see it too.", name


def test_on_a_notice_a_line_that_is_plainly_a_template_loses_its_person_whatever_filled_it() -> (
    None
):
    """On a card kept as written, a catalogue line never keeps what filled a person's slot, even
    when it does not look like a name; a compressed sentence that only brushes a thin template
    ("{name} is {value}.") is kept."""
    notice = deidentify(
        CardType.NOTICE,
        "en",
        headline="A safety notice",
        body=(
            "My neighbour can see it too.",
            "Ahmad bin Ali can see it too.",
            "Blood pressure is how hard your blood pushes.",
        ),
        voice=(),
        why="",
    )
    assert notice.lines["body"] == [
        "{name} can see it too.",
        "{name} can see it too.",
        "Blood pressure is how hard your blood pushes.",
    ]


async def test_a_sample_that_fails_never_costs_him_the_card(
    deployment: Deployment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sampling runs where every card is written, a red flag's included; whatever goes wrong in
    it is rolled back and logged, and the card is made."""

    async def broken(session: AsyncSession, item: FeedItem) -> None:
        raise RuntimeError("the catalogue scan could not read a file")

    monkeypatch.setattr(review, "sample_card", broken)
    pa, profile_id = await _pa_and_mei(deployment)
    page = await _feed(deployment, profile_id, pa["token"])
    assert "reading" in {item["type"] for item in page["items"]}
    async with deployment.sessions() as session:
        assert (await session.scalars(select(ReviewItem))).all() == []
